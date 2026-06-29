"""Multi-tenant schema routing primitives.

Schema-per-tenant model: each onboarded business gets its own PostgreSQL schema
(e.g. travel_make_my_trip). Every domain model that moves per-tenant declares
{"schema": "tenant"} in its __table_args__. At request time, SQLAlchemy's
schema_translate_map execution option rewrites "tenant" → actual schema name
on the connection, routing all queries transparently.

Shared tables (organizations, users, refresh_tokens, pipeline_stages) live in
public and are never translated — they're always accessible regardless of
whether a tenant schema is active.

Public API
----------
set_tenant_schema(session, schema_name)   — async; sets schema routing
get_schema(session)                       — returns active schema name or None
bypass(session)                           — context manager; disables bypass flag
set_scope(session, org_id)               — compat stub; stores org_id in session.info
current_org(session)                      — returns org_id from session.info
is_bypassed(session)                      — returns bypass flag
register_listeners()                      — no-op; retained for import compat
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


async def set_tenant_schema(session: AsyncSession, schema_name: str) -> None:
    """Route all per-tenant model queries to schema_name for this request.

    Uses schema_translate_map on the session's underlying connection so that
    every query against a model with {"schema": "tenant"} in __table_args__ is
    rewritten to use schema_name instead of the literal "tenant". This is
    pooling-safe — the option is scoped to the connection, not the process.

    The map is applied to the live connection IN PLACE via run_sync. Passing
    execution_options to session.connection() only takes effect when the
    connection is first procured in the transaction; if a connection was already
    established earlier in the request (e.g. the user lookup in get_current_user),
    that form silently no-ops and tenant queries hit the untranslated literal
    "tenant" schema (UndefinedTableError). Setting it on the existing Connection
    in place avoids that.
    """
    conn = await session.connection()
    await conn.run_sync(
        lambda sync_conn: sync_conn.execution_options(
            schema_translate_map={"tenant": schema_name}
        )
    )
    session.info["schema_name"] = schema_name


def get_schema(session: AsyncSession) -> str | None:
    """Return the active tenant schema name for this session, or None."""
    return session.info.get("schema_name")


def set_scope(session: AsyncSession, organization_id: UUID | None) -> None:
    """Store the current org ID on session.info.

    Compatibility stub retained so auth-service code (login/register/refresh)
    does not need to change. In the schema-per-tenant model, isolation is
    provided by set_tenant_schema(); this function no longer drives SELECT
    filtering.
    """
    if organization_id is None:
        session.info.pop("organization_id", None)
    else:
        session.info["organization_id"] = organization_id


def current_org(session: AsyncSession) -> UUID | None:
    """Return the org UUID stored on session.info, if any."""
    return session.info.get("organization_id")


def is_bypassed(session: AsyncSession) -> bool:
    """True when the bypass flag has been set for this session block."""
    return bool(session.info.get("bypass_tenancy"))


@contextmanager
def bypass(session: AsyncSession) -> Iterator[None]:
    """Mark this block as bypassing tenant-filter logic.

    With schema_translate_map, SharedBase tables (users, organizations,
    refresh_tokens, pipeline_stages) are always accessible in public
    regardless of whether a tenant schema is active — no SQL change is
    needed. This context manager is retained for the auth flow that needs
    cross-org user lookups, and for any code that checks is_bypassed().
    """
    previous = session.info.get("bypass_tenancy", False)
    session.info["bypass_tenancy"] = True
    try:
        yield
    finally:
        session.info["bypass_tenancy"] = previous


def register_listeners() -> None:
    """No-op. Retained for import compatibility with main.py.

    Tenant isolation is now via schema_translate_map (set by set_tenant_schema)
    rather than ORM event listeners. The listeners were removed when
    OrgScopedMixin and the associated row-level filter were deleted.
    """
