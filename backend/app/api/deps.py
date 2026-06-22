from uuid import UUID

from fastapi import Depends, Query, Request
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError, AuthorizationError
from app.core.permissions import (
    PermissionCode,
    effective_permissions_for_user,
)
from app.core.security import bearer_scheme, decode_token, get_bearer_token
from app.core.tenancy import bypass, set_scope
from app.database.enums import UserStatus
from app.database.session import get_db_session
from app.models.user_permission_grant import UserPermissionGrant
from app.repositories.users import UserRepository
from app.schemas.common import PaginationParams


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_db_session),
):
    token = get_bearer_token(credentials)
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise AuthenticationError("Invalid access token.")

    # The user lookup itself must bypass the tenancy filter — at this point
    # the session has no org context yet. As soon as we resolve the user, we
    # set the scope so every subsequent query in the request is filtered.
    with bypass(session):
        user = await UserRepository(session).get(UUID(payload["sub"]))
    if user is None or user.status != UserStatus.active:
        raise AuthenticationError("The user account is not active.")

    # Prefer the org_id from the JWT (cheap), fall back to the user row in
    # case an older token was issued before this field existed.
    org_id_str = payload.get("org") or (str(user.organization_id) if user.organization_id else None)
    set_scope(session, UUID(org_id_str) if org_id_str else None)

    # Stamp the is_platform_admin flag from the JWT onto the transient User
    # object so endpoint code can check it without a second DB hit. The model
    # column is the source of truth; the JWT merely caches it for the request.
    if payload.get("is_platform_admin"):
        user.is_platform_admin = True

    return user


async def load_effective_permissions(
    session: AsyncSession,
    user,
) -> frozenset[PermissionCode]:
    """Compute the user's effective permissions: role defaults ∪ explicit grants.

    Grants are tenancy-filtered automatically because `UserPermissionGrant`
    inherits `OrgScopedMixin` — Org A grants are invisible to Org B sessions.
    """
    rows = (
        await session.execute(
            select(UserPermissionGrant.permission_code).where(
                UserPermissionGrant.user_id == user.id
            )
        )
    ).scalars().all()
    return effective_permissions_for_user(user.role, rows)


def require_permissions(*codes: PermissionCode):
    """Require the caller to hold every code in `codes` (after alias expansion)."""
    async def dependency(
        current_user=Depends(get_current_user),
        session: AsyncSession = Depends(get_db_session),
    ):
        effective = await load_effective_permissions(session, current_user)
        missing = [c.value for c in codes if c not in effective]
        if missing:
            raise AuthorizationError(
                f"Missing permission(s): {', '.join(missing)}.",
                extra={"missing_permissions": missing},
            )
        return current_user

    return dependency


def require_platform_admin():
    """Require the caller to be a platform admin (FlexCRM operator).

    Platform admins bypass org tenancy entirely — their endpoints are protected
    by this dependency, NOT by org-level permissions.
    """
    async def dependency(current_user=Depends(get_current_user)):
        if not current_user.is_platform_admin:
            raise AuthorizationError("Platform admin access required.")
        return current_user

    return dependency


def require_any_permissions(*codes: PermissionCode):
    """Allow if the caller holds at least one of `codes`."""
    async def dependency(
        current_user=Depends(get_current_user),
        session: AsyncSession = Depends(get_db_session),
    ):
        effective = await load_effective_permissions(session, current_user)
        if not any(c in effective for c in codes):
            raise AuthorizationError(
                f"Missing any of permission(s): {', '.join(c.value for c in codes)}.",
                extra={"missing_permissions": [c.value for c in codes]},
            )
        return current_user

    return dependency


def pagination_params(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> PaginationParams:
    return PaginationParams(page=page, page_size=page_size)


def get_request_metadata(request: Request) -> tuple[str | None, str | None]:
    user_agent = request.headers.get("user-agent")
    ip_address = request.client.host if request.client else None
    return user_agent, ip_address
