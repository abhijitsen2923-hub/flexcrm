"""Nightly HR scorecard recompute (spec §5.3).

Iterates per Organization, then per active sales/manager/admin user within
each, writing one PerformanceSnapshot row per (user, date). Idempotent.

Trigger:
    python -m app.jobs.scorecard_compute
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.tenancy import bypass, set_scope
from app.database.session import db_manager
from app.hr.services import ScorecardService, list_active_sales_users
from app.models.organization import Organization


async def run() -> dict[str, int]:
    db_manager.configure()
    counts = {"orgs": 0, "users": 0, "snapshots_written": 0}
    today = datetime.now(UTC).date()
    async with db_manager.session_factory() as session:
        with bypass(session):
            orgs = (await session.execute(select(Organization))).scalars().all()

        for org in orgs:
            set_scope(session, org.id)
            counts["orgs"] += 1
            users = await list_active_sales_users(session)
            service = ScorecardService(session)
            for user in users:
                await service.compute_user(user.id, snapshot_date=today)
                counts["snapshots_written"] += 1
            counts["users"] += len(users)
            await session.commit()
        set_scope(session, None)
    await db_manager.dispose()
    return counts


def main() -> None:
    argparse.ArgumentParser(description="Compute today's HR scorecard snapshots per org.").parse_args()
    counts = asyncio.run(run())
    print(
        f"scorecard_compute: orgs={counts['orgs']} "
        f"users={counts['users']} snapshots={counts['snapshots_written']}"
    )


if __name__ == "__main__":
    main()
