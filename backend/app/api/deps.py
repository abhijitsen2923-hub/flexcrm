from uuid import UUID

from fastapi import Depends, Query, Request
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache_client
from app.core.config import get_settings
from app.core.exceptions import AuthenticationError, AuthorizationError
from app.core.permissions import (
    PermissionCode,
    effective_permissions_for_user,
)
from app.core.security import bearer_scheme, decode_token, get_bearer_token
from app.core.tenancy import bypass, set_scope, set_tenant_schema
from app.database.enums import UserStatus
from app.database.session import get_db_session
from app.models.organization import Organization
from app.models.user_permission_grant import UserPermissionGrant
from app.repositories.users import UserRepository
from app.schemas.common import PaginationParams


async def _resolve_schema_for_org(session: AsyncSession, org_id: UUID) -> str | None:
    """Return the tenant schema_name for org_id, using Redis cache."""
    cache_key = f"schema:{org_id}"
    cached = await cache_client.get_json(cache_key)
    if cached:
        return cached

    result = await session.execute(
        select(Organization.schema_name).where(Organization.id == org_id)
    )
    schema_name: str | None = result.scalar_one_or_none()
    if schema_name:
        settings = get_settings()
        await cache_client.set_json(cache_key, schema_name, ttl_seconds=settings.cache_ttl_seconds)
    return schema_name


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_db_session),
):
    token = get_bearer_token(credentials)
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise AuthenticationError("Invalid access token.")

    # The user lookup must bypass tenant routing — at this point the session
    # has no schema context yet. SharedBase tables (users) are always in public.
    with bypass(session):
        user = await UserRepository(session).get(UUID(payload["sub"]))
    if user is None or user.status != UserStatus.active:
        raise AuthenticationError("The user account is not active.")

    # Stamp is_platform_admin from JWT (avoids a second DB hit per request).
    if payload.get("is_platform_admin"):
        user.is_platform_admin = True

    if user.is_platform_admin:
        # Platform admins query public tables only; no tenant schema routing needed.
        return user

    # Resolve org_id and activate tenant schema routing for this request.
    org_id_str = payload.get("org") or (str(user.organization_id) if user.organization_id else None)
    org_id = UUID(org_id_str) if org_id_str else None
    set_scope(session, org_id)

    if org_id:
        schema_name = await _resolve_schema_for_org(session, org_id)
        if schema_name:
            await set_tenant_schema(session, schema_name)

    return user


async def load_effective_permissions(
    session: AsyncSession,
    user,
) -> frozenset[PermissionCode]:
    """Compute the user's effective permissions: role defaults ∪ explicit grants.

    Grants are in the tenant schema and are automatically scoped by the
    schema_translate_map set in get_current_user.
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
