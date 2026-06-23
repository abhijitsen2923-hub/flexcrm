from uuid import UUID

from sqlalchemy import Enum, ForeignKey, Index, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import TenantBase
from app.database.enums import ActivityType
from app.models.base import TenantAuditMixin, TenantSoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Activity(TenantBase, UUIDPrimaryKeyMixin, TimestampMixin, TenantAuditMixin, TenantSoftDeleteMixin):
    __tablename__ = "activities"
    __table_args__ = (
        Index("ix_activities_customer_created_at", "customer_id", "created_at"),
        Index("ix_activities_type", "type"),
        {"schema": "tenant"},
    )

    customer_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type: Mapped[ActivityType] = mapped_column(Enum(ActivityType, name="activity_type_enum"), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)

    customer = relationship("Customer", back_populates="activities")
