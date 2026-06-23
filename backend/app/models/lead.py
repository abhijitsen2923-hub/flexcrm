from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import TenantBase
from app.database.enums import LeadIndustry
from app.models.user import User  # direct ref to avoid cross-registry string lookup
from app.models.base import TenantAuditMixin, TenantSoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Lead(TenantBase, UUIDPrimaryKeyMixin, TimestampMixin, TenantAuditMixin, TenantSoftDeleteMixin):
    __tablename__ = "leads"
    __table_args__ = (
        CheckConstraint("probability >= 0 AND probability <= 100", name="ck_leads_probability_range"),
        CheckConstraint("value >= 0", name="ck_leads_value_non_negative"),
        # Composite FK validates (industry, stage_code) against public.pipeline_stages.
        ForeignKeyConstraint(
            ["industry", "stage_code"],
            ["public.pipeline_stages.industry", "public.pipeline_stages.code"],
            name="fk_leads_pipeline_stage",
            ondelete="RESTRICT",
        ),
        # Per-tenant lead numbering: schema isolation ensures no collision across orgs.
        UniqueConstraint("lead_number", name="uq_leads_lead_number"),
        Index("ix_leads_industry_stage_code", "industry", "stage_code"),
        Index("ix_leads_stage_assigned_to", "stage_code", "assigned_to_id"),
        {"schema": "tenant"},
    )

    customer_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    industry: Mapped[LeadIndustry] = mapped_column(
        Enum(LeadIndustry, name="lead_industry_enum"),
        nullable=False,
        index=True,
    )
    stage_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    lead_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    probability: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expected_close_date: Mapped[date | None] = mapped_column(nullable=True, index=True)
    source: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    interest: Mapped[str | None] = mapped_column(String(255), nullable=True)

    contact_name: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    contact_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    last_comment_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_comment_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    assigned_to_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("public.users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    batch_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    property_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    budget_min: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    budget_max: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    preferred_location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    possession_preference: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    customer = relationship(
        "Customer",
        back_populates="leads",
        foreign_keys=[customer_id],
        post_update=True,
    )
    assigned_to = relationship(User, foreign_keys=[assigned_to_id])
    stage_transitions = relationship(
        "StageTransition",
        back_populates="lead",
        cascade="all, delete-orphan",
        order_by="StageTransition.performed_at.desc()",
    )
    documents = relationship(
        "LeadDocument",
        back_populates="lead",
        cascade="all, delete-orphan",
    )
