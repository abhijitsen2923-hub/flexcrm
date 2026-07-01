from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Body, Depends, File, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import pagination_params, require_permissions
from app.core.exceptions import ValidationError
from app.core.permissions import PermissionCode
from app.database.enums import LeadIndustry
from app.database.session import get_db_session
from app.schemas.common import MessageResponse, PaginatedResponse, PaginationParams, build_page_meta
from app.schemas.lead import LeadCreate, LeadDuplicate, LeadFilterParams, LeadRead, LeadUpdate
from app.schemas.lead_document import LeadDocumentRead, LeadDocumentUpload
from app.schemas.stage_transition import StageTransitionCreate, StageTransitionRead
from app.services.lead_documents import LeadDocumentService, get_lead_or_404
from app.services.lead_import import LeadImportService
from app.services.leads import LeadService
from app.services.stage_transitions import StageTransitionService


router = APIRouter()


@router.get("", response_model=PaginatedResponse[LeadRead])
async def list_leads(
    filters: LeadFilterParams = Depends(),
    pagination: PaginationParams = Depends(pagination_params),
    _: object = Depends(require_permissions(PermissionCode.LEAD_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    items, total = await LeadService(session).list_leads(pagination, filters)
    return PaginatedResponse[LeadRead](items=items, pagination=build_page_meta(total, pagination))


@router.get("/duplicates", response_model=list[LeadDuplicate])
async def check_duplicate_leads(
    email: str | None = None,
    phone: str | None = None,
    _: object = Depends(require_permissions(PermissionCode.LEAD_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    """Warn-but-allow duplicate check for the New Lead form. Returns active
    leads in the caller's tenant matching the email (case-insensitive) or phone
    (digits-only). Empty list when nothing matches or both inputs are blank."""
    return await LeadService(session).find_duplicate_leads(email, phone)


@router.post("", response_model=LeadRead, status_code=status.HTTP_201_CREATED)
async def create_lead(
    payload: LeadCreate,
    background_tasks: BackgroundTasks,
    current_user=Depends(require_permissions(PermissionCode.LEAD_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    # Inherit the user's business_type so the New Lead form doesn't need to
    # ask which vertical (chosen once at registration).
    return await LeadService(session).create_lead(
        payload,
        actor_id=current_user.id,
        actor_business_type=current_user.business_type,
        background_tasks=background_tasks,
    )


@router.put("/{lead_id}", response_model=LeadRead)
async def update_lead(
    lead_id: UUID,
    background_tasks: BackgroundTasks,
    raw_body: dict = Body(...),
    current_user=Depends(require_permissions(PermissionCode.LEAD_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    # Per spec §3.2, stage moves require a comment trail; they cannot ride along
    # a regular PUT. Reject early with a clear hint pointing at the transitions
    # endpoint.
    if "stage_code" in raw_body:
        raise ValidationError(
            "stage_code cannot be updated via PUT. "
            "Use POST /leads/{id}/transitions with a mandatory comment."
        )
    payload = LeadUpdate(**raw_body)
    return await LeadService(session).update_lead(
        lead_id, payload, actor_id=current_user.id, background_tasks=background_tasks
    )


@router.delete("/{lead_id}", response_model=MessageResponse)
async def delete_lead(
    lead_id: UUID,
    current_user=Depends(require_permissions(PermissionCode.LEAD_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    await LeadService(session).delete_lead(lead_id, actor_id=current_user.id)
    return MessageResponse(message="Lead deleted successfully.")


# --- Stage transitions (spec §3.2) ----------------------------------------

@router.get("/{lead_id}/transitions", response_model=list[StageTransitionRead])
async def list_transitions(
    lead_id: UUID,
    _: object = Depends(require_permissions(PermissionCode.LEAD_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    return await StageTransitionService(session).list_transitions(lead_id)


@router.post(
    "/{lead_id}/transitions",
    response_model=StageTransitionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_transition(
    lead_id: UUID,
    payload: StageTransitionCreate,
    current_user=Depends(require_permissions(PermissionCode.LEAD_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    return await StageTransitionService(session).create_transition(
        lead_id, payload, actor_id=current_user.id, actor_role=current_user.role
    )


# --- CSV bulk import -------------------------------------------------------

# Vertical-aware starter CSVs. Friendly headers (Title, Email, Phone, ...) so
# users opening this in Excel don't have to translate snake_case columns. The
# alias map in `app.services.lead_import.HEADER_ALIASES` resolves these to the
# canonical names on re-upload. Em-dashes replaced with hyphens for cross-
# spreadsheet-app portability (Excel/Google Sheets sometimes default-decode
# UTF-8 as Windows-1252).
_IMPORT_TEMPLATE_EDUCATION = (
    "Title,contact_name,Email,Phone,Company / Organization,Course,Source,Value,Currency,Probability (%),Expected close\n"
    "MBA Marketing applicant,Rohan Sharma,rohan.sharma@gmail.com,+91 98300 12345,Tata Consultancy Services,MBA - Marketing,Instagram,150000,INR,60,30-06-2026\n"
    "Data Science enquiry,Priya Nair,priya.nair@outlook.com,+91 99876 54321,,PG Diploma - Data Science,Referral,95000,INR,45,15-07-2026\n"
    "Digital Marketing course interest,Aman Verma,aman.verma@yahoo.com,+91 90123 45678,Wipro Ltd,Certificate - Digital Marketing,Walk-in,40000,INR,75,05-06-2026\n"
    "MBA Finance applicant,Sneha Iyer,sneha.iyer@gmail.com,+91 98765 43210,,MBA - Finance,Website,180000,INR,55,20-08-2026\n"
    "UX Design bootcamp lead,David Thompson,david.t@protonmail.com,+1 415 555 0192,Freelance,Bootcamp - UX Design,Google Ads,3500,USD,40,12-07-2026\n"
    "B.Com admission query,Kavya Reddy,kavya.reddy@gmail.com,+91 96543 21098,,B.Com - General,Education Fair,75000,INR,65,01-07-2026\n"
    "Cloud Computing certification,Arjun Mehta,arjun.mehta@hotmail.com,+91 97654 32109,Infosys,Certificate - AWS Cloud,LinkedIn,55000,INR,50,18-06-2026\n"
    "Executive MBA enquiry,Fatima Khan,fatima.khan@gmail.com,+91 93456 78901,HDFC Bank,Executive MBA - Leadership,Referral,250000,INR,70,10-09-2026\n"
    "Graphic Design course lead,Vikram Singh,vikram.singh@gmail.com,+91 91234 56780,,Diploma - Graphic Design,Instagram,48000,INR,35,25-07-2026\n"
    "Full Stack Developer program,Emily Carter,emily.carter@gmail.com,+1 646 555 0148,Self-employed,Bootcamp - Full Stack Web,Walk-in,4200,USD,80,08-06-2026\n"
)

_IMPORT_TEMPLATE_TRAVEL = (
    "Title,contact_name,Email,Phone,Company / Organization,Destination,Source,Value,Currency,Probability (%),Expected close\n"
    "Bali honeymoon package,Rohit & Anjali Sharma,rohit.sharma@gmail.com,+91 98300 12345,,Bali - 7 days,Instagram,180000,INR,65,30-06-2026\n"
    "Maldives family vacation,Priya Nair,priya.nair@outlook.com,+91 99876 54321,Tata Steel,Maldives - 5 days,Referral,250000,INR,55,20-07-2026\n"
    "Europe 14-day tour,Aman Verma,aman.verma@yahoo.com,+91 90123 45678,Wipro,Europe Multi-city - 14 days,Walk-in,450000,INR,40,15-09-2026\n"
    "Dubai weekend break,Sneha Iyer,sneha.iyer@gmail.com,+91 98765 43210,,Dubai - 3 days,Website,95000,INR,70,12-06-2026\n"
    "Swiss Alps adventure,David Thompson,david.t@protonmail.com,+1 415 555 0192,Self-employed,Switzerland - 8 days,Google Ads,4200,USD,50,25-07-2026\n"
    "Thailand group tour,Kavya Reddy,kavya.reddy@gmail.com,+91 96543 21098,,Thailand - 6 days,Travel Expo,85000,INR,75,05-07-2026\n"
    "Singapore family trip,Arjun Mehta,arjun.mehta@hotmail.com,+91 97654 32109,Infosys,Singapore - 4 days,LinkedIn,120000,INR,60,18-08-2026\n"
    "Paris romantic getaway,Fatima Khan,fatima.khan@gmail.com,+91 93456 78901,HDFC Bank,Paris - 6 days,Referral,2800,EUR,55,10-10-2026\n"
    "Goa beach holiday,Vikram Singh,vikram.singh@gmail.com,+91 91234 56780,,Goa - 4 days,Instagram,35000,INR,80,22-06-2026\n"
    "Bangkok business + leisure,Emily Carter,emily.carter@gmail.com,+1 646 555 0148,Globex Ltd,Bangkok - 5 days,Walk-in,1900,USD,45,08-08-2026\n"
)


def _template_for(business_type: LeadIndustry | None) -> tuple[str, str]:
    """Return (csv_body, filename) for the caller's vertical.

    Falls back to the Education template if the user has no business_type set
    (legacy accounts) — Education is the more familiar of the two samples.
    """
    if business_type == LeadIndustry.travel:
        return _IMPORT_TEMPLATE_TRAVEL, "leads-import-template-travel.csv"
    return _IMPORT_TEMPLATE_EDUCATION, "leads-import-template-education.csv"


@router.get("/import/template.csv")
async def download_import_template(
    current_user=Depends(require_permissions(PermissionCode.LEAD_IMPORT)),
):
    """Vertical-aware starter CSV — same shape the `POST /import` endpoint accepts."""
    body, filename = _template_for(current_user.business_type)
    return StreamingResponse(
        iter([body]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/import")
async def import_leads_csv(
    file: UploadFile = File(..., description="CSV file. UTF-8, header row required."),
    current_user=Depends(require_permissions(PermissionCode.LEAD_IMPORT)),
    session: AsyncSession = Depends(get_db_session),
):
    """Bulk-create leads from a CSV file.

    Scope is the caller's org (tenancy filter applies). Each row produces
    one Lead; if the row's `stage` column is set, the lead is transitioned
    to that stage via the regular service so the Sold auto-promotion fires
    where applicable. Per-row errors are returned in the response — they
    don't abort the rest of the upload.
    """
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise ValidationError("Upload must be a .csv file.")
    content = await file.read()
    if not content:
        raise ValidationError("CSV file is empty.")

    summary = await LeadImportService(session).import_csv(
        content,
        actor_id=current_user.id,
        actor_role=current_user.role,
        actor_business_type=current_user.business_type,
    )
    return {
        "created": summary.created,
        "promoted": summary.promoted,
        "errors": [{"row": e.row, "error": e.error} for e in summary.errors],
    }


# --- Travel visa documents (Phase 2) ---------------------------------------

@router.get("/{lead_id}/documents", response_model=list[LeadDocumentRead])
async def list_lead_documents(
    lead_id: UUID,
    _: object = Depends(require_permissions(PermissionCode.LEAD_DOCS_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    lead = await get_lead_or_404(session, lead_id)
    service = LeadDocumentService(session)
    return await service.ensure_checklist(lead)


@router.post("/{lead_id}/documents/upload", response_model=LeadDocumentRead)
async def upload_lead_document(
    lead_id: UUID,
    payload: LeadDocumentUpload,
    current_user=Depends(require_permissions(PermissionCode.LEAD_DOCS_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    lead = await get_lead_or_404(session, lead_id)
    service = LeadDocumentService(session)
    await service.ensure_checklist(lead)
    return await service.mark_uploaded(lead, payload.doc_type, uploaded_path=payload.uploaded_path)
