"""Finance vertical Phase 1 — expenses, vendors, vendor bills/payments, categories, docs.

Creates the per-tenant finance tables for the Expenses/Vendors phase. Enum types
are created once in the PUBLIC schema by public migration 0114 and referenced here
with create_type=False (never CREATE TYPE in a per-schema tenant migration — it
would DuplicateObject on the 2nd schema). Cross-domain project links are plain
UUID columns with no FK, per the codebase convention.

Revision ID: 20260903_t033
Revises: 20260827_t032
Create Date: 2026-09-03 10:05:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20260903_t033"
down_revision: str | None = "20260827_t032"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_USERS = "public.users.id"


def _enum(name: str, *values: str):
    return postgresql.ENUM(*values, name=name, create_type=False, schema="public")


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    ]


def _audit() -> list[sa.Column]:
    return [
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
    ]


def _soft_delete() -> list[sa.Column]:
    return [
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_id", sa.Uuid(), nullable=True),
    ]


def _audit_fks() -> list[sa.ForeignKeyConstraint]:
    return [
        sa.ForeignKeyConstraint(["created_by_id"], [_USERS], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_id"], [_USERS], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["deleted_by_id"], [_USERS], ondelete="SET NULL"),
    ]


def _gst_cols() -> list[sa.Column]:
    return [
        sa.Column("gst_applicable", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("gst_treatment", _enum("gst_treatment_enum", "intra_state", "inter_state"), nullable=True),
        sa.Column("gst_inclusive", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("gst_rate", sa.Numeric(5, 2), nullable=True),
        sa.Column("amount_entered", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("taxable_amount", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("cgst_amount", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("sgst_amount", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("igst_amount", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("tds_amount", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("total_amount", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("net_payable", sa.Numeric(14, 2), server_default="0", nullable=False),
    ]


def upgrade() -> None:
    # 1. finance_settings (Timestamp + Audit; no soft-delete)
    op.create_table(
        "finance_settings",
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        *_audit(),
        sa.Column("gst_registered", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("gstin", sa.String(15), nullable=True),
        sa.Column("home_state_code", sa.String(2), nullable=True),
        sa.Column("default_place_of_supply_state", sa.String(2), nullable=True),
        sa.ForeignKeyConstraint(["created_by_id"], [_USERS], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_id"], [_USERS], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    # 2. finance_categories (full mixins)
    op.create_table(
        "finance_categories",
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        *_audit(),
        *_soft_delete(),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("kind", _enum("finance_category_kind_enum", "expense", "income"), nullable=False),
        sa.Column("group_label", sa.String(80), nullable=True),
        sa.Column("source", sa.String(16), server_default="custom", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=True),
        *_audit_fks(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "kind", name="uq_finance_categories_name_kind"),
    )
    op.create_index("ix_finance_categories_kind", "finance_categories", ["kind"])

    # 3. vendors (full mixins)
    op.create_table(
        "vendors",
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        *_audit(),
        *_soft_delete(),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("contact_name", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(40), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("gstin", sa.String(15), nullable=True),
        sa.Column("pan", sa.String(20), nullable=True),
        sa.Column("state_code", sa.String(2), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("bank_account", sa.String(64), nullable=True),
        sa.Column("ifsc", sa.String(20), nullable=True),
        sa.Column("upi", sa.String(120), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        *_audit_fks(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vendors_is_active", "vendors", ["is_active"])

    # 4. vendor_bills (full mixins + GST group; FK → vendors, finance_categories)
    op.create_table(
        "vendor_bills",
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        *_audit(),
        *_soft_delete(),
        sa.Column("bill_number", sa.String(32), nullable=False),
        sa.Column("vendor_id", sa.Uuid(), nullable=False),
        sa.Column("vendor_invoice_no", sa.String(64), nullable=True),
        sa.Column("category_id", sa.Uuid(), nullable=True),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("bill_date", sa.Date(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        *_gst_cols(),
        sa.Column(
            "status",
            _enum("vendor_bill_status_enum", "open", "partially_paid", "paid", "cancelled"),
            server_default="open",
            nullable=False,
        ),
        sa.Column("amount_paid", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("paid_on", sa.Date(), nullable=True),
        sa.CheckConstraint("amount_entered >= 0", name="ck_vendor_bills_amount_non_negative"),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["category_id"], ["finance_categories.id"], ondelete="SET NULL"),
        *_audit_fks(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bill_number", name="uq_vendor_bills_bill_number"),
    )
    op.create_index("ix_vendor_bills_vendor", "vendor_bills", ["vendor_id"])
    op.create_index("ix_vendor_bills_status", "vendor_bills", ["status"])
    op.create_index("ix_vendor_bills_project_id", "vendor_bills", ["project_id"])

    # 5. vendor_payments (Timestamp only; FK → vendor_bills, public.users)
    op.create_table(
        "vendor_payments",
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.Column("payment_number", sa.String(32), nullable=False),
        sa.Column("bill_id", sa.Uuid(), nullable=False),
        sa.Column("vendor_id", sa.Uuid(), nullable=True),
        sa.Column("amount", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("paid_on", sa.Date(), nullable=False),
        sa.Column("method", sa.String(64), nullable=True),
        sa.Column("txn_ref", sa.String(120), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("recorded_by_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint("amount > 0", name="ck_vendor_payments_amount_positive"),
        sa.ForeignKeyConstraint(["bill_id"], ["vendor_bills.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recorded_by_id"], [_USERS], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("payment_number", name="uq_vendor_payments_payment_number"),
    )
    op.create_index("ix_vendor_payments_bill", "vendor_payments", ["bill_id"])

    # 6. expenses (full mixins + GST group; FK → finance_categories, vendors, vendor_bills)
    op.create_table(
        "expenses",
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        *_audit(),
        *_soft_delete(),
        sa.Column("expense_number", sa.String(32), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("category_id", sa.Uuid(), nullable=False),
        sa.Column("vendor_id", sa.Uuid(), nullable=True),
        sa.Column("bill_id", sa.Uuid(), nullable=True),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("department", sa.String(80), nullable=True),
        sa.Column("expense_date", sa.Date(), nullable=False),
        sa.Column("payment_mode", sa.String(32), nullable=True),
        *_gst_cols(),
        sa.Column(
            "status",
            _enum("expense_status_enum", "draft", "submitted", "approved", "rejected", "paid"),
            server_default="draft",
            nullable=False,
        ),
        sa.Column("submitted_by_id", sa.Uuid(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by_id", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_reason", sa.Text(), nullable=True),
        sa.Column("paid_at", sa.Date(), nullable=True),
        sa.CheckConstraint("amount_entered >= 0", name="ck_expenses_amount_non_negative"),
        sa.ForeignKeyConstraint(["category_id"], ["finance_categories.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["bill_id"], ["vendor_bills.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["submitted_by_id"], [_USERS], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["approved_by_id"], [_USERS], ondelete="SET NULL"),
        *_audit_fks(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("expense_number", name="uq_expenses_expense_number"),
    )
    op.create_index("ix_expenses_status", "expenses", ["status"])
    op.create_index("ix_expenses_category", "expenses", ["category_id"])
    op.create_index("ix_expenses_vendor", "expenses", ["vendor_id"])
    op.create_index("ix_expenses_date", "expenses", ["expense_date"])
    op.create_index("ix_expenses_project_id", "expenses", ["project_id"])

    # 7. finance_documents (Timestamp only; FK → public.users)
    op.create_table(
        "finance_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.Column("owner_type", sa.String(24), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("doc_type", sa.String(64), nullable=True),
        sa.Column("file_name", sa.String(255), nullable=True),
        sa.Column("content_type", sa.String(120), nullable=True),
        sa.Column("file_path", sa.String(512), nullable=False),
        sa.Column("uploaded_by_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["uploaded_by_id"], [_USERS], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_finance_documents_owner", "finance_documents", ["owner_type", "owner_id"])


def downgrade() -> None:
    op.drop_table("finance_documents")
    op.drop_table("expenses")
    op.drop_table("vendor_payments")
    op.drop_table("vendor_bills")
    op.drop_table("vendors")
    op.drop_table("finance_categories")
    op.drop_table("finance_settings")
