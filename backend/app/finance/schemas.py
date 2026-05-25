from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field

from app.database.enums import CommissionDirection, InvoiceStatus, PaymentStatus
from app.schemas.common import ORMModel, SearchSortParams


class SalesOrderAssistRead(ORMModel):
    id: UUID
    user_id: UUID
    percent: int
    reason: str | None = None


class SalesOrderRead(ORMModel):
    id: UUID
    order_number: str
    lead_id: UUID | None = None
    customer_id: UUID
    primary_owner_id: UUID | None = None
    title: str
    deal_value: Decimal
    currency: str
    payment_status: PaymentStatus
    closed_at: datetime
    created_at: datetime
    assists: list[SalesOrderAssistRead] = []


class InvoiceRead(ORMModel):
    id: UUID
    invoice_number: str
    sales_order_id: UUID
    amount: Decimal
    due_date: date | None = None
    status: InvoiceStatus
    created_at: datetime


class PaymentCreate(ORMModel):
    amount: Decimal = Field(gt=0)
    method: str | None = Field(default=None, max_length=64)
    txn_ref: str | None = Field(default=None, max_length=120)


class PaymentRead(ORMModel):
    id: UUID
    invoice_id: UUID
    amount: Decimal
    received_at: datetime
    method: str | None = None
    txn_ref: str | None = None


class CommissionLedgerRead(ORMModel):
    id: UUID
    user_id: UUID
    sales_order_id: UUID | None = None
    direction: CommissionDirection
    amount: Decimal
    note: str | None = None
    recorded_at: datetime


class RefundCreate(ORMModel):
    amount: Decimal = Field(gt=0)
    reason: str | None = Field(default=None, max_length=255)


class RefundRead(ORMModel):
    id: UUID
    payment_id: UUID
    amount: Decimal
    reason: str | None = None
    refunded_at: datetime


class MonthlyRevenueRow(ORMModel):
    user_id: UUID | None
    user_name: str
    deals_closed: int
    revenue: Decimal
    collections: Decimal


class MonthlyReportResponse(ORMModel):
    month: str
    rows: list[MonthlyRevenueRow]


class SalesOrderFilters(SearchSortParams):
    customer_id: UUID | None = None
    primary_owner_id: UUID | None = None
    payment_status: PaymentStatus | None = None
