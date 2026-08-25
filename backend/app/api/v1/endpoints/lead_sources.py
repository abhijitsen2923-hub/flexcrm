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
    LeadSourceConnectionRead,
    LeadSourceConnectRequest,
    LeadSourceConnectResponse,
)
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
