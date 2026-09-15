"""Callyzer integration endpoints.

Two routers:
- `router` (mounted at /integrations): tenant-facing connect / list / disconnect (ORG_MANAGE).
- `calls_router` (mounted at /calls): read synced call records (LEAD_VIEW) — the tenant-wide
  Calls page and the per-lead call list for the lead drawer.
Both operate in the caller's tenant schema.
"""
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import pagination_params, require_permissions
from app.core.permissions import ASSIGNED_ONLY_LEAD_ROLES, PermissionCode
from app.core.tenancy import current_org
from app.database.session import get_db_session
from app.models.external_call import ExternalCall
from app.models.lead import Lead
from app.models.user import User
from app.schemas.callyzer import (
    CallAgentAssignRequest,
    CallAgentMappingRead,
    CallLeadMini,
    CallStatsResponse,
    CallTrendResponse,
    CallyzerConnectionRead,
    CallyzerConnectRequest,
    ExternalCallRead,
)
from app.schemas.common import PaginatedResponse, PaginationParams, build_page_meta
from app.services.callyzer_connection import CallyzerConnectionService, normalize_phone_key
from app.services.external_call_stats import ExternalCallStatsService
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


@calls_router.get("/stats", response_model=CallStatsResponse)
async def call_stats(
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    current_user=Depends(require_permissions(PermissionCode.LEAD_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    """Per-employee call performance over a date range (default: the current calendar
    month). Reps (ASSIGNED_ONLY_LEAD_ROLES) see only their own row; managers/owner see
    the whole team — the same scoping the dashboard uses."""
    now = datetime.now(UTC)
    date_to = date_to or now
    date_from = date_from or datetime(now.year, now.month, 1, tzinfo=UTC)
    owner_user_id = current_user.id if current_user.role in ASSIGNED_ONLY_LEAD_ROLES else None
    return await ExternalCallStatsService(session).employee_stats(
        date_from=date_from, date_to=date_to, owner_user_id=owner_user_id
    )


@calls_router.get("/stats/trend", response_model=CallTrendResponse)
async def call_stats_trend(
    user_id: UUID = Query(...),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    current_user=Depends(require_permissions(PermissionCode.LEAD_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    """Per-day call counts for one employee (the Performance drill-down). Reps may only
    view their own trend; managers/owner may view any user's."""
    now = datetime.now(UTC)
    date_to = date_to or now
    date_from = date_from or datetime(now.year, now.month, 1, tzinfo=UTC)
    if current_user.role in ASSIGNED_ONLY_LEAD_ROLES:
        user_id = current_user.id
    return await ExternalCallStatsService(session).daily_trend(
        user_id=user_id, date_from=date_from, date_to=date_to
    )


# --- Caller → user mapping (fix unmatched attribution; USER_VIEW = managers) ---

@calls_router.get("/agents", response_model=list[CallAgentMappingRead])
async def list_call_agents(
    current_user=Depends(require_permissions(PermissionCode.USER_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    rows = await CallyzerConnectionService(session).list_agent_mappings()
    ids = [m.user_id for m in rows]
    names: dict[UUID, str] = {}
    if ids:
        org_id = current_org(session)
        urows = (
            await session.execute(
                select(User.id, User.first_name, User.last_name).where(
                    User.organization_id == org_id, User.id.in_(ids)
                )
            )
        ).all()
        names = {uid: f"{(fn or '').strip()} {(ln or '').strip()}".strip() for uid, fn, ln in urows}
    out: list[CallAgentMappingRead] = []
    for m in rows:
        read = CallAgentMappingRead.model_validate(m)
        read.user_name = names.get(m.user_id)
        out.append(read)
    return out


@calls_router.post("/agents", response_model=CallAgentMappingRead, status_code=status.HTTP_201_CREATED)
async def assign_call_agent(
    payload: CallAgentAssignRequest,
    current_user=Depends(require_permissions(PermissionCode.USER_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    """Pin a device number to a FlexCRM user; re-attributes that number's past calls too."""
    mapping = await CallyzerConnectionService(session).assign_agent(
        emp_number=payload.emp_number,
        emp_name=payload.emp_name,
        user_id=payload.user_id,
        actor_id=current_user.id,
    )
    return CallAgentMappingRead.model_validate(mapping)


@calls_router.delete("/agents/{emp_key}")
async def clear_call_agent(
    emp_key: str,
    current_user=Depends(require_permissions(PermissionCode.USER_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    await CallyzerConnectionService(session).clear_agent(emp_key)
    return {"status": "cleared"}


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
