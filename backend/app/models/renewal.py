from datetime import date, datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, Numeric, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.tenancy import OrgScopedMixin
from app.database.base import Base
from app.database.enums import RenewalStatus
from app.models.base import UUIDPrimaryKeyMixin


class Renewal(Base, UUIDPrimaryKeyMixin, OrgScopedMixin):
    __tablename__ = "renewals"
    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_renewals_amount_non_negative"),
        Index("ix_renewals_customer_due_date", "customer_id", "due_date"),
    )

    customer_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    due_date: Mapped[date] = mapped_column(nullable=False, index=True)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    status: Mapped[RenewalStatus] = mapped_column(
        Enum(RenewalStatus, name="renewal_status_enum"),
        nullable=False,
        default=RenewalStatus.upcoming,
    )
    renewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    customer = relationship("Customer", back_populates="renewals")
