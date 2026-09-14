"""Callyzer integration endpoints.

Two routers:
- `router` (mounted at /integrations): tenant-facing connect / list / disconnect (ORG_MANAGE).
- `calls_router` (mounted at /calls): read synced call records (LEAD_VIEW) — the tenant-wide
  Calls page and the per-lead call list for the lead drawer.
Both operate in the caller's tenant schema.
"""
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import pagination_params, require_permissions
from app.core.permissions import PermissionCode
from app.database.session import get_db_session
from app.models.external_call import ExternalCall
from app.models.lead import Lead
from app.schemas.callyzer import (
    CallLeadMini,
    CallyzerConnectionRead,
    CallyzerConnectRequest,
    ExternalCallRead,
)
from app.schemas.common import PaginatedResponse, PaginationParams, build_page_meta
from app.services.callyzer_connection import CallyzerConnectionService, normalize_phone_key
from app.services.lead_documents import get_lead_or_404

router = APIRouter()
calls_router = APIRouter()


# --- Connection management (ORG_MANAGE) ------------------------------------

@router.post("/callyzer/connect", response_model=CallyzerConnectionRead, status_code=status.HTTP_201_CREATED)
async def connect_callyzer(
    payload: CallyzerConnectRequest,
    current_user=Depends(require_permissions(PermissionCode.ORG_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    conn = await CallyzerConnectionService(session).connect(payload, actor_id=current_user.id)
    return CallyzerConnectionRead.model_validate(conn)


@router.get("/callyzer", response_model=list[CallyzerConnectionRead])
async def list_callyzer(
    current_user=Depends(require_permissions(PermissionCode.ORG_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    return await CallyzerConnectionService(session).list_connections()


@router.delete("/callyzer/{connection_id}")
async def disconnect_callyzer(
    connection_id: UUID,
    current_user=Depends(require_permissions(PermissionCode.ORG_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    await CallyzerConnectionService(session).disconnect(connection_id, actor_id=current_user.id)
    return {"status": "disconnected"}


# --- Reading synced calls (LEAD_VIEW) --------------------------------------

def _lead_key(col):
    """Last-10 digits of a lead phone column, as SQL (matches ExternalCall.client_number_key)."""
    return func.right(func.regexp_replace(col, r"[^0-9]", "", "g"), 10)


@calls_router.get("", response_model=PaginatedResponse[ExternalCallRead])
async def list_calls(
    call_type: str | None = Query(default=None),
    q: str | None = Query(default=None, description="Search client number / name / employee"),
    matched: bool | None = Query(default=None, description="true=only matched to a lead, false=unmatched"),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    pagination: PaginationParams = Depends(pagination_params),
    current_user=Depends(require_permissions(PermissionCode.LEAD_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    """The tenant-wide Calls page: every synced call, newest first, with the matched lead."""
    stmt = select(ExternalCall)
    conds = []
    if call_type:
        conds.append(ExternalCall.call_type == call_type)
    if q:
        like = f"%{q.strip()}%"
        conds.append(
            or_(
                ExternalCall.client_number.ilike(like),
                ExternalCall.client_name.ilike(like),
                ExternalCall.emp_name.ilike(like),
                ExternalCall.emp_number.ilike(like),
            )
        )
    if date_from:
        conds.append(ExternalCall.call_at >= date_from)
    if date_to:
        conds.append(ExternalCall.call_at <= date_to)
    if matched is not None:
        match_exists = (
            select(1)
            .where(
                Lead.is_deleted.is_(False),
                ExternalCall.client_number_key.is_not(None),
                _lead_key(Lead.contact_phone) == ExternalCall.client_number_key,
            )
            .exists()
        )
        conds.append(match_exists if matched else ~match_exists)
    if conds:
        stmt = stmt.where(and_(*conds))

    total = (
        await session.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar_one()
    rows = (
        await session.execute(
            stmt.order_by(ExternalCall.call_at.desc().nullslast())
            .offset(pagination.offset())
            .limit(pagination.page_size)
        )
    ).scalars().all()

    # Resolve the most-recent matching lead for each distinct number on this page.
    keys = list({r.client_number_key for r in rows if r.client_number_key})
    lead_by_key: dict[str, CallLeadMini] = {}
    if keys:
        lead_rows = (
            await session.execute(
                select(
                    _lead_key(Lead.contact_phone).label("k"),
                    Lead.id,
                    Lead.lead_number,
                    Lead.contact_name,
                )
                .where(Lead.is_deleted.is_(False), _lead_key(Lead.contact_phone).in_(keys))
                .order_by(Lead.created_at.desc())
            )
        ).all()
        for k, lid, lnum, lname in lead_rows:
            lead_by_key.setdefault(k, CallLeadMini(id=lid, lead_number=lnum, contact_name=lname or ""))

    items: list[ExternalCallRead] = []
    for r in rows:
        read = ExternalCallRead.model_validate(r)
        if r.client_number_key:
            read.lead = lead_by_key.get(r.client_number_key)
        items.append(read)
    return PaginatedResponse[ExternalCallRead](items=items, pagination=build_page_meta(total, pagination))


@calls_router.get("/lead/{lead_id}", response_model=list[ExternalCallRead])
async def list_calls_for_lead(
    lead_id: UUID,
    current_user=Depends(require_permissions(PermissionCode.LEAD_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    """Synced calls whose number matches this lead's phone(s) — for the lead drawer."""
    lead = await get_lead_or_404(session, lead_id)
    keys = {
        normalize_phone_key(lead.contact_phone),
        normalize_phone_key(lead.contact_phone_alt),
    }
    keys.discard(None)
    if not keys:
        return []
    rows = (
        await session.execute(
            select(ExternalCall)
            .where(ExternalCall.client_number_key.in_(list(keys)))
            .order_by(ExternalCall.call_at.desc().nullslast())
            .limit(100)
        )
    ).scalars().all()
    return [ExternalCallRead.model_validate(r) for r in rows]
