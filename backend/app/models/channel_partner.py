"""Channel-partner (broker) domain models — per-tenant schema.

A ChannelPartner is a first-class profile for a real-estate broker who refers
leads. It links (optionally) to a broker login `User` via `user_id`, but keeps
its own contact / KYC / brokerage fields so a partner can exist before a login
is provisioned. `BrokeragePayout` records the brokerage a partner earns when one
of their referred leads is Sold (auto-accrued from the partner's rate).

No cross-registry relationship to `public.users` is declared here — `user_id`
is a plain column resolved on demand — so these mappers stay init-safe.
"""
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, Date, ForeignKey, Index, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import TenantBase
from app.models.base import (
    TenantAuditMixin,
    TenantSoftDeleteMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class ChannelPartner(TenantBase, UUIDPrimaryKeyMixin, TimestampMixin, TenantAuditMixin, TenantSoftDeleteMixin):
    __tablename__ = "channel_partners"
    __table_args__ = (
        Index("ix_channel_partners_user_id", "user_id"),
        {"schema": "tenant"},
    )

    # The broker's login (public.users). Nullable so a partner profile can be
    # created before / without provisioning a portal login. Plain column (no ORM
    # relationship) to avoid a tenant→public cross-registry mapper dependency.
    user_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("public.users.id", ondelete="SET NULL"), nullable=True
    )
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rera_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pan: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Brokerage: percent (of deal value) or a flat amount per closed deal.
    brokerage_type: Mapped[str] = mapped_column(String(10), nullable=False, server_default="percent")
    brokerage_rate: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, server_default="0")

    # Payout details (free-text; no validation beyond length).
    payout_bank_account: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payout_ifsc: Mapped[str | None] = mapped_column(String(20), nullable=True)
    payout_upi: Mapped[str | None] = mapped_column(String(120), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    payouts: Mapped[list["BrokeragePayout"]] = relationship(
        "BrokeragePayout",
        back_populates="partner",
        cascade="all, delete-orphan",
        order_by="BrokeragePayout.created_at.desc()",
    )


class BrokeragePayout(TenantBase, UUIDPrimaryKeyMixin, TimestampMixin):
    """Brokerage a partner earns on a Sold referral. Auto-accrued from the
    partner's rate at Sold; accounts later marks it paid."""
    __tablename__ = "brokerage_payouts"
    __table_args__ = (
        Index("ix_brokerage_payouts_partner", "partner_id"),
        Index("ix_brokerage_payouts_lead", "lead_id"),
        {"schema": "tenant"},
    )

    partner_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("channel_partners.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lead_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("leads.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Sales order that closed the deal (plain column — finance lives in the same
    # tenant schema but we avoid coupling the FK graph across domains).
    sales_order_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    deal_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    rate_type: Mapped[str] = mapped_column(String(10), nullable=False)  # percent | flat
    rate_snapshot: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    # accrued | paid | reversed — validated app-side.
    status: Mapped[str] = mapped_column(String(12), nullable=False, server_default="accrued")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    paid_on: Mapped[date | None] = mapped_column(Date, nullable=True)

    partner: Mapped["ChannelPartner"] = relationship("ChannelPartner", back_populates="payouts")
