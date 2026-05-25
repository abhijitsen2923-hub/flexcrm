from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field

from app.database.enums import RenewalStatus, ReferralStatus
from app.schemas.common import ORMModel


class DeliveryLogCreate(ORMModel):
    item: str = Field(min_length=1, max_length=255)
    notes: str | None = None
    delivered_at: datetime | None = None
    delivered_by_id: UUID | None = None


class DeliveryLogRead(ORMModel):
    id: UUID
    customer_id: UUID
    item: str
    delivered_at: datetime
    delivered_by_id: UUID | None = None
    notes: str | None = None


class RenewalCreate(ORMModel):
    due_date: date
    amount: Decimal = Field(ge=0, default=Decimal("0"))
    status: RenewalStatus = RenewalStatus.upcoming


class RenewalRead(ORMModel):
    id: UUID
    customer_id: UUID
    due_date: date
    amount: Decimal
    status: RenewalStatus
    renewed_at: datetime | None = None
    created_at: datetime


class ReferralCreate(ORMModel):
    referred_lead_id: UUID | None = None
    awarded_credit: Decimal = Field(ge=0, default=Decimal("0"))
    status: ReferralStatus = ReferralStatus.pending


class ReferralRead(ORMModel):
    id: UUID
    referring_customer_id: UUID
    referred_lead_id: UUID | None = None
    awarded_credit: Decimal
    status: ReferralStatus
    created_at: datetime
