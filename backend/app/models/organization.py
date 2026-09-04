"""Organization — the tenant boundary.

Every domain row (Customer, Lead, SalesOrder, Invoice, …) carries an
`organization_id` FK to this table. Cross-org reads/writes are blocked by the
global SQLAlchemy filter declared in `app.core.tenancy`.

`business_type` lives here — every user inside an org shares the vertical
the org operates in. This replaces the per-user `business_type` that was
introduced in Phase 1.

`features` is a per-org JSON map keyed by feature flag (e.g.
`{"travel.visa_docs": true, "education.batch_code": true}`). For Phase 7 we
only define the column; vertical features still check `org.business_type`
directly. The flag layer lets us toggle features per plan later without
touching code.

NOTE: Organization → User audit FKs use `use_alter=True` because User in
turn carries `organization_id → organizations.id`. Without it, SQLAlchemy
can't order CREATE/DROP TABLE statements (cycle error in `create_all`).
"""
from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, JSON, String, Text, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.database.enums import FinanceBusinessMode, LeadIndustry
from app.models.base import UUIDPrimaryKeyMixin


class Organization(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    business_type: Mapped[LeadIndustry] = mapped_column(
        Enum(LeadIndustry, name="lead_industry_enum"),
        nullable=False,
    )
    plan: Mapped[str] = mapped_column(String(32), nullable=False, default="free")
    # Finance category-preset selector, chosen at signup. Immutable for tenants;
    # platform-admin settable. Drives which income/expense categories the org sees.
    finance_business_mode: Mapped[FinanceBusinessMode] = mapped_column(
        Enum(FinanceBusinessMode, name="finance_business_mode_enum"),
        nullable=False,
        server_default=text("'general'"),
    )
    features: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    schema_name: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)

    # Platform-admin suspension toggle. When false, the org's users are blocked
    # from login and from authenticated requests (orthogonal to is_deleted).
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true"), index=True
    )

    # Timestamps inlined here (not via TimestampMixin) to keep the cycle
    # surface minimal.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Audit FKs use `use_alter=True` so `Base.metadata.create_all` can resolve
    # the users ↔ organizations FK cycle.
    created_by_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL", use_alter=True, name="fk_organizations_created_by"),
        nullable=True,
        index=True,
    )
    updated_by_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL", use_alter=True, name="fk_organizations_updated_by"),
        nullable=True,
        index=True,
    )

    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    deleted_by_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL", use_alter=True, name="fk_organizations_deleted_by"),
        nullable=True,
        index=True,
    )

    # Be explicit about the FK path — multiple User→Organization FKs exist
    # (organization_id, plus the audit columns on this row pointing the other
    # way), and SQLAlchemy needs help picking the right one.
    users = relationship(
        "User",
        back_populates="organization",
        foreign_keys="User.organization_id",
    )
