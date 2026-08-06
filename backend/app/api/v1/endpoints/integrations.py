"""Tenant-facing integration endpoints (ORG_MANAGE). Currently: Meta Lead Ads connect.

Self-service — the org admin manages their own Meta connection from their workspace.
The access token is only ever an input; it is never returned.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permissions
from app.core import crypto
from app.core.permissions import PermissionCode
from app.database.session import get_db_session
from app.schemas.meta import (
    MetaConnectionRead,
    MetaConnectionUpdate,
    MetaConnectRequest,
    MetaValidateRequest,
    MetaValidateResult,
)
from app.services.meta_connection import MetaConnectionService

router = APIRouter()

_VAULT_UNCONFIGURED = "Integration encryption is not configured on the server."


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
