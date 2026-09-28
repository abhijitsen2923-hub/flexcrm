"""The tenant's own campaign list (read for the New Lead form; managed by CAMPAIGN_MANAGE holders)."""
from collections.abc import Awaitable
from typing import TypeVar
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.exc import DBAPIError, OperationalError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_any_permissions, require_permissions
from app.core.exceptions import ConflictError
from app.core.permissions import ASSIGNED_ONLY_LEAD_ROLES, PermissionCode
from app.database.session import get_db_session
from app.schemas.campaign import (
    CampaignCreate,
    CampaignMerge,
    CampaignMutationResult,
    CampaignOption,
    CampaignOverview,
    CampaignRead,
    CampaignRename,
    CampaignUpdate,
)
from app.schemas.common import MessageResponse
from app.services.campaigns import RACE_MESSAGE, CampaignService, is_lock_conflict, is_missing_table

router = APIRouter()
T = TypeVar("T")


async def _not_ready(session: AsyncSession, exc: Exception) -> None:
    """The tenant's campaign tables aren't there yet (migration still running) → a clear 409 (not a 5xx,
    which the client would retry for seconds); the frontend then falls back to its legacy behaviour."""
    if not is_missing_table(exc):
        raise exc
    await session.rollback()
    raise ConflictError(
        "Campaigns are still being set up — try again in a minute.", extra={"reason": "not_ready"}
    ) from exc


async def _guarded(session: AsyncSession, change: Awaitable[T]) -> T:
    """Run a manager change; a deadlock / lock timeout against a concurrent change → 409 "try again", not 500."""
    try:
        return await change
    except DBAPIError as exc:
        if not is_lock_conflict(exc):
            raise
        await session.rollback()
        raise ConflictError(RACE_MESSAGE, extra={"reason": "busy"}) from exc


def _read(row: dict) -> CampaignRead:
    campaign = row["campaign"]
    return CampaignRead(
        id=campaign.id,
        name=campaign.name,
        is_active=campaign.is_active,
        needs_review=campaign.needs_review,
        source=campaign.source,
        lead_count=row["lead_count"],
        aliases=row["aliases"],
        created_at=campaign.created_at,
        updated_at=campaign.updated_at,
    )


@router.get("", response_model=list[CampaignOption])
async def list_campaigns(
    include_inactive: bool = Query(default=False),
    current_user=Depends(require_any_permissions(PermissionCode.LEAD_VIEW, PermissionCode.CAMPAIGN_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    """The tenant's campaigns for the New Lead form. Front-line reps always get active ones only."""
    if current_user.role in ASSIGNED_ONLY_LEAD_ROLES:
        include_inactive = False
    try:
        return await CampaignService(session).list_options(include_inactive=include_inactive)
    except (ProgrammingError, OperationalError) as exc:
        await _not_ready(session, exc)


@router.get("/manage", response_model=CampaignOverview)
async def manage_campaigns(
    _=Depends(require_permissions(PermissionCode.CAMPAIGN_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    """Every campaign with lead counts, remembered old spellings, and merge suggestions."""
    try:
        overview = await CampaignService(session).overview()
    except (ProgrammingError, OperationalError) as exc:
        await _not_ready(session, exc)
    return CampaignOverview(items=[_read(row) for row in overview["items"]], suggestions=overview["suggestions"])


@router.post("", response_model=CampaignRead, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    payload: CampaignCreate,
    current_user=Depends(require_permissions(PermissionCode.CAMPAIGN_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    service = CampaignService(session)
    campaign = await _guarded(session, service.create(payload.name, actor_id=current_user.id))
    return _read(await service.read_row(campaign))


@router.post("/merge", response_model=CampaignMutationResult)
async def merge_campaigns(
    payload: CampaignMerge,
    current_user=Depends(require_permissions(PermissionCode.CAMPAIGN_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    """Merge campaigns into one: their leads move to the target and their names are remembered."""
    service = CampaignService(session)
    target, count = await _guarded(
        session, service.merge(payload.source_ids, payload.target_id, actor_id=current_user.id)
    )
    return CampaignMutationResult(campaign=_read(await service.read_row(target)), leads_updated=count)


@router.patch("/{campaign_id}", response_model=CampaignRead)
async def update_campaign(
    campaign_id: UUID,
    payload: CampaignUpdate,
    current_user=Depends(require_permissions(PermissionCode.CAMPAIGN_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    """Activate / deactivate, or mark a needs-review campaign as reviewed."""
    service = CampaignService(session)
    campaign = await _guarded(
        session,
        service.set_flags(
            campaign_id,
            is_active=payload.is_active,
            reviewed=payload.needs_review is False,
            actor_id=current_user.id,
        ),
    )
    return _read(await service.read_row(campaign))


@router.post("/{campaign_id}/rename", response_model=CampaignMutationResult)
async def rename_campaign(
    campaign_id: UUID,
    payload: CampaignRename,
    current_user=Depends(require_permissions(PermissionCode.CAMPAIGN_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    service = CampaignService(session)
    campaign, count = await _guarded(session, service.rename(campaign_id, payload.name, actor_id=current_user.id))
    return CampaignMutationResult(campaign=_read(await service.read_row(campaign)), leads_updated=count)


@router.post("/{campaign_id}/clear", response_model=CampaignMutationResult)
async def clear_campaign(
    campaign_id: UUID,
    current_user=Depends(require_permissions(PermissionCode.CAMPAIGN_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    """Remove a (junk) campaign: its leads end up with no campaign."""
    count = await _guarded(session, CampaignService(session).clear(campaign_id, actor_id=current_user.id))
    return CampaignMutationResult(campaign=None, leads_updated=count)


@router.delete("/{campaign_id}/aliases/{alias_id}", response_model=MessageResponse)
async def delete_campaign_alias(
    campaign_id: UUID,
    alias_id: UUID,
    _=Depends(require_permissions(PermissionCode.CAMPAIGN_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    await _guarded(session, CampaignService(session).delete_alias(campaign_id, alias_id))
    return MessageResponse(message="Old spelling removed.")
