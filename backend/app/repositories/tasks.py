from sqlalchemy.orm import selectinload

from app.models.task import Task
from app.repositories.base import BaseRepository


class TaskRepository(BaseRepository[Task]):
    def __init__(self, session):
        super().__init__(session, Task)

    @property
    def default_options(self):
        return [selectinload(Task.assigned_to)]
