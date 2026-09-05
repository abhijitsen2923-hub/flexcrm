from datetime import UTC, date, datetime
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
    text,
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
        # Idempotency anchor for externally-ingested leads (e.g. Meta Lead Ads):
        # the same (provider, external_id) can be ingested only once. Partial so it
        # only applies to rows that actually carry an external id.
        Index(
            "uq_leads_provider_external_id",
            "source_provider",
            "external_id",
            unique=True,
            postgresql_where=text("external_id IS NOT NULL"),
        ),
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
    # Contact salutation (Mr / Mrs / Ms / Master) — free string, validated app-side.
    salutation: Mapped[str | None] = mapped_column(String(16), nullable=True)
    value: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    probability: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expected_close_date: Mapped[date | None] = mapped_column(nullable=True, index=True)
    source: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    # Marketing campaign this lead is attributed to (free string, controlled list
    # app-side) — a secondary attribution dimension alongside source.
    campaign: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    interest: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # External provenance for leads ingested from an outside source (e.g. Meta
    # Lead Ads). `external_id` is the provider's own record id (the Meta
    # leadgen_id); the partial-unique (source_provider, external_id) index above
    # makes re-ingesting the same record a no-op. Null for manually-created leads.
    source_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    contact_name: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    contact_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Optional secondary phone. Nullable in the DB (older rows predate it and
    # it's optional on capture); the API/UI make the primary phone mandatory.
    contact_phone_alt: Mapped[str | None] = mapped_column(String(32), nullable=True)
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    last_comment_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_comment_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Denormalized from the lead's LATEST stage transition (mirrors last_comment_*):
    # the next scheduled call/follow-up, used by the leads "due on a day" filter and
    # the follow-up reminders job. Nullable when no action is scheduled.
    next_action_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    # Timestamp of the lead's LATEST stage change (set on every stage move + the
    # initial seed). Unlike last_comment_at (bumped by DNP/call-logs), this is a
    # pure stage-change stamp — drives the leads "stage changed between" range filter.
    # The default stamps creation time for any lead built WITHOUT going through
    # seed_initial_transition (e.g. customer-portal referrals), so it's never NULL.
    stage_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True, default=lambda: datetime.now(UTC)
    )

    assigned_to_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("public.users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Channel partner (broker) who referred this lead, if any. Same-schema FK, so
    # a plain string relationship resolves fine (unlike the public.users links).
    partner_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("channel_partners.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # "Others / owner's reference" sale: when true, NO incentive accrues on Sold —
    # neither internal commission (to assigned_to_id) nor channel-partner brokerage.
    incentive_exempt: Mapped[bool] = mapped_column(
        nullable=False, server_default=text("false"), default=False
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
    # Cross-schema relationship to the public users table. The FK string
    # "public.users.id" registers a stub table in TenantBase.metadata that is
    # distinct from the real User mapper in Base.metadata, so SQLAlchemy can't
    # infer the join condition (NoForeignKeysError). Specify it explicitly.
    # viewonly because assignment is written via the assigned_to_id column.
    assigned_to = relationship(
        User,
        primaryjoin=lambda: Lead.assigned_to_id == User.id,
        foreign_keys=lambda: [Lead.assigned_to_id],
        viewonly=True,
    )
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
    call_logs = relationship(
        "LeadCallLog",
        back_populates="lead",
        cascade="all, delete-orphan",
        order_by="LeadCallLog.created_at",
    )
    # Read-only link to the referring channel partner (name on the lead card).
    partner = relationship("ChannelPartner", foreign_keys=[partner_id], viewonly=True)


class LeadCallLog(TenantBase, UUIDPrimaryKeyMixin, TimestampMixin):
    """A call logged by a specific user against a lead. Tracked per (lead, user)
    so a reassigned owner can record their own first call independently of the
    previous owner's."""
    __tablename__ = "lead_call_logs"
    __table_args__ = (
        Index("ix_lead_call_logs_lead", "lead_id"),
        {"schema": "tenant"},
    )

    lead_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("public.users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    call_type: Mapped[str] = mapped_column(String(20), nullable=False)  # first_call | follow_up | dnp
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Optional next-call date scheduled from this call (esp. a DNP → schedule a
    # callback). Denormalized onto lead.next_action_date so it feeds the leads
    # date-filter + follow-up reminders.
    next_action_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    lead = relationship("Lead", back_populates="call_logs")
    # Read-only link to the caller (name on the timeline). Lambda + imported User
    # to resolve the cross-registry (tenant → public.users) reference.
    user = relationship(
        User,
        primaryjoin=lambda: LeadCallLog.user_id == User.id,
        foreign_keys=lambda: [LeadCallLog.user_id],
        viewonly=True,
        lazy="selectin",
    )
