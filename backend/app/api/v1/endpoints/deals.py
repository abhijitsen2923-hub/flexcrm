from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import pagination_params, require_permissions
from app.core.permissions import PermissionCode
from app.database.session import get_db_session
from app.schemas.common import MessageResponse, PaginatedResponse, PaginationParams, build_page_meta
from app.schemas.deal import DealCreate, DealFilterParams, DealRead, DealUpdate
from app.services.deals import DealService


router = APIRouter()


@router.get("", response_model=PaginatedResponse[DealRead])
async def list_deals(
    filters: DealFilterParams = Depends(),
    pagination: PaginationParams = Depends(pagination_params),
    _: object = Depends(require_permissions(PermissionCode.DEAL_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    items, total = await DealService(session).list_deals(pagination, filters)
    return PaginatedResponse[DealRead](items=items, pagination=build_page_meta(total, pagination))


@router.post("", response_model=DealRead, status_code=status.HTTP_201_CREATED)
async def create_deal(
    payload: DealCreate,
    current_user=Depends(require_permissions(PermissionCode.DEAL_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    return await DealService(session).create_deal(payload, actor_id=current_user.id)


@router.put("/{deal_id}", response_model=DealRead)
async def update_deal(
    deal_id: UUID,
    payload: DealUpdate,
    current_user=Depends(require_permissions(PermissionCode.DEAL_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    return await DealService(session).update_deal(deal_id, payload, actor_id=current_user.id)


@router.delete("/{deal_id}", response_model=MessageResponse)
async def delete_deal(
    deal_id: UUID,
    current_user=Depends(require_permissions(PermissionCode.DEAL_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    await DealService(session).delete_deal(deal_id, actor_id=current_user.id)
    return MessageResponse(message="Deal deleted successfully.")
