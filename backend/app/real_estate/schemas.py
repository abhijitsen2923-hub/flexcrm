"""Real estate Pydantic schemas."""
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field

from app.database.enums import BookingStatus, SiteVisitFeedback, UnitStatus, UnitType
from app.schemas.common import ORMModel
from app.schemas.customer import CustomerCompact


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


class ProjectRead(ORMModel):
    id: UUID
    name: str
    builder_name: str
    location: str
    city: str
    rera_number: str | None = None
    created_at: datetime
    updated_at: datetime


class ProjectWithTowersRead(ProjectRead):
    towers: list[TowerRead] = []


class ProjectCreate(ORMModel):
    name: str = Field(min_length=1, max_length=255)
    builder_name: str = Field(min_length=1, max_length=255)
    location: str = Field(min_length=1, max_length=255)
    city: str = Field(min_length=1, max_length=100)
    rera_number: str | None = Field(default=None, max_length=64)


class TowerCreate(ORMModel):
    name: str = Field(min_length=1, max_length=100)
    total_floors: int = Field(ge=1, le=200)


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
    is_overdue: bool
    created_at: datetime


class PaymentScheduleCreate(ORMModel):
    installment_name: str = Field(min_length=1, max_length=120)
    due_date: date
    demand_amount: Decimal = Field(ge=0)
    paid_amount: Decimal = Field(default=Decimal("0"), ge=0)


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
    created_at: datetime
    updated_at: datetime
    customer: CustomerCompact | None = None
    kyc_documents: list[BookingKycDocRead] = []
    payment_schedules: list[PaymentScheduleRead] = []


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
