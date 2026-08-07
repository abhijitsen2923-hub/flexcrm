from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Body, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import pagination_params, require_permissions
from app.core.exceptions import ValidationError
from app.core.lead_csv import build_template_csv
from app.core.permissions import ASSIGNED_ONLY_LEAD_ROLES, PermissionCode
from app.database.session import get_db_session
from app.schemas.common import MessageResponse, PaginatedResponse, PaginationParams, build_page_meta
from app.schemas.lead import (
    LeadBulkActionResult,
    LeadBulkReassign,
    LeadBulkTransition,
    LeadCallLogCreate,
    LeadCallLogRead,
    LeadCreate,
    LeadDuplicate,
    LeadFilterParams,
    LeadRead,
    LeadUpdate,
)
from app.schemas.channel_partner import BrokeragePayoutRead
from app.schemas.lead_document import LeadDocumentRead, LeadDocumentUpload
from app.schemas.stage_transition import StageTransitionCreate, StageTransitionRead
from app.services.channel_partners import ChannelPartnerService
from app.services.lead_documents import LeadDocumentService, get_lead_or_404
from app.services.lead_import import LeadImportService
from app.services.leads import LeadService
from app.services.stage_transitions import StageTransitionService


router = APIRouter()


async def _enforce_lead_access(session: AsyncSession, lead_id: UUID, user) -> None:
    """Assigned-only roles (front-line reps) may only touch leads assigned to
    them — reaching another rep's lead by id returns 404 (not 403, so the id's
    existence isn't leaked). Higher roles pass through."""
    if user.role in ASSIGNED_ONLY_LEAD_ROLES:
        lead = await get_lead_or_404(session, lead_id)
        if lead.assigned_to_id != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")


@router.get("/{lead_id}/brokerage", response_model=list[BrokeragePayoutRead])
async def list_lead_brokerage(
    lead_id: UUID,
    current_user=Depends(require_permissions(PermissionCode.FINANCE_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    """Brokerage payout(s) accrued for this lead's referring partner (Phase C4).
    Financial data — gated by FINANCE_VIEW; the partner's NAME is already on
    LeadRead for any lead viewer."""
    await _enforce_lead_access(session, lead_id, current_user)
    return await ChannelPartnerService(session).payouts_for_lead(lead_id)


@router.get("", response_model=PaginatedResponse[LeadRead])
async def list_leads(
    filters: LeadFilterParams = Depends(),
    pagination: PaginationParams = Depends(pagination_params),
    current_user=Depends(require_permissions(PermissionCode.LEAD_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    # Front-line reps only ever see their own assigned leads — force the filter
    # regardless of any client-supplied assigned_to_id (anti-poaching, BR-2).
    if current_user.role in ASSIGNED_ONLY_LEAD_ROLES:
        filters.assigned_to_id = current_user.id
    items, total = await LeadService(session).list_leads(pagination, filters)
    return PaginatedResponse[LeadRead](items=items, pagination=build_page_meta(total, pagination))


@router.get("/duplicates", response_model=list[LeadDuplicate])
async def check_duplicate_leads(
    email: str | None = None,
    phone: str | None = None,
    current_user=Depends(require_permissions(PermissionCode.LEAD_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    """Warn-but-allow duplicate check for the New Lead form. Returns active
    leads in the caller's tenant matching the email (case-insensitive) or phone
    (digits-only). Empty list when nothing matches or both inputs are blank.
    Front-line reps only match against their OWN leads (same anti-poaching scope
    as the list)."""
    owner_id = current_user.id if current_user.role in ASSIGNED_ONLY_LEAD_ROLES else None
    return await LeadService(session).find_duplicate_leads(email, phone, owner_id=owner_id)


@router.get("/campaigns", response_model=list[str])
async def list_lead_campaigns(
    current_user=Depends(require_permissions(PermissionCode.LEAD_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    """Distinct campaign values in use across the tenant's leads — populates the
    list's Campaign filter so custom/imported campaigns (not just the predefined
    ones) are selectable. Declared before any `/{lead_id}` route so the literal
    path wins; tenant-scoped by the session's schema routing. Front-line reps are
    scoped to their own leads (same anti-poaching rule as the list/duplicates)."""
    owner_id = current_user.id if current_user.role in ASSIGNED_ONLY_LEAD_ROLES else None
    return await LeadService(session).list_campaigns(owner_id=owner_id)


@router.post("", response_model=LeadRead, status_code=status.HTTP_201_CREATED)
async def create_lead(
    payload: LeadCreate,
    background_tasks: BackgroundTasks,
    current_user=Depends(require_permissions(PermissionCode.LEAD_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    # A front-line rep's new lead is theirs by default — otherwise the scoped
    # list would immediately hide it from them.
    if current_user.role in ASSIGNED_ONLY_LEAD_ROLES and payload.assigned_to_id is None:
        payload.assigned_to_id = current_user.id
    # Inherit the user's business_type so the New Lead form doesn't need to
    # ask which vertical (chosen once at registration).
    return await LeadService(session).create_lead(
        payload,
        actor_id=current_user.id,
        actor_business_type=current_user.business_type,
        background_tasks=background_tasks,
    )


@router.post("/bulk-reassign", response_model=MessageResponse)
async def bulk_reassign_leads(
    payload: LeadBulkReassign,
    # Manager-only: needs both lead management AND user visibility (to pick owners).
    current_user=Depends(require_permissions(PermissionCode.LEAD_MANAGE, PermissionCode.USER_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    count = await LeadService(session).bulk_reassign(
        payload.lead_ids, payload.assigned_to_id, actor_id=current_user.id
    )
    return MessageResponse(message=f"Reassigned {count} lead(s).")


@router.post("/bulk-transition", response_model=LeadBulkActionResult)
async def bulk_transition_leads(
    payload: LeadBulkTransition,
    current_user=Depends(require_permissions(PermissionCode.LEAD_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    """Move many selected leads to one stage in a single action. Each lead goes
    through the normal transition (mandatory comment, role/backward gates, side
    effects); rejected leads are reported, not fatal. Front-line reps are scoped
    to their own leads, same as the single-transition endpoint."""
    enforce = current_user.id if current_user.role in ASSIGNED_ONLY_LEAD_ROLES else None
    result = await StageTransitionService(session).bulk_transition(
        payload.lead_ids,
        payload.to_stage_code,
        payload.comment,
        actor_id=current_user.id,
        actor_role=current_user.role,
        next_action_date=payload.next_action_date,
        enforce_owner_id=enforce,
    )
    return LeadBulkActionResult(**result)


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
    await _enforce_lead_access(session, lead_id, current_user)
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
    await _enforce_lead_access(session, lead_id, current_user)
    await LeadService(session).delete_lead(lead_id, actor_id=current_user.id)
    return MessageResponse(message="Lead deleted successfully.")


# --- Call tracking (per lead + user) --------------------------------------

@router.get("/{lead_id}/calls", response_model=list[LeadCallLogRead])
async def list_lead_calls(
    lead_id: UUID,
    current_user=Depends(require_permissions(PermissionCode.LEAD_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    await get_lead_or_404(session, lead_id)
    await _enforce_lead_access(session, lead_id, current_user)
    return await LeadService(session).list_calls(lead_id)


@router.post("/{lead_id}/calls", response_model=LeadCallLogRead, status_code=status.HTTP_201_CREATED)
async def log_lead_call(
    lead_id: UUID,
    payload: LeadCallLogCreate,
    current_user=Depends(require_permissions(PermissionCode.LEAD_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    await get_lead_or_404(session, lead_id)
    await _enforce_lead_access(session, lead_id, current_user)
    return await LeadService(session).log_call(
        lead_id,
        payload.call_type,
        actor_id=current_user.id,
        notes=payload.notes,
        next_action_date=payload.next_action_date,
    )


# --- Stage transitions (spec §3.2) ----------------------------------------

@router.get("/{lead_id}/transitions", response_model=list[StageTransitionRead])
async def list_transitions(
    lead_id: UUID,
    current_user=Depends(require_permissions(PermissionCode.LEAD_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    await _enforce_lead_access(session, lead_id, current_user)
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
    await _enforce_lead_access(session, lead_id, current_user)
    return await StageTransitionService(session).create_transition(
        lead_id, payload, actor_id=current_user.id, actor_role=current_user.role
    )


# --- CSV bulk import -------------------------------------------------------

# Per-vertical template/import/export columns live in app.core.lead_csv — the
# single source of truth. Add or change a column there and the template, the
# importer, and the export sheet all stay consistent.


@router.get("/import/template.csv")
async def download_import_template(
    current_user=Depends(require_permissions(PermissionCode.LEAD_IMPORT)),
):
    """Vertical-aware starter CSV — same shape the `POST /import` endpoint accepts."""
    body, filename = build_template_csv(current_user.business_type)
    return StreamingResponse(
        iter([body]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/import")
async def import_leads_csv(
    file: UploadFile = File(..., description="CSV file. UTF-8, header row required."),
    skip_duplicates: bool = False,
    current_user=Depends(require_permissions(PermissionCode.LEAD_IMPORT)),
    session: AsyncSession = Depends(get_db_session),
):
    """Bulk-create leads from a CSV file.

    Scope is the caller's org (tenancy filter applies). Each row produces
    one Lead; if the row's `stage` column is set, the lead is transitioned
    to that stage via the regular service so the Sold auto-promotion fires
    where applicable. Per-row errors are returned in the response — they
    don't abort the rest of the upload.

    Duplicate handling: a row whose email or phone matches an existing lead is
    always reported under `duplicates`. When `skip_duplicates=true` those rows
    are skipped (only fresh leads created); otherwise they are imported and
    flagged so the UI can show them with the "!" marker.
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
        skip_duplicates=skip_duplicates,
    )
    return {
        "created": summary.created,
        "promoted": summary.promoted,
        "skipped": summary.skipped,
        "errors": [{"row": e.row, "error": e.error} for e in summary.errors],
        "duplicates": [
            {
                "row": d.row,
                "contact_name": d.contact_name,
                "contact_email": d.contact_email,
                "contact_phone": d.contact_phone,
                "matched": d.matched,
                "skipped": d.skipped,
            }
            for d in summary.duplicates
        ],
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
