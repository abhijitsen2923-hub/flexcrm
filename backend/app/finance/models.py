"""Finance domain models — per-tenant schema."""
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import TenantBase
from app.database.enums import (
    CommissionDirection,
    ExpenseStatus,
    FinanceCategoryKind,
    GstTreatment,
    InvoiceStatus,
    PaymentStatus,
    VendorBillStatus,
)
from app.models.base import TenantAuditMixin, TenantSoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class SalesOrder(TenantBase, UUIDPrimaryKeyMixin, TimestampMixin, TenantAuditMixin, TenantSoftDeleteMixin):
    __tablename__ = "sales_orders"
    __table_args__ = (
        CheckConstraint("deal_value >= 0", name="ck_sales_orders_value_non_negative"),
        # Schema isolation removes the need for org_id in the uniqueness constraint.
        UniqueConstraint("order_number", name="uq_sales_orders_order_number"),
        Index("ix_sales_orders_customer", "customer_id"),
        Index("ix_sales_orders_owner", "primary_owner_id"),
        {"schema": "tenant"},
    )

    order_number: Mapped[str] = mapped_column(String(32), nullable=False)
    lead_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("leads.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    customer_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    primary_owner_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("public.users.id", ondelete="SET NULL"),
        nullable=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    deal_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    payment_status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status_enum"),
        nullable=False,
        default=PaymentStatus.pending,
    )
    closed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    customer = relationship("Customer")
    lead = relationship("Lead")
    assists = relationship(
        "SalesOrderAssist",
        back_populates="sales_order",
        cascade="all, delete-orphan",
    )
    invoice = relationship(
        "Invoice",
        back_populates="sales_order",
        uselist=False,
        cascade="all, delete-orphan",
    )


class SalesOrderAssist(TenantBase, UUIDPrimaryKeyMixin):
    __tablename__ = "sales_order_assists"
    __table_args__ = (
        CheckConstraint("percent >= 0 AND percent <= 100", name="ck_sales_order_assists_percent_range"),
        Index("ix_sales_order_assists_user", "user_id"),
        {"schema": "tenant"},
    )

    sales_order_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("sales_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("public.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    sales_order = relationship("SalesOrder", back_populates="assists")


class Invoice(TenantBase, UUIDPrimaryKeyMixin, TimestampMixin, TenantAuditMixin, TenantSoftDeleteMixin):
    __tablename__ = "invoices"
    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_invoices_amount_non_negative"),
        UniqueConstraint("invoice_number", name="uq_invoices_invoice_number"),
        Index("ix_invoices_sales_order", "sales_order_id"),
        Index("ix_invoices_status", "status"),
        {"schema": "tenant"},
    )

    invoice_number: Mapped[str] = mapped_column(String(32), nullable=False)
    sales_order_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("sales_orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    due_date: Mapped[date | None] = mapped_column(nullable=True)
    status: Mapped[InvoiceStatus] = mapped_column(
        Enum(InvoiceStatus, name="invoice_status_enum"),
        nullable=False,
        default=InvoiceStatus.issued,
    )

    sales_order = relationship("SalesOrder", back_populates="invoice")
    payments = relationship(
        "Payment",
        back_populates="invoice",
        cascade="all, delete-orphan",
    )


class Payment(TenantBase, UUIDPrimaryKeyMixin):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_payments_amount_non_negative"),
        Index("ix_payments_invoice", "invoice_id"),
        {"schema": "tenant"},
    )

    invoice_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("invoices.id", ondelete="CASCADE"),
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    method: Mapped[str | None] = mapped_column(String(64), nullable=True)
    txn_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    recorded_by_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("public.users.id", ondelete="SET NULL"),
        nullable=True,
    )

    invoice = relationship("Invoice", back_populates="payments")


class CommissionLedger(TenantBase, UUIDPrimaryKeyMixin):
    __tablename__ = "commission_ledger"
    __table_args__ = (
        Index("ix_commission_ledger_user_recorded", "user_id", "recorded_at"),
        {"schema": "tenant"},
    )

    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("public.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sales_order_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("sales_orders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    direction: Mapped[CommissionDirection] = mapped_column(
        Enum(CommissionDirection, name="commission_direction_enum"),
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    sales_order = relationship("SalesOrder")


class Refund(TenantBase, UUIDPrimaryKeyMixin):
    __tablename__ = "refunds"
    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_refunds_amount_non_negative"),
        {"schema": "tenant"},
    )

    payment_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("payments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    refunded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    refunded_by_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("public.users.id", ondelete="SET NULL"),
        nullable=True,
    )

    payment = relationship("Payment")


# =====================================================================
# Finance vertical — Phase 1: expenses / vendors / vendor payments.
# All per-tenant; cross-domain refs (project_id → real_estate.projects)
# are plain UUID columns with no FK, per the codebase convention.
# =====================================================================


class FinanceSettings(TenantBase, UUIDPrimaryKeyMixin, TimestampMixin, TenantAuditMixin):
    """Per-tenant finance/GST config — a single row (get_or_create)."""

    __tablename__ = "finance_settings"
    __table_args__ = ({"schema": "tenant"},)

    gst_registered: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    gstin: Mapped[str | None] = mapped_column(String(15), nullable=True)
    home_state_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    default_place_of_supply_state: Mapped[str | None] = mapped_column(String(2), nullable=True)


class FinanceCategory(TenantBase, UUIDPrimaryKeyMixin, TimestampMixin, TenantAuditMixin, TenantSoftDeleteMixin):
    """Income/expense category master. Presets are seeded per-org by business mode;
    custom rows add on top. Disable via is_active — never hard-delete (expenses RESTRICT)."""

    __tablename__ = "finance_categories"
    __table_args__ = (
        UniqueConstraint("name", "kind", name="uq_finance_categories_name_kind"),
        Index("ix_finance_categories_kind", "kind"),
        {"schema": "tenant"},
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[FinanceCategoryKind] = mapped_column(
        Enum(FinanceCategoryKind, name="finance_category_kind_enum"), nullable=False
    )
    group_label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="custom")  # preset | custom
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Vendor(TenantBase, UUIDPrimaryKeyMixin, TimestampMixin, TenantAuditMixin, TenantSoftDeleteMixin):
    """A payee for expenses / vendor bills. Modeled on ChannelPartner's payee fields."""

    __tablename__ = "vendors"
    __table_args__ = (
        Index("ix_vendors_is_active", "is_active"),
        {"schema": "tenant"},
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gstin: Mapped[str | None] = mapped_column(String(15), nullable=True)
    pan: Mapped[str | None] = mapped_column(String(20), nullable=True)
    state_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    bank_account: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ifsc: Mapped[str | None] = mapped_column(String(20), nullable=True)
    upi: Mapped[str | None] = mapped_column(String(120), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class _GstAmountMixin:
    """Shared GST + amount snapshot columns (computed server-side by
    app.finance.gst.compute_gst) — used by both expenses and vendor_bills."""

    gst_applicable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    gst_treatment: Mapped[GstTreatment | None] = mapped_column(
        Enum(GstTreatment, name="gst_treatment_enum"), nullable=True
    )
    gst_inclusive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    gst_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    amount_entered: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    taxable_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    cgst_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    sgst_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    igst_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    tds_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    net_payable: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)


class VendorBill(
    TenantBase, UUIDPrimaryKeyMixin, TimestampMixin, TenantAuditMixin, TenantSoftDeleteMixin, _GstAmountMixin
):
    """A vendor's bill (accounts payable). open → partially_paid → paid; amount_paid
    is Σ of vendor_payments. Modeled on BrokeragePayout + BookingInvoice."""

    __tablename__ = "vendor_bills"
    __table_args__ = (
        CheckConstraint("amount_entered >= 0", name="ck_vendor_bills_amount_non_negative"),
        UniqueConstraint("bill_number", name="uq_vendor_bills_bill_number"),
        Index("ix_vendor_bills_vendor", "vendor_id"),
        Index("ix_vendor_bills_status", "status"),
        {"schema": "tenant"},
    )

    bill_number: Mapped[str] = mapped_column(String(32), nullable=False)
    vendor_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("vendors.id", ondelete="RESTRICT"), nullable=False
    )
    vendor_invoice_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    category_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("finance_categories.id", ondelete="SET NULL"), nullable=True
    )
    project_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)  # cross-domain, no FK
    bill_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[VendorBillStatus] = mapped_column(
        Enum(VendorBillStatus, name="vendor_bill_status_enum"), nullable=False, default=VendorBillStatus.open
    )
    amount_paid: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    paid_on: Mapped[date | None] = mapped_column(Date, nullable=True)

    vendor = relationship("Vendor")
    payments = relationship("VendorPayment", back_populates="bill", cascade="all, delete-orphan")


class VendorPayment(TenantBase, UUIDPrimaryKeyMixin, TimestampMixin):
    """A payment against a vendor bill. Mirrors Payment→Invoice; supports partials."""

    __tablename__ = "vendor_payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_vendor_payments_amount_positive"),
        UniqueConstraint("payment_number", name="uq_vendor_payments_payment_number"),
        Index("ix_vendor_payments_bill", "bill_id"),
        {"schema": "tenant"},
    )

    payment_number: Mapped[str] = mapped_column(String(32), nullable=False)
    bill_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("vendor_bills.id", ondelete="CASCADE"), nullable=False
    )
    vendor_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)  # denormalized, no FK
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    paid_on: Mapped[date] = mapped_column(Date, nullable=False)
    method: Mapped[str | None] = mapped_column(String(64), nullable=True)
    txn_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_by_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("public.users.id", ondelete="SET NULL"), nullable=True
    )

    bill = relationship("VendorBill", back_populates="payments")


class Expense(
    TenantBase, UUIDPrimaryKeyMixin, TimestampMixin, TenantAuditMixin, TenantSoftDeleteMixin, _GstAmountMixin
):
    """A business expense (P&L). draft → submitted → approved → paid; can be rejected.
    Optionally references a vendor (payee) and/or a vendor_bill it books."""

    __tablename__ = "expenses"
    __table_args__ = (
        CheckConstraint("amount_entered >= 0", name="ck_expenses_amount_non_negative"),
        UniqueConstraint("expense_number", name="uq_expenses_expense_number"),
        Index("ix_expenses_status", "status"),
        Index("ix_expenses_category", "category_id"),
        Index("ix_expenses_vendor", "vendor_id"),
        Index("ix_expenses_date", "expense_date"),
        {"schema": "tenant"},
    )

    expense_number: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    category_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("finance_categories.id", ondelete="RESTRICT"), nullable=False
    )
    vendor_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("vendors.id", ondelete="SET NULL"), nullable=True
    )
    bill_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("vendor_bills.id", ondelete="SET NULL"), nullable=True
    )
    project_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)  # cross-domain, no FK
    department: Mapped[str | None] = mapped_column(String(80), nullable=True)
    expense_date: Mapped[date] = mapped_column(Date, nullable=False)
    payment_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[ExpenseStatus] = mapped_column(
        Enum(ExpenseStatus, name="expense_status_enum"), nullable=False, default=ExpenseStatus.draft
    )
    submitted_by_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("public.users.id", ondelete="SET NULL"), nullable=True
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("public.users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    paid_at: Mapped[date | None] = mapped_column(Date, nullable=True)

    category = relationship("FinanceCategory")
    vendor = relationship("Vendor")


class FinanceDocument(TenantBase, UUIDPrimaryKeyMixin, TimestampMixin):
    """An uploaded attachment (bill/receipt/proof) for an expense or vendor bill.
    Polymorphic parent via (owner_type, owner_id) — app-validated, no FK."""

    __tablename__ = "finance_documents"
    __table_args__ = (
        Index("ix_finance_documents_owner", "owner_type", "owner_id"),
        {"schema": "tenant"},
    )

    owner_type: Mapped[str] = mapped_column(String(24), nullable=False)  # 'expense' | 'vendor_bill'
    owner_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    doc_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    uploaded_by_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("public.users.id", ondelete="SET NULL"), nullable=True
    )


class ManualIncome(
    TenantBase, UUIDPrimaryKeyMixin, TimestampMixin, TenantAuditMixin, TenantSoftDeleteMixin, _GstAmountMixin
):
    """Income NOT originating from a sale/booking (interest, rent, misc). Sale
    revenue stays in SalesOrder/Booking — this only records the extras, so the
    finance dashboard unions the two without duplicating a sale."""

    __tablename__ = "manual_income"
    __table_args__ = (
        CheckConstraint("amount_entered >= 0", name="ck_manual_income_amount_non_negative"),
        UniqueConstraint("income_number", name="uq_manual_income_income_number"),
        Index("ix_manual_income_category", "category_id"),
        Index("ix_manual_income_date", "income_date"),
        {"schema": "tenant"},
    )

    income_number: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    category_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("finance_categories.id", ondelete="RESTRICT"), nullable=False
    )
    source: Mapped[str | None] = mapped_column(String(120), nullable=True)  # bank, tenant, party…
    project_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)  # cross-domain, no FK
    income_date: Mapped[date] = mapped_column(Date, nullable=False)
    payment_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    category = relationship("FinanceCategory")
