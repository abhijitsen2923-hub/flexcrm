from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from app.database.enums import DealStatus, PipelineStageCategory, TaskStatus
from app.models.activity import Activity
from app.models.customer import Customer
from app.models.deal import Deal
from app.models.lead import Lead
from app.models.pipeline_stage import PipelineStage
from app.models.task import Task


class DashboardRepository:
    def __init__(self, session):
        self.session = session

    async def summary(self) -> dict[str, int | Decimal]:
        total_customers = int(
            (await self.session.execute(select(func.count()).select_from(Customer).where(Customer.is_deleted.is_(False)))).scalar_one()
        )
        # "Active" leads = stage category 'active' (not closed-won, not closed-lost).
        active_leads = int(
            (
                await self.session.execute(
                    select(func.count())
                    .select_from(Lead)
                    .join(
                        PipelineStage,
                        (PipelineStage.industry == Lead.industry)
                        & (PipelineStage.code == Lead.stage_code),
                    )
                    .where(
                        Lead.is_deleted.is_(False),
                        PipelineStage.category == PipelineStageCategory.active,
                    )
                )
            ).scalar_one()
        )
        open_deals_value = (
            (
                await self.session.execute(
                    select(func.coalesce(func.sum(Deal.amount), 0)).where(
                        Deal.is_deleted.is_(False),
                        Deal.status == DealStatus.open,
                    )
                )
            ).scalar_one()
            or Decimal("0")
        )
        overdue_tasks = int(
            (
                await self.session.execute(
                    select(func.count()).select_from(Task).where(
                        Task.is_deleted.is_(False),
                        Task.status.not_in([TaskStatus.completed, TaskStatus.cancelled]),
                        Task.due_date.is_not(None),
                        Task.due_date < datetime.now(UTC),
                    )
                )
            ).scalar_one()
        )
        recent_activity_count = int(
            (
                await self.session.execute(
                    select(func.count()).select_from(Activity).where(
                        Activity.is_deleted.is_(False),
                        Activity.created_at >= datetime.now(UTC) - timedelta(days=7),
                    )
                )
            ).scalar_one()
        )
        return {
            "total_customers": total_customers,
            "active_leads": active_leads,
            "open_deals_value": open_deals_value,
            "overdue_tasks": overdue_tasks,
            "recent_activity_count": recent_activity_count,
        }

    async def revenue_trend(self) -> list[tuple[str, Decimal]]:
        rows = (
            await self.session.execute(
                select(Deal.expected_close, Deal.amount).where(
                    Deal.is_deleted.is_(False),
                    Deal.expected_close.is_not(None),
                    Deal.status == DealStatus.won,
                )
            )
        ).all()
        buckets: dict[str, Decimal] = {}
        for expected_close, amount in rows:
            label = expected_close.strftime("%Y-%m")
            buckets[label] = buckets.get(label, Decimal("0")) + Decimal(amount)
        return sorted(buckets.items())

    async def lead_stage_breakdown(self) -> list[tuple[str, int]]:
        # Group by the human-readable stage name (joined from pipeline_stages)
        # so dashboard charts show "Counseling Session Booked" rather than
        # an opaque slug.
        rows = (
            await self.session.execute(
                select(PipelineStage.name, func.count(Lead.id))
                .join(
                    Lead,
                    (Lead.industry == PipelineStage.industry)
                    & (Lead.stage_code == PipelineStage.code),
                )
                .where(Lead.is_deleted.is_(False))
                .group_by(PipelineStage.name)
            )
        ).all()
        return [(name, count) for name, count in rows]

    async def task_status_breakdown(self) -> list[tuple[str, int]]:
        rows = (
            await self.session.execute(
                select(Task.status, func.count(Task.id))
                .where(Task.is_deleted.is_(False))
                .group_by(Task.status)
            )
        ).all()
        return [(status.value, count) for status, count in rows]

    async def recent_activities(self, limit: int = 10):
        query = (
            select(
                Activity.id,
                Activity.customer_id,
                Customer.company_name,
                Activity.type,
                Activity.note,
                Activity.created_at,
            )
            .join(Customer, Customer.id == Activity.customer_id)
            .where(Activity.is_deleted.is_(False), Customer.is_deleted.is_(False))
            .order_by(Activity.created_at.desc())
            .limit(limit)
        )
        return (await self.session.execute(query)).all()
