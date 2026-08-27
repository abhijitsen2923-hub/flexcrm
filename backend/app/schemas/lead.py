from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import EmailStr, Field

from app.database.enums import LeadIndustry
from app.schemas.common import ORMModel, SearchSortParams
from app.schemas.customer import CustomerCompact
from app.schemas.stage_transition import MIN_COMMENT_LENGTH
from app.schemas.user import UserSummary


class LeadCreate(ORMModel):
    # Optional in the API: if omitted, the service falls back to the current
    # user's `business_type` (chosen at registration). Explicit only for
    # admins/managers who need to create leads outside their own vertical.
    industry: LeadIndustry | None = None
    title: str = Field(min_length=1, max_length=255)
    salutation: str | None = Field(default=None, max_length=16)
    # Contact fields live on the Lead so a prospect can be captured before
    # a Customer record exists. `contact_name` is the only required identity
    # field; the others are optional and populate the auto-created Customer
    # on Sold.
    contact_name: str = Field(min_length=1, max_length=255)
    # Primary phone is mandatory on capture (all verticals); email is optional
    # (many walk-in / call / WhatsApp leads have a phone but no email); a second
    # phone is optional. Enforced here so both the New Lead form and the CSV
    # importer apply the same rules.
    contact_email: EmailStr | None = None
    contact_phone: str = Field(min_length=1, max_length=32)
    contact_phone_alt: str | None = Field(default=None, max_length=32)
    company_name: str | None = Field(default=None, max_length=255)
    # Legacy attach-to-existing-customer flow is still supported by passing
    # an existing customer_id. If null, a new Customer is materialized on Sold.
    customer_id: UUID | None = None
    value: Decimal = Field(default=Decimal("0"), ge=0)
    # ISO 4217 currency code. Validated against the org's allow-list in the
    # service layer. Defaults to INR (the vertical default for both Education
    # and Travel orgs).
    currency: str = Field(default="INR", min_length=3, max_length=3)
    probability: int = Field(default=0, ge=0, le=100)
    expected_close_date: date | None = None
    source: str | None = Field(default=None, max_length=120)
    campaign: str | None = Field(default=None, max_length=120)
    interest: str | None = Field(default=None, max_length=255)
    assigned_to_id: UUID | None = None
    # Referring channel partner (broker), if this walk-in came via one.
    partner_id: UUID | None = None
    property_type: str | None = Field(default=None, max_length=64)
    budget_min: Decimal | None = Field(default=None, ge=0)
    budget_max: Decimal | None = Field(default=None, ge=0)
    preferred_location: str | None = Field(default=None, max_length=255)
    possession_preference: str | None = Field(default=None, max_length=64)
    notes: str | None = None


class LeadUpdate(ORMModel):
    """Patch payload — note that `stage_code` is intentionally absent.

    Stage transitions are gated through `POST /leads/{id}/transitions` so every
    move carries a mandatory comment (per spec §3.2). Sending `stage_code` here
    is rejected at the router with a 400 hint.
    """
    customer_id: UUID | None = None
    title: str | None = Field(default=None, min_length=1, max_length=255)
    salutation: str | None = Field(default=None, max_length=16)
    industry: LeadIndustry | None = None
    contact_name: str | None = Field(default=None, min_length=1, max_length=255)
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(default=None, max_length=32)
    contact_phone_alt: str | None = Field(default=None, max_length=32)
    company_name: str | None = Field(default=None, max_length=255)
    value: Decimal | None = Field(default=None, ge=0)
    probability: int | None = Field(default=None, ge=0, le=100)
    expected_close_date: date | None = None
    source: str | None = Field(default=None, max_length=120)
    campaign: str | None = Field(default=None, max_length=120)
    interest: str | None = Field(default=None, max_length=255)
    assigned_to_id: UUID | None = None
    partner_id: UUID | None = None
    property_type: str | None = Field(default=None, max_length=64)
    budget_min: Decimal | None = Field(default=None, ge=0)
    budget_max: Decimal | None = Field(default=None, ge=0)
    preferred_location: str | None = Field(default=None, max_length=255)
    possession_preference: str | None = Field(default=None, max_length=64)
    notes: str | None = None


class LeadBulkReassign(ORMModel):
    lead_ids: list[UUID] = Field(min_length=1)
    assigned_to_id: UUID


class LeadBulkTransition(ORMModel):
    """Move many leads to the same stage in one action. Each lead still goes
    through the full single-lead transition (mandatory comment, role/backward
    gates, side effects), so the shared comment must clear the ≥10-char floor."""
    lead_ids: list[UUID] = Field(min_length=1, max_length=200)
    to_stage_code: str = Field(min_length=1, max_length=64)
    comment: str = Field(min_length=MIN_COMMENT_LENGTH, max_length=4000)
    next_action_date: datetime | None = None


class LeadBulkActionResult(ORMModel):
    """Per-lead outcome summary for a bulk action — some leads may be rejected
    (e.g. a backward move a rep can't make) while the rest succeed."""
    updated: int
    failed: int
    # A few human-readable failure reasons (deduped, capped) for a toast.
    errors: list[str] = []


class LeadCallLogCreate(ORMModel):
    # "dnp" (did-not-pick) stacks like follow_up — only first_call is idempotent.
    call_type: Literal["first_call", "follow_up", "dnp"]
    notes: str | None = Field(default=None, max_length=500)
    # Optional next-call date scheduled from this call (denormalized onto the lead).
    next_action_date: datetime | None = None


class LeadCallLogRead(ORMModel):
    id: UUID
    lead_id: UUID
    user_id: UUID
    call_type: str
    notes: str | None = None
    next_action_date: datetime | None = None
    created_at: datetime
    user: UserSummary | None = None


class LeadPartnerCompact(ORMModel):
    """Just enough of the referring partner to label a lead."""
    id: UUID
    company_name: str
    contact_name: str


class LeadRead(ORMModel):
    id: UUID
    customer_id: UUID | None = None
    industry: LeadIndustry
    stage_code: str
    lead_number: int
    title: str
    salutation: str | None = None
    contact_name: str
    contact_email: EmailStr | None = None
    contact_phone: str | None = None
    contact_phone_alt: str | None = None
    company_name: str | None = None
    value: Decimal
    currency: str = "INR"
    probability: int
    expected_close_date: date | None = None
    source: str | None = None
    campaign: str | None = None
    # External provenance (set only on ingested leads): which connector and the
    # portal's own id (e.g. the 99acres lead_id). Surfaced in the lead detail.
    source_provider: str | None = None
    external_id: str | None = None
    interest: str | None = None
    last_comment_preview: str | None = None
    last_comment_at: datetime | None = None
    next_action_date: datetime | None = None
    stage_changed_at: datetime | None = None
    assigned_to_id: UUID | None = None
    partner_id: UUID | None = None
    property_type: str | None = None
    budget_min: Decimal | None = None
    budget_max: Decimal | None = None
    preferred_location: str | None = None
    possession_preference: str | None = None
    notes: str | None = None
    created_by_id: UUID | None = None
    updated_by_id: UUID | None = None
    created_at: datetime
    updated_at: datetime
    customer: CustomerCompact | None = None
    assigned_to: UserSummary | None = None
    partner: LeadPartnerCompact | None = None
    # True when another active lead in the tenant shares this lead's email or
    # phone — surfaced as a "!" marker in the list so duplicates are visible.
    # Computed at list time (not stored); defaults False for single-lead reads.
    is_duplicate: bool = False


class LeadDuplicate(ORMModel):
    """Lightweight match returned by the duplicate-check endpoint."""
    id: UUID
    lead_number: int
    title: str
    contact_name: str
    contact_email: EmailStr | None = None
    contact_phone: str | None = None
    stage_code: str


class LeadFilterParams(SearchSortParams):
    customer_id: UUID | None = None
    industry: LeadIndustry | None = None
    stage_code: str | None = None  # single code, or comma-joined for multi-select → IN (...)
    source: str | None = None
    campaign: str | None = None
    assigned_to_id: UUID | None = None
    partner_id: UUID | None = None
    # Filter to leads whose next action (call/follow-up) is due within a datetime
    # range. The client sends the selected LOCAL day's UTC boundaries (tz-correct),
    # so `next_action_from <= next_action_date < next_action_to`.
    next_action_from: datetime | None = None
    next_action_to: datetime | None = None
    # Filter to leads whose LATEST stage change falls within a datetime range
    # (client sends local-day UTC boundaries, half-open like next_action_*):
    # `stage_changed_from <= stage_changed_at < stage_changed_to`.
    stage_changed_from: datetime | None = None
    stage_changed_to: datetime | None = None
