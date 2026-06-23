from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

# Prefix used for cross-schema FK references from tenant tables to public.users.
_PUBLIC_USERS = "public.users.id"


class UUIDPrimaryKeyMixin:
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
    )


class AuditMixin:
    created_by_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    updated_by_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )


class SoftDeleteMixin:
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    deleted_by_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )


class TenantAuditMixin:
    """AuditMixin for tenant-schema models. FKs point to public.users."""

    created_by_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey(_PUBLIC_USERS, ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    updated_by_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey(_PUBLIC_USERS, ondelete="SET NULL"),
        nullable=True,
        index=True,
    )


class TenantSoftDeleteMixin:
    """SoftDeleteMixin for tenant-schema models. FK points to public.users."""

    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    deleted_by_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey(_PUBLIC_USERS, ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
