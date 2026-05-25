"""Nightly customer health recompute (spec §4.1).

Iterates per Organization, scoping the session for each one so the global
tenancy filter stays satisfied and no row from one org leaks into another's
evaluation.

Trigger:
    python -m app.jobs.customer_health
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.tenancy import bypass, set_scope
from app.database.enums import CustomerLifecycleStage
from app.database.session import db_manager
from app.models.customer import Customer
from app.models.organization import Organization
from app.services.customer_lifecycle import evaluate_health, recompute_ltv


async def run() -> dict[str, int]:
    db_manager.configure()
    counts: dict[str, int] = {"orgs": 0, "evaluated": 0, "changed": 0}
    async with db_manager.session_factory() as session:
        with bypass(session):
            orgs = (await session.execute(select(Organization))).scalars().all()

        for org in orgs:
            set_scope(session, org.id)
            counts["orgs"] += 1
            rows = (
                await session.execute(
                    select(Customer).where(
                        Customer.is_deleted.is_(False),
                        Customer.lifecycle_stage != CustomerLifecycleStage.churned,
                    )
                )
            ).scalars().all()
            for customer in rows:
                previous = customer.lifecycle_stage
                await evaluate_health(session, customer, today=datetime.now(UTC).date())
                await recompute_ltv(session, customer)
                counts["evaluated"] += 1
                if customer.lifecycle_stage != previous:
                    counts["changed"] += 1
            await session.commit()
        set_scope(session, None)
    await db_manager.dispose()
    return counts


def main() -> None:
    argparse.ArgumentParser(description="Re-evaluate customer health for every org.").parse_args()
    counts = asyncio.run(run())
    print(
        f"customer_health: orgs={counts['orgs']} "
        f"evaluated={counts['evaluated']} changed={counts['changed']}"
    )


if __name__ == "__main__":
    main()
