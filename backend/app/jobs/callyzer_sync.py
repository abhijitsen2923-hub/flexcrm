"""Poll every enabled org's Callyzer connection and ingest new call records.

Runs on the Cloudflare Worker cron (dedicated ~20-min cadence). For each org with the
`callyzer` module on and an active `CallyzerConnection`, fetch callHistory since the
watermark and upsert `ExternalCall` rows (idempotent on provider+external_id). Mirrors
`dispatch_google_sheet_sync`: list orgs under bypass(), snapshot scalars, per org
set_scope + set_tenant_schema, warn-and-continue so one bad tenant can't break the rest.

Trigger: python -m app.jobs.callyzer_sync   (or POST /cron/callyzer-sync)
"""
from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from app.core.logging import get_logger
from app.core.tenancy import bypass, set_scope, set_tenant_schema
from app.database.session import db_manager
from app.models.callyzer_connection import CallyzerConnection
from app.models.organization import Organization
from app.services.callyzer_connection import CallyzerConnectionService

logger = get_logger(__name__)


async def dispatch_callyzer_sync(session) -> dict[str, int]:
    counts = {"orgs": 0, "fetched": 0, "created": 0, "updated": 0}

    with bypass(session):
        orgs = (
            await session.execute(
                select(Organization).where(
                    Organization.is_active.is_(True), Organization.is_deleted.is_(False)
                )
            )
        ).scalars().all()
        org_scopes = [(o.id, o.schema_name, o.features or {}) for o in orgs]

    for org_id, schema_name, features in org_scopes:
        if not features.get("module.callyzer"):
            continue
        set_scope(session, org_id)
        await set_tenant_schema(session, schema_name)
        try:
            conn = (
                await session.execute(
                    select(CallyzerConnection).where(
                        CallyzerConnection.is_active.is_(True),
                        CallyzerConnection.is_deleted.is_(False),
                    )
                )
            ).scalars().first()
            if conn is None:
                continue
            counts["orgs"] += 1
            stats = await CallyzerConnectionService(session).sync_connection(
                conn, organization_id=org_id
            )
            for k in ("fetched", "created", "updated"):
                counts[k] += stats.get(k, 0)
        except Exception:
            await session.rollback()
            logger.warning("callyzer_sync failed for org %s", org_id, exc_info=True)

    set_scope(session, None)
    return counts


async def run() -> dict[str, int]:
    db_manager.configure()
    async with db_manager.session_factory() as session:
        counts = await dispatch_callyzer_sync(session)
    await db_manager.dispose()
    return counts


def main() -> None:
    argparse.ArgumentParser(description="Poll connected Callyzer accounts and ingest calls.").parse_args()
    counts = asyncio.run(run())
    print(
        f"callyzer_sync: orgs={counts['orgs']} fetched={counts['fetched']} "
        f"created={counts['created']} updated={counts['updated']}"
    )


if __name__ == "__main__":
    main()
