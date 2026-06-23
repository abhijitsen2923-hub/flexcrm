"""Customer portal models — per-tenant schema."""
from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import TenantBase
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class CustomerDocument(TenantBase, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "customer_documents"
    __table_args__ = (
        Index("ix_customer_documents_customer", "customer_id"),
        {"schema": "tenant"},
    )

    customer_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    booking_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("bookings.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ServiceRequest(TenantBase, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "service_requests"
    __table_args__ = (
        Index("ix_service_requests_customer_status", "customer_id", "status"),
        {"schema": "tenant"},
    )

    customer_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("public.users.id", ondelete="SET NULL"), nullable=True
    )
