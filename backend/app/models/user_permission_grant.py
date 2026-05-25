"""Per-user explicit permission overrides (Phase 8).

A row here is an *additive* grant on top of the user's role default — a
counselor's role doesn't include `FINANCE_REFUND` by default, but inserting a
grant row gives that one counselor the refund button. There is no revoke-by-row
for role defaults; to take a default permission away, change the role.

Org-scoped via `OrgScopedMixin` so Org A's admin can't grant or revoke against
Org B's users — the global SELECT filter (`app.core.tenancy`) handles that.
"""
from uuid import UUID

from sqlalchemy import ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.tenancy import OrgScopedMixin
from app.database.base import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class UserPermissionGrant(Base, UUIDPrimaryKeyMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "user_permission_grants"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "permission_code",
            name="uq_user_permission_grants_user_code",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Stored as a string so a deprecated PermissionCode in the catalog doesn't
    # crash loads — `effective_permissions_for_user` silently drops unknown
    # codes when computing the final set.
    permission_code: Mapped[str] = mapped_column(String(64), nullable=False)
    granted_by_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    user = relationship("User", foreign_keys=[user_id], back_populates="permission_grants")
    granted_by = relationship("User", foreign_keys=[granted_by_id])
