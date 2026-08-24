"""Entry point for the soft-delete archival job.

Run via:
    python -m app.jobs.archive
    python -m app.jobs.archive --retention-days 30

Or, inside Docker:
    docker compose exec backend python -m app.jobs.archive

Also exposed as `POST /api/v1/cron/archive` for the Cloudflare Worker scheduler.
The job is idempotent: running it more often than needed is safe but wasteful.

Every table it purges except `users` is per-tenant, so the work is a per-org loop
with the session routed by `set_tenant_schema` — `set_scope` alone does NOT route
queries (see app/core/tenancy.py). `users` is public and shared, so it is purged
once at the end with routing cleared.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.logging import configure_logging, get_logger
from app.core.tenancy import bypass, clear_tenant_schema, set_scope, set_tenant_schema
from app.database.session import db_manager
from app.models.organization import Organization
from app.models.user import User
from app.services.archival import ArchivalReport, ArchivalService, retention_cutoff


logger = get_logger(__name__)


async def dispatch_archival(session, retention_days: int | None = None) -> ArchivalReport:
    """Purge expired soft-deleted rows across every org using the provided session.

    Does NOT own the engine lifecycle (shared by the CLI and the HTTP cron).
    """
    cutoff = retention_cutoff(retention_days)
    if cutoff is None:
        logger.info("Archival skipped: retention_days <= 0")
        return ArchivalReport(cutoff=datetime.now(UTC))

    report = ArchivalReport(cutoff=cutoff)
    service = ArchivalService()

    with bypass(session):
        rows = (await session.execute(select(Organization))).scalars().all()
        # Snapshot to plain scalars while the rows are fresh: commit()/rollback()
        # EXPIRES every persistent object, so reading org.schema_name on a later
        # iteration would fire a lazy reload. Same guard as the Meta jobs.
        org_scopes = [(o.id, o.schema_name) for o in rows]

    for org_id, schema_name in org_scopes:
        if not schema_name:
            continue
        # BOTH are required: set_scope stores the org id, set_tenant_schema is
        # what actually points tenant-model queries at the org's real schema.
        set_scope(session, org_id)
        await set_tenant_schema(session, schema_name)
        report.orgs += 1
        try:
            deleted, blocked = await service.purge_tenant_scope(session, cutoff)
            await session.commit()
            for table, count in deleted.items():
                report.deleted[table] = report.deleted.get(table, 0) + count
            report.skipped_customers += blocked
        except Exception:
            await session.rollback()
            logger.warning("archival failed for org %s", org_id, exc_info=True)

    # `users` is PUBLIC and shared by every tenant — purge it exactly once, with
    # routing cleared so nothing resolves through whichever org came last.
    set_scope(session, None)
    clear_tenant_schema(session)
    try:
        report.deleted[User.__tablename__] = await service.purge_public_users(session, cutoff)
        await session.commit()
    except Exception:
        await session.rollback()
        logger.warning("archival: public user purge failed", exc_info=True)

    logger.info(
        "Archival completed",
        extra={
            "cutoff": cutoff.isoformat(),
            "orgs": report.orgs,
            "deleted": report.deleted,
            "skipped_customers": report.skipped_customers,
        },
    )
    return report


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Hard-delete expired soft-deleted rows.")
    parser.add_argument(
        "--retention-days",
        type=int,
        default=None,
        help="Override ARCHIVAL_RETENTION_DAYS for this run.",
    )
    return parser.parse_args(argv)


async def run(retention_days: int | None = None) -> ArchivalReport:
    db_manager.configure()
    try:
        async with db_manager.session_factory() as session:
            return await dispatch_archival(session, retention_days)
    finally:
        await db_manager.dispose()


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    args = _parse_args(argv)
    report = asyncio.run(run(args.retention_days))
    print(
        json.dumps(
            {
                "cutoff": report.cutoff.isoformat(),
                "orgs": report.orgs,
                "deleted": report.deleted,
                "skipped_customers": report.skipped_customers,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
