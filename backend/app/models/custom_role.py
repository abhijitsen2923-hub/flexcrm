"""Custom role definitions and per-user assignments.

Org admins can create named CustomRole templates with any combination of the
23 PermissionCodes. Assigning one to a user sets `user.role = UserRole.custom`
and creates a UserCustomRoleAssignment row linking user → role template.

Both models live in the tenant schema so Org A's custom roles are invisible
to Org B. Cross-schema FKs to public.users are enforced at the application
layer (no DB FK across schema boundaries).
"""
import uuid

import sqlalchemy as sa
from sqlalchemy import ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import TenantBase
from app.models.base import TimestampMixin, TenantAuditMixin, UUIDPrimaryKeyMixin


class CustomRole(TenantBase, UUIDPrimaryKeyMixin, TimestampMixin, TenantAuditMixin):
    """Named permission template that can be assigned to org users."""

    __tablename__ = "custom_roles"
    __table_args__ = (
        UniqueConstraint("name", name="uq_custom_roles_name"),
        {"schema": "tenant"},
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSON array of PermissionCode string values, e.g. ["LEAD_VIEW", "TASK_VIEW"]
    permissions: Mapped[list] = mapped_column(sa.JSON, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.true())

    assignments: Mapped[list["UserCustomRoleAssignment"]] = relationship(
        "UserCustomRoleAssignment",
        back_populates="custom_role",
        cascade="all, delete-orphan",
    )


class UserCustomRoleAssignment(TenantBase, UUIDPrimaryKeyMixin, TimestampMixin):
    """Links a user (public.users) to a CustomRole for this tenant.

    Unique on user_id — one custom role per user at a time.
    Use the /users/{id}/custom-role endpoint to change or remove the assignment.
    """

    __tablename__ = "user_custom_role_assignments"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_user_custom_role_assignments_user"),
        {"schema": "tenant"},
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("public.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    custom_role_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("tenant.custom_roles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    custom_role: Mapped["CustomRole"] = relationship(
        "CustomRole",
        back_populates="assignments",
        lazy="selectin",
    )
