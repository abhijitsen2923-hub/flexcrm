"""HR domain models — per-tenant schema."""
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import TenantBase
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


DEFAULT_SCORE_WEIGHTS: dict[str, int] = {
    "revenue": 40,
    "collections": 20,
    "conversion_rate": 15,
    "pipeline_velocity": 10,
    "activity_quality": 10,
    "retention": 5,
}


class EmployeeProfile(TenantBase, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "employee_profiles"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_employee_profiles_user"),
        CheckConstraint("commission_rate >= 0 AND commission_rate <= 100", name="ck_employee_profiles_rate_range"),
        {"schema": "tenant"},
    )

    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("public.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_revenue_monthly: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    commission_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    manager_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("public.users.id", ondelete="SET NULL"),
        nullable=True,
    )
    score_weights: Mapped[dict | None] = mapped_column(JSON, nullable=True)



class PerformanceSnapshot(TenantBase, UUIDPrimaryKeyMixin):
    __tablename__ = "performance_snapshots"
    __table_args__ = (
        UniqueConstraint("user_id", "snapshot_date", name="uq_performance_snapshots_user_date"),
        Index("ix_performance_snapshots_user_date", "user_id", "snapshot_date"),
        {"schema": "tenant"},
    )

    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("public.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)

    deals_closed: Mapped[int] = mapped_column(nullable=False, default=0)
    revenue: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    collections: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    conversion_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    pipeline_velocity_days: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False, default=0)
    activity_quality: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    retention: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    grade: Mapped[str] = mapped_column(String(2), nullable=False, default="D")
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

