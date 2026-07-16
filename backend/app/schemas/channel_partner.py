"""Channel-partner (broker) schemas."""
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import EmailStr, Field

from app.schemas.common import ORMModel

BrokerageType = Literal["percent", "flat"]
PayoutStatus = Literal["accrued", "paid", "reversed"]


class ChannelPartnerBase(ORMModel):
    company_name: str = Field(min_length=1, max_length=255)
    contact_name: str = Field(min_length=1, max_length=255)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=255)
    rera_number: str | None = Field(default=None, max_length=64)
    pan: str | None = Field(default=None, max_length=20)
    brokerage_type: BrokerageType = "percent"
    brokerage_rate: Decimal = Field(default=Decimal("0"), ge=0)
    payout_bank_account: str | None = Field(default=None, max_length=64)
    payout_ifsc: str | None = Field(default=None, max_length=20)
    payout_upi: str | None = Field(default=None, max_length=120)
    is_active: bool = True


class ChannelPartnerCreate(ChannelPartnerBase):
    # Optionally link an existing broker login (public.users) so the partner can
    # sign into the portal. Left null → profile-only until a login is attached.
    user_id: UUID | None = None


class ChannelPartnerUpdate(ORMModel):
    company_name: str | None = Field(default=None, min_length=1, max_length=255)
    contact_name: str | None = Field(default=None, min_length=1, max_length=255)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=255)
    rera_number: str | None = Field(default=None, max_length=64)
    pan: str | None = Field(default=None, max_length=20)
    brokerage_type: BrokerageType | None = None
    brokerage_rate: Decimal | None = Field(default=None, ge=0)
    payout_bank_account: str | None = Field(default=None, max_length=64)
    payout_ifsc: str | None = Field(default=None, max_length=20)
    payout_upi: str | None = Field(default=None, max_length=120)
    is_active: bool | None = None
    user_id: UUID | None = None


class ChannelPartnerRead(ORMModel):
    """Non-sensitive partner view returned to any _VIEW role (incl. analyst).
    Deliberately OMITS PAN + payout bank/UPI details — those are PII/financial
    and only surface via the USER_MANAGE-gated `ChannelPartnerFull`."""
    id: UUID
    user_id: UUID | None = None
    company_name: str
    contact_name: str
    phone: str | None = None
    email: str | None = None
    rera_number: str | None = None
    brokerage_type: BrokerageType = "percent"
    brokerage_rate: Decimal = Decimal("0")
    is_active: bool = True
    created_at: datetime
    updated_at: datetime


class ChannelPartnerFull(ChannelPartnerRead):
    """Full record incl. PAN + payout details — only for editing (USER_MANAGE)."""
    pan: str | None = None
    payout_bank_account: str | None = None
    payout_ifsc: str | None = None
    payout_upi: str | None = None


class ChannelPartnerStats(ORMModel):
    """Per-partner performance rollup for the roster + dashboard."""
    leads_total: int = 0
    leads_active: int = 0
    leads_sold: int = 0
    conversion_rate: float = 0.0  # sold / total, 0..1
    brokerage_accrued: Decimal = Decimal("0")
    brokerage_paid: Decimal = Decimal("0")
    brokerage_outstanding: Decimal = Decimal("0")


class ChannelPartnerListItem(ChannelPartnerRead):
    stats: ChannelPartnerStats = ChannelPartnerStats()


class BrokeragePayoutRead(ORMModel):
    id: UUID
    partner_id: UUID
    lead_id: UUID | None = None
    sales_order_id: UUID | None = None
    deal_value: Decimal | None = None
    rate_type: str
    rate_snapshot: Decimal
    amount: Decimal
    status: str
    note: str | None = None
    paid_on: date | None = None
    created_at: datetime


class BrokeragePayoutUpdate(ORMModel):
    status: PayoutStatus
    paid_on: date | None = None
    note: str | None = None


class PartnerStageCount(ORMModel):
    stage_code: str
    label: str
    count: int


class PartnerLeadRow(ORMModel):
    """Compact lead view for the partner's own tracker (no PII of other partners)."""
    id: UUID
    lead_number: int
    title: str
    contact_name: str
    stage_code: str
    property_type: str | None = None
    preferred_location: str | None = None
    budget_min: Decimal | None = None
    budget_max: Decimal | None = None
    created_at: datetime


class PartnerDashboard(ORMModel):
    partner: ChannelPartnerRead
    stats: ChannelPartnerStats
    stage_breakdown: list[PartnerStageCount] = []
    recent_payouts: list[BrokeragePayoutRead] = []


class PartnerLeadSubmit(ORMModel):
    """Payload a logged-in broker uses to refer a new lead. Industry, source and
    partner attribution are forced server-side — the broker only sends contact +
    requirement details."""
    title: str | None = Field(default=None, max_length=255)
    contact_name: str = Field(min_length=1, max_length=255)
    contact_email: EmailStr
    contact_phone: str = Field(min_length=3, max_length=32)
    property_type: str | None = Field(default=None, max_length=64)
    preferred_location: str | None = Field(default=None, max_length=255)
    budget_min: Decimal | None = Field(default=None, ge=0)
    budget_max: Decimal | None = Field(default=None, ge=0)
    interest: str | None = Field(default=None, max_length=255)
    notes: str | None = None
