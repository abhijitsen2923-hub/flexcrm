"""Customer portal API routes — payments, documents, service requests, referrals."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.exceptions import AuthorizationError
from app.customer_portal.models import CustomerDocument, ServiceRequest
from app.customer_portal.schemas import (
    CustomerDocumentOut,
    PaymentScheduleEntryOut,
    ReferralCreate,
    ServiceRequestCreate,
    ServiceRequestOut,
)
from app.database.enums import LeadIndustry, UserRole
from app.database.pipeline_seed import initial_stage_code
from app.database.session import get_db_session
from app.models.customer import Customer
from app.models.lead import Lead
from app.real_estate.models import Booking, PaymentSchedule
from app.repositories.leads import LeadRepository

router = APIRouter()


async def _get_customer(
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Customer:
    if current_user.role != UserRole.customer:
        raise AuthorizationError("Customer portal access only.")
    result = await session.execute(
        select(Customer)
        .where(Customer.email == current_user.email, Customer.is_deleted.is_(False))
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="No customer record linked to this account.")
    return customer


@router.get("/payments", response_model=list[PaymentScheduleEntryOut])
async def get_payments(
    customer: Customer = Depends(_get_customer),
    session: AsyncSession = Depends(get_db_session),
):
    stmt = (
        select(PaymentSchedule)
        .join(Booking, PaymentSchedule.booking_id == Booking.id)
        .where(Booking.customer_id == customer.id, Booking.is_deleted.is_(False))
        .order_by(PaymentSchedule.due_date)
    )
    return list((await session.execute(stmt)).scalars().all())


@router.get("/documents", response_model=list[CustomerDocumentOut])
async def get_documents(
    customer: Customer = Depends(_get_customer),
    session: AsyncSession = Depends(get_db_session),
):
    stmt = (
        select(CustomerDocument)
        .where(
            CustomerDocument.customer_id == customer.id,
            CustomerDocument.is_active.is_(True),
        )
        .order_by(CustomerDocument.created_at.desc())
    )
    docs = list((await session.execute(stmt)).scalars().all())
    return [
        CustomerDocumentOut(
            id=d.id,
            name=d.name,
            type=d.type,
            url=f"/files/customer-documents/{d.id}",
            created_at=d.created_at,
        )
        for d in docs
    ]


@router.get("/documents/{doc_id}/download")
async def download_document(
    doc_id: UUID,
    customer: Customer = Depends(_get_customer),
    session: AsyncSession = Depends(get_db_session),
):
    doc = await session.get(CustomerDocument, doc_id)
    if not doc or doc.customer_id != customer.id or not doc.is_active:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"url": f"/files/customer-documents/{doc_id}"}


@router.get("/service-requests", response_model=list[ServiceRequestOut])
async def list_service_requests(
    customer: Customer = Depends(_get_customer),
    session: AsyncSession = Depends(get_db_session),
):
    stmt = (
        select(ServiceRequest)
        .where(ServiceRequest.customer_id == customer.id)
        .order_by(ServiceRequest.created_at.desc())
    )
    return list((await session.execute(stmt)).scalars().all())


@router.post("/service-requests", response_model=ServiceRequestOut, status_code=status.HTTP_201_CREATED)
async def create_service_request(
    payload: ServiceRequestCreate,
    customer: Customer = Depends(_get_customer),
    session: AsyncSession = Depends(get_db_session),
):
    sr = ServiceRequest(customer_id=customer.id, **payload.model_dump())
    session.add(sr)
    await session.commit()
    await session.refresh(sr)
    return sr


@router.post("/referrals", status_code=status.HTTP_201_CREATED)
async def submit_referral(
    payload: ReferralCreate,
    customer: Customer = Depends(_get_customer),
    session: AsyncSession = Depends(get_db_session),
):
    repo = LeadRepository(session)
    lead_number = await repo.next_lead_number()
    stage_code = initial_stage_code(LeadIndustry.real_estate)
    lead = Lead(
        industry=LeadIndustry.real_estate,
        stage_code=stage_code,
        lead_number=lead_number,
        title=f"Referral — {payload.contact_name}",
        contact_name=payload.contact_name,
        contact_phone=payload.contact_phone,
        contact_email=payload.contact_email,
        preferred_location=payload.preferred_location,
        notes=payload.notes,
        source="customer_referral",
        value=0,
        probability=0,
    )
    session.add(lead)
    await session.commit()
    return {"message": "Referral submitted", "lead_id": str(lead.id)}
