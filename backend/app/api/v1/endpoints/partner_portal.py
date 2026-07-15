"""Broker self-service portal endpoints. Everything is scoped to the caller's
own ChannelPartner profile — a broker can only ever see their own referrals and
brokerage. Gated by `require_broker` (role identity), not permission codes."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_broker
from app.database.session import get_db_session
from app.models.channel_partner import ChannelPartner
from app.schemas.channel_partner import (
    BrokeragePayoutRead,
    ChannelPartnerRead,
    PartnerDashboard,
    PartnerLeadRow,
    PartnerLeadSubmit,
)
from app.services.channel_partners import ChannelPartnerService

router = APIRouter()

_NO_PROFILE = "No channel-partner profile is linked to your account. Contact the developer/admin."


async def _my_partner(session: AsyncSession, user) -> ChannelPartner:
    partner = await ChannelPartnerService(session).partner_for_user(user.id)
    if partner is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NO_PROFILE)
    return partner


@router.get("/me", response_model=ChannelPartnerRead)
async def get_my_partner_profile(
    current_user=Depends(require_broker()),
    session: AsyncSession = Depends(get_db_session),
):
    return await _my_partner(session, current_user)


@router.get("/dashboard", response_model=PartnerDashboard)
async def get_partner_dashboard(
    current_user=Depends(require_broker()),
    session: AsyncSession = Depends(get_db_session),
):
    svc = ChannelPartnerService(session)
    partner = await _my_partner(session, current_user)
    stats = await svc.stats_for(partner.id)
    breakdown = await svc.stage_breakdown(partner.id)
    payouts = (await svc.list_payouts(partner.id))[:5]
    return PartnerDashboard(
        partner=ChannelPartnerRead.model_validate(partner),
        stats=stats,
        stage_breakdown=breakdown,
        recent_payouts=[BrokeragePayoutRead.model_validate(p) for p in payouts],
    )


@router.get("/leads", response_model=list[PartnerLeadRow])
async def list_my_referred_leads(
    current_user=Depends(require_broker()),
    session: AsyncSession = Depends(get_db_session),
):
    svc = ChannelPartnerService(session)
    partner = await _my_partner(session, current_user)
    leads = await svc.partner_leads(partner.id)
    return [PartnerLeadRow.model_validate(lead) for lead in leads]


@router.post("/leads", response_model=PartnerLeadRow, status_code=status.HTTP_201_CREATED)
async def submit_referred_lead(
    payload: PartnerLeadSubmit,
    current_user=Depends(require_broker()),
    session: AsyncSession = Depends(get_db_session),
):
    svc = ChannelPartnerService(session)
    partner = await _my_partner(session, current_user)
    lead = await svc.submit_partner_lead(partner, payload, actor_id=current_user.id)
    return PartnerLeadRow.model_validate(lead)


@router.get("/commissions", response_model=list[BrokeragePayoutRead])
async def list_my_commissions(
    current_user=Depends(require_broker()),
    session: AsyncSession = Depends(get_db_session),
):
    svc = ChannelPartnerService(session)
    partner = await _my_partner(session, current_user)
    return await svc.list_payouts(partner.id)
