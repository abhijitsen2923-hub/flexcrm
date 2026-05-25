"""Lifecycle sub-endpoints for a customer: delivery log, renewals, referrals.

Mounted under `/customers/{customer_id}/...`. The base customer CRUD lives in
`customers.py`; this module focuses on the per-customer collections that arrived
in Phase 3.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permissions
from app.core.exceptions import NotFoundError
from app.core.permissions import PermissionCode
from app.database.session import get_db_session
from app.models.customer import Customer
from app.models.delivery_log import DeliveryLog
from app.models.referral import Referral
from app.models.renewal import Renewal
from app.schemas.customer_lifecycle import (
    DeliveryLogCreate,
    DeliveryLogRead,
    ReferralCreate,
    ReferralRead,
    RenewalCreate,
    RenewalRead,
)


router = APIRouter()


async def _get_customer(session: AsyncSession, customer_id: UUID) -> Customer:
    customer = (
        await session.execute(select(Customer).where(Customer.id == customer_id))
    ).scalar_one_or_none()
    if customer is None:
        raise NotFoundError("Customer not found.")
    return customer


# --- Delivery log ----------------------------------------------------------

@router.get("/{customer_id}/delivery", response_model=list[DeliveryLogRead])
async def list_deliveries(
    customer_id: UUID,
    _: object = Depends(require_permissions(PermissionCode.CUSTOMER_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    await _get_customer(session, customer_id)
    rows = (
        await session.execute(
            select(DeliveryLog).where(DeliveryLog.customer_id == customer_id).order_by(DeliveryLog.delivered_at.desc())
        )
    ).scalars().all()
    return list(rows)


@router.post(
    "/{customer_id}/delivery",
    response_model=DeliveryLogRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_delivery(
    customer_id: UUID,
    payload: DeliveryLogCreate,
    current_user=Depends(require_permissions(PermissionCode.CUSTOMER_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    await _get_customer(session, customer_id)
    entry = DeliveryLog(
        customer_id=customer_id,
        item=payload.item,
        notes=payload.notes,
        delivered_by_id=payload.delivered_by_id or current_user.id,
    )
    if payload.delivered_at is not None:
        entry.delivered_at = payload.delivered_at
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


# --- Renewals -------------------------------------------------------------

@router.get("/{customer_id}/renewals", response_model=list[RenewalRead])
async def list_renewals(
    customer_id: UUID,
    _: object = Depends(require_permissions(PermissionCode.CUSTOMER_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    await _get_customer(session, customer_id)
    rows = (
        await session.execute(
            select(Renewal).where(Renewal.customer_id == customer_id).order_by(Renewal.due_date.asc())
        )
    ).scalars().all()
    return list(rows)


@router.post(
    "/{customer_id}/renewals",
    response_model=RenewalRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_renewal(
    customer_id: UUID,
    payload: RenewalCreate,
    _: object = Depends(require_permissions(PermissionCode.CUSTOMER_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    customer = await _get_customer(session, customer_id)
    entry = Renewal(
        customer_id=customer_id,
        due_date=payload.due_date,
        amount=payload.amount,
        status=payload.status,
    )
    session.add(entry)
    customer.renewal_due_at = payload.due_date
    await session.commit()
    await session.refresh(entry)
    return entry


# --- Referrals ------------------------------------------------------------

@router.get("/{customer_id}/referrals", response_model=list[ReferralRead])
async def list_referrals(
    customer_id: UUID,
    _: object = Depends(require_permissions(PermissionCode.CUSTOMER_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    await _get_customer(session, customer_id)
    rows = (
        await session.execute(
            select(Referral).where(Referral.referring_customer_id == customer_id).order_by(Referral.created_at.desc())
        )
    ).scalars().all()
    return list(rows)


@router.post(
    "/{customer_id}/referrals",
    response_model=ReferralRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_referral(
    customer_id: UUID,
    payload: ReferralCreate,
    _: object = Depends(require_permissions(PermissionCode.CUSTOMER_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    await _get_customer(session, customer_id)
    entry = Referral(
        referring_customer_id=customer_id,
        referred_lead_id=payload.referred_lead_id,
        awarded_credit=payload.awarded_credit,
        status=payload.status,
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry
