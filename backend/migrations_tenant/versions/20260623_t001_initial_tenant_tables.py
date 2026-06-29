"""Initial per-tenant schema tables.

Creates the 20 domain tables in whichever schema is active (set via
search_path by the env.py runner before this migration is applied).
All FK references to public.users use the fully-qualified name so they
work correctly from any tenant schema.

Revision ID: 20260623_t001
Revises:
Create Date: 2026-06-23 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20260623_t001"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "leads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_id", sa.Uuid(), nullable=True),
        sa.Column("customer_id", sa.Uuid(), nullable=True),
        # Bind explicitly to public.lead_industry_enum so this column matches
        # public.pipeline_stages.industry (required for the cross-schema FK
        # fk_leads_pipeline_stage). Must use postgresql.ENUM, not sa.Enum:
        # sa.Enum ignores create_type=False and would either create a tenant-local
        # copy (→ DatatypeMismatch on the FK) or, with schema="public", try to
        # CREATE TYPE in public where it already exists (→ DuplicateObject).
        # postgresql.ENUM honors create_type=False, emitting no CREATE TYPE.
        sa.Column(
            "industry",
            postgresql.ENUM(
                "travel", "education", "realestate",
                name="lead_industry_enum",
                create_type=False,
                schema="public",
            ),
            nullable=False,
        ),
        sa.Column("stage_code", sa.String(64), nullable=False),
        sa.Column("lead_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("value", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("probability", sa.Integer(), nullable=False),
        sa.Column("expected_close_date", sa.Date(), nullable=True),
        sa.Column("source", sa.String(120), nullable=True),
        sa.Column("interest", sa.String(255), nullable=True),
        sa.Column("contact_name", sa.String(255), nullable=False),
        sa.Column("contact_email", sa.String(255), nullable=True),
        sa.Column("contact_phone", sa.String(32), nullable=True),
        sa.Column("company_name", sa.String(255), nullable=True),
        sa.Column("last_comment_preview", sa.Text(), nullable=True),
        sa.Column("last_comment_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assigned_to_id", sa.Uuid(), nullable=True),
        sa.Column("batch_code", sa.String(64), nullable=True),
        sa.CheckConstraint("probability >= 0 AND probability <= 100", name="ck_leads_probability_range"),
        sa.CheckConstraint("value >= 0", name="ck_leads_value_non_negative"),
        sa.ForeignKeyConstraint(["assigned_to_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["deleted_by_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["industry", "stage_code"],
            ["public.pipeline_stages.industry", "public.pipeline_stages.code"],
            name="fk_leads_pipeline_stage",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("lead_number", name="uq_leads_lead_number"),
    )
    op.create_index("ix_leads_industry_stage_code", "leads", ["industry", "stage_code"])
    op.create_index("ix_leads_stage_assigned_to", "leads", ["stage_code", "assigned_to_id"])
    op.create_index("ix_leads_contact_email", "leads", ["contact_email"])
    op.create_index("ix_leads_expected_close_date", "leads", ["expected_close_date"])
    op.create_index("ix_leads_is_deleted", "leads", ["is_deleted"])
    op.create_index("ix_leads_source", "leads", ["source"])
    op.create_index("ix_leads_industry", "leads", ["industry"])
    op.create_index("ix_leads_stage_code", "leads", ["stage_code"])
    op.create_index("ix_leads_customer_id", "leads", ["customer_id"])
    op.create_index("ix_leads_assigned_to_id", "leads", ["assigned_to_id"])

    op.create_table(
        "customers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_id", sa.Uuid(), nullable=True),
        sa.Column("company_name", sa.String(255), nullable=False),
        sa.Column("contact_name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("source", sa.String(120), nullable=True),
        sa.Column("status", sa.Enum("active", "inactive", "prospect", "churned", name="customer_status_enum", create_type=False), nullable=False),
        sa.Column("lifecycle_stage", sa.Enum("onboarding", "active", "at_risk", "renewal_due", "renewed", "churned", name="customer_lifecycle_stage_enum", create_type=False), nullable=False),
        sa.Column("customer_number", sa.Integer(), nullable=True),
        sa.Column("onboarding_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("renewal_due_at", sa.Date(), nullable=True),
        sa.Column("ltv", sa.Numeric(12, 2), nullable=False),
        sa.Column("churn_reason", sa.String(255), nullable=True),
        sa.Column("original_owner_id", sa.Uuid(), nullable=True),
        sa.Column("current_owner_id", sa.Uuid(), nullable=True),
        sa.Column("source_lead_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["deleted_by_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["original_owner_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["current_owner_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_lead_id"], ["leads.id"], name="fk_customers_source_lead", ondelete="SET NULL", use_alter=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("customer_number", name="uq_customers_customer_number"),
    )
    op.create_index("ix_customers_company_name", "customers", ["company_name"])
    op.create_index("ix_customers_source_status", "customers", ["source", "status"])
    op.create_index("ix_customers_lifecycle_stage", "customers", ["lifecycle_stage"])
    op.create_index("ix_customers_email", "customers", ["email"])
    op.create_index("ix_customers_phone", "customers", ["phone"])
    op.create_index("ix_customers_is_deleted", "customers", ["is_deleted"])
    op.create_index("ix_customers_renewal_due_at", "customers", ["renewal_due_at"])
    op.create_index("ix_customers_source_lead_id", "customers", ["source_lead_id"])

    # Add leads.customer_id FK now that customers table exists.
    op.create_foreign_key(
        "fk_leads_customer",
        "leads", "customers",
        ["customer_id"], ["id"],
        ondelete="RESTRICT",
    )

    op.create_table(
        "deals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_id", sa.Uuid(), nullable=True),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("stage", sa.Enum("discovery", "proposal", "negotiation", "closed_won", "closed_lost", name="deal_stage_enum", create_type=False), nullable=False),
        sa.Column("expected_close", sa.Date(), nullable=True),
        sa.Column("status", sa.Enum("open", "won", "lost", "on_hold", name="deal_status_enum", create_type=False), nullable=False),
        sa.CheckConstraint("amount >= 0", name="ck_deals_amount_non_negative"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["deleted_by_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_deals_stage_status", "deals", ["stage", "status"])
    op.create_index("ix_deals_expected_close", "deals", ["expected_close"])
    op.create_index("ix_deals_is_deleted", "deals", ["is_deleted"])
    op.create_index("ix_deals_customer_id", "deals", ["customer_id"])

    op.create_table(
        "tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("assigned_to_id", sa.Uuid(), nullable=True),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("priority", sa.Enum("low", "medium", "high", "urgent", name="task_priority_enum", create_type=False), nullable=False),
        sa.Column("status", sa.Enum("pending", "in_progress", "completed", "cancelled", name="task_status_enum", create_type=False), nullable=False),
        sa.ForeignKeyConstraint(["assigned_to_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["deleted_by_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tasks_assigned_due_date", "tasks", ["assigned_to_id", "due_date"])
    op.create_index("ix_tasks_status_priority", "tasks", ["status", "priority"])
    op.create_index("ix_tasks_is_deleted", "tasks", ["is_deleted"])
    op.create_index("ix_tasks_assigned_to_id", "tasks", ["assigned_to_id"])
    op.create_index("ix_tasks_due_date", "tasks", ["due_date"])

    op.create_table(
        "activities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_id", sa.Uuid(), nullable=True),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.Enum("note", "call", "email", "meeting", "task", "status_change", name="activity_type_enum", create_type=False), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["deleted_by_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_activities_customer_created_at", "activities", ["customer_id", "created_at"])
    op.create_index("ix_activities_type", "activities", ["type"])
    op.create_index("ix_activities_is_deleted", "activities", ["is_deleted"])
    op.create_index("ix_activities_customer_id", "activities", ["customer_id"])

    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_id", sa.Uuid(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("read_status", sa.Enum("unread", "read", name="notification_status_enum", create_type=False), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["public.users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["deleted_by_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notifications_user_read_created", "notifications", ["user_id", "read_status", "created_at"])
    op.create_index("ix_notifications_is_deleted", "notifications", ["is_deleted"])

    op.create_table(
        "stage_transitions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("from_stage_code", sa.String(64), nullable=True),
        sa.Column("to_stage_code", sa.String(64), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("next_action_date", sa.Date(), nullable=True),
        sa.Column("attachment_path", sa.String(512), nullable=True),
        sa.Column("performed_by_id", sa.Uuid(), nullable=True),
        sa.Column("performed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("mentions", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["performed_by_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_stage_transitions_lead_performed_at", "stage_transitions", ["lead_id", "performed_at"])
    op.create_index("ix_stage_transitions_lead_id", "stage_transitions", ["lead_id"])
    op.create_index("ix_stage_transitions_performed_by_id", "stage_transitions", ["performed_by_id"])

    op.create_table(
        "referrals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("referring_customer_id", sa.Uuid(), nullable=False),
        sa.Column("referred_lead_id", sa.Uuid(), nullable=True),
        sa.Column("awarded_credit", sa.Numeric(12, 2), nullable=False),
        sa.Column("status", sa.Enum("pending", "awarded", "dismissed", name="referral_status_enum", create_type=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["referring_customer_id"], ["customers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["referred_lead_id"], ["leads.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_referrals_referring_customer", "referrals", ["referring_customer_id"])
    op.create_index("ix_referrals_referred_lead", "referrals", ["referred_lead_id"])

    op.create_table(
        "renewals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("status", sa.Enum("upcoming", "renewed", "declined", name="renewal_status_enum", create_type=False), nullable=False),
        sa.Column("renewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("amount >= 0", name="ck_renewals_amount_non_negative"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_renewals_customer_due_date", "renewals", ["customer_id", "due_date"])
    op.create_index("ix_renewals_customer_id", "renewals", ["customer_id"])
    op.create_index("ix_renewals_due_date", "renewals", ["due_date"])

    op.create_table(
        "lead_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("doc_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("uploaded_path", sa.String(512), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_lead_documents_lead_doc_type", "lead_documents", ["lead_id", "doc_type"])
    op.create_index("ix_lead_documents_lead_id", "lead_documents", ["lead_id"])

    op.create_table(
        "delivery_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("item", sa.String(255), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("delivered_by_id", sa.Uuid(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["delivered_by_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_delivery_logs_customer_delivered_at", "delivery_logs", ["customer_id", "delivered_at"])
    op.create_index("ix_delivery_logs_customer_id", "delivery_logs", ["customer_id"])
    op.create_index("ix_delivery_logs_delivered_by_id", "delivery_logs", ["delivered_by_id"])

    op.create_table(
        "user_permission_grants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("permission_code", sa.String(64), nullable=False),
        sa.Column("granted_by_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["public.users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["granted_by_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "permission_code", name="uq_user_permission_grants_user_code"),
    )
    op.create_index("ix_user_permission_grants_user_id", "user_permission_grants", ["user_id"])

    # Finance tables
    op.create_table(
        "sales_orders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_id", sa.Uuid(), nullable=True),
        sa.Column("order_number", sa.String(32), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=True),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("primary_owner_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("deal_value", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("payment_status", sa.Enum("pending", "received", "refunded", name="payment_status_enum", create_type=False), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("deal_value >= 0", name="ck_sales_orders_value_non_negative"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["primary_owner_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["deleted_by_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_number", name="uq_sales_orders_order_number"),
    )
    op.create_index("ix_sales_orders_customer", "sales_orders", ["customer_id"])
    op.create_index("ix_sales_orders_owner", "sales_orders", ["primary_owner_id"])
    op.create_index("ix_sales_orders_lead_id", "sales_orders", ["lead_id"])
    op.create_index("ix_sales_orders_is_deleted", "sales_orders", ["is_deleted"])

    op.create_table(
        "sales_order_assists",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("sales_order_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("percent", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.CheckConstraint("percent >= 0 AND percent <= 100", name="ck_sales_order_assists_percent_range"),
        sa.ForeignKeyConstraint(["sales_order_id"], ["sales_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["public.users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sales_order_assists_user", "sales_order_assists", ["user_id"])
    op.create_index("ix_sales_order_assists_sales_order_id", "sales_order_assists", ["sales_order_id"])

    op.create_table(
        "invoices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_id", sa.Uuid(), nullable=True),
        sa.Column("invoice_number", sa.String(32), nullable=False),
        sa.Column("sales_order_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("status", sa.Enum("draft", "issued", "paid", "refunded", "void", name="invoice_status_enum", create_type=False), nullable=False),
        sa.CheckConstraint("amount >= 0", name="ck_invoices_amount_non_negative"),
        sa.ForeignKeyConstraint(["sales_order_id"], ["sales_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["deleted_by_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("invoice_number", name="uq_invoices_invoice_number"),
    )
    op.create_index("ix_invoices_sales_order", "invoices", ["sales_order_id"])
    op.create_index("ix_invoices_status", "invoices", ["status"])
    op.create_index("ix_invoices_is_deleted", "invoices", ["is_deleted"])

    op.create_table(
        "payments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("invoice_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("method", sa.String(64), nullable=True),
        sa.Column("txn_ref", sa.String(120), nullable=True),
        sa.Column("recorded_by_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint("amount >= 0", name="ck_payments_amount_non_negative"),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recorded_by_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_payments_invoice", "payments", ["invoice_id"])

    op.create_table(
        "commission_ledger",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("sales_order_id", sa.Uuid(), nullable=True),
        sa.Column("direction", sa.Enum("accrued", "payable", "paid", "reversed", name="commission_direction_enum", create_type=False), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["public.users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sales_order_id"], ["sales_orders.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_commission_ledger_user_recorded", "commission_ledger", ["user_id", "recorded_at"])
    op.create_index("ix_commission_ledger_user_id", "commission_ledger", ["user_id"])
    op.create_index("ix_commission_ledger_sales_order_id", "commission_ledger", ["sales_order_id"])

    op.create_table(
        "refunds",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("payment_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("refunded_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("refunded_by_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint("amount >= 0", name="ck_refunds_amount_non_negative"),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["refunded_by_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_refunds_payment_id", "refunds", ["payment_id"])

    # HR tables
    op.create_table(
        "employee_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("target_revenue_monthly", sa.Numeric(12, 2), nullable=False),
        sa.Column("commission_rate", sa.Numeric(5, 2), nullable=False),
        sa.Column("manager_id", sa.Uuid(), nullable=True),
        sa.Column("score_weights", sa.JSON(), nullable=True),
        sa.CheckConstraint("commission_rate >= 0 AND commission_rate <= 100", name="ck_employee_profiles_rate_range"),
        sa.ForeignKeyConstraint(["user_id"], ["public.users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["manager_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_employee_profiles_user"),
    )
    op.create_index("ix_employee_profiles_user_id", "employee_profiles", ["user_id"])

    op.create_table(
        "performance_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("deals_closed", sa.Integer(), nullable=False),
        sa.Column("revenue", sa.Numeric(12, 2), nullable=False),
        sa.Column("collections", sa.Numeric(12, 2), nullable=False),
        sa.Column("conversion_rate", sa.Numeric(5, 2), nullable=False),
        sa.Column("pipeline_velocity_days", sa.Numeric(6, 2), nullable=False),
        sa.Column("activity_quality", sa.Numeric(5, 2), nullable=False),
        sa.Column("retention", sa.Numeric(5, 2), nullable=False),
        sa.Column("score", sa.Numeric(5, 2), nullable=False),
        sa.Column("grade", sa.String(2), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["public.users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "snapshot_date", name="uq_performance_snapshots_user_date"),
    )
    op.create_index("ix_performance_snapshots_user_date", "performance_snapshots", ["user_id", "snapshot_date"])
    op.create_index("ix_performance_snapshots_user_id", "performance_snapshots", ["user_id"])


def downgrade() -> None:
    op.drop_table("performance_snapshots")
    op.drop_table("employee_profiles")
    op.drop_table("refunds")
    op.drop_table("commission_ledger")
    op.drop_table("payments")
    op.drop_table("invoices")
    op.drop_table("sales_order_assists")
    op.drop_table("sales_orders")
    op.drop_table("user_permission_grants")
    op.drop_table("delivery_logs")
    op.drop_table("lead_documents")
    op.drop_table("renewals")
    op.drop_table("referrals")
    op.drop_table("stage_transitions")
    op.drop_table("notifications")
    op.drop_table("activities")
    op.drop_table("tasks")
    op.drop_table("deals")
    op.drop_table("customers")
    op.drop_table("leads")
