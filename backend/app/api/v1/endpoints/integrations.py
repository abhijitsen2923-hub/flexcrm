"""Tenant-facing integration endpoints (ORG_MANAGE). Currently: Meta Lead Ads connect.

Self-service — the org admin manages their own Meta connection from their workspace.
The access token is only ever an input; it is never returned.
"""
import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permissions
from app.core import crypto
from app.core.cache import cache_client
from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.permissions import PermissionCode
from app.core.tenancy import current_org
from app.database.session import get_db_session
from app.schemas.meta import (
    MetaConnectionRead,
    MetaConnectionUpdate,
    MetaConnectRequest,
    MetaOAuthConnectRequest,
    MetaOAuthPage,
    MetaOAuthStartResponse,
    MetaValidateRequest,
    MetaValidateResult,
)
from app.services import meta_oauth
from app.services.meta_connection import MetaConnectionService

router = APIRouter()

_VAULT_UNCONFIGURED = "Integration encryption is not configured on the server."
_OAUTH_UNCONFIGURED = "Facebook one-click connect is not configured on the server."
# TTL for the server-side OAuth stash (user token + pages) between the callback and
# the page-picker connect step. Short — the round-trip should be seconds.
_OAUTH_STASH_TTL = 600
_OAUTH_STASH_PREFIX = "metaoauth:"


def _oauth_stash_key(handle: str) -> str:
    return f"{_OAUTH_STASH_PREFIX}{handle}"


def _frontend_integrations_url() -> str:
    """Where the callback bounces the browser back to (the tenant Integrations page).
    Uses the dedicated frontend origin (app_base_url) — NOT cors_origins[0], which is an
    unordered allowlist that may not have the frontend first."""
    return f"{get_settings().app_base_url.rstrip('/')}/integrations"


@router.post("/meta/validate", response_model=MetaValidateResult)
async def validate_meta_connection(
    payload: MetaValidateRequest,
    current_user=Depends(require_permissions(PermissionCode.ORG_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    """Test-connection probe (does not save) — classifies bad-token vs missing
    Lead-Access vs not-owned so the wizard can guide the admin."""
    return await MetaConnectionService(session).validate(payload.page_id, payload.token)


@router.get("/meta", response_model=list[MetaConnectionRead])
async def list_meta_connections(
    current_user=Depends(require_permissions(PermissionCode.ORG_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    return await MetaConnectionService(session).list_connections()


@router.post("/meta", response_model=MetaConnectionRead, status_code=status.HTTP_201_CREATED)
async def connect_meta(
    payload: MetaConnectRequest,
    current_user=Depends(require_permissions(PermissionCode.ORG_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    if not crypto.is_configured():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_VAULT_UNCONFIGURED)
    return await MetaConnectionService(session).connect(payload, actor_id=current_user.id)


@router.patch("/meta/{connection_id}", response_model=MetaConnectionRead)
async def update_meta_connection(
    connection_id: UUID,
    payload: MetaConnectionUpdate,
    current_user=Depends(require_permissions(PermissionCode.ORG_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    if payload.token is not None and not crypto.is_configured():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_VAULT_UNCONFIGURED)
    return await MetaConnectionService(session).update(connection_id, payload, actor_id=current_user.id)


@router.delete("/meta/{connection_id}")
async def disconnect_meta(
    connection_id: UUID,
    current_user=Depends(require_permissions(PermissionCode.ORG_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    await MetaConnectionService(session).disconnect(connection_id, actor_id=current_user.id)
    return {"status": "disconnected"}


# --- OAuth "Connect Facebook" (one-click) --------------------------------
# Coexists with the bring-your-own-token routes above. Needs FlexCRM's own Meta app
# (META_APP_* env) + Advanced Access (Meta App Review) to serve real customers; in
# Development mode it works for app-role users. Leads still arrive via the poll job.


@router.get("/meta/oauth/start", response_model=MetaOAuthStartResponse)
async def meta_oauth_start(
    current_user=Depends(require_permissions(PermissionCode.ORG_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    """Return the Facebook OAuth dialog URL for this org (the frontend redirects the
    browser to it). The org is bound into a signed `state` so the public callback is
    tamper-proof."""
    if not meta_oauth.is_oauth_configured():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_OAUTH_UNCONFIGURED)
    if not crypto.is_configured():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_VAULT_UNCONFIGURED)
    org_id = current_org(session)
    if org_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No organization in context.")
    return MetaOAuthStartResponse(
        authorize_url=meta_oauth.MetaOAuthService().build_authorize_url(org_id)
    )


@router.get("/meta/oauth/callback")
async def meta_oauth_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    session: AsyncSession = Depends(get_db_session),
):
    """PUBLIC — Meta redirects the browser here. Verify the signed state → org, exchange
    the code for a long-lived user token, list the user's Pages, stash it all server-side
    (encrypted, short TTL), then bounce back to the frontend Integrations page with a
    one-time handle for the page picker. The user's token NEVER reaches the browser."""
    frontend = _frontend_integrations_url()
    if error or not code or not state:
        return RedirectResponse(f"{frontend}?meta_oauth_error=denied")
    svc = meta_oauth.MetaOAuthService()
    # Everything that can fail — including the vault encryption of the tokens — is inside
    # the try, so ANY failure bounces the browser back with a clean error rather than a 500.
    try:
        org_id = svc.verify_state(state)
        user_token, expires_in = await svc.exchange_code_for_user_token(code)
        pages = await svc.list_pages(user_token)
        handle = secrets.token_urlsafe(24)
        stash = {
            "org_id": str(org_id),
            "user_token": crypto.encrypt_secret(user_token),
            "expires_in": expires_in,
            "pages": [
                {
                    "id": p["id"],
                    "name": p.get("name"),
                    "token": crypto.encrypt_secret(p["access_token"]),
                    "has_instagram": bool(p.get("instagram_business_account")),
                }
                for p in pages
                if p.get("access_token")
            ],
        }
        await cache_client.set_json(_oauth_stash_key(handle), stash, ttl_seconds=_OAUTH_STASH_TTL)
    except Exception:  # noqa: BLE001 — surface a clean error to the browser, never a 500
        return RedirectResponse(f"{frontend}?meta_oauth_error=exchange_failed")
    return RedirectResponse(f"{frontend}?meta_oauth={handle}")


@router.get("/meta/oauth/session/{handle}", response_model=list[MetaOAuthPage])
async def meta_oauth_session(
    handle: str,
    current_user=Depends(require_permissions(PermissionCode.ORG_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    """List the Pages captured during the OAuth round-trip so the admin can pick which
    to connect. Verifies the stash belongs to the caller's org. No tokens returned."""
    stash = await cache_client.get_json(_oauth_stash_key(handle))
    if not stash or stash.get("org_id") != str(current_org(session)):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This connect session has expired — please start again.",
        )
    return [
        MetaOAuthPage(id=p["id"], name=p.get("name"), has_instagram=p.get("has_instagram", False))
        for p in stash.get("pages", [])
    ]


@router.post("/meta/oauth/connect", response_model=list[MetaConnectionRead], status_code=status.HTTP_201_CREATED)
async def meta_oauth_connect(
    payload: MetaOAuthConnectRequest,
    current_user=Depends(require_permissions(PermissionCode.ORG_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    """Finalize: connect the chosen Page(s) from a completed OAuth round-trip. Re-checks
    the stash belongs to the caller's org, then stores a `MetaConnection(auth_type=oauth)`
    + the public page→tenant route for each selected Page."""
    if not crypto.is_configured():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_VAULT_UNCONFIGURED)
    stash = await cache_client.get_json(_oauth_stash_key(payload.handle))
    if not stash or stash.get("org_id") != str(current_org(session)):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This connect session has expired — please start again.",
        )
    svc = MetaConnectionService(session)
    connections: list[MetaConnectionRead] = []
    errors: list[str] = []
    try:
        # Inside the try so the finally always consumes the one-time handle, even if a
        # decrypt fails (e.g. key rotated between the callback and this step).
        user_token = crypto.decrypt_secret(stash["user_token"])
        pages_by_id = {p["id"]: p for p in stash.get("pages", [])}
        for page_id in payload.page_ids:
            page = pages_by_id.get(page_id)
            if page is None:
                continue  # ignore ids not in this session's Page set
            try:
                conn = await svc.create_oauth_connection(
                    page_id=page_id,
                    page_name=page.get("name"),
                    page_token=crypto.decrypt_secret(page["token"]),
                    user_token=user_token,
                    granted_scopes=None,
                    user_token_expires_in=stash.get("expires_in"),
                    actor_id=current_user.id,
                )
                # Materialize NOW, while the just-committed ORM object is still loaded — a
                # LATER page's rollback() would EXPIRE it, and serializing an expired
                # object would trigger an async lazy-load in sync context (MissingGreenlet).
                connections.append(MetaConnectionRead.model_validate(conn))
            except AppException as exc:
                # One bad Page (e.g. already owned by another workspace) must not abort
                # the others; roll back its partial state and keep going.
                await session.rollback()
                errors.append(getattr(exc, "detail", str(exc)))
    finally:
        # The one-time handle is always consumed, success or partial failure.
        await cache_client.delete(_oauth_stash_key(payload.handle))
    if not connections and errors:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="; ".join(errors))
    return connections
