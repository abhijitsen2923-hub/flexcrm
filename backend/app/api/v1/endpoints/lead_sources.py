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
        sheet_id=payload.sheet_id, label=payload.label, actor_id=current_user.id
    )
    return GoogleSheetConnectResponse(
        connection=LeadSourceConnectionRead.model_validate(conn),
        service_account_email=get_settings().google_sa_email,
    )


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
