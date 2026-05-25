from sqlalchemy import select

from app.database.enums import LeadIndustry
from app.models.pipeline_stage import PipelineStage
from app.repositories.base import BaseRepository


class PipelineStageRepository(BaseRepository[PipelineStage]):
    def __init__(self, session):
        super().__init__(session, PipelineStage)

    async def all_stages(self) -> list[PipelineStage]:
        result = await self.session.execute(
            select(PipelineStage).order_by(PipelineStage.industry, PipelineStage.position)
        )
        return list(result.scalars().all())

    async def by_industry(self, industry: LeadIndustry) -> list[PipelineStage]:
        result = await self.session.execute(
            select(PipelineStage)
            .where(PipelineStage.industry == industry)
            .order_by(PipelineStage.position)
        )
        return list(result.scalars().all())

    async def find(self, industry: LeadIndustry, code: str) -> PipelineStage | None:
        result = await self.session.execute(
            select(PipelineStage).where(
                PipelineStage.industry == industry,
                PipelineStage.code == code,
            )
        )
        return result.scalar_one_or_none()
