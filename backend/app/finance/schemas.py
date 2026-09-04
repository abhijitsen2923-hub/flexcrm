from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field

from app.database.enums import (
    CommissionDirection,
    ExpenseStatus,
    FinanceBusinessMode,
    FinanceCategoryKind,
    GstTreatment,
    InvoiceStatus,
    PaymentStatus,
    VendorBillStatus,
)
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


# =====================================================================
# Finance vertical — Phase 1: settings, categories, vendors, expenses,
# vendor bills/payments, documents.
# =====================================================================


class _GstInput(ORMModel):
    """GST + amount inputs the client sends; the server computes the breakdown."""
    amount_entered: Decimal = Field(ge=0)
    gst_applicable: bool = False
    gst_treatment: GstTreatment | None = None
    gst_inclusive: bool = False
    gst_rate: Decimal | None = Field(default=None, ge=0, le=100)
    tds_amount: Decimal = Field(default=Decimal("0"), ge=0)


class _GstRead(ORMModel):
    """The stored GST snapshot returned on reads."""
    gst_applicable: bool
    gst_treatment: GstTreatment | None = None
    gst_inclusive: bool
    gst_rate: Decimal | None = None
    amount_entered: Decimal
    taxable_amount: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    tds_amount: Decimal
    total_amount: Decimal
    net_payable: Decimal


# ---- Settings ----

class FinanceSettingsRead(ORMModel):
    gst_registered: bool
    gstin: str | None = None
    home_state_code: str | None = None
    default_place_of_supply_state: str | None = None
    expense_approval_threshold: Decimal = Decimal("0")
    finance_business_mode: FinanceBusinessMode


class FinanceSettingsUpdate(ORMModel):
    gst_registered: bool | None = None
    gstin: str | None = Field(default=None, max_length=15)
    home_state_code: str | None = Field(default=None, max_length=2)
    default_place_of_supply_state: str | None = Field(default=None, max_length=2)
    expense_approval_threshold: Decimal | None = Field(default=None, ge=0)


# ---- Categories ----

class FinanceCategoryRead(ORMModel):
    id: UUID
    name: str
    kind: FinanceCategoryKind
    group_label: str | None = None
    source: str
    is_active: bool
    sort_order: int | None = None


class FinanceCategoryCreate(ORMModel):
    name: str = Field(min_length=1, max_length=120)
    kind: FinanceCategoryKind = FinanceCategoryKind.expense
    group_label: str | None = Field(default=None, max_length=80)
    sort_order: int | None = None


class FinanceCategoryUpdate(ORMModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    group_label: str | None = Field(default=None, max_length=80)
    is_active: bool | None = None
    sort_order: int | None = None


# ---- Vendors ----

class VendorRead(ORMModel):
    id: UUID
    name: str
    contact_name: str | None = None
    phone: str | None = None
    email: str | None = None
    gstin: str | None = None
    pan: str | None = None
    state_code: str | None = None
    address: str | None = None
    bank_account: str | None = None
    ifsc: str | None = None
    upi: str | None = None
    notes: str | None = None
    is_active: bool
    created_at: datetime


class VendorCreate(ORMModel):
    name: str = Field(min_length=1, max_length=255)
    contact_name: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=255)
    gstin: str | None = Field(default=None, max_length=15)
    pan: str | None = Field(default=None, max_length=20)
    state_code: str | None = Field(default=None, max_length=2)
    address: str | None = None
    bank_account: str | None = Field(default=None, max_length=64)
    ifsc: str | None = Field(default=None, max_length=20)
    upi: str | None = Field(default=None, max_length=120)
    notes: str | None = None


class VendorUpdate(VendorCreate):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    is_active: bool | None = None


# ---- Expenses ----

class ExpenseWrite(_GstInput):
    """Editable fields shared by create + update."""
    title: str = Field(min_length=1, max_length=255)
    notes: str | None = None
    category_id: UUID
    vendor_id: UUID | None = None
    bill_id: UUID | None = None
    project_id: UUID | None = None
    department: str | None = Field(default=None, max_length=80)
    expense_date: date
    payment_mode: str | None = Field(default=None, max_length=32)


class ExpenseCreate(ExpenseWrite):
    submit: bool = False  # create and immediately submit for approval


class ExpenseUpdate(ExpenseWrite):
    pass


class ExpenseRead(_GstRead):
    id: UUID
    expense_number: str
    title: str
    notes: str | None = None
    category_id: UUID
    vendor_id: UUID | None = None
    bill_id: UUID | None = None
    project_id: UUID | None = None
    department: str | None = None
    expense_date: date
    payment_mode: str | None = None
    status: ExpenseStatus
    submitted_by_id: UUID | None = None
    submitted_at: datetime | None = None
    approved_by_id: UUID | None = None
    approved_at: datetime | None = None
    rejected_reason: str | None = None
    paid_at: date | None = None
    created_at: datetime


class ExpenseRejectRequest(ORMModel):
    reason: str = Field(min_length=1, max_length=1000)


class ExpenseMarkPaidRequest(ORMModel):
    paid_at: date | None = None
    payment_mode: str | None = Field(default=None, max_length=32)


class ExpenseFilters(SearchSortParams):
    status: ExpenseStatus | None = None
    category_id: UUID | None = None
    vendor_id: UUID | None = None
    date_from: date | None = None
    date_to: date | None = None


# ---- Vendor bills + payments ----

class VendorBillWrite(_GstInput):
    vendor_id: UUID
    vendor_invoice_no: str | None = Field(default=None, max_length=64)
    category_id: UUID | None = None
    project_id: UUID | None = None
    bill_date: date | None = None
    due_date: date | None = None
    description: str | None = None


class VendorBillCreate(VendorBillWrite):
    pass


class VendorBillUpdate(VendorBillWrite):
    """Full-write edit (only allowed while the bill is open)."""
    pass


class VendorPaymentRead(ORMModel):
    id: UUID
    payment_number: str
    bill_id: UUID
    vendor_id: UUID | None = None
    amount: Decimal
    paid_on: date
    method: str | None = None
    txn_ref: str | None = None
    note: str | None = None
    created_at: datetime


class VendorBillRead(_GstRead):
    id: UUID
    bill_number: str
    vendor_id: UUID
    vendor_invoice_no: str | None = None
    category_id: UUID | None = None
    project_id: UUID | None = None
    bill_date: date | None = None
    due_date: date | None = None
    description: str | None = None
    status: VendorBillStatus
    amount_paid: Decimal
    paid_on: date | None = None
    created_at: datetime
    payments: list[VendorPaymentRead] = []


class VendorPaymentCreate(ORMModel):
    amount: Decimal = Field(gt=0)
    paid_on: date
    method: str | None = Field(default=None, max_length=64)
    txn_ref: str | None = Field(default=None, max_length=120)
    note: str | None = None


class FinanceDocumentRead(ORMModel):
    id: UUID
    owner_type: str
    owner_id: UUID
    doc_type: str | None = None
    file_name: str | None = None
    content_type: str | None = None
    created_at: datetime


# ---- Manual income (Phase 2) ----

class ManualIncomeWrite(_GstInput):
    title: str = Field(min_length=1, max_length=255)
    category_id: UUID
    source: str | None = Field(default=None, max_length=120)
    project_id: UUID | None = None
    income_date: date
    payment_mode: str | None = Field(default=None, max_length=32)
    notes: str | None = None


class ManualIncomeCreate(ManualIncomeWrite):
    pass


class ManualIncomeUpdate(ManualIncomeWrite):
    pass


class ManualIncomeRead(_GstRead):
    id: UUID
    income_number: str
    title: str
    category_id: UUID
    source: str | None = None
    project_id: UUID | None = None
    income_date: date
    payment_mode: str | None = None
    notes: str | None = None
    created_at: datetime


class ManualIncomeFilters(SearchSortParams):
    category_id: UUID | None = None
    date_from: date | None = None
    date_to: date | None = None


# ---- Unified finance dashboard summary (Phase 2) ----

class FinanceBreakdownRow(ORMModel):
    label: str
    value: Decimal


class FinanceSummaryResponse(ORMModel):
    # Income (sale revenue + manual income; no duplication)
    income_total: Decimal
    manual_income_total: Decimal
    sales_revenue_total: Decimal
    # Expenses (expenses + vendor bills)
    expense_total: Decimal
    expense_paid: Decimal
    expense_pending_approval: int
    vendor_payable_outstanding: Decimal
    # GST
    output_gst: Decimal
    input_gst: Decimal
    net_gst: Decimal
    # Rough cash position (income recorded − amounts actually paid out)
    net_position: Decimal
    # Charts
    expense_by_category: list[FinanceBreakdownRow] = []
    income_by_category: list[FinanceBreakdownRow] = []


# ---- Per-customer demand ledger (Phase 3a) ----

class CustomerContractCreate(ORMModel):
    customer_id: UUID
    title: str = Field(min_length=1, max_length=255)
    contract_value: Decimal = Field(ge=0)
    currency: str = Field(default="INR", max_length=3)
    notes: str | None = None


class CustomerContractUpdate(ORMModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    contract_value: Decimal | None = Field(default=None, ge=0)
    notes: str | None = None
    status: str | None = Field(default=None, max_length=16)


class DemandReceiptRead(ORMModel):
    id: UUID
    receipt_number: str
    demand_id: UUID
    amount: Decimal
    received_on: date
    method: str | None = None
    txn_ref: str | None = None
    note: str | None = None
    created_at: datetime


class CustomerDemandRead(ORMModel):
    id: UUID
    demand_number: str
    contract_id: UUID
    description: str | None = None
    amount: Decimal
    due_date: date | None = None
    status: str
    amount_received: Decimal
    outstanding: Decimal
    created_at: datetime
    receipts: list[DemandReceiptRead] = []


class CustomerContractRead(ORMModel):
    id: UUID
    customer_id: UUID
    title: str
    contract_value: Decimal
    currency: str
    notes: str | None = None
    status: str
    created_at: datetime
    total_demanded: Decimal
    total_received: Decimal
    balance: Decimal
    demands: list[CustomerDemandRead] = []


class CustomerContractListItem(ORMModel):
    id: UUID
    customer_id: UUID
    title: str
    contract_value: Decimal
    currency: str
    status: str
    total_demanded: Decimal
    total_received: Decimal
    balance: Decimal
    created_at: datetime


class CustomerDemandCreate(ORMModel):
    description: str | None = Field(default=None, max_length=255)
    amount: Decimal = Field(gt=0)
    due_date: date | None = None


class CustomerDemandUpdate(ORMModel):
    description: str | None = Field(default=None, max_length=255)
    amount: Decimal | None = Field(default=None, gt=0)
    due_date: date | None = None


class DemandReceiptCreate(ORMModel):
    amount: Decimal = Field(gt=0)
    received_on: date
    method: str | None = Field(default=None, max_length=64)
    txn_ref: str | None = Field(default=None, max_length=120)
    note: str | None = None


# ---- Payroll (Phase 3) ----

class PayrollEmployeeRead(ORMModel):
    user_id: UUID
    name: str
    role: str | None = None
    monthly_salary: Decimal


class SetSalaryRequest(ORMModel):
    monthly_salary: Decimal = Field(ge=0)


class PayrollRunRequest(ORMModel):
    month: str = Field(pattern=r"^\d{4}-\d{2}$")  # YYYY-MM
    employee_ids: list[UUID] | None = None


class PayrollRunResult(ORMModel):
    month: str
    created: int
    skipped: int
    total_amount: Decimal


# ---- Budgets (Phase 3) ----

class BudgetCreate(ORMModel):
    name: str = Field(min_length=1, max_length=120)
    period_key: str = Field(pattern=r"^\d{4}-\d{2}$")  # YYYY-MM
    category_id: UUID | None = None
    department: str | None = Field(default=None, max_length=80)
    amount: Decimal = Field(ge=0)
    notes: str | None = None


class BudgetUpdate(ORMModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    period_key: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}$")
    category_id: UUID | None = None
    department: str | None = Field(default=None, max_length=80)
    amount: Decimal | None = Field(default=None, ge=0)
    notes: str | None = None


class BudgetRead(ORMModel):
    id: UUID
    name: str
    period_key: str
    category_id: UUID | None = None
    category_name: str | None = None
    department: str | None = None
    amount: Decimal
    actual: Decimal  # computed: spend so far this period (+ category)
    variance: Decimal  # amount − actual
    used_pct: float  # 0..100+ (0 when amount is 0)
    notes: str | None = None
