"""Drain unprocessed / failed inbound lead-source (99acres) deliveries — cross-org.

The 99acres webhook is persist-then-ACK: it stores the raw delivery, returns 200, then maps +
ingests in a BackgroundTask. If that background step never ran (server restarted right after the
ACK) or failed (transient DB/mapping error, a deploy blip), the delivery is left `received`/`failed`
in `lead_source_deliveries`. Because the source is PUSH-only there is no re-fetch — this cron is the
backstop that replays those deliveries, so a paid-for lead is never silently lost.

Idempotent: `process_delivery` dedupes on `external_id` (the same lead is never created twice) and
no-ops an already-processed row, so re-running is always safe. Mirrors the meta_lead_sync org-loop:
list orgs under bypass(), then per org set_scope + set_tenant_schema; per-delivery commits happen
inside the service; one bad org can't break the rest.

Trigger: python -m app.jobs.lead_source_reconcile   (or POST /cron/lead-source-reconcile)
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.logging import get_logger
from app.core.tenancy import bypass, set_scope, set_tenant_schema
from app.database.session import db_manager
from app.models.lead_source_delivery import LeadSourceDelivery
from app.models.organization import Organization
from app.services.lead_source_service import LeadSourceService

logger = get_logger(__name__)

# Statuses worth retrying. "received" = the inline background task never finished; "failed" = it
# errored. "processed"/"ignored" are terminal.
_RETRY_STATUSES = ("received", "failed")
# Don't touch a delivery whose inline background task may still be running — give it a grace window.
_GRACE_MINUTES = 5
# Cap per org per run so one huge backlog can't monopolise a run.
_MAX_PER_ORG = 500


async def dispatch_lead_source_reconcile(session) -> dict[str, int]:
    """Reprocess stuck/failed deliveries across every org. Shared by the CLI and the HTTP cron;
    does NOT own the engine lifecycle."""
    counts = {"orgs": 0, "processed": 0, "created": 0, "failed": 0, "skipped": 0}
    cutoff = datetime.now(UTC) - timedelta(minutes=_GRACE_MINUTES)

    with bypass(session):
        orgs = (
            await session.execute(
                select(Organization).where(
                    Organization.is_active.is_(True), Organization.is_deleted.is_(False)
                )
            )
        ).scalars().all()
        # Snapshot scalars while fresh — an org-level rollback() below expires ORM rows, and touching
        # org.id/schema_name on a later iteration would MissingGreenlet (same fix as the other jobs).
        org_scopes = [(o.id, o.schema_name) for o in orgs]

    for org_id, schema_name in org_scopes:
        set_scope(session, org_id)
        await set_tenant_schema(session, schema_name)
        try:
            ids = (
                await session.execute(
                    select(LeadSourceDelivery.id)
                    .where(
                        LeadSourceDelivery.status.in_(_RETRY_STATUSES),
                        LeadSourceDelivery.received_at < cutoff,
                    )
                    .order_by(LeadSourceDelivery.received_at.asc())
                    .limit(_MAX_PER_ORG)
                )
            ).scalars().all()
            if not ids:
                continue
            counts["orgs"] += 1
            svc = LeadSourceService(session)
            for delivery_id in ids:
                result = await svc.process_delivery(delivery_id, organization_id=org_id)
                if result == "created":
                    counts["created"] += 1
                    counts["processed"] += 1
                elif result == "duplicate":
                    counts["processed"] += 1
                elif result == "failed":
                    counts["failed"] += 1
                else:  # ignored | already | missing
                    counts["skipped"] += 1
        except Exception:
            await session.rollback()
            logger.warning("lead_source_reconcile failed for org %s", org_id, exc_info=True)

    set_scope(session, None)
    return counts


async def run() -> dict[str, int]:
    db_manager.configure()
    async with db_manager.session_factory() as session:
        counts = await dispatch_lead_source_reconcile(session)
    await db_manager.dispose()
    return counts


def main() -> None:
    argparse.ArgumentParser(description="Reprocess stuck/failed 99acres lead deliveries.").parse_args()
    counts = asyncio.run(run())
    print(
        f"lead_source_reconcile: orgs={counts['orgs']} processed={counts['processed']} "
        f"created={counts['created']} failed={counts['failed']} skipped={counts['skipped']}"
    )


if __name__ == "__main__":
    main()
