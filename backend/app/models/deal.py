from datetime import date
from uuid import UUID

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Index, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.tenancy import OrgScopedMixin
from app.database.base import Base
from app.database.enums import DealStage, DealStatus
from app.models.base import AuditMixin, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Deal(Base, UUIDPrimaryKeyMixin, TimestampMixin, AuditMixin, SoftDeleteMixin, OrgScopedMixin):
    __tablename__ = "deals"
    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_deals_amount_non_negative"),
        Index("ix_deals_stage_status", "stage", "status"),
    )

    customer_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    stage: Mapped[DealStage] = mapped_column(Enum(DealStage, name="deal_stage_enum"), nullable=False)
    expected_close: Mapped[date | None] = mapped_column(nullable=True, index=True)
    status: Mapped[DealStatus] = mapped_column(
        Enum(DealStatus, name="deal_status_enum"),
        nullable=False,
        default=DealStatus.open,
    )

    customer = relationship("Customer", back_populates="deals")
