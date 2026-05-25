"""Phases 2-5 schema additions in a single additive migration.

- Phase 2: `lead_documents`, `leads.batch_code`.
- Phase 3: Customer lifecycle columns, `delivery_logs`, `renewals`, `referrals`,
  enums (customer_lifecycle_stage_enum, renewal_status_enum, referral_status_enum).
- Phase 4: finance tables (sales_orders, sales_order_assists, invoices,
  payments, commission_ledger, refunds) + matching enums.
- Phase 5: hr tables (employee_profiles, performance_snapshots).

Migration is additive — no data wipe. Existing leads/customers keep working.

Revision ID: 20260522_0005
Revises: 20260522_0004
Create Date: 2026-05-22 14:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260522_0005"
down_revision: str | None = "20260522_0004"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


_NEW_ENUMS: list[tuple[str, list[str]]] = [
    ("customer_lifecycle_stage_enum", ["onboarding", "active", "at_risk", "renewal_due", "renewed", "churned"]),
    ("renewal_status_enum", ["upcoming", "renewed", "declined"]),
    ("referral_status_enum", ["pending", "awarded", "dismissed"]),
    ("invoice_status_enum", ["draft", "issued", "paid", "refunded", "void"]),
    ("payment_status_enum", ["pending", "received", "refunded"]),
    ("commission_direction_enum", ["accrued", "payable", "paid", "reversed"]),
]


def _create_enum_sql(name: str, values: list[str]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return (
        "DO $$ BEGIN "
        f"CREATE TYPE {name} AS ENUM ({quoted}); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
    )


def upgrade() -> None:
    for name, values in _NEW_ENUMS:
        op.execute(_create_enum_sql(name, values))

    customer_lifecycle = postgresql.ENUM(
        "onboarding", "active", "at_risk", "renewal_due", "renewed", "churned",
        name="customer_lifecycle_stage_enum",
        create_type=False,
    )
    renewal_status = postgresql.ENUM("upcoming", "renewed", "declined", name="renewal_status_enum", create_type=False)
    referral_status = postgresql.ENUM("pending", "awarded", "dismissed", name="referral_status_enum", create_type=False)
    invoice_status = postgresql.ENUM(
        "draft", "issued", "paid", "refunded", "void", name="invoice_status_enum", create_type=False
    )
    payment_status = postgresql.ENUM("pending", "received", "refunded", name="payment_status_enum", create_type=False)
    commission_direction = postgresql.ENUM(
        "accrued", "payable", "paid", "reversed", name="commission_direction_enum", create_type=False
    )

    # --- Phase 2: lead_documents + leads.batch_code ----------------------
    op.add_column("leads", sa.Column("batch_code", sa.String(length=64), nullable=True))

    op.create_table(
        "lead_documents",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("doc_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("uploaded_path", sa.String(length=512), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_lead_documents_lead_id", "lead_documents", ["lead_id"])
    op.create_index("ix_lead_documents_lead_doc_type", "lead_documents", ["lead_id", "doc_type"])

    # --- Phase 3: customer lifecycle columns + new tables ----------------
    op.add_column("customers", sa.Column("lifecycle_stage", customer_lifecycle, nullable=False, server_default="onboarding"))
    op.add_column("customers", sa.Column("customer_number", sa.Integer(), nullable=True))
    op.create_unique_constraint("uq_customers_customer_number", "customers", ["customer_number"])
    op.add_column("customers", sa.Column("onboarding_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("customers", sa.Column("renewal_due_at", sa.Date(), nullable=True))
    op.add_column("customers", sa.Column("ltv", sa.Numeric(12, 2), nullable=False, server_default="0"))
    op.add_column("customers", sa.Column("churn_reason", sa.String(length=255), nullable=True))
    op.add_column("customers", sa.Column("original_owner_id", sa.Uuid(), nullable=True))
    op.add_column("customers", sa.Column("current_owner_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_customers_original_owner", "customers", "users", ["original_owner_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_customers_current_owner", "customers", "users", ["current_owner_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_customers_lifecycle_stage", "customers", ["lifecycle_stage"])
    op.create_index("ix_customers_renewal_due_at", "customers", ["renewal_due_at"])
    op.create_index("ix_customers_original_owner_id", "customers", ["original_owner_id"])
    op.create_index("ix_customers_current_owner_id", "customers", ["current_owner_id"])

    op.create_table(
        "delivery_logs",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("item", sa.String(length=255), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("delivered_by_id", sa.Uuid(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["delivered_by_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_delivery_logs_customer_id", "delivery_logs", ["customer_id"])
    op.create_index("ix_delivery_logs_delivered_by_id", "delivery_logs", ["delivered_by_id"])
    op.create_index("ix_delivery_logs_customer_delivered_at", "delivery_logs", ["customer_id", "delivered_at"])

    op.create_table(
        "renewals",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("status", renewal_status, nullable=False, server_default="upcoming"),
        sa.Column("renewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("amount >= 0", name="ck_renewals_amount_non_negative"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_renewals_customer_id", "renewals", ["customer_id"])
    op.create_index("ix_renewals_due_date", "renewals", ["due_date"])
    op.create_index("ix_renewals_customer_due_date", "renewals", ["customer_id", "due_date"])

    op.create_table(
        "referrals",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("referring_customer_id", sa.Uuid(), nullable=False),
        sa.Column("referred_lead_id", sa.Uuid(), nullable=True),
        sa.Column("awarded_credit", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("status", referral_status, nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["referring_customer_id"], ["customers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["referred_lead_id"], ["leads.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_referrals_referring_customer", "referrals", ["referring_customer_id"])
    op.create_index("ix_referrals_referred_lead", "referrals", ["referred_lead_id"])

    # --- Phase 4: finance tables ----------------------------------------
    op.create_table(
        "sales_orders",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("order_number", sa.String(length=32), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=True),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("primary_owner_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("deal_value", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="INR"),
        sa.Column("payment_status", payment_status, nullable=False, server_default="pending"),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint("deal_value >= 0", name="ck_sales_orders_value_non_negative"),
        sa.UniqueConstraint("order_number", name="uq_sales_orders_order_number"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["primary_owner_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["deleted_by_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_sales_orders_customer", "sales_orders", ["customer_id"])
    op.create_index("ix_sales_orders_owner", "sales_orders", ["primary_owner_id"])
    op.create_index("ix_sales_orders_lead_id", "sales_orders", ["lead_id"])

    op.create_table(
        "sales_order_assists",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("sales_order_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("percent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.CheckConstraint("percent >= 0 AND percent <= 100", name="ck_sales_order_assists_percent_range"),
        sa.ForeignKeyConstraint(["sales_order_id"], ["sales_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_sales_order_assists_sales_order_id", "sales_order_assists", ["sales_order_id"])
    op.create_index("ix_sales_order_assists_user", "sales_order_assists", ["user_id"])

    op.create_table(
        "invoices",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("invoice_number", sa.String(length=32), nullable=False),
        sa.Column("sales_order_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("status", invoice_status, nullable=False, server_default="issued"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint("amount >= 0", name="ck_invoices_amount_non_negative"),
        sa.UniqueConstraint("invoice_number", name="uq_invoices_invoice_number"),
        sa.ForeignKeyConstraint(["sales_order_id"], ["sales_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["deleted_by_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_invoices_sales_order", "invoices", ["sales_order_id"])
    op.create_index("ix_invoices_status", "invoices", ["status"])

    op.create_table(
        "payments",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("invoice_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("method", sa.String(length=64), nullable=True),
        sa.Column("txn_ref", sa.String(length=120), nullable=True),
        sa.Column("recorded_by_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint("amount >= 0", name="ck_payments_amount_non_negative"),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recorded_by_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_payments_invoice", "payments", ["invoice_id"])

    op.create_table(
        "commission_ledger",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("sales_order_id", sa.Uuid(), nullable=True),
        sa.Column("direction", commission_direction, nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sales_order_id"], ["sales_orders.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_commission_ledger_user_id", "commission_ledger", ["user_id"])
    op.create_index("ix_commission_ledger_sales_order_id", "commission_ledger", ["sales_order_id"])
    op.create_index("ix_commission_ledger_user_recorded", "commission_ledger", ["user_id", "recorded_at"])

    op.create_table(
        "refunds",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("payment_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("refunded_by_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint("amount >= 0", name="ck_refunds_amount_non_negative"),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["refunded_by_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_refunds_payment_id", "refunds", ["payment_id"])

    # --- Phase 5: hr tables ---------------------------------------------
    op.create_table(
        "employee_profiles",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("target_revenue_monthly", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("commission_rate", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("manager_id", sa.Uuid(), nullable=True),
        sa.Column("score_weights", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("user_id", name="uq_employee_profiles_user"),
        sa.CheckConstraint("commission_rate >= 0 AND commission_rate <= 100", name="ck_employee_profiles_rate_range"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["manager_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_employee_profiles_user_id", "employee_profiles", ["user_id"])

    op.create_table(
        "performance_snapshots",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("deals_closed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("revenue", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("collections", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("conversion_rate", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("pipeline_velocity_days", sa.Numeric(6, 2), nullable=False, server_default="0"),
        sa.Column("activity_quality", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("retention", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("score", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("grade", sa.String(length=2), nullable=False, server_default="D"),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("user_id", "snapshot_date", name="uq_performance_snapshots_user_date"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_performance_snapshots_user_id", "performance_snapshots", ["user_id"])
    op.create_index("ix_performance_snapshots_user_date", "performance_snapshots", ["user_id", "snapshot_date"])


def downgrade() -> None:
    op.drop_index("ix_performance_snapshots_user_date", table_name="performance_snapshots")
    op.drop_index("ix_performance_snapshots_user_id", table_name="performance_snapshots")
    op.drop_table("performance_snapshots")
    op.drop_index("ix_employee_profiles_user_id", table_name="employee_profiles")
    op.drop_table("employee_profiles")

    op.drop_index("ix_refunds_payment_id", table_name="refunds")
    op.drop_table("refunds")
    op.drop_index("ix_commission_ledger_user_recorded", table_name="commission_ledger")
    op.drop_index("ix_commission_ledger_sales_order_id", table_name="commission_ledger")
    op.drop_index("ix_commission_ledger_user_id", table_name="commission_ledger")
    op.drop_table("commission_ledger")
    op.drop_index("ix_payments_invoice", table_name="payments")
    op.drop_table("payments")
    op.drop_index("ix_invoices_status", table_name="invoices")
    op.drop_index("ix_invoices_sales_order", table_name="invoices")
    op.drop_table("invoices")
    op.drop_index("ix_sales_order_assists_user", table_name="sales_order_assists")
    op.drop_index("ix_sales_order_assists_sales_order_id", table_name="sales_order_assists")
    op.drop_table("sales_order_assists")
    op.drop_index("ix_sales_orders_lead_id", table_name="sales_orders")
    op.drop_index("ix_sales_orders_owner", table_name="sales_orders")
    op.drop_index("ix_sales_orders_customer", table_name="sales_orders")
    op.drop_table("sales_orders")

    op.drop_index("ix_referrals_referred_lead", table_name="referrals")
    op.drop_index("ix_referrals_referring_customer", table_name="referrals")
    op.drop_table("referrals")

    op.drop_index("ix_renewals_customer_due_date", table_name="renewals")
    op.drop_index("ix_renewals_due_date", table_name="renewals")
    op.drop_index("ix_renewals_customer_id", table_name="renewals")
    op.drop_table("renewals")

    op.drop_index("ix_delivery_logs_customer_delivered_at", table_name="delivery_logs")
    op.drop_index("ix_delivery_logs_delivered_by_id", table_name="delivery_logs")
    op.drop_index("ix_delivery_logs_customer_id", table_name="delivery_logs")
    op.drop_table("delivery_logs")

    op.drop_index("ix_customers_current_owner_id", table_name="customers")
    op.drop_index("ix_customers_original_owner_id", table_name="customers")
    op.drop_index("ix_customers_renewal_due_at", table_name="customers")
    op.drop_index("ix_customers_lifecycle_stage", table_name="customers")
    op.drop_constraint("fk_customers_current_owner", "customers", type_="foreignkey")
    op.drop_constraint("fk_customers_original_owner", "customers", type_="foreignkey")
    op.drop_column("customers", "current_owner_id")
    op.drop_column("customers", "original_owner_id")
    op.drop_column("customers", "churn_reason")
    op.drop_column("customers", "ltv")
    op.drop_column("customers", "renewal_due_at")
    op.drop_column("customers", "onboarding_started_at")
    op.drop_constraint("uq_customers_customer_number", "customers", type_="unique")
    op.drop_column("customers", "customer_number")
    op.drop_column("customers", "lifecycle_stage")

    op.drop_index("ix_lead_documents_lead_doc_type", table_name="lead_documents")
    op.drop_index("ix_lead_documents_lead_id", table_name="lead_documents")
    op.drop_table("lead_documents")
    op.drop_column("leads", "batch_code")

    for name, _ in reversed(_NEW_ENUMS):
        op.execute(f"DROP TYPE IF EXISTS {name};")
