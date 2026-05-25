from decimal import Decimal

from sqlalchemy import func, select

from app.database.enums import DealStatus, PipelineStageCategory
from app.models.customer import Customer
from app.models.deal import Deal
from app.models.lead import Lead
from app.models.pipeline_stage import PipelineStage


class AnalyticsRepository:
    def __init__(self, session):
        self.session = session

    async def closed_revenue(self) -> Decimal:
        value = (
            await self.session.execute(
                select(func.coalesce(func.sum(Deal.amount), 0)).where(
                    Deal.is_deleted.is_(False),
                    Deal.status == DealStatus.won,
                )
            )
        ).scalar_one()
        return Decimal(value or 0)

    async def open_pipeline_value(self) -> Decimal:
        value = (
            await self.session.execute(
                select(func.coalesce(func.sum(Deal.amount), 0)).where(
                    Deal.is_deleted.is_(False),
                    Deal.status == DealStatus.open,
                )
            )
        ).scalar_one()
        return Decimal(value or 0)

    async def total_leads(self) -> int:
        return int(
            (await self.session.execute(select(func.count()).select_from(Lead).where(Lead.is_deleted.is_(False)))).scalar_one()
        )

    async def won_leads(self) -> int:
        return int(
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
                        PipelineStage.category == PipelineStageCategory.closed_won,
                    )
                )
            ).scalar_one()
        )

    async def lead_stage_breakdown(self) -> list[tuple[str, int]]:
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

    async def source_breakdown(self) -> list[tuple[str, int]]:
        # Source now lives on the Lead itself, not the customer.
        rows = (
            await self.session.execute(
                select(Lead.source, func.count(Lead.id))
                .where(Lead.is_deleted.is_(False))
                .group_by(Lead.source)
            )
        ).all()
        return [(source or "unknown", count) for source, count in rows]

    async def deal_counts(self) -> tuple[int, int]:
        won = int(
            (
                await self.session.execute(
                    select(func.count()).select_from(Deal).where(
                        Deal.is_deleted.is_(False),
                        Deal.status == DealStatus.won,
                    )
                )
            ).scalar_one()
        )
        total = int(
            (await self.session.execute(select(func.count()).select_from(Deal).where(Deal.is_deleted.is_(False)))).scalar_one()
        )
        return won, total

    async def average_lead_probability(self) -> float:
        average = (
            await self.session.execute(
                select(func.coalesce(func.avg(Lead.probability), 0)).where(Lead.is_deleted.is_(False))
            )
        ).scalar_one()
        return float(average or 0)
