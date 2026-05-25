from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import pagination_params, require_permissions
from app.core.permissions import PermissionCode
from app.database.session import get_db_session
from app.schemas.activity import ActivityCreate, ActivityFilterParams, ActivityRead
from app.schemas.common import PaginatedResponse, PaginationParams, build_page_meta
from app.services.activities import ActivityService


router = APIRouter()


@router.get("", response_model=PaginatedResponse[ActivityRead])
async def list_activities(
    filters: ActivityFilterParams = Depends(),
    pagination: PaginationParams = Depends(pagination_params),
    _: object = Depends(require_permissions(PermissionCode.ACTIVITY_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    items, total = await ActivityService(session).list_activities(pagination, filters)
    return PaginatedResponse[ActivityRead](items=items, pagination=build_page_meta(total, pagination))


@router.post("", response_model=ActivityRead, status_code=status.HTTP_201_CREATED)
async def create_activity(
    payload: ActivityCreate,
    current_user=Depends(require_permissions(PermissionCode.ACTIVITY_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    return await ActivityService(session).create_activity(payload, actor_id=current_user.id)
