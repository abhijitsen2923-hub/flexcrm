"""Poll every enabled org's connected Google Sheet(s) and ingest new rows as leads.

Runs on the Cloudflare Worker cron. For each org with the `sheet_leads` module enabled and an active
`google_sheets` LeadSourceConnection, read the sheet and ingest its rows (idempotent on external_id).
Mirrors `dispatch_meta_lead_sync`: list orgs under bypass(), snapshot scalars, per org
set_scope + set_tenant_schema, warn-and-continue so one bad sheet can't break the rest.

Trigger: python -m app.jobs.google_sheet_sync   (or POST /cron/google-sheet-sync)
"""
from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from app.core.logging import get_logger
from app.core.tenancy import bypass, set_scope, set_tenant_schema
from app.database.session import db_manager
from app.models.lead_source_connection import LeadSourceConnection
from app.models.organization import Organization
from app.services.google_sheet_service import GoogleSheetService

logger = get_logger(__name__)


async def dispatch_google_sheet_sync(session) -> dict[str, int]:
    """Poll + ingest across every org that has the module on + an active sheet connection. Shared by
    the CLI and the HTTP cron; does NOT own the engine lifecycle."""
    counts = {"orgs": 0, "connections": 0, "rows": 0, "created": 0, "duplicate": 0, "ignored": 0}

    with bypass(session):
        orgs = (
            await session.execute(
                select(Organization).where(
                    Organization.is_active.is_(True), Organization.is_deleted.is_(False)
                )
            )
        ).scalars().all()
        # Snapshot scalars while fresh — a per-org rollback() below expires persistent objects.
        org_scopes = [(o.id, o.schema_name, o.features or {}) for o in orgs]

    for org_id, schema_name, features in org_scopes:
        if not features.get("module.sheet_leads"):
            continue  # module not enabled for this org
        set_scope(session, org_id)
        await set_tenant_schema(session, schema_name)
        try:
            conn_ids = (
                await session.execute(
                    select(LeadSourceConnection.id).where(
                        LeadSourceConnection.provider == "google_sheets",
                        LeadSourceConnection.is_active.is_(True),
                        LeadSourceConnection.is_deleted.is_(False),
                    )
                )
            ).scalars().all()
            if not conn_ids:
                continue
            counts["orgs"] += 1
            service = GoogleSheetService(session)
            for conn_id in conn_ids:
                # Re-fetch each connection fresh — a prior connection's per-row commit/rollback can
                # expire sibling ORM rows, so we load by id right before syncing.
                conn = (
                    await session.execute(
                        select(LeadSourceConnection).where(LeadSourceConnection.id == conn_id)
                    )
                ).scalar_one_or_none()
                if conn is None:
                    continue
                counts["connections"] += 1
                stats = await service.sync_connection(conn, organization_id=org_id)
                for k in ("rows", "created", "duplicate", "ignored"):
                    counts[k] += stats.get(k, 0)
        except Exception:
            await session.rollback()
            logger.warning("google_sheet_sync failed for org %s", org_id, exc_info=True)

    set_scope(session, None)
    return counts


async def run() -> dict[str, int]:
    db_manager.configure()
    async with db_manager.session_factory() as session:
        counts = await dispatch_google_sheet_sync(session)
    await db_manager.dispose()
    return counts


def main() -> None:
    argparse.ArgumentParser(description="Poll connected Google Sheets and ingest new leads.").parse_args()
    counts = asyncio.run(run())
    print(
        f"google_sheet_sync: orgs={counts['orgs']} connections={counts['connections']} "
        f"rows={counts['rows']} created={counts['created']} duplicate={counts['duplicate']} "
        f"ignored={counts['ignored']}"
    )


if __name__ == "__main__":
    main()
