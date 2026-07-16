"""Registration reminders (real-estate).

Notifies the deal owner when a confirmed booking's registration date is imminent
and the unit is still Booked (not yet Registered). Meant to run **daily** — it
reminds for anything registering within the next few days, so a booking gets a
heads-up each day in the window until it's registered.

Trigger:
    python -m app.jobs.registration_reminders
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.tenancy import bypass, set_scope
from app.database.enums import BookingStatus, UnitStatus
from app.database.session import db_manager
from app.models.customer import Customer
from app.models.lead import Lead
from app.models.organization import Organization
from app.models.user import User
from app.real_estate.models import Booking, Unit
from app.services.email import EmailService
from app.services.notifications import NotificationService


REMIND_WITHIN_DAYS = 3


async def _owner_id(session, booking):
    if booking.customer_id:
        cust = await session.get(Customer, booking.customer_id)
        if cust and cust.current_owner_id:
            return cust.current_owner_id
    if booking.lead_id:
        lead = await session.get(Lead, booking.lead_id)
        if lead and lead.assigned_to_id:
            return lead.assigned_to_id
    return booking.created_by_id


async def dispatch_registration_reminders(session) -> dict[str, int]:
    """Send reminders for imminent registrations across every org, using the
    provided session. Does NOT configure/dispose the engine — so both the CLI
    (`run`) and the HTTP cron trigger can share the same logic."""
    counts: dict[str, int] = {"orgs": 0, "reminders": 0}
    today = datetime.now(UTC).date()
    horizon = today + timedelta(days=REMIND_WITHIN_DAYS)
    with bypass(session):
        orgs = (await session.execute(select(Organization))).scalars().all()

    for org in orgs:
        set_scope(session, org.id)
        counts["orgs"] += 1
        rows = (
            await session.execute(
                select(Booking, Unit)
                .join(Unit, Booking.unit_id == Unit.id)
                .where(
                    Booking.is_deleted.is_(False),
                    Booking.status == BookingStatus.confirmed,
                    Booking.scheduled_date >= today,
                    Booking.scheduled_date <= horizon,
                    Unit.status == UnitStatus.booked,
                )
            )
        ).all()
        service = NotificationService(session)
        email_service = EmailService()
        for booking, unit in rows:
            owner = await _owner_id(session, booking)
            if owner:
                await service.create_notification(
                    user_id=owner,
                    message=(
                        f"Registration due on {booking.scheduled_date.isoformat()} "
                        f"for unit {unit.unit_number}."
                    ),
                )
                counts["reminders"] += 1
                # Also email the owner (best-effort; no-op if email unconfigured).
                owner_user = await session.get(User, owner)
                if owner_user and owner_user.email:
                    await email_service.send_registration_reminder(
                        owner_user.email,
                        unit_label=unit.unit_number,
                        register_on=booking.scheduled_date.isoformat(),
                    )
        await session.commit()
    set_scope(session, None)
    return counts


async def run() -> dict[str, int]:
    """CLI entrypoint: owns the engine lifecycle around the shared dispatch."""
    db_manager.configure()
    async with db_manager.session_factory() as session:
        counts = await dispatch_registration_reminders(session)
    await db_manager.dispose()
    return counts


def main() -> None:
    argparse.ArgumentParser(description="Send reminders for imminent registrations.").parse_args()
    counts = asyncio.run(run())
    print(f"registration_reminders: orgs={counts['orgs']} reminders={counts['reminders']}")


if __name__ == "__main__":
    main()
