from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field

from app.database.enums import DealStage, DealStatus
from app.schemas.common import ORMModel, SearchSortParams
from app.schemas.customer import CustomerCompact


class DealCreate(ORMModel):
    customer_id: UUID
    title: str = Field(min_length=1, max_length=255)
    amount: Decimal = Field(default=Decimal("0"), ge=0)
    stage: DealStage
    expected_close: date | None = None
    status: DealStatus = DealStatus.open


class DealUpdate(ORMModel):
    customer_id: UUID | None = None
    title: str | None = Field(default=None, min_length=1, max_length=255)
    amount: Decimal | None = Field(default=None, ge=0)
    stage: DealStage | None = None
    expected_close: date | None = None
    status: DealStatus | None = None


class DealRead(ORMModel):
    id: UUID
    customer_id: UUID
    title: str
    amount: Decimal
    stage: DealStage
    expected_close: date | None = None
    status: DealStatus
    created_by_id: UUID | None = None
    updated_by_id: UUID | None = None
    created_at: datetime
    updated_at: datetime
    customer: CustomerCompact | None = None


class DealFilterParams(SearchSortParams):
    customer_id: UUID | None = None
    stage: DealStage | None = None
    status: DealStatus | None = None
