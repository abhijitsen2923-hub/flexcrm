"""Customer portal Pydantic schemas."""
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field

from app.schemas.common import ORMModel


class PaymentScheduleEntryOut(ORMModel):
    id: UUID
    booking_id: UUID
    installment_name: str
    due_date: date
    demand_amount: Decimal
    paid_amount: Decimal
    outstanding: Decimal
    is_overdue: bool


class CustomerDocumentOut(ORMModel):
    id: UUID
    name: str
    type: str
    url: str
    created_at: datetime


class ServiceRequestOut(ORMModel):
    id: UUID
    category: str
    description: str
    status: str
    created_at: datetime
    resolved_at: datetime | None = None


class ServiceRequestCreate(ORMModel):
    category: str = Field(min_length=1, max_length=32)
    description: str = Field(min_length=1)


class ReferralCreate(ORMModel):
    contact_name: str = Field(min_length=1, max_length=255)
    contact_phone: str | None = Field(default=None, max_length=32)
    contact_email: str | None = Field(default=None, max_length=255)
    preferred_location: str | None = Field(default=None, max_length=255)
    notes: str | None = None
