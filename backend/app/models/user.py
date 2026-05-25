from sqlalchemy import Enum, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.tenancy import OrgScopedMixin
from app.database.base import Base
from app.database.enums import LeadIndustry, UserRole, UserStatus
from app.models.base import AuditMixin, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin, AuditMixin, SoftDeleteMixin, OrgScopedMixin):
    __tablename__ = "users"
    __table_args__ = (
        Index(
            "uq_users_email_active",
            "email",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
    )

    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, name="user_role_enum"), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, name="user_status_enum"),
        nullable=False,
        default=UserStatus.active,
    )
    # DEPRECATED in Phase 7 — business_type now lives on the Organization.
    # Kept here for backward compat with existing rows; new code should read
    # `user.organization.business_type` instead.
    business_type: Mapped[LeadIndustry | None] = mapped_column(
        Enum(LeadIndustry, name="lead_industry_enum"),
        nullable=True,
        index=True,
    )

    organization = relationship(
        "Organization",
        back_populates="users",
        foreign_keys=lambda: [User.organization_id],
    )

    assigned_leads = relationship("Lead", back_populates="assigned_to", foreign_keys="Lead.assigned_to_id")
    assigned_tasks = relationship("Task", back_populates="assigned_to", foreign_keys="Task.assigned_to_id")
    notifications = relationship("Notification", back_populates="user", foreign_keys="Notification.user_id")
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")
    permission_grants = relationship(
        "UserPermissionGrant",
        back_populates="user",
        foreign_keys="UserPermissionGrant.user_id",
        cascade="all, delete-orphan",
    )
