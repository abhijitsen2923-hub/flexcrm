"""Nightly customer health recompute (spec §4.1).

Iterates per Organization, routing the session into each org's schema so the
per-tenant Customer rows are actually reachable.

`set_scope` alone does NOT route queries — it only records the org id on
session.info (see app/core/tenancy.py). `set_tenant_schema` is what installs the
schema_translate_map. This job used to call only the former, so every query
targeted the literal "tenant" schema and the job could never have run.

Trigger:
    python -m app.jobs.customer_health
    POST /api/v1/cron/customer-health   (X-Cron-Key)
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.logging import get_logger
from app.core.tenancy import bypass, clear_tenant_schema, set_scope, set_tenant_schema
from app.database.enums import CustomerLifecycleStage
from app.database.session import db_manager
from app.models.customer import Customer
from app.models.organization import Organization
from app.services.customer_lifecycle import evaluate_health, recompute_ltv


logger = get_logger(__name__)


async def dispatch_customer_health(session) -> dict[str, int]:
    """Re-evaluate customer health across every org using the provided session.
    Does NOT own the engine lifecycle (shared by the CLI and the HTTP cron)."""
    counts: dict[str, int] = {"orgs": 0, "evaluated": 0, "changed": 0}

    with bypass(session):
        rows = (await session.execute(select(Organization))).scalars().all()
        # Snapshot while the rows are fresh — commit()/rollback() expires every
        # persistent object, so a later org.schema_name read would lazy-load.
        org_scopes = [(o.id, o.schema_name) for o in rows]

    for org_id, schema_name in org_scopes:
        if not schema_name:
            continue
        set_scope(session, org_id)
        await set_tenant_schema(session, schema_name)
        counts["orgs"] += 1
        try:
            customers = (
                await session.execute(
                    select(Customer).where(
                        Customer.is_deleted.is_(False),
                        Customer.lifecycle_stage != CustomerLifecycleStage.churned,
                    )
                )
            ).scalars().all()
            for customer in customers:
                previous = customer.lifecycle_stage
                await evaluate_health(session, customer, today=datetime.now(UTC).date())
                await recompute_ltv(session, customer)
                counts["evaluated"] += 1
                if customer.lifecycle_stage != previous:
                    counts["changed"] += 1
            await session.commit()
        except Exception:
            await session.rollback()
            logger.warning("customer_health failed for org %s", org_id, exc_info=True)

    set_scope(session, None)
    clear_tenant_schema(session)
    return counts


async def run() -> dict[str, int]:
    db_manager.configure()
    try:
        async with db_manager.session_factory() as session:
            return await dispatch_customer_health(session)
    finally:
        await db_manager.dispose()


def main() -> None:
    argparse.ArgumentParser(description="Re-evaluate customer health for every org.").parse_args()
    counts = asyncio.run(run())
    print(
        f"customer_health: orgs={counts['orgs']} "
        f"evaluated={counts['evaluated']} changed={counts['changed']}"
    )


if __name__ == "__main__":
    main()
