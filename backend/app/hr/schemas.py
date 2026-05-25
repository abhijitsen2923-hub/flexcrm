from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field

from app.schemas.common import ORMModel


class EmployeeProfileRead(ORMModel):
    id: UUID
    user_id: UUID
    target_revenue_monthly: Decimal
    commission_rate: Decimal
    manager_id: UUID | None = None
    score_weights: dict | None = None


class EmployeeProfileUpdate(ORMModel):
    target_revenue_monthly: Decimal | None = Field(default=None, ge=0)
    commission_rate: Decimal | None = Field(default=None, ge=0, le=100)
    manager_id: UUID | None = None
    score_weights: dict | None = None


class PerformanceSnapshotRead(ORMModel):
    id: UUID
    user_id: UUID
    snapshot_date: date
    deals_closed: int
    revenue: Decimal
    collections: Decimal
    conversion_rate: Decimal
    pipeline_velocity_days: Decimal
    activity_quality: Decimal
    retention: Decimal
    score: Decimal
    grade: str
    computed_at: datetime


class ScorecardRow(ORMModel):
    user_id: UUID
    user_name: str
    deals_closed: int
    revenue: Decimal
    collections: Decimal
    conversion_rate: Decimal
    score: Decimal
    grade: str


class TeamScorecard(ORMModel):
    snapshot_date: date
    rows: list[ScorecardRow]
