from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.stage_transition import StageTransition
from app.repositories.base import BaseRepository


class StageTransitionRepository(BaseRepository[StageTransition]):
    def __init__(self, session):
        super().__init__(session, StageTransition)

    @property
    def default_options(self):
        return [selectinload(StageTransition.performed_by)]

    async def for_lead(self, lead_id: UUID) -> list[StageTransition]:
        query = (
            select(StageTransition)
            .where(StageTransition.lead_id == lead_id)
            .order_by(StageTransition.performed_at.desc())
            .options(*self.default_options)
        )
        return list((await self.session.execute(query)).scalars().all())
