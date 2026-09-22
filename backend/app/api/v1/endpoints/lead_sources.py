"""Tenant-facing inbound lead-source (99acres) connection management (ORG_MANAGE).

Self-service: the org admin mints a connection, receives a unique webhook URL (the token in its
path IS the credential — shown once), gives it to their 99acres account manager, and can list or
disconnect connections. The public inbound endpoint that actually receives leads lives in
webhooks.py.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permissions
from app.core.config import get_settings
from app.core.permissions import PermissionCode
from app.database.session import get_db_session
from app.schemas.lead_source import (
    GoogleSheetConnectRequest,
    GoogleSheetConnectResponse,
    GoogleSheetUpdateRequest,
    LeadSourceConnectionRead,
    LeadSourceConnectRequest,
    LeadSourceConnectResponse,
)
from app.services.google_sheet_service import GoogleSheetService
from app.services.lead_source_service import LeadSourceService

router = APIRouter()


def _webhook_url(request: Request, token: str) -> str:
    """Build the per-account inbound URL to hand to 99acres. Forces https (behind Cloud Run the
    request scheme can be http without --proxy-headers; the public endpoint is always https)."""
    prefix = get_settings().api_v1_prefix
    return f"https://{request.url.netloc}{prefix}/webhooks/99acres/{token}"


@router.post("/99acres/connect", response_model=LeadSourceConnectResponse, status_code=status.HTTP_201_CREATED)
async def connect_99acres(
    request: Request,
    payload: LeadSourceConnectRequest,
    current_user=Depends(require_permissions(PermissionCode.ORG_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    """Mint a 99acres connection and return its one-time URL + token. Store only the token hash."""
    conn, token = await LeadSourceService(session).create_connection(
        label=payload.label, actor_id=current_user.id
    )
    return LeadSourceConnectResponse(
        connection=LeadSourceConnectionRead.model_validate(conn),
        webhook_url=_webhook_url(request, token),
        token=token,
    )


@router.get("/99acres", response_model=list[LeadSourceConnectionRead])
async def list_99acres_connections(
    current_user=Depends(require_permissions(PermissionCode.ORG_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    return await LeadSourceService(session).list_connections()


@router.delete("/99acres/{connection_id}")
async def disconnect_99acres(
    connection_id: UUID,
    current_user=Depends(require_permissions(PermissionCode.ORG_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    await LeadSourceService(session).disconnect(connection_id, actor_id=current_user.id)
    return {"status": "disconnected"}


# --- Google Ads Lead Form (webhook push) ----------------------------------


def _google_ads_webhook_url(request: Request) -> str:
    """The FIXED Google Ads webhook URL (same for every tenant — the per-tenant secret is the Key,
    sent by Google in the body). Forces https (Cloud Run may present http without --proxy-headers)."""
    prefix = get_settings().api_v1_prefix
    return f"https://{request.url.netloc}{prefix}/webhooks/google-ads"


@router.post("/google-ads/connect", response_model=LeadSourceConnectResponse, status_code=status.HTTP_201_CREATED)
async def connect_google_ads(
    request: Request,
    payload: LeadSourceConnectRequest,
    current_user=Depends(require_permissions(PermissionCode.ORG_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    """Mint a Google Ads Lead Form connection. Returns the FIXED webhook URL + a one-time Key (`token`)
    the tenant pastes into Google Ads' SEPARATE URL + Key fields. Only the Key's hash is stored."""
    conn, token = await LeadSourceService(session).create_connection(
        provider="google_ads", label=payload.label, actor_id=current_user.id
    )
    return LeadSourceConnectResponse(
        connection=LeadSourceConnectionRead.model_validate(conn),
        webhook_url=_google_ads_webhook_url(request),
        token=token,
    )


@router.get("/google-ads", response_model=list[LeadSourceConnectionRead])
async def list_google_ads_connections(
    current_user=Depends(require_permissions(PermissionCode.ORG_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    return await LeadSourceService(session).list_connections(provider="google_ads")


@router.delete("/google-ads/{connection_id}")
async def disconnect_google_ads(
    connection_id: UUID,
    current_user=Depends(require_permissions(PermissionCode.ORG_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    await LeadSourceService(session).disconnect(connection_id, actor_id=current_user.id)
    return {"status": "disconnected"}


# --- Google Sheets (pull) lead source -------------------------------------

@router.get("/google-sheets/service-account")
async def google_sheet_service_account(
    current_user=Depends(require_permissions(PermissionCode.ORG_MANAGE)),
):
    """The platform service-account email the tenant must share their sheet (Viewer) with."""
    return {"email": get_settings().google_sa_email}


@router.post(
    "/google-sheets/connect",
    response_model=GoogleSheetConnectResponse,
    status_code=status.HTTP_201_CREATED,
)
async def connect_google_sheet(
    payload: GoogleSheetConnectRequest,
    current_user=Depends(require_permissions(PermissionCode.ORG_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    """Verify the service account can read the sheet (it must be shared with the SA email), then
    store the connection. The poll cron then ingests rows on a schedule."""
    conn = await GoogleSheetService(session).connect(
        sheet_id=payload.sheet_id,
        label=payload.label,
        source=payload.source,
        sheet_format=payload.sheet_format,
        actor_id=current_user.id,
    )
    return GoogleSheetConnectResponse(
        connection=LeadSourceConnectionRead.model_validate(conn),
        service_account_email=get_settings().google_sa_email,
    )


@router.patch("/google-sheets/{connection_id}", response_model=LeadSourceConnectionRead)
async def update_google_sheet(
    connection_id: UUID,
    payload: GoogleSheetUpdateRequest,
    current_user=Depends(require_permissions(PermissionCode.ORG_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    """Set/change an existing connection's lead source + sheet format in place (no reconnect)."""
    conn = await GoogleSheetService(session).update_connection(
        connection_id,
        source=payload.source,
        sheet_format=payload.sheet_format,
        actor_id=current_user.id,
    )
    return LeadSourceConnectionRead.model_validate(conn)


@router.get("/google-sheets", response_model=list[LeadSourceConnectionRead])
async def list_google_sheets(
    current_user=Depends(require_permissions(PermissionCode.ORG_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    return await GoogleSheetService(session).list_connections()


@router.delete("/google-sheets/{connection_id}")
async def disconnect_google_sheet(
    connection_id: UUID,
    current_user=Depends(require_permissions(PermissionCode.ORG_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    await GoogleSheetService(session).disconnect(connection_id, actor_id=current_user.id)
    return {"status": "disconnected"}
