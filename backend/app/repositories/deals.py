from sqlalchemy.orm import selectinload

from app.models.deal import Deal
from app.repositories.base import BaseRepository


class DealRepository(BaseRepository[Deal]):
    def __init__(self, session):
        super().__init__(session, Deal)

    @property
    def default_options(self):
        return [selectinload(Deal.customer)]
