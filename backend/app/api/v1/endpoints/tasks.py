from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import pagination_params, require_permissions
from app.core.permissions import PermissionCode
from app.database.session import get_db_session
from app.schemas.common import MessageResponse, PaginatedResponse, PaginationParams, build_page_meta
from app.schemas.task import TaskCreate, TaskFilterParams, TaskRead, TaskUpdate
from app.services.tasks import TaskService


router = APIRouter()


@router.get("", response_model=PaginatedResponse[TaskRead])
async def list_tasks(
    filters: TaskFilterParams = Depends(),
    pagination: PaginationParams = Depends(pagination_params),
    _: object = Depends(require_permissions(PermissionCode.TASK_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    items, total = await TaskService(session).list_tasks(pagination, filters)
    return PaginatedResponse[TaskRead](items=items, pagination=build_page_meta(total, pagination))


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(
    payload: TaskCreate,
    background_tasks: BackgroundTasks,
    current_user=Depends(require_permissions(PermissionCode.TASK_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    return await TaskService(session).create_task(payload, actor_id=current_user.id, background_tasks=background_tasks)


@router.put("/{task_id}", response_model=TaskRead)
async def update_task(
    task_id: UUID,
    payload: TaskUpdate,
    background_tasks: BackgroundTasks,
    current_user=Depends(require_permissions(PermissionCode.TASK_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    return await TaskService(session).update_task(task_id, payload, actor_id=current_user.id, background_tasks=background_tasks)


@router.delete("/{task_id}", response_model=MessageResponse)
async def delete_task(
    task_id: UUID,
    current_user=Depends(require_permissions(PermissionCode.TASK_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    await TaskService(session).delete_task(task_id, actor_id=current_user.id)
    return MessageResponse(message="Task deleted successfully.")
