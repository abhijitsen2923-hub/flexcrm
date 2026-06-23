"""Per-user explicit permission overrides.

A row here is an *additive* grant on top of the user's role default.
Lives in the tenant schema so Org A's admin can't see or modify Org B's grants.
Cross-schema FKs reference public.users.
"""
from uuid import UUID

from sqlalchemy import ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import TenantBase
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class UserPermissionGrant(TenantBase, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "user_permission_grants"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "permission_code",
            name="uq_user_permission_grants_user_code",
        ),
        {"schema": "tenant"},
    )

    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("public.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    permission_code: Mapped[str] = mapped_column(String(64), nullable=False)
    granted_by_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("public.users.id", ondelete="SET NULL"),
        nullable=True,
    )

    user = relationship("User", foreign_keys=[user_id], back_populates="permission_grants")
    granted_by = relationship("User", foreign_keys=[granted_by_id])
