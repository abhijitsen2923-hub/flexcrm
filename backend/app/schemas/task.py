from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.database.enums import TaskPriority, TaskStatus
from app.schemas.common import ORMModel, SearchSortParams
from app.schemas.user import UserSummary


class TaskCreate(ORMModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    assigned_to_id: UUID | None = None
    due_date: datetime | None = None
    priority: TaskPriority = TaskPriority.medium
    status: TaskStatus = TaskStatus.pending


class TaskUpdate(ORMModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    assigned_to_id: UUID | None = None
    due_date: datetime | None = None
    priority: TaskPriority | None = None
    status: TaskStatus | None = None


class TaskRead(ORMModel):
    id: UUID
    title: str
    description: str | None = None
    assigned_to_id: UUID | None = None
    due_date: datetime | None = None
    priority: TaskPriority
    status: TaskStatus
    created_by_id: UUID | None = None
    updated_by_id: UUID | None = None
    created_at: datetime
    updated_at: datetime
    assigned_to: UserSummary | None = None


class TaskFilterParams(SearchSortParams):
    assigned_to_id: UUID | None = None
    priority: TaskPriority | None = None
    status: TaskStatus | None = None
