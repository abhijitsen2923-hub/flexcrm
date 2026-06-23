"""Finance domain models — per-tenant schema."""
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
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
from app.database.enums import CommissionDirection, InvoiceStatus, PaymentStatus
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
