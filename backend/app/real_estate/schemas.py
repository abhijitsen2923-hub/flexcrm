"""Real estate Pydantic schemas."""
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field, computed_field

from app.database.enums import BookingStatus, SiteVisitFeedback, UnitStatus, UnitType
from app.schemas.common import ORMModel
from app.schemas.customer import CustomerCompact


PaymentMode = Literal["upi", "neft", "cheque", "cash", "card", "other"]


class UnitRead(ORMModel):
    id: UUID
    project_id: UUID
    tower_id: UUID
    floor: int
    unit_number: str
    unit_type: str = "residential"
    area: Decimal
    area_unit: str
    facing: str | None = None
    view: str | None = None
    base_price: Decimal
    status: UnitStatus
    created_at: datetime
    updated_at: datetime


class UnitStatusUpdate(ORMModel):
    status: UnitStatus


class TowerRead(ORMModel):
    id: UUID
    project_id: UUID
    name: str
    total_floors: int
    units: list[UnitRead] = []
    created_at: datetime
    updated_at: datetime


# Garage / parking types a project offers (Multi-Level, Covered, Independent, Open).
GarageOption = Literal["MLP", "CP", "IP", "OP"]


class ProjectDetailsMixin(ORMModel):
    """Phase-B project detail + default box-price fields — shared, all optional,
    so ProjectRead exposes them and ProjectCreate/Update accept them uniformly."""
    pin_code: str | None = Field(default=None, max_length=12)
    landmark: str | None = Field(default=None, max_length=255)
    total_towers: int | None = Field(default=None, ge=0)
    total_floors: int | None = Field(default=None, ge=0)
    flats_per_floor: int | None = Field(default=None, ge=0)
    total_garages: int | None = Field(default=None, ge=0)
    garage_options: list[GarageOption] | None = None
    # Default box-price components (₹). rate_* are per-sqft; the rest are lump sums.
    rate_a: Decimal | None = Field(default=None, ge=0)
    rate_b: Decimal | None = Field(default=None, ge=0)
    rate_c: Decimal | None = Field(default=None, ge=0)
    parking_cost: Decimal | None = Field(default=None, ge=0)
    legal_fees: Decimal | None = Field(default=None, ge=0)
    overhead_cost: Decimal | None = Field(default=None, ge=0)
    other_charges: Decimal | None = Field(default=None, ge=0)
    sinking_fund: Decimal | None = Field(default=None, ge=0)
    amenities_charges: Decimal | None = Field(default=None, ge=0)


class ProjectRead(ProjectDetailsMixin):
    id: UUID
    name: str
    builder_name: str
    location: str
    city: str
    rera_number: str | None = None
    created_at: datetime
    updated_at: datetime


class ProjectMediaRead(ORMModel):
    id: UUID
    type: str          # ← ProjectMedia.media_type (via model property)
    url: str           # ← presigned GET URL (via model property); "" if storage unconfigured
    label: str | None = None


class ProjectWithTowersRead(ProjectRead):
    towers: list[TowerRead] = []
    media: list[ProjectMediaRead] = []


class ProjectCreate(ProjectDetailsMixin):
    name: str = Field(min_length=1, max_length=255)
    builder_name: str = Field(min_length=1, max_length=255)
    location: str = Field(min_length=1, max_length=255)
    city: str = Field(min_length=1, max_length=100)
    rera_number: str | None = Field(default=None, max_length=64)


class ProjectUpdate(ProjectDetailsMixin):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    builder_name: str | None = Field(default=None, min_length=1, max_length=255)
    location: str | None = Field(default=None, min_length=1, max_length=255)
    city: str | None = Field(default=None, min_length=1, max_length=100)
    rera_number: str | None = Field(default=None, max_length=64)


class TowerCreate(ORMModel):
    name: str = Field(min_length=1, max_length=100)
    total_floors: int = Field(ge=1, le=200)


class TowerUpdate(ORMModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    total_floors: int | None = Field(default=None, ge=1, le=200)


class UnitUpdate(ORMModel):
    unit_number: str | None = Field(default=None, min_length=1, max_length=20)
    unit_type: UnitType | None = None
    area: Decimal | None = Field(default=None, gt=0)
    area_unit: str | None = Field(default=None, max_length=20)
    facing: str | None = Field(default=None, max_length=50)
    view: str | None = Field(default=None, max_length=100)
    base_price: Decimal | None = Field(default=None, ge=0)


class FloorUnits(ORMModel):
    """How many units to create on one floor."""
    floor: int = Field(ge=0)
    count: int = Field(ge=1, le=200)


class UnitBatchCreate(ORMModel):
    """Create a batch of same-type units across floors. The client expands a
    'same on every floor' choice into the explicit `floors` list."""
    unit_type: UnitType = UnitType.residential
    floors: list[FloorUnits] = Field(min_length=1)
    area: Decimal = Field(gt=0)
    base_price: Decimal = Field(ge=0)
    area_unit: str = Field(default="sqft", max_length=20)
    facing: str | None = Field(default=None, max_length=50)
    unit_prefix: str | None = Field(default=None, max_length=8)


class ProjectTowerCreate(ORMModel):
    """One tower + its (optional) unit batch, for the combined Add-Project form."""
    name: str = Field(min_length=1, max_length=100)
    total_floors: int = Field(ge=1, le=200)
    units: UnitBatchCreate | None = None


class ProjectFullCreate(ProjectCreate):
    """Create a project together with its towers and each tower's units in one
    atomic call (the combined Add-Project wizard)."""
    towers: list[ProjectTowerCreate] = Field(default_factory=list)


class SiteVisitProjectMini(ORMModel):
    id: UUID
    name: str


class SiteVisitLeadMini(ORMModel):
    id: UUID
    lead_number: int
    contact_name: str
    contact_phone: str | None = None


class SiteVisitRead(ORMModel):
    id: UUID
    lead_id: UUID | None = None
    project_id: UUID
    scheduled_at: datetime
    assigned_to_id: UUID | None = None
    feedback: SiteVisitFeedback | None = None
    attended: bool | None = None
    notes: str | None = None
    status: str = "scheduled"
    created_at: datetime
    updated_at: datetime
    project: SiteVisitProjectMini | None = None
    lead: SiteVisitLeadMini | None = None


class SiteVisitCreate(ORMModel):
    lead_id: UUID | None = None
    project_id: UUID
    scheduled_at: datetime
    assigned_to_id: UUID | None = None
    notes: str | None = None


class SiteVisitUpdate(ORMModel):
    feedback: SiteVisitFeedback | None = None
    attended: bool | None = None
    notes: str | None = None
    # Reschedule / reassign / cancel.
    scheduled_at: datetime | None = None
    assigned_to_id: UUID | None = None
    status: Literal["scheduled", "completed", "cancelled"] | None = None


class BookingKycDocRead(ORMModel):
    id: UUID
    booking_id: UUID
    doc_type: str
    file_path: str | None = None
    created_at: datetime


class BookingKycDocCreate(ORMModel):
    doc_type: str = Field(min_length=1, max_length=64)
    file_path: str | None = Field(default=None, max_length=512)


class PaymentScheduleRead(ORMModel):
    id: UUID
    booking_id: UUID
    installment_name: str
    due_date: date
    demand_amount: Decimal
    paid_amount: Decimal
    outstanding: Decimal
    created_at: datetime

    # Overdue is time-dependent — derive it at read time from the parsed fields
    # rather than trusting the stored column (which goes stale between writes).
    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_overdue(self) -> bool:
        return self.outstanding > 0 and self.due_date < date.today()


class PaymentScheduleCreate(ORMModel):
    installment_name: str = Field(min_length=1, max_length=120)
    due_date: date
    demand_amount: Decimal = Field(ge=0)
    paid_amount: Decimal = Field(default=Decimal("0"), ge=0)


class PaymentReceiptRead(ORMModel):
    id: UUID
    booking_id: UUID
    schedule_id: UUID | None = None
    amount: Decimal
    paid_on: date
    mode: str
    reference: str | None = None
    notes: str | None = None
    created_at: datetime


class PaymentPlanInstallment(ORMModel):
    installment_name: str = Field(min_length=1, max_length=120)
    due_date: date
    # Amount is either an explicit rupee value OR a percentage of the booking's
    # total consideration (server computes the amount). At least one is required.
    amount: Decimal | None = Field(default=None, ge=0)
    percentage: Decimal | None = Field(default=None, ge=0, le=100)


class PaymentPlanCreate(ORMModel):
    installments: list[PaymentPlanInstallment] = Field(min_length=1)


class PaymentReceiptCreate(ORMModel):
    schedule_id: UUID | None = None
    amount: Decimal = Field(gt=0)
    paid_on: date
    mode: PaymentMode
    reference: str | None = Field(default=None, max_length=120)
    notes: str | None = None


class BookingRefundRead(ORMModel):
    id: UUID
    booking_id: UUID
    gross_paid: Decimal
    deduction_amount: Decimal
    refund_amount: Decimal
    mode: str
    refunded_on: date
    reference: str | None = None
    reason: str | None = None
    created_at: datetime


class BookingRefundCreate(ORMModel):
    # gross_paid + refund_amount are computed server-side from recorded receipts;
    # the client only supplies the withheld deduction and the payout details.
    deduction_amount: Decimal = Field(default=Decimal("0"), ge=0)
    mode: PaymentMode
    refunded_on: date
    reference: str | None = Field(default=None, max_length=120)
    reason: str | None = Field(default=None, max_length=500)


class BookingUnitInfo(ORMModel):
    """Unit details + site (project) and tower names for a purchase card."""
    id: UUID
    unit_number: str
    floor: int
    unit_type: str = "residential"
    area: Decimal
    area_unit: str
    base_price: Decimal
    status: UnitStatus
    tower_name: str | None = None
    project_name: str | None = None


class BookingRead(ORMModel):
    id: UUID
    unit_id: UUID
    lead_id: UUID | None = None
    customer_id: UUID | None = None
    unit: BookingUnitInfo | None = None
    step: int
    status: BookingStatus
    pricing_snapshot: dict | None = None
    scheduled_date: date | None = None
    possession_checklist: list[bool] | None = None
    cancellation_reason: str | None = None
    registration_number: str | None = None
    sub_registrar_office: str | None = None
    created_at: datetime
    updated_at: datetime
    customer: CustomerCompact | None = None
    kyc_documents: list[BookingKycDocRead] = []
    payment_schedules: list[PaymentScheduleRead] = []
    payment_receipts: list[PaymentReceiptRead] = []
    refunds: list[BookingRefundRead] = []


class BookingCreate(ORMModel):
    unit_id: UUID
    lead_id: UUID | None = None
    customer_id: UUID | None = None


class BookingStepAdvance(ORMModel):
    customer_id: UUID | None = None
    pricing_snapshot: dict | None = None
    scheduled_date: date | None = None
    payment_schedules: list[PaymentScheduleCreate] = []
    # Only an explicit confirm (step 4) finalizes the booking + books the unit.
    # Saving the date for a document preview passes confirm=False.
    confirm: bool = False


class BookingCancel(ORMModel):
    reason: str | None = Field(default=None, max_length=500)


class BookingRegister(ORMModel):
    registration_date: date
    registration_number: str | None = Field(default=None, max_length=120)
    sub_registrar_office: str | None = Field(default=None, max_length=255)


class PricingUpdate(ORMModel):
    pricing_snapshot: dict


class PossessionChecklistUpdate(ORMModel):
    checklist: list[bool]


class CollectionLedgerEntry(ORMModel):
    payment_schedule_id: UUID
    booking_id: UUID
    installment_name: str
    due_date: date
    demand_amount: Decimal
    paid_amount: Decimal
    outstanding: Decimal
    is_overdue: bool
    project_name: str
    unit_number: str
    status: BookingStatus
