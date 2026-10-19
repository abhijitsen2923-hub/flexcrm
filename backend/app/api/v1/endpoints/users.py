from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ensure_caller_holds, get_current_user, pagination_params, require_permissions
from app.core.exceptions import AuthorizationError
from app.core.permissions import PermissionCode
from app.database.enums import UserRole
from app.database.session import get_db_session
from app.models.custom_role import CustomRole, UserCustomRoleAssignment
from app.schemas.common import MessageResponse, PaginatedResponse, PaginationParams, build_page_meta
from app.schemas.user import UserCreate, UserFilterParams, UserRead, UserUpdate
from app.services.users import UserService


router = APIRouter()


@router.get("", response_model=PaginatedResponse[UserRead])
async def list_users(
    filters: UserFilterParams = Depends(),
    pagination: PaginationParams = Depends(pagination_params),
    _: object = Depends(require_permissions(PermissionCode.USER_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    items, total = await UserService(session).list_users(pagination, filters)
    # Custom-role users show their role's name (Users list → Role column, "Change role").
    custom_ids = [u.id for u in items if u.role == UserRole.custom]
    by_user: dict = {}
    if custom_ids:
        rows = await session.execute(
            select(UserCustomRoleAssignment.user_id, CustomRole.id, CustomRole.name)
            .join(CustomRole, CustomRole.id == UserCustomRoleAssignment.custom_role_id)
            .where(UserCustomRoleAssignment.user_id.in_(custom_ids))
        )
        by_user = {user_id: (role_id, name) for user_id, role_id, name in rows}
    reads = [
        UserRead.model_validate(u).model_copy(
            update={"custom_role_id": by_user[u.id][0], "custom_role_name": by_user[u.id][1]}
        )
        if u.id in by_user
        else UserRead.model_validate(u)
        for u in items
    ]
    return PaginatedResponse[UserRead](items=reads, pagination=build_page_meta(total, pagination))


@router.get("/{user_id}", response_model=UserRead)
async def get_user(
    user_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    # Users can always view themselves; viewing other users requires USER_VIEW.
    if current_user.id != user_id:
        from app.api.deps import load_effective_permissions

        effective = await load_effective_permissions(session, current_user)
        if PermissionCode.USER_VIEW not in effective:
            raise AuthorizationError("You do not have permission to view this user.")
    return await UserService(session).get_user(user_id)


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    current_user=Depends(require_permissions(PermissionCode.USER_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    if payload.role == UserRole.custom and payload.custom_role_id:
        # Same rule as assigning a custom role later: only a role whose permissions the caller holds.
        template = (
            await session.execute(select(CustomRole).where(CustomRole.id == payload.custom_role_id))
        ).scalar_one_or_none()
        if template is not None:
            await ensure_caller_holds(session, current_user, template.permissions or [])
    return await UserService(session).create_user(payload, actor_id=current_user.id)


@router.put("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: UUID,
    payload: UserUpdate,
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    # Authorization model:
    #  - Updating another user requires USER_MANAGE.
    #  - Privileged fields (role, status) may ONLY be changed by a USER_MANAGE
    #    holder — never through a self-service update. Without this guard any
    #    user could PUT /users/{self} {"role": "owner"} and self-escalate to
    #    full permissions (the self-update path skipped the permission check).
    from app.api.deps import load_effective_permissions

    effective = await load_effective_permissions(session, current_user)
    can_manage = PermissionCode.USER_MANAGE in effective

    if current_user.id != user_id and not can_manage:
        raise AuthorizationError("You do not have permission to update this user.")

    if not can_manage:
        privileged = {"role", "status"} & payload.model_fields_set
        if privileged:
            raise AuthorizationError(
                "Changing role or status requires the User Manage permission."
            )

    return await UserService(session).update_user(user_id, payload, actor_id=current_user.id)


@router.delete("/{user_id}", response_model=MessageResponse)
async def delete_user(
    user_id: UUID,
    current_user=Depends(require_permissions(PermissionCode.USER_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    await UserService(session).delete_user(user_id, actor_id=current_user.id)
    return MessageResponse(message="User deleted successfully.")
