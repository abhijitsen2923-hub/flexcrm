from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import EmailStr, Field

from app.database.enums import CustomerLifecycleStage, CustomerStatus
from app.schemas.common import ORMModel, SearchSortParams
from app.schemas.user import UserSummary


class CustomerCompact(ORMModel):
    id: UUID
    company_name: str
    contact_name: str
    email: str | None = None  # read model — no EmailStr re-validation (see LeadRead note)
    status: CustomerStatus


class CustomerCreate(ORMModel):
    company_name: str = Field(min_length=1, max_length=255)
    contact_name: str = Field(min_length=1, max_length=255)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    address: str | None = None
    source: str | None = Field(default=None, max_length=120)
    status: CustomerStatus = CustomerStatus.prospect


class CustomerUpdate(ORMModel):
    company_name: str | None = Field(default=None, min_length=1, max_length=255)
    contact_name: str | None = Field(default=None, min_length=1, max_length=255)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    address: str | None = None
    source: str | None = Field(default=None, max_length=120)
    status: CustomerStatus | None = None


class CustomerSourceLead(ORMModel):
    """Compact reference to the lead a customer was promoted from."""
    id: UUID
    lead_number: int
    title: str


class CustomerRead(CustomerCompact):
    email: str | None = None  # read model — no EmailStr re-validation (see LeadRead note)
    phone: str | None = None
    address: str | None = None
    source: str | None = None
    source_lead_id: UUID | None = None
    source_lead: CustomerSourceLead | None = None
    lifecycle_stage: CustomerLifecycleStage
    customer_number: int | None = None
    onboarding_started_at: datetime | None = None
    renewal_due_at: date | None = None
    ltv: Decimal = Decimal("0")
    sale_value: Decimal | None = None
    churn_reason: str | None = None
    original_owner_id: UUID | None = None
    current_owner_id: UUID | None = None
    current_owner: UserSummary | None = None
    created_by_id: UUID | None = None
    updated_by_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class CustomerFilterParams(SearchSortParams):
    status: CustomerStatus | None = None
    source: str | None = None
    created_by_id: UUID | None = None
