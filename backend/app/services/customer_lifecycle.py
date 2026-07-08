"""Customer lifecycle helpers (spec §4.1).

Extends the auto-promotion done in `customer_promotion` with the full
six-stage lifecycle (onboarding → active → at_risk → renewal_due →
renewed → churned). The nightly health-check job (see
`app/jobs/customer_health.py`) is responsible for flipping rows
between at_risk / renewal_due / active based on activity and renewals.
"""
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from uuid import UUID

from sqlalchemy import func, select

from app.database.enums import CustomerLifecycleStage
from app.models.activity import Activity
from app.models.customer import Customer
from app.models.deal import Deal
from app.models.renewal import Renewal


AT_RISK_INACTIVITY_DAYS = 30
RENEWAL_WARNING_DAYS = 30


async def recompute_ltv(session, customer: Customer) -> Decimal:
    """Sum of every won Deal + every renewed Renewal + every confirmed real-estate
    booking's total consideration for this customer."""
    deals = (
        await session.execute(
            select(func.coalesce(func.sum(Deal.amount), 0)).where(
                Deal.customer_id == customer.id,
                Deal.is_deleted.is_(False),
            )
        )
    ).scalar_one() or Decimal("0")
    renewals = (
        await session.execute(
            select(func.coalesce(func.sum(Renewal.amount), 0)).where(
                Renewal.customer_id == customer.id,
                Renewal.status == "renewed",
            )
        )
    ).scalar_one() or Decimal("0")
    total = Decimal(deals) + Decimal(renewals) + await _confirmed_booking_total(session, customer.id)
    customer.ltv = total
    return total


async def _confirmed_booking_total(session, customer_id: UUID) -> Decimal:
    """Total consideration across a customer's confirmed real-estate bookings.

    Imported lazily so this core lifecycle helper doesn't hard-depend on the
    real-estate vertical. The `bookings` table exists in every tenant schema, so
    the query is safe (non-RE tenants just have zero rows).
    """
    from app.database.enums import BookingStatus
    from app.real_estate.models import Booking

    snapshots = (
        await session.execute(
            select(Booking.pricing_snapshot).where(
                Booking.customer_id == customer_id,
                Booking.status == BookingStatus.confirmed,
                Booking.is_deleted.is_(False),
            )
        )
    ).scalars().all()

    total = Decimal("0")
    for snap in snapshots:
        if isinstance(snap, dict) and snap.get("total") is not None:
            try:
                total += Decimal(str(snap["total"]))
            except (InvalidOperation, TypeError):
                pass
    return total


async def transition_lifecycle(customer: Customer, to_stage: CustomerLifecycleStage, *, reason: str | None = None) -> None:
    """Move a customer to a lifecycle stage, stamping side-fields as needed."""
    customer.lifecycle_stage = to_stage
    if to_stage == CustomerLifecycleStage.onboarding and customer.onboarding_started_at is None:
        customer.onboarding_started_at = datetime.now(UTC)
    if to_stage == CustomerLifecycleStage.churned and reason:
        customer.churn_reason = reason


async def evaluate_health(session, customer: Customer, *, today: date | None = None) -> CustomerLifecycleStage:
    """Decide the lifecycle bucket for a customer based on activity + renewals.

    Mutates `customer.lifecycle_stage` and returns the new value. Idempotent.
    """
    today = today or datetime.now(UTC).date()

    # Already-churned customers don't flip back automatically.
    if customer.lifecycle_stage == CustomerLifecycleStage.churned:
        return customer.lifecycle_stage

    # Any upcoming renewal within the warning window? → renewal_due.
    upcoming = (
        await session.execute(
            select(func.min(Renewal.due_date)).where(
                Renewal.customer_id == customer.id,
                Renewal.status == "upcoming",
                Renewal.due_date <= today + timedelta(days=RENEWAL_WARNING_DAYS),
                Renewal.due_date >= today,
            )
        )
    ).scalar_one()
    if upcoming is not None:
        customer.lifecycle_stage = CustomerLifecycleStage.renewal_due
        customer.renewal_due_at = upcoming
        return customer.lifecycle_stage

    # No activity for N days? → at_risk.
    cutoff = datetime.now(UTC) - timedelta(days=AT_RISK_INACTIVITY_DAYS)
    last_activity = (
        await session.execute(
            select(func.max(Activity.created_at)).where(
                Activity.customer_id == customer.id,
                Activity.is_deleted.is_(False),
            )
        )
    ).scalar_one()
    if last_activity is None or last_activity < cutoff:
        if customer.lifecycle_stage != CustomerLifecycleStage.onboarding:
            customer.lifecycle_stage = CustomerLifecycleStage.at_risk
            return customer.lifecycle_stage

    # Default — healthy / active.
    if customer.lifecycle_stage in {CustomerLifecycleStage.at_risk, CustomerLifecycleStage.renewal_due}:
        customer.lifecycle_stage = CustomerLifecycleStage.active
    return customer.lifecycle_stage


def next_customer_number(highest_existing: int | None) -> int:
    """Customer numbers start at 50000 — kept distinct from lead numbers (89000+)."""
    return (highest_existing or 50000) + 1


async def claim_customer_number(session) -> int:
    current = (
        await session.execute(select(func.max(Customer.customer_number)))
    ).scalar_one()
    return next_customer_number(current)


_ = UUID  # mypy guard: keep the import alive
