"""Follow-up reminders (all verticals, but keyed on the real-estate workflow).

For every active, assigned lead whose LATEST stage transition carries a
`next_action_date` that is due (today or overdue), email + in-app-notify the
assigned executive so follow-ups don't slip (FR-4 / anti-leakage). Meant to run
**daily** — a due follow-up is re-sent each day until the owner acts on it
(logs a new transition with a future next action, or moves the lead on).

Trigger:
    python -m app.jobs.followup_reminders
"""
from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict
from datetime import UTC, datetime, time, timedelta

from sqlalchemy import select

from app.core.logging import get_logger
from app.core.tenancy import bypass, set_scope, set_tenant_schema
from app.database.enums import UserStatus
from app.database.session import db_manager
from app.models.lead import Lead
from app.models.organization import Organization
from app.models.user import User
from app.services.email import EmailService
from app.services.notifications import NotificationService

logger = get_logger(__name__)

# Closed stages — a follow-up on a won/dead lead is moot.
CLOSED_STAGE_CODES = ("sold", "lost")


async def dispatch_followup_reminders(session) -> dict[str, int]:
    """Send due-follow-up digests across every org using the provided session.
    Does NOT own the engine lifecycle (shared by the CLI and the HTTP cron)."""
    counts: dict[str, int] = {"orgs": 0, "reminders": 0, "recipients": 0}
    now = datetime.now(UTC)
    # Everything due up to end-of-today (any time today) or overdue.
    horizon = datetime.combine(now.date() + timedelta(days=1), time.min, tzinfo=UTC)

    with bypass(session):
        orgs = (await session.execute(select(Organization))).scalars().all()

    for org in orgs:
        # set_scope alone does NOT route queries — set_tenant_schema is what
        # points tenant-model queries at the org's real schema.
        set_scope(session, org.id)
        await set_tenant_schema(session, org.schema_name)
        counts["orgs"] += 1
        try:
            # A lead's current follow-up is its denormalized next_action_date —
            # set by the latest stage transition OR a DNP scheduling a callback.
            rows = (
                await session.execute(
                    select(Lead).where(
                        Lead.is_deleted.is_(False),
                        Lead.assigned_to_id.is_not(None),
                        Lead.stage_code.notin_(CLOSED_STAGE_CODES),
                        Lead.next_action_date.is_not(None),
                        Lead.next_action_date < horizon,
                    )
                )
            ).scalars().all()

            by_owner: dict = defaultdict(list)
            for lead in rows:
                by_owner[lead.assigned_to_id].append(lead)

            notif = NotificationService(session)
            emailer = EmailService()
            for owner_id, leads in by_owner.items():
                owner = await session.get(User, owner_id)
                # Skip deactivated / soft-deleted owners.
                if owner is None or owner.status != UserStatus.active or owner.is_deleted:
                    continue
                counts["reminders"] += len(leads)
                counts["recipients"] += 1
                await notif.create_notification(
                    user_id=owner_id,
                    message=f"You have {len(leads)} follow-up(s) due. Log the call and set the next action.",
                )
                if owner.email:
                    digest = [
                        {
                            "lead": lead.lead_number,
                            "name": lead.contact_name,
                            "due": lead.next_action_date.strftime("%d %b %Y, %H:%M"),
                            "note": (lead.last_comment_preview or "")[:120],
                        }
                        for lead in leads
                    ]
                    await emailer.send_followup_digest(
                        owner.email, rep_name=owner.first_name or "there", items=digest
                    )
            await session.commit()
        except Exception:
            await session.rollback()
            logger.warning("followup reminders failed for org %s", org.id, exc_info=True)

    set_scope(session, None)
    return counts


async def run() -> dict[str, int]:
    db_manager.configure()
    async with db_manager.session_factory() as session:
        counts = await dispatch_followup_reminders(session)
    await db_manager.dispose()
    return counts


def main() -> None:
    argparse.ArgumentParser(description="Send due-follow-up reminders.").parse_args()
    counts = asyncio.run(run())
    print(
        f"followup_reminders: orgs={counts['orgs']} "
        f"recipients={counts['recipients']} reminders={counts['reminders']}"
    )


if __name__ == "__main__":
    main()
