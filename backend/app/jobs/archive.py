"""Entry point for the soft-delete archival job.

Run via:
    python -m app.jobs.archive
    python -m app.jobs.archive --retention-days 30

Or, inside Docker:
    docker compose exec backend python -m app.jobs.archive

Schedule it with cron / Kubernetes CronJob / a similar facility. The job is
idempotent: running it more often than needed is safe but wasteful.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from app.core.logging import configure_logging
from app.database.session import db_manager
from app.services.archival import archival_service


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Hard-delete expired soft-deleted rows.")
    parser.add_argument(
        "--retention-days",
        type=int,
        default=None,
        help="Override ARCHIVAL_RETENTION_DAYS for this run.",
    )
    return parser.parse_args(argv)


async def _run(retention_days: int | None) -> int:
    db_manager.configure()
    try:
        report = await archival_service.purge_expired(retention_days)
    finally:
        await db_manager.dispose()

    payload = {
        "cutoff": report.cutoff.isoformat(),
        "deleted": report.deleted,
        "skipped_customers": report.skipped_customers,
    }
    print(json.dumps(payload, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    args = _parse_args(argv)
    return asyncio.run(_run(args.retention_days))


if __name__ == "__main__":
    sys.exit(main())
