from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import TenantBase
from app.database.enums import CustomerLifecycleStage, CustomerStatus
from app.models.base import TenantAuditMixin, TenantSoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.user import User  # direct ref to avoid cross-registry string lookup


class Customer(TenantBase, UUIDPrimaryKeyMixin, TimestampMixin, TenantAuditMixin, TenantSoftDeleteMixin):
    __tablename__ = "customers"
    __table_args__ = (
        Index("ix_customers_company_name", "company_name"),
        Index("ix_customers_source_status", "source", "status"),
        Index("ix_customers_lifecycle_stage", "lifecycle_stage"),
        # Schema isolation removes the need for org_id in the uniqueness constraint.
        UniqueConstraint("customer_number", name="uq_customers_customer_number"),
        {"schema": "tenant"},
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

    lifecycle_stage: Mapped[CustomerLifecycleStage] = mapped_column(
        Enum(CustomerLifecycleStage, name="customer_lifecycle_stage_enum"),
        nullable=False,
        default=CustomerLifecycleStage.onboarding,
    )
    customer_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    onboarding_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    renewal_due_at: Mapped[date | None] = mapped_column(nullable=True, index=True)
    ltv: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    # Deal value snapshotted from the source lead at close/promotion (Phase C4).
    # Point-in-time — distinct from `ltv`, which is a running aggregate of
    # confirmed bookings/deals/renewals (often 0 at promotion, before any booking).
    sale_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    churn_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    original_owner_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("public.users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    current_owner_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("public.users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

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
    source_lead = relationship(
        "Lead",
        foreign_keys=[source_lead_id],
        lazy="selectin",
    )
    # Read-only link to the owning user (for display: owner name in Customer 360).
    # Uses lambda + imported User (not strings) because User lives in a different
    # declarative registry — a string primaryjoin can't resolve it (mapper init fails).
    current_owner = relationship(
        User,
        primaryjoin=lambda: Customer.current_owner_id == User.id,
        foreign_keys=lambda: [Customer.current_owner_id],
        viewonly=True,
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
