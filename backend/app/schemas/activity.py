from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.database.enums import ActivityType
from app.schemas.common import ORMModel, SearchSortParams
from app.schemas.customer import CustomerCompact


class ActivityCreate(ORMModel):
    customer_id: UUID
    type: ActivityType
    note: str = Field(min_length=1)


class ActivityRead(ORMModel):
    id: UUID
    customer_id: UUID
    type: ActivityType
    note: str
    created_by_id: UUID | None = None
    updated_by_id: UUID | None = None
    created_at: datetime
    updated_at: datetime
    customer: CustomerCompact | None = None


class ActivityFilterParams(SearchSortParams):
    customer_id: UUID | None = None
    type: ActivityType | None = None
    created_by_id: UUID | None = None
