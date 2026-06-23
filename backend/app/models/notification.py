from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import TenantBase
from app.database.enums import NotificationStatus
from app.models.base import TenantSoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Notification(TenantBase, UUIDPrimaryKeyMixin, TimestampMixin, TenantSoftDeleteMixin):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_user_read_created", "user_id", "read_status", "created_at"),
        {"schema": "tenant"},
    )

    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("public.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    read_status: Mapped[NotificationStatus] = mapped_column(
        Enum(NotificationStatus, name="notification_status_enum"),
        nullable=False,
        default=NotificationStatus.unread,
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="notifications", foreign_keys=[user_id])
