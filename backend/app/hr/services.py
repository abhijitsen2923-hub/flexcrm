"""HR scorecard computation (spec §5.3).

The score is a weighted sum of six factors (revenue, collections, conversion
rate, pipeline velocity, activity quality, retention). Default weights are
40/20/15/10/10/5 (spec §5.3) and can be overridden per-user via
`EmployeeProfile.score_weights`.

`ScorecardService.compute_user(user_id, snapshot_date)` is the entry point.
The nightly job in `app/jobs/scorecard_compute.py` calls it for every
active sales user.
"""
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select

from app.core.permissions import SCORECARD_ROLES
from app.database.enums import (
    CustomerLifecycleStage,
    InvoiceStatus,
    UserStatus,
)
from app.finance.models import Invoice, Payment, SalesOrder
from app.hr.models import DEFAULT_SCORE_WEIGHTS, EmployeeProfile, PerformanceSnapshot
from app.models.customer import Customer
from app.models.lead import Lead
from app.models.pipeline_stage import PipelineStage
from app.models.stage_transition import StageTransition
from app.models.user import User
from app.services.base import ServiceBase


def grade_for_score(score: Decimal) -> str:
    s = float(score)
    if s >= 90:
        return "A+"
    if s >= 80:
        return "A"
    if s >= 70:
        return "B+"
    if s >= 60:
        return "B"
    if s >= 50:
        return "C"
    return "D"


class ScorecardService(ServiceBase):
    async def get_profile(self, user_id: UUID) -> EmployeeProfile:
        existing = (
            await self.session.execute(select(EmployeeProfile).where(EmployeeProfile.user_id == user_id))
        ).scalar_one_or_none()
        if existing is not None:
            return existing
        profile = EmployeeProfile(user_id=user_id)
        self.session.add(profile)
        await self.session.flush()
        return profile

    async def compute_user(self, user_id: UUID, *, snapshot_date: date | None = None) -> PerformanceSnapshot:
        snapshot_date = snapshot_date or datetime.now(UTC).date()
        profile = await self.get_profile(user_id)
        weights = self._normalised_weights(profile.score_weights or DEFAULT_SCORE_WEIGHTS)

        deals_closed, revenue = await self._revenue_factor(user_id, snapshot_date)
        collections = await self._collections_factor(user_id, snapshot_date)
        conversion_rate = await self._conversion_rate(user_id)
        pipeline_velocity_days = await self._pipeline_velocity(user_id)
        activity_quality = await self._activity_quality(user_id)
        retention = await self._retention(user_id)

        revenue_score = self._against_target(revenue, profile.target_revenue_monthly)
        collections_score = (
            (collections / revenue * 100) if revenue > 0 else Decimal("0")
        ).quantize(Decimal("0.01"))
        velocity_score = self._velocity_score(pipeline_velocity_days)

        composite = (
            Decimal(revenue_score) * Decimal(weights["revenue"]) / Decimal(100)
            + Decimal(collections_score) * Decimal(weights["collections"]) / Decimal(100)
            + Decimal(conversion_rate) * Decimal(weights["conversion_rate"]) / Decimal(100)
            + Decimal(velocity_score) * Decimal(weights["pipeline_velocity"]) / Decimal(100)
            + Decimal(activity_quality) * Decimal(weights["activity_quality"]) / Decimal(100)
            + Decimal(retention) * Decimal(weights["retention"]) / Decimal(100)
        ).quantize(Decimal("0.01"))

        # Upsert today's snapshot.
        existing = (
            await self.session.execute(
                select(PerformanceSnapshot).where(
                    PerformanceSnapshot.user_id == user_id,
                    PerformanceSnapshot.snapshot_date == snapshot_date,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            existing = PerformanceSnapshot(user_id=user_id, snapshot_date=snapshot_date)
            self.session.add(existing)

        existing.deals_closed = deals_closed
        existing.revenue = revenue
        existing.collections = collections
        existing.conversion_rate = conversion_rate
        existing.pipeline_velocity_days = pipeline_velocity_days
        existing.activity_quality = activity_quality
        existing.retention = retention
        existing.score = composite
        existing.grade = grade_for_score(composite)
        existing.computed_at = datetime.now(UTC)

        await self.session.flush()
        return existing

    # --- factor helpers ----------------------------------------------------

    async def _revenue_factor(self, user_id: UUID, snapshot_date: date) -> tuple[int, Decimal]:
        """Deals closed + revenue for the calendar month containing snapshot_date."""
        start = datetime(snapshot_date.year, snapshot_date.month, 1, tzinfo=UTC)
        deals_closed = int(
            (
                await self.session.execute(
                    select(func.count(SalesOrder.id)).where(
                        SalesOrder.primary_owner_id == user_id,
                        SalesOrder.closed_at >= start,
                    )
                )
            ).scalar_one()
            or 0
        )
        revenue = Decimal(
            (
                await self.session.execute(
                    select(func.coalesce(func.sum(SalesOrder.deal_value), 0)).where(
                        SalesOrder.primary_owner_id == user_id,
                        SalesOrder.closed_at >= start,
                    )
                )
            ).scalar_one()
            or 0
        )
        return deals_closed, revenue

    async def _collections_factor(self, user_id: UUID, snapshot_date: date) -> Decimal:
        start = datetime(snapshot_date.year, snapshot_date.month, 1, tzinfo=UTC)
        total = Decimal(
            (
                await self.session.execute(
                    select(func.coalesce(func.sum(Payment.amount), 0))
                    .select_from(Payment)
                    .join(Invoice, Payment.invoice_id == Invoice.id)
                    .join(SalesOrder, Invoice.sales_order_id == SalesOrder.id)
                    .where(
                        SalesOrder.primary_owner_id == user_id,
                        Payment.received_at >= start,
                    )
                )
            ).scalar_one()
            or 0
        )
        return total

    async def _conversion_rate(self, user_id: UUID) -> Decimal:
        """(Sold ÷ Qualified) for leads owned by this user, all-time."""
        qualified = int(
            (
                await self.session.execute(
                    select(func.count(Lead.id.distinct()))
                    .select_from(Lead)
                    .join(StageTransition, StageTransition.lead_id == Lead.id)
                    .where(
                        Lead.assigned_to_id == user_id,
                        StageTransition.to_stage_code == "qualified",
                    )
                )
            ).scalar_one()
            or 0
        )
        if qualified == 0:
            return Decimal("0")
        sold = int(
            (
                await self.session.execute(
                    select(func.count(Lead.id)).where(
                        Lead.assigned_to_id == user_id,
                        Lead.stage_code == "sold",
                    )
                )
            ).scalar_one()
            or 0
        )
        return (Decimal(sold) / Decimal(qualified) * Decimal(100)).quantize(Decimal("0.01"))

    async def _pipeline_velocity(self, user_id: UUID) -> Decimal:
        """Average days between Lead create and the Sold transition."""
        rows = (
            await self.session.execute(
                select(Lead.created_at, StageTransition.performed_at)
                .select_from(Lead)
                .join(StageTransition, StageTransition.lead_id == Lead.id)
                .where(
                    Lead.assigned_to_id == user_id,
                    StageTransition.to_stage_code == "sold",
                )
            )
        ).all()
        if not rows:
            return Decimal("0")
        deltas = [(closed - created).total_seconds() / 86400 for created, closed in rows]
        avg = sum(deltas) / len(deltas)
        return Decimal(str(avg)).quantize(Decimal("0.01"))

    async def _activity_quality(self, user_id: UUID) -> Decimal:
        """Comments-per-stage-change for this user (capped at 100)."""
        total = int(
            (
                await self.session.execute(
                    select(func.count(StageTransition.id)).where(
                        StageTransition.performed_by_id == user_id,
                    )
                )
            ).scalar_one()
            or 0
        )
        if total == 0:
            return Decimal("0")
        with_comments = int(
            (
                await self.session.execute(
                    select(func.count(StageTransition.id)).where(
                        StageTransition.performed_by_id == user_id,
                        func.length(StageTransition.comment) > 10,
                    )
                )
            ).scalar_one()
            or 0
        )
        ratio = Decimal(with_comments) / Decimal(total) * Decimal(100)
        return ratio.quantize(Decimal("0.01"))

    async def _retention(self, user_id: UUID) -> Decimal:
        """Pct of this user's original customers still active (not churned)."""
        total = int(
            (
                await self.session.execute(
                    select(func.count(Customer.id)).where(Customer.original_owner_id == user_id)
                )
            ).scalar_one()
            or 0
        )
        if total == 0:
            return Decimal("0")
        still_active = int(
            (
                await self.session.execute(
                    select(func.count(Customer.id)).where(
                        Customer.original_owner_id == user_id,
                        Customer.lifecycle_stage != CustomerLifecycleStage.churned,
                    )
                )
            ).scalar_one()
            or 0
        )
        return (Decimal(still_active) / Decimal(total) * Decimal(100)).quantize(Decimal("0.01"))

    def _against_target(self, value: Decimal, target: Decimal) -> Decimal:
        if target is None or target <= 0:
            # No target set — credit 100% if any revenue exists, 0 otherwise.
            return Decimal("100") if value > 0 else Decimal("0")
        ratio = Decimal(value) / Decimal(target) * Decimal(100)
        return min(ratio, Decimal("150")).quantize(Decimal("0.01"))  # cap at 150% to dampen outliers

    def _velocity_score(self, days: Decimal) -> Decimal:
        """Lower days → higher score. 0 days = 100, 60+ days = 0."""
        if days <= 0:
            return Decimal("0")
        capped = min(days, Decimal("60"))
        return ((Decimal("60") - capped) / Decimal("60") * Decimal("100")).quantize(Decimal("0.01"))

    def _normalised_weights(self, weights: dict) -> dict[str, int]:
        merged = {**DEFAULT_SCORE_WEIGHTS, **weights}
        # Normalise so the keys sum to 100; protects against partial overrides.
        total = sum(merged[k] for k in DEFAULT_SCORE_WEIGHTS) or 1
        return {k: int(merged[k] / total * 100) for k in DEFAULT_SCORE_WEIGHTS}


async def list_active_sales_users(session, organization_id: UUID) -> list[User]:
    """Active sales-flavoured users in ONE org.

    `organization_id` is mandatory, not optional. `users` lives in the PUBLIC
    schema and is shared by every tenant, so an unfiltered query returns users
    from all orgs — the nightly scorecard job would then write a
    PerformanceSnapshot for every org's users into every org's schema. Schema
    routing does not save us here precisely because this table is not routed.
    """
    rows = (
        await session.execute(
            select(User).where(
                User.organization_id == organization_id,
                User.status == UserStatus.active,
                User.role.in_(tuple(SCORECARD_ROLES)),
                User.is_deleted.is_(False),
            )
        )
    ).scalars().all()
    return list(rows)
