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

from app.core.tenancy import OrgScopedMixin
from app.database.base import Base
from app.database.enums import LeadIndustry
from app.models.base import AuditMixin, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Lead(Base, UUIDPrimaryKeyMixin, TimestampMixin, AuditMixin, SoftDeleteMixin, OrgScopedMixin):
    __tablename__ = "leads"
    __table_args__ = (
        CheckConstraint("probability >= 0 AND probability <= 100", name="ck_leads_probability_range"),
        CheckConstraint("value >= 0", name="ck_leads_value_non_negative"),
        # Composite FK validates (industry, stage_code) against pipeline_stages.
        ForeignKeyConstraint(
            ["industry", "stage_code"],
            ["pipeline_stages.industry", "pipeline_stages.code"],
            name="fk_leads_pipeline_stage",
            ondelete="RESTRICT",
        ),
        # Per-org lead numbering: each org starts at 89001 and increments
        # independently. The constraint is composite so org-A #89001 and
        # org-B #89001 are both valid.
        UniqueConstraint("organization_id", "lead_number", name="uq_leads_org_lead_number"),
        Index("ix_leads_industry_stage_code", "industry", "stage_code"),
        Index("ix_leads_stage_assigned_to", "stage_code", "assigned_to_id"),
    )

    # `customer_id` is now nullable: a Lead is the entry point of the funnel,
    # and the Customer row is auto-materialized when the lead reaches the
    # industry's "sold" stage. The legacy path (Customer created manually
    # first, then attached to a Lead) is still supported by setting this at
    # create time.
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
    # Per-org sequence; uniqueness is enforced by the composite constraint
    # `uq_leads_org_lead_number` declared in __table_args__.
    lead_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    # ISO 4217 currency code. The per-org allow-list lives in
    # `app.core.currencies.allowed_currencies_for_org`. Defaults to INR; the
    # auto-promotion service copies this through to SalesOrder.currency.
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    probability: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expected_close_date: Mapped[date | None] = mapped_column(nullable=True, index=True)
    source: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    # "Course / Destination" in the spec — label varies by industry on the UI side.
    interest: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Contact info embedded on the Lead so a prospect can be captured without
    # pre-creating a Customer. When the lead reaches Sold, the auto-promotion
    # service copies these into a new Customer row.
    contact_name: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    contact_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Denormalized snapshot of the latest StageTransition for cheap list-view rendering.
    last_comment_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_comment_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    assigned_to_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # `post_update=True` breaks the Lead ↔ Customer FK cycle: Customer holds a
    # `source_lead_id` back-reference, so SQLAlchemy can't decide which row to
    # INSERT first. With post_update, the Lead's customer_id assignment is
    # issued as a separate UPDATE after both rows exist.
    # Phase 2: Education-specific identifier captured at Sold (e.g. batch
    # number / cohort code). Free-form string. Optional — only meaningful for
    # education industry, set via the StageTransitionModal's extra field.
    batch_code: Mapped[str | None] = mapped_column(String(64), nullable=True)

    customer = relationship(
        "Customer",
        back_populates="leads",
        foreign_keys=[customer_id],
        post_update=True,
    )
    assigned_to = relationship("User", back_populates="assigned_leads", foreign_keys=[assigned_to_id])
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
