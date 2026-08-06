"""Poll every connected org's Meta (Facebook/Instagram) Lead Ads and ingest new leads.

Runs frequently (every 5-15 min) via the Cloudflare Worker cron. For each org with an
active MetaConnection it pulls leadgen leads created after the stored per-form cursor
and creates them (idempotent). Mirrors the dispatch_followup_reminders org-loop:
list orgs under bypass(), then per org set_scope + set_tenant_schema, commit-per-org,
warn-and-continue on failure so one bad token can't break the rest.

Overlap note: overlapping runs are SAFE — the (source_provider, external_id) partial
unique index makes a re-poll a no-op — but wasteful. A true single-flight (Cloud Tasks
per org, or a job-lock table) is a deferred scale hardening: the per-record commit in
the ingest releases any transaction-scoped advisory lock, so a lock can't span a batch.

Trigger: python -m app.jobs.meta_lead_sync   (or POST /cron/meta-lead-sync)
"""
from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from app.core.logging import get_logger
from app.core.tenancy import bypass, set_scope, set_tenant_schema
from app.database.enums import UserRole, UserStatus
from app.database.session import db_manager
from app.models.meta_connection import MetaConnection
from app.models.organization import Organization
from app.models.user import User
from app.services.meta_sync import MetaSyncService
from app.services.notifications import NotificationService

logger = get_logger(__name__)

# Managers who get the "new leads arrived, assign them" nudge (RE + cross-vertical owner).
_MANAGER_ROLES = (UserRole.sales_manager, UserRole.owner)


async def dispatch_meta_lead_sync(session) -> dict[str, int]:
    """Poll + ingest across every org with an active connection. Shared by the CLI
    and the HTTP cron; does NOT own the engine lifecycle."""
    counts = {"orgs": 0, "connections": 0, "created": 0, "skipped": 0, "filtered": 0}

    with bypass(session):
        orgs = (
            await session.execute(
                select(Organization).where(
                    Organization.is_active.is_(True), Organization.is_deleted.is_(False)
                )
            )
        ).scalars().all()

    for org in orgs:
        # Which platforms this org is granted (per-tenant admin toggles). FB and IG
        # share one connection, so the poll filters ingestion by platform.
        features = org.features or {}
        allowed = {p for p in ("facebook", "instagram") if features.get(f"module.meta_{p}")}
        if not allowed:
            continue  # neither Facebook nor Instagram granted for this org
        set_scope(session, org.id)
        await set_tenant_schema(session, org.schema_name)
        try:
            connections = (
                await session.execute(
                    select(MetaConnection).where(
                        MetaConnection.is_active.is_(True),
                        MetaConnection.is_deleted.is_(False),
                        MetaConnection.status != "needs_reauth",
                    )
                )
            ).scalars().all()
            if not connections:
                continue
            counts["orgs"] += 1
            org_created = 0
            for conn in connections:
                counts["connections"] += 1
                stats = await MetaSyncService(session).sync_connection(
                    conn, organization_id=org.id, allowed_platforms=allowed
                )
                counts["created"] += stats["created"]
                counts["skipped"] += stats["skipped"]
                counts["filtered"] += stats["filtered"]
                org_created += stats["created"]
            if org_created:
                await _notify_managers(session, org.id, org_created)
                await session.commit()
        except Exception:
            await session.rollback()
            logger.warning("meta_lead_sync failed for org %s", org.id, exc_info=True)

    set_scope(session, None)
    return counts


async def _notify_managers(session, org_id, created: int) -> None:
    manager_ids = (
        await session.execute(
            select(User.id).where(
                User.organization_id == org_id,
                User.role.in_(_MANAGER_ROLES),
                User.status == UserStatus.active,
                User.is_deleted.is_(False),
            )
        )
    ).scalars().all()
    if not manager_ids:
        return
    notif = NotificationService(session)
    plural = "s" if created != 1 else ""
    for manager_id in manager_ids:
        await notif.create_notification(
            user_id=manager_id,
            message=f"{created} new Meta lead{plural} arrived and need assigning.",
        )


async def run() -> dict[str, int]:
    db_manager.configure()
    async with db_manager.session_factory() as session:
        counts = await dispatch_meta_lead_sync(session)
    await db_manager.dispose()
    return counts


def main() -> None:
    argparse.ArgumentParser(description="Poll Meta Lead Ads and ingest new leads.").parse_args()
    counts = asyncio.run(run())
    print(
        f"meta_lead_sync: orgs={counts['orgs']} connections={counts['connections']} "
        f"created={counts['created']} skipped={counts['skipped']} filtered={counts['filtered']}"
    )


if __name__ == "__main__":
    main()
