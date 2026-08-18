"""Refresh OAuth Meta connection tokens before they expire (cross-org).

The "Connect Facebook" flow mints a long-lived (~60-day) user token; the Page token we
poll/webhook with is derived from it. This job re-extends tokens that are within a week of
expiry (or whose expiry is unknown) so a connection never silently goes dark, and flips any
connection whose user has revoked access to `needs_reauth` so the admin is prompted to
reconnect. Bring-your-own-token connections are skipped (their tokens aren't ours to renew).

Mirrors the meta_lead_sync org-loop: list orgs under bypass(), then per org set_scope +
set_tenant_schema; the per-connection refresh commits itself, and one bad org can't break the
rest. Idempotent + cheap — safe to run daily (or more often).

Trigger: python -m app.jobs.meta_token_refresh   (or POST /cron/meta-token-refresh)
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select

from app.core.logging import get_logger
from app.core.tenancy import bypass, set_scope, set_tenant_schema
from app.database.session import db_manager
from app.models.meta_connection import MetaConnection
from app.models.organization import Organization
from app.services.meta_connection import MetaConnectionService

logger = get_logger(__name__)

# Refresh when a token is within this many days of expiry (or its expiry is unknown).
_REFRESH_WINDOW_DAYS = 7
_REAUTH_RESULTS = {"needs_reauth", "page_lost", "decrypt_failed"}


async def dispatch_meta_token_refresh(session) -> dict[str, int]:
    """Refresh soon-to-expire OAuth tokens across every org. Shared by the CLI and the HTTP
    cron; does NOT own the engine lifecycle."""
    counts = {"orgs": 0, "checked": 0, "refreshed": 0, "needs_reauth": 0, "transient": 0}
    cutoff = datetime.now(UTC) + timedelta(days=_REFRESH_WINDOW_DAYS)

    with bypass(session):
        orgs = (
            await session.execute(
                select(Organization).where(
                    Organization.is_active.is_(True), Organization.is_deleted.is_(False)
                )
            )
        ).scalars().all()
        # Snapshot the scalars WHILE the ORM rows are fresh: an org-level rollback() below
        # EXPIRES every persistent object, so touching org.id/schema_name on a later iteration
        # would trigger an async lazy-load in sync context (MissingGreenlet) and abort the run.
        org_scopes = [(o.id, o.schema_name) for o in orgs]

    for org_id, schema_name in org_scopes:
        set_scope(session, org_id)
        await set_tenant_schema(session, schema_name)
        try:
            conns = (
                await session.execute(
                    select(MetaConnection).where(
                        MetaConnection.auth_type == "oauth",
                        MetaConnection.is_active.is_(True),
                        MetaConnection.is_deleted.is_(False),
                        or_(
                            MetaConnection.token_expires_at.is_(None),
                            MetaConnection.token_expires_at <= cutoff,
                        ),
                    )
                )
            ).scalars().all()
            if not conns:
                continue
            counts["orgs"] += 1
            svc = MetaConnectionService(session)
            for conn in conns:
                counts["checked"] += 1
                result = await svc.refresh_oauth_connection(conn)
                if result == "refreshed":
                    counts["refreshed"] += 1
                elif result in _REAUTH_RESULTS:
                    counts["needs_reauth"] += 1
                elif result == "transient_error":
                    counts["transient"] += 1
        except Exception:
            await session.rollback()
            logger.warning("meta_token_refresh failed for org %s", org_id, exc_info=True)

    set_scope(session, None)
    return counts


async def run() -> dict[str, int]:
    db_manager.configure()
    async with db_manager.session_factory() as session:
        counts = await dispatch_meta_token_refresh(session)
    await db_manager.dispose()
    return counts


def main() -> None:
    argparse.ArgumentParser(description="Refresh Meta OAuth tokens nearing expiry.").parse_args()
    counts = asyncio.run(run())
    print(
        f"meta_token_refresh: orgs={counts['orgs']} checked={counts['checked']} "
        f"refreshed={counts['refreshed']} needs_reauth={counts['needs_reauth']} "
        f"transient={counts['transient']}"
    )


if __name__ == "__main__":
    main()
