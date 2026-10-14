"""Real estate Pydantic schemas."""
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, computed_field, field_validator, model_validator

from app.database.enums import BookingStatus, InvoiceStatus, SiteVisitFeedback, UnitStatus, UnitType
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
    carpet_area: Decimal | None = None
    built_up_area: Decimal | None = None
    area_unit: str
    facing: str | None = None
    view: str | None = None
    base_price: Decimal
    status: UnitStatus
    flat_type: str | None = None
    configuration: str | None = None
    has_plc: bool = False
    created_at: datetime
    updated_at: datetime


class UnitStatusUpdate(ORMModel):
    status: UnitStatus


class TowerRead(ORMModel):
    id: UUID
    project_id: UUID
    name: str
    total_floors: int
    # The layout last saved from the project wizard (TowerLayout shape) — read back as a plain dict so a later
    # change to the layout schema can never make an older tower unreadable. None for pre-t048 towers.
    layout: dict | None = None
    units: list[UnitRead] = []
    created_at: datetime
    updated_at: datetime


# Garage / parking types a project offers (Multi-Level, Covered, Independent, Open). Kept to the original four:
# `garage_options` is also READ by builds older than t048, which would reject anything else.
GarageOption = Literal["MLP", "CP", "IP", "OP"]
# Every parking type a spot can be (adds Dependent Parking). Used for counts and prices — never written into
# garage_options.
ParkingType = Literal["MLP", "CP", "IP", "OP", "DP"]

ProjectType = Literal["residential", "commercial", "mixed"]
# The area a unit's basic price is worked out on. None/absent = super_built_up (= Unit.area), as before t048.
PricingBasis = Literal["super_built_up", "built_up", "carpet"]
FloorRiseBasis = Literal["per_sqft", "per_floor"]

# When a payment-plan milestone falls due. on_booking / days_after_booking / on_date get a date when the booking
# takes the plan; the EVENT ones (on_stage / on_possession / on_registration) only when the builder marks them
# reached (whole project or per tower) or raises them on one booking.
PlanDueOn = Literal["on_booking", "days_after_booking", "on_date", "on_stage", "on_possession", "on_registration"]
EVENT_DUE_ON: frozenset[str] = frozenset({"on_stage", "on_possession", "on_registration"})
MAX_PLAN_MILESTONES = 40
# milestone_key of the "Booking amount" row a token creates on a booking with no instalments (token_receipts.py) —
# never a plan milestone's key.
TOKEN_MILESTONE_KEY = "__token__"


class PlanMilestone(ORMModel):
    """One milestone of a project's payment plan. The name is the builder's own (free text); `percent` is a share
    of the booking's price (box price + GST)."""
    key: str = Field(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")
    label: str = Field(min_length=1, max_length=120)
    percent: Decimal = Field(gt=0, le=100)
    due_on: PlanDueOn
    days: int | None = Field(default=None, ge=1, le=3650)   # days_after_booking only
    due_date: date | None = None                             # on_date only

    @field_validator("label", mode="before")
    @classmethod
    def _strip_label(cls, value):
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _check_due(self):
        if self.due_on == "days_after_booking" and self.days is None:
            raise ValueError(f"“{self.label}”: say within how many days of booking it is due.")
        if self.due_on == "on_date" and self.due_date is None:
            raise ValueError(f"“{self.label}”: pick the date it is due.")
        if self.due_on != "days_after_booking":
            self.days = None
        if self.due_on != "on_date":
            self.due_date = None
        return self


def check_payment_plan(plan: list[PlanMilestone] | None) -> list[PlanMilestone] | None:
    """A plan (when it has milestones) must add up to 100% and use each key once. Used by the WRITE schemas only,
    so a stored plan is never re-judged on read."""
    if not plan:
        return plan
    if len(plan) > MAX_PLAN_MILESTONES:
        raise ValueError(f"A payment plan can have at most {MAX_PLAN_MILESTONES} milestones.")
    keys = [m.key for m in plan]
    if len(set(keys)) != len(keys):
        raise ValueError("Two milestones share the same key — reload the page and try again.")
    if TOKEN_MILESTONE_KEY in keys:
        # Reserved for the "Booking amount" row a token creates (token_receipts.py).
        raise ValueError(f"“{TOKEN_MILESTONE_KEY}” is reserved — rename that milestone's key.")
    # Each % is stored (and billed) to 3 decimals, so the plan must add up to exactly 100 at that precision — 33.33
    # three times (99.99%) would leave 0.01% of every booking's price never demanded.
    for m in plan:
        m.percent = m.percent.quantize(Decimal("0.001"))
    total = sum((m.percent for m in plan), Decimal("0"))
    if total != Decimal("100"):
        raise ValueError(f"The payment plan adds up to {total.normalize():f}% — it must add up to 100%.")
    return plan


class MilestoneReached(ORMModel):
    """An event milestone the builder marked reached — for one tower, or the whole project (tower_id None)."""
    key: str
    tower_id: UUID | None = None
    reached_on: date


class DemandMilestone(ORMModel):
    """One project demand milestone — a percentage of the unit price due on a fixed
    calendar date. Bookings inherit these as installments."""
    label: str = Field(min_length=1, max_length=120)
    percent: Decimal = Field(gt=0, le=100)
    due_date: date


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
    # Builder's demand schedule (% of unit price on fixed dates), inherited by bookings. Legacy: superseded by
    # payment_plan (writing a payment_plan clears it).
    demand_schedule: list[DemandMilestone] | None = None
    # --- Add Project wizard (t048) — all optional; absent = unchanged on PATCH. ---
    project_type: ProjectType | None = None
    pricing_basis: PricingBasis | None = None
    floor_rise_rate: Decimal | None = Field(default=None, ge=0)
    floor_rise_basis: FloorRiseBasis | None = None
    floor_rise_from: int | None = Field(default=None, ge=1, le=200)
    plc_rate: Decimal | None = Field(default=None, ge=0)
    amenities_rate: Decimal | None = Field(default=None, ge=0)
    parking_prices: dict[ParkingType, Annotated[Decimal, Field(ge=0)]] | None = None
    payment_plan: list[PlanMilestone] | None = None


class ProjectRead(ProjectDetailsMixin):
    id: UUID
    name: str
    builder_name: str
    location: str
    city: str
    rera_number: str | None = None
    milestones_reached: list[MilestoneReached] | None = None
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


class ProjectPossessionUnit(ORMModel):
    """One unit's registration + possession status within a project rollup."""
    unit_id: UUID
    unit_number: str
    tower_name: str | None = None
    floor: int
    unit_status: UnitStatus
    booking_id: UUID | None = None
    customer_name: str | None = None
    registration_number: str | None = None
    registered: bool = False
    possession_done: int = 0
    possession_total: int = 0


class ProjectPossessionSummary(ORMModel):
    total_units: int = 0
    booked: int = 0
    registered: int = 0
    possession_complete: int = 0


class ProjectPossessionRollup(ORMModel):
    """Project-wise possession & registration rollup (Phase C3)."""
    project_id: UUID
    project_name: str
    summary: ProjectPossessionSummary
    units: list[ProjectPossessionUnit] = []


class ProjectCreate(ProjectDetailsMixin):
    name: str = Field(min_length=1, max_length=255)
    builder_name: str = Field(min_length=1, max_length=255)
    location: str = Field(min_length=1, max_length=255)
    city: str = Field(min_length=1, max_length=100)
    rera_number: str | None = Field(default=None, max_length=64)

    @field_validator("payment_plan")
    @classmethod
    def _check_plan(cls, plan):
        return check_payment_plan(plan)


class ProjectUpdate(ProjectDetailsMixin):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    builder_name: str | None = Field(default=None, min_length=1, max_length=255)
    location: str | None = Field(default=None, min_length=1, max_length=255)
    city: str | None = Field(default=None, min_length=1, max_length=100)
    rera_number: str | None = Field(default=None, max_length=64)

    @field_validator("payment_plan")
    @classmethod
    def _check_plan(cls, plan):
        return check_payment_plan(plan)


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
    carpet_area: Decimal | None = Field(default=None, gt=0)
    built_up_area: Decimal | None = Field(default=None, gt=0)
    area_unit: str | None = Field(default=None, max_length=20)
    facing: str | None = Field(default=None, max_length=50)
    view: str | None = Field(default=None, max_length=100)
    base_price: Decimal | None = Field(default=None, ge=0)
    flat_type: str | None = Field(default=None, pattern=r"^[A-Z]{1,2}$")
    configuration: str | None = Field(default=None, max_length=32)
    has_plc: bool | None = None


class FloorUnits(ORMModel):
    """How many units to create on one floor."""
    floor: int = Field(ge=0)
    count: int = Field(ge=1, le=200)


class UnitBatchCreate(ORMModel):
    """Create a batch of same-type units across floors. The client expands a
    'same on every floor' choice into the explicit `floors` list."""
    unit_type: UnitType = UnitType.residential
    floors: list[FloorUnits] = Field(min_length=1)
    area: Decimal = Field(gt=0)  # Super built-up (saleable) — required, drives pricing
    carpet_area: Decimal | None = Field(default=None, gt=0)
    built_up_area: Decimal | None = Field(default=None, gt=0)
    base_price: Decimal = Field(ge=0)
    area_unit: str = Field(default="sqft", max_length=20)
    facing: str | None = Field(default=None, max_length=50)
    unit_prefix: str | None = Field(default=None, max_length=8)
    # Flat type (one unit of it per floor — its number ends in the type's position: A → 01, B → 02 …),
    # configuration and PLC flag, copied onto every unit of the batch.
    flat_type: str | None = Field(default=None, pattern=r"^[A-Z]{1,2}$")
    configuration: str | None = Field(default=None, max_length=32)
    has_plc: bool = False


MAX_FLAT_TYPES_PER_TOWER = 99  # positions 01..99 on a floor


class FlatTypeSpec(ORMModel):
    """One flat type of a tower: ONE unit of it on every floor in its range (4 types = 4 flats per floor). The code
    (A, B … Z, AA …) is the type's identity and fixes its position on the floor (A → x01, B → x02 …)."""
    code: str = Field(pattern=r"^[A-Z]{1,2}$")
    configuration: str | None = Field(default=None, max_length=32)
    carpet_area: Decimal | None = Field(default=None, gt=0)
    built_up_area: Decimal | None = Field(default=None, gt=0)
    super_built_up_area: Decimal = Field(gt=0)
    has_plc: bool = False
    floor_from: int | None = Field(default=None, ge=0, le=200)  # default 1
    floor_to: int | None = Field(default=None, ge=0, le=200)    # default the tower's top floor

    @field_validator("configuration", mode="before")
    @classmethod
    def _strip_configuration(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value


class OtherUnitSpec(ORMModel):
    """Shops / godowns in a tower: `per_floor` of them on each floor of the range (ground floor = 0)."""
    unit_type: Literal["shop", "godown"]
    per_floor: int = Field(ge=1, le=200)
    floor_from: int = Field(ge=0, le=200)
    floor_to: int = Field(ge=0, le=200)
    area: Decimal = Field(gt=0)  # super built-up
    carpet_area: Decimal | None = Field(default=None, gt=0)
    built_up_area: Decimal | None = Field(default=None, gt=0)
    unit_prefix: str | None = Field(default=None, max_length=8)


class TowerLayout(ORMModel):
    """A tower as the project wizard describes it. The server turns it into unit batches and prices each unit
    from the project's pricing (basis area × base rate)."""
    unit_prefix: str = Field(default="", max_length=8)
    flat_types: list[FlatTypeSpec] = Field(default_factory=list, max_length=MAX_FLAT_TYPES_PER_TOWER)
    others: list[OtherUnitSpec] = Field(default_factory=list, max_length=20)
    # Floors with no flats at all (a refuge floor, say): every flat type leaves them out. Shops / godowns rows keep
    # their own floors. Layouts saved before this field read as [] (every floor of a type's range has its flats).
    skip_floors: list[Annotated[int, Field(ge=0, le=200)]] = Field(default_factory=list, max_length=200)

    @field_validator("unit_prefix", mode="before")
    @classmethod
    def _strip_prefix(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("skip_floors")
    @classmethod
    def _unique_skip_floors(cls, value: list[int]) -> list[int]:
        if len(set(value)) != len(value):
            raise ValueError("A floor is listed twice under floors with no flats.")
        return sorted(value)

    @model_validator(mode="after")
    def _unique_codes(self):
        codes = [t.code for t in self.flat_types]
        if len(set(codes)) != len(codes):
            raise ValueError("Two flat types in one tower share the same letter.")
        return self


class ProjectTowerCreate(ORMModel):
    """One tower + its unit batches, for the combined Add-Project form. A tower can
    hold SEVERAL unit types (residential flats + shop/commercial + parking + godown),
    each its own batch with its own count + sizes + price.

    `layout` (the project wizard, t048) describes the tower as flat types + shops/godowns instead; when it is
    sent the server builds the batches from it (priced from the project) and `unit_specs` / `units` are ignored."""
    name: str = Field(min_length=1, max_length=100)
    total_floors: int = Field(ge=1, le=200)
    unit_specs: list[UnitBatchCreate] = Field(default_factory=list)
    units: UnitBatchCreate | None = None  # legacy single-spec — still honoured
    layout: TowerLayout | None = None


# Parking spots per type (Multi-Level / Covered / Independent / Open / Dependent), numbered per type across the
# whole project (CP01, CP02 … OP01 … DP01 …) regardless of tower.
ParkingCounts = dict[ParkingType, Annotated[int, Field(ge=0, le=5000)]]


class ProjectFullCreate(ProjectCreate):
    """Create a project together with its towers and each tower's units in one
    atomic call (the combined Add-Project wizard)."""
    towers: list[ProjectTowerCreate] = Field(default_factory=list)
    parking: ParkingCounts = Field(default_factory=dict)


class ProjectTowerSync(ProjectTowerCreate):
    """A tower card on the project page: an existing tower (`tower_id`) or a new one. Its unit specs are the
    TARGET layout — saving adds only the units that are missing."""
    tower_id: UUID | None = None


class ProjectInventorySync(ORMModel):
    """Edit project → Save: bring the project's inventory up to the page's layout. Additive only: units that
    exist (and any booking on them) are never changed or removed."""
    towers: list[ProjectTowerSync] = Field(default_factory=list)
    parking: ParkingCounts = Field(default_factory=dict)


class InventoryCreatedCounts(ORMModel):
    towers: int = 0
    units: int = 0
    parking: int = 0


class ProjectInventorySyncResult(ORMModel):
    project: ProjectWithTowersRead
    created: InventoryCreatedCounts
    notes: list[str] = []


class PlannedUnit(ORMModel):
    """A unit Save would create (the wizard's inventory preview)."""
    floor: int
    unit_number: str
    unit_type: str
    flat_type: str | None = None
    configuration: str | None = None
    area: Decimal
    carpet_area: Decimal | None = None
    built_up_area: Decimal | None = None
    base_price: Decimal | None = None  # None when the project has no rate for it yet
    has_plc: bool = False


class PlannedTower(ORMModel):
    tower_id: UUID | None = None
    name: str
    existing_units: int = 0          # live units already in the tower (archived ones not counted)
    new_units: list[PlannedUnit] = []


class PlannedParking(ORMModel):
    parking_type: ParkingType
    existing: int = 0
    new_numbers: list[str] = []
    price: Decimal | None = None


class InventoryPreview(ORMModel):
    """What Save would build — the same planner, nothing written."""
    towers: list[PlannedTower] = []
    parking: list[PlannedParking] = []
    notes: list[str] = []
    new_units: int = 0
    new_parking: int = 0


class InventoryPreviewRequest(ProjectInventorySync):
    """Preview for an existing project: the page's towers + parking, plus the page's (unsaved) pricing so the
    preview prices match what Save will use."""
    pricing_basis: PricingBasis | None = None
    rate_a: Decimal | None = Field(default=None, ge=0)
    rate_b: Decimal | None = Field(default=None, ge=0)
    rate_c: Decimal | None = Field(default=None, ge=0)
    parking_prices: dict[ParkingType, Annotated[Decimal, Field(ge=0)]] | None = None


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
    milestone_key: str | None = None   # set on rows a payment plan generated
    percent: Decimal | None = None     # while set, the amount follows the booking's price
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


class PaymentScheduleUpdate(ORMModel):
    """Edit an individual demand row after it was generated. All optional — only
    the sent fields change; payments/receipts are untouched (those go through the
    payment endpoints)."""
    installment_name: str | None = Field(default=None, min_length=1, max_length=120)
    due_date: date | None = None
    demand_amount: Decimal | None = Field(default=None, ge=0)


class PaymentReceiptRead(ORMModel):
    id: UUID
    booking_id: UUID
    schedule_id: UUID | None = None
    amount: Decimal
    paid_on: date
    mode: str
    reference: str | None = None
    notes: str | None = None
    # The booking's token (one per booking; mirrors Booking.token_*) — counted once, as this receipt.
    is_token: bool = False
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
    carpet_area: Decimal | None = None
    built_up_area: Decimal | None = None
    area_unit: str
    base_price: Decimal
    status: UnitStatus
    flat_type: str | None = None
    configuration: str | None = None
    has_plc: bool = False
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
    token_amount: Decimal | None = None
    token_received_on: date | None = None
    token_mode: str | None = None
    token_reference: str | None = None
    # The payment plan this booking took from its project (PlanMilestone shape, as stored). Milestones with no
    # schedule row carrying their key are still to be raised.
    payment_plan: list[dict] | None = None
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


class BookingTokenUpdate(ORMModel):
    """Record (or update) the token / booking amount on a booking."""
    token_amount: Decimal = Field(gt=0)
    token_received_on: date
    token_mode: PaymentMode
    token_reference: str | None = Field(default=None, max_length=120)


class BookingInvoiceRead(ORMModel):
    id: UUID
    booking_id: UUID
    schedule_id: UUID | None = None
    invoice_number: str
    installment_name: str
    amount: Decimal
    due_date: date | None = None
    status: InvoiceStatus
    created_at: datetime


class BookingInvoiceCreate(ORMModel):
    """Raise an invoice. Either bind to an existing installment (copies its name /
    amount / due date) or supply the details directly for an ad-hoc invoice."""
    schedule_id: UUID | None = None
    installment_name: str | None = Field(default=None, max_length=120)
    amount: Decimal | None = Field(default=None, ge=0)
    due_date: date | None = None


class BookingInvoiceStatusUpdate(ORMModel):
    status: InvoiceStatus


class PricingUpdate(ORMModel):
    pricing_snapshot: dict


class MilestoneReachedCreate(ORMModel):
    """Mark an event milestone reached — raises its demand on every live booking that holds it (in the chosen
    towers, or the whole project when tower_ids is empty / absent)."""
    reached_on: date
    tower_ids: list[UUID] | None = None


class MilestoneReachedResult(ORMModel):
    raised: int = 0                 # bookings that got the demand now
    already_raised: int = 0         # bookings that already had it
    amount: Decimal = Decimal("0")  # total demanded now
    project: ProjectRead


class MilestoneRaise(ORMModel):
    """Raise one milestone on one booking (e.g. its registration), due on `due_date`."""
    due_date: date


class MilestoneUndoResult(ORMModel):
    removed: int = 0   # unpaid, un-invoiced demands removed
    kept: int = 0      # demands kept because money was paid or an invoice raised
    project: ProjectRead


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
    project_id: UUID
    project_name: str
    unit_number: str
    customer_name: str | None = None  # "from whom" — the booking's customer
    status: BookingStatus
