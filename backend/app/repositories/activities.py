from sqlalchemy.orm import selectinload

from app.models.activity import Activity
from app.repositories.base import BaseRepository


class ActivityRepository(BaseRepository[Activity]):
    def __init__(self, session):
        super().__init__(session, Activity)

    @property
    def default_options(self):
        return [selectinload(Activity.customer)]
