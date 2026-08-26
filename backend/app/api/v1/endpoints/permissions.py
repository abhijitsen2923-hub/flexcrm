"""Permission inspection + grant management endpoints (Phase 8).

- `GET /me/permissions` — caller's own effective permission set. Cheap because
  it doesn't touch any other user; frontend hits this after a grant is added
  so the sidebar/buttons refresh without forcing a re-login.
- `GET /users/{id}/permissions` — admin view of one user. Returns the role
  defaults, the explicit grants, and the effective union so the admin drawer
  can render role defaults as disabled-checked and grants as toggleable.
- `POST /users/{id}/permissions` / `DELETE /users/{id}/permissions/{code}` —
  grant + revoke. Both require USER_MANAGE.

Cross-org snooping is impossible: `UserPermissionGrant` is org-scoped and
`UserService.get_user` already filters target lookups by the caller's org.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, load_effective_permissions, require_permissions
from app.core.exceptions import AuthorizationError, ConflictError, NotFoundError
from app.core.permissions import (
    PermissionCode,
    ROLE_PERMISSION_DEFAULTS,
    _expand_aliases,
)
from app.database.enums import UserRole
from app.database.session import get_db_session
from app.models.custom_role import UserCustomRoleAssignment
from app.models.user_permission_grant import UserPermissionGrant
from app.schemas.common import MessageResponse
from app.schemas.user_permission_grant import (
    GrantPermissionRequest,
    GrantedPermissionRead,
    UserPermissionsRead,
)
from app.services.users import UserService


router = APIRouter()


async def _role_default_codes(role, session, user_id) -> list[str]:
    """Return alias-expanded default permissions for a role.

    For UserRole.custom, looks up the linked CustomRole template instead of
    ROLE_PERMISSION_DEFAULTS.
    """
    if role == UserRole.custom:
        assignment = (
            await session.execute(
                select(UserCustomRoleAssignment).where(UserCustomRoleAssignment.user_id == user_id)
            )
        ).scalar_one_or_none()
        base_codes = assignment.custom_role.permissions if (assignment and assignment.custom_role) else []
        valid: set[PermissionCode] = set()
        for raw in base_codes:
            try:
                valid.add(PermissionCode(raw))
            except ValueError:
                continue
        expanded = _expand_aliases(valid)
    else:
        expanded = _expand_aliases(set(ROLE_PERMISSION_DEFAULTS.get(role, ())))
    return sorted(c.value for c in expanded)


@router.get("/me/permissions", response_model=UserPermissionsRead)
async def get_my_permissions(
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Live effective permissions for the calling user.

    Frontend polls this (or just refetches on demand) to refresh after an
    admin grants something — no re-login needed.
    """
    grants = (
        await session.execute(
            select(UserPermissionGrant).where(UserPermissionGrant.user_id == current_user.id)
        )
    ).scalars().all()
    effective = await load_effective_permissions(session, current_user)
    return UserPermissionsRead(
        user_id=current_user.id,
        role_defaults=await _role_default_codes(current_user.role, session, current_user.id),
        granted=[GrantedPermissionRead.model_validate(g) for g in grants],
        effective=sorted(c.value for c in effective),
    )


@router.get("/users/{user_id}/permissions", response_model=UserPermissionsRead)
async def list_user_permissions(
    user_id: UUID,
    _: object = Depends(require_permissions(PermissionCode.USER_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    user = await UserService(session).get_user(user_id)
    if user is None:
        raise NotFoundError("User not found.")
    grants = (
        await session.execute(
            select(UserPermissionGrant).where(UserPermissionGrant.user_id == user_id)
        )
    ).scalars().all()
    effective = await load_effective_permissions(session, user)
    return UserPermissionsRead(
        user_id=user_id,
        role_defaults=await _role_default_codes(user.role, session, user_id),
        granted=[GrantedPermissionRead.model_validate(g) for g in grants],
        effective=sorted(c.value for c in effective),
    )


@router.post(
    "/users/{user_id}/permissions",
    response_model=GrantedPermissionRead,
    status_code=status.HTTP_201_CREATED,
)
async def grant_permission(
    user_id: UUID,
    payload: GrantPermissionRequest,
    current_user=Depends(require_permissions(PermissionCode.USER_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    # Verify the target user is reachable (tenancy filter returns None for
    # cross-org users) — surfaces a clean 404 rather than a unique-constraint
    # error inserting a grant for an invisible user.
    target = await UserService(session).get_user(user_id)
    if target is None:
        raise NotFoundError("User not found.")

    # Privilege-escalation guard: a grantor may only grant permissions they
    # themselves hold (platform admins excepted). Without this, any USER_MANAGE
    # holder could grant ORG_MANAGE / FINANCE_REFUND — to another user or to
    # themselves — and escalate beyond their own level.
    if not getattr(current_user, "is_platform_admin", False):
        caller_effective = await load_effective_permissions(session, current_user)
        if payload.permission_code not in caller_effective:
            raise AuthorizationError("You can only grant permissions that you already hold.")

    existing = (
        await session.execute(
            select(UserPermissionGrant).where(
                UserPermissionGrant.user_id == user_id,
                UserPermissionGrant.permission_code == payload.permission_code.value,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError("This permission is already granted to the user.")

    grant = UserPermissionGrant(
        user_id=user_id,
        permission_code=payload.permission_code.value,
        granted_by_id=current_user.id,
    )
    session.add(grant)
    await session.commit()
    await session.refresh(grant)
    return GrantedPermissionRead.model_validate(grant)


@router.delete(
    "/users/{user_id}/permissions/{code}",
    response_model=MessageResponse,
)
async def revoke_permission(
    user_id: UUID,
    code: str,
    _: object = Depends(require_permissions(PermissionCode.USER_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    target = await UserService(session).get_user(user_id)
    if target is None:
        raise NotFoundError("User not found.")

    grant = (
        await session.execute(
            select(UserPermissionGrant).where(
                UserPermissionGrant.user_id == user_id,
                UserPermissionGrant.permission_code == code,
            )
        )
    ).scalar_one_or_none()
    if grant is None:
        raise NotFoundError("No explicit grant exists for that permission. Role defaults are not revocable.")

    await session.delete(grant)
    await session.commit()
    return MessageResponse(message="Permission revoked.")
