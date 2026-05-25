from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.tenancy import OrgScopedMixin
from app.database.base import Base
from app.models.base import UUIDPrimaryKeyMixin


class DeliveryLog(Base, UUIDPrimaryKeyMixin, OrgScopedMixin):
    """Post-sale delivery audit (spec §4.2).

    Education: batches attended, certificates issued. Travel: trips completed.
    Free-form `item` keeps the model industry-agnostic; per-industry semantics
    live in the UI label.
    """
    __tablename__ = "delivery_logs"
    __table_args__ = (
        Index("ix_delivery_logs_customer_delivered_at", "customer_id", "delivered_at"),
    )

    customer_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    item: Mapped[str] = mapped_column(String(255), nullable=False)
    delivered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    delivered_by_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    customer = relationship("Customer", back_populates="delivery_logs")
