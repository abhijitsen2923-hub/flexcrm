"""Nightly HR scorecard recompute (spec §5.3).

Iterates per Organization, then per active sales-flavoured user within each,
writing one PerformanceSnapshot row per (user, date). Idempotent.

Two things this job depends on, both of which it used to get wrong:

* `set_tenant_schema` — `set_scope` alone does NOT route queries (see
  app/core/tenancy.py), and PerformanceSnapshot / EmployeeProfile are per-tenant,
  so without it every write targeted the literal "tenant" schema.
* an org-filtered user list — `users` is PUBLIC and shared across tenants, so
  `list_active_sales_users` must be told which org it is scoring.

Trigger:
    python -m app.jobs.scorecard_compute
    POST /api/v1/cron/scorecard-compute   (X-Cron-Key)
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.logging import get_logger
from app.core.tenancy import bypass, clear_tenant_schema, set_scope, set_tenant_schema
from app.database.session import db_manager
from app.hr.services import ScorecardService, list_active_sales_users
from app.models.organization import Organization


logger = get_logger(__name__)


async def dispatch_scorecard_compute(session) -> dict[str, int]:
    """Compute today's scorecard snapshots across every org using the provided
    session. Does NOT own the engine lifecycle (shared by the CLI and HTTP cron)."""
    counts = {"orgs": 0, "users": 0, "snapshots_written": 0}
    today = datetime.now(UTC).date()

    with bypass(session):
        rows = (await session.execute(select(Organization))).scalars().all()
        # Snapshot while fresh — commit()/rollback() expires persistent objects.
        org_scopes = [(o.id, o.schema_name) for o in rows]

    for org_id, schema_name in org_scopes:
        if not schema_name:
            continue
        set_scope(session, org_id)
        await set_tenant_schema(session, schema_name)
        counts["orgs"] += 1
        try:
            users = await list_active_sales_users(session, org_id)
            service = ScorecardService(session)
            for user in users:
                await service.compute_user(user.id, snapshot_date=today)
                counts["snapshots_written"] += 1
            counts["users"] += len(users)
            await session.commit()
        except Exception:
            await session.rollback()
            logger.warning("scorecard_compute failed for org %s", org_id, exc_info=True)

    set_scope(session, None)
    clear_tenant_schema(session)
    return counts


async def run() -> dict[str, int]:
    db_manager.configure()
    try:
        async with db_manager.session_factory() as session:
            return await dispatch_scorecard_compute(session)
    finally:
        await db_manager.dispose()


def main() -> None:
    argparse.ArgumentParser(description="Compute today's HR scorecard snapshots per org.").parse_args()
    counts = asyncio.run(run())
    print(
        f"scorecard_compute: orgs={counts['orgs']} "
        f"users={counts['users']} snapshots={counts['snapshots_written']}"
    )


if __name__ == "__main__":
    main()
