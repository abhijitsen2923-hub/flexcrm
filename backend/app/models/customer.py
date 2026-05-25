from datetime import date, datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.tenancy import OrgScopedMixin
from app.database.base import Base
from app.database.enums import CustomerLifecycleStage, CustomerStatus
from app.models.base import AuditMixin, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Customer(Base, UUIDPrimaryKeyMixin, TimestampMixin, AuditMixin, SoftDeleteMixin, OrgScopedMixin):
    __tablename__ = "customers"
    __table_args__ = (
        Index("ix_customers_company_name", "company_name"),
        Index("ix_customers_source_status", "source", "status"),
        Index("ix_customers_lifecycle_stage", "lifecycle_stage"),
        # Per-org customer numbering; each org maintains its own sequence
        # starting at 50001.
        UniqueConstraint("organization_id", "customer_number", name="uq_customers_org_customer_number"),
    )

    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    status: Mapped[CustomerStatus] = mapped_column(
        Enum(CustomerStatus, name="customer_status_enum"),
        nullable=False,
        default=CustomerStatus.prospect,
    )

    # Phase 3 — full customer lifecycle.
    lifecycle_stage: Mapped[CustomerLifecycleStage] = mapped_column(
        Enum(CustomerLifecycleStage, name="customer_lifecycle_stage_enum"),
        nullable=False,
        default=CustomerLifecycleStage.onboarding,
    )
    # Per-org sequence (50001+). Uniqueness is enforced by the composite
    # `uq_customers_org_customer_number` constraint in __table_args__.
    customer_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    onboarding_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    renewal_due_at: Mapped[date | None] = mapped_column(nullable=True, index=True)
    ltv: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    churn_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    original_owner_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    current_owner_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Tracks the originating Lead (if any) that this Customer was promoted from.
    source_lead_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("leads.id", ondelete="SET NULL", use_alter=True, name="fk_customers_source_lead"),
        nullable=True,
        index=True,
    )

    leads = relationship(
        "Lead",
        back_populates="customer",
        foreign_keys="Lead.customer_id",
    )
    # `selectin` (separate SELECT) — a LEFT JOIN would compose poorly with
    # the tenancy filter's `with_loader_criteria` on `leads_1.organization_id`,
    # because the NULL row from a missing join fails the equality check and
    # drops the parent customer.
    source_lead = relationship(
        "Lead",
        foreign_keys=[source_lead_id],
        lazy="selectin",
    )
    deals = relationship("Deal", back_populates="customer")
    activities = relationship("Activity", back_populates="customer")
    delivery_logs = relationship(
        "DeliveryLog",
        back_populates="customer",
        cascade="all, delete-orphan",
    )
    renewals = relationship(
        "Renewal",
        back_populates="customer",
        cascade="all, delete-orphan",
    )
    referrals = relationship(
        "Referral",
        back_populates="referring_customer",
        foreign_keys="Referral.referring_customer_id",
        cascade="all, delete-orphan",
    )
