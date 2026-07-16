"""Staff-facing channel-partner management: roster, per-partner overview,
brokerage payouts. Broker self-service lives in `partner_portal.py`."""
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permissions
from app.core.permissions import PermissionCode
from app.database.session import get_db_session
from app.schemas.channel_partner import (
    BrokeragePayoutRead,
    BrokeragePayoutUpdate,
    ChannelPartnerCreate,
    ChannelPartnerFull,
    ChannelPartnerListItem,
    ChannelPartnerRead,
    ChannelPartnerUpdate,
)
from app.schemas.lead import LeadPartnerCompact, LeadRead
from app.services.channel_partners import ChannelPartnerService

router = APIRouter()


def _to_list_item(partner, stats) -> ChannelPartnerListItem:
    return ChannelPartnerListItem.model_validate(partner).model_copy(update={"stats": stats})


@router.get("", response_model=list[ChannelPartnerListItem])
async def list_channel_partners(
    _: object = Depends(require_permissions(PermissionCode.USER_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    roster = await ChannelPartnerService(session).roster_with_stats()
    return [_to_list_item(p, s) for p, s in roster]


@router.post("", response_model=ChannelPartnerRead, status_code=status.HTTP_201_CREATED)
async def create_channel_partner(
    payload: ChannelPartnerCreate,
    current_user=Depends(require_permissions(PermissionCode.USER_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    partner = await ChannelPartnerService(session).create_partner(payload, actor_id=current_user.id)
    return partner


# Lightweight picker for the New Lead form — any lead creator (LEAD_MANAGE) can
# attribute a walk-in to a partner without needing USER_VIEW for the full roster.
# Registered before /{partner_id} so "options" isn't parsed as an id.
@router.get("/options", response_model=list[LeadPartnerCompact])
async def channel_partner_options(
    _: object = Depends(require_permissions(PermissionCode.LEAD_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    partners = await ChannelPartnerService(session).list_partners()
    return [p for p in partners if p.is_active]


# Static path registered before /{partner_id} so "payouts" isn't parsed as an id.
@router.patch("/payouts/{payout_id}", response_model=BrokeragePayoutRead)
async def update_brokerage_payout(
    payout_id: UUID,
    payload: BrokeragePayoutUpdate,
    _: object = Depends(require_permissions(PermissionCode.FINANCE_RECORD_PAYMENT)),
    session: AsyncSession = Depends(get_db_session),
):
    return await ChannelPartnerService(session).update_payout(
        payout_id, status=payload.status, paid_on=payload.paid_on, note=payload.note
    )


@router.get("/{partner_id}", response_model=ChannelPartnerListItem)
async def get_channel_partner(
    partner_id: UUID,
    _: object = Depends(require_permissions(PermissionCode.USER_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    svc = ChannelPartnerService(session)
    partner = await svc.get_partner(partner_id)
    stats = await svc.stats_for(partner_id)
    return _to_list_item(partner, stats)


@router.get("/{partner_id}/full", response_model=ChannelPartnerFull)
async def get_channel_partner_full(
    partner_id: UUID,
    _: object = Depends(require_permissions(PermissionCode.USER_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    """Full record incl. PAN + payout details — for the edit form only, gated by
    USER_MANAGE so view-only roles never receive partner PII/bank details."""
    return await ChannelPartnerService(session).get_partner(partner_id)


@router.patch("/{partner_id}", response_model=ChannelPartnerRead)
async def update_channel_partner(
    partner_id: UUID,
    payload: ChannelPartnerUpdate,
    current_user=Depends(require_permissions(PermissionCode.USER_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    return await ChannelPartnerService(session).update_partner(
        partner_id, payload, actor_id=current_user.id
    )


@router.get("/{partner_id}/leads", response_model=list[LeadRead])
async def list_channel_partner_leads(
    partner_id: UUID,
    _: object = Depends(require_permissions(PermissionCode.USER_VIEW, PermissionCode.LEAD_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    svc = ChannelPartnerService(session)
    await svc.get_partner(partner_id)  # 404 if missing
    return await svc.partner_leads(partner_id, eager=True)


@router.get("/{partner_id}/payouts", response_model=list[BrokeragePayoutRead])
async def list_channel_partner_payouts(
    partner_id: UUID,
    _: object = Depends(require_permissions(PermissionCode.FINANCE_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    svc = ChannelPartnerService(session)
    await svc.get_partner(partner_id)
    return await svc.list_payouts(partner_id)
