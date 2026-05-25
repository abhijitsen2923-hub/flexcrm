"""Create initial CRM schema.

Revision ID: 20260519_0001
Revises:
Create Date: 2026-05-19 11:50:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260519_0001"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


# All column types reference existing PG enum types by name. `create_type=False`
# stops `op.create_table()` from emitting CREATE TYPE again — we pre-create
# them idempotently in `upgrade()` via DO blocks.
def _enum(*values: str, name: str) -> postgresql.ENUM:
    return postgresql.ENUM(*values, name=name, create_type=False)


user_role_enum = _enum("admin", "manager", "sales", "support", "analyst", name="user_role_enum")
user_status_enum = _enum("active", "inactive", "invited", "suspended", name="user_status_enum")
customer_status_enum = _enum("active", "inactive", "prospect", "churned", name="customer_status_enum")
lead_stage_enum = _enum("new", "qualified", "proposal", "negotiation", "won", "lost", name="lead_stage_enum")
deal_stage_enum = _enum(
    "discovery", "proposal", "negotiation", "closed_won", "closed_lost", name="deal_stage_enum"
)
deal_status_enum = _enum("open", "won", "lost", "on_hold", name="deal_status_enum")
task_priority_enum = _enum("low", "medium", "high", "urgent", name="task_priority_enum")
task_status_enum = _enum("pending", "in_progress", "completed", "cancelled", name="task_status_enum")
activity_type_enum = _enum(
    "note", "call", "email", "meeting", "task", "status_change", name="activity_type_enum"
)
notification_status_enum = _enum("unread", "read", name="notification_status_enum")


_ENUM_DEFINITIONS: list[tuple[str, list[str]]] = [
    ("user_role_enum", ["admin", "manager", "sales", "support", "analyst"]),
    ("user_status_enum", ["active", "inactive", "invited", "suspended"]),
    ("customer_status_enum", ["active", "inactive", "prospect", "churned"]),
    ("lead_stage_enum", ["new", "qualified", "proposal", "negotiation", "won", "lost"]),
    ("deal_stage_enum", ["discovery", "proposal", "negotiation", "closed_won", "closed_lost"]),
    ("deal_status_enum", ["open", "won", "lost", "on_hold"]),
    ("task_priority_enum", ["low", "medium", "high", "urgent"]),
    ("task_status_enum", ["pending", "in_progress", "completed", "cancelled"]),
    ("activity_type_enum", ["note", "call", "email", "meeting", "task", "status_change"]),
    ("notification_status_enum", ["unread", "read"]),
]


def _create_enum_sql(name: str, values: list[str]) -> str:
    quoted_values = ", ".join(f"'{value}'" for value in values)
    return (
        "DO $$ BEGIN "
        f"CREATE TYPE {name} AS ENUM ({quoted_values}); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
    )


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto";')

    for name, values in _ENUM_DEFINITIONS:
        op.execute(_create_enum_sql(name, values))

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", user_role_enum, nullable=False),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("status", user_status_enum, nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["deleted_by_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_created_by_id", "users", ["created_by_id"])
    op.create_index("ix_users_updated_by_id", "users", ["updated_by_id"])
    op.create_index("ix_users_deleted_by_id", "users", ["deleted_by_id"])
    op.create_index("ix_users_is_deleted", "users", ["is_deleted"])
    op.create_index("ix_users_deleted_at", "users", ["deleted_at"])
    op.create_index(
        "uq_users_email_active",
        "users",
        ["email"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
    )

    op.create_table(
        "customers",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_name", sa.String(length=255), nullable=False),
        sa.Column("contact_name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=120), nullable=True),
        sa.Column("status", customer_status_enum, nullable=False, server_default="prospect"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["deleted_by_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_customers_company_name", "customers", ["company_name"])
    op.create_index("ix_customers_email", "customers", ["email"])
    op.create_index("ix_customers_phone", "customers", ["phone"])
    op.create_index("ix_customers_source", "customers", ["source"])
    op.create_index("ix_customers_source_status", "customers", ["source", "status"])
    op.create_index("ix_customers_created_by_id", "customers", ["created_by_id"])
    op.create_index("ix_customers_updated_by_id", "customers", ["updated_by_id"])
    op.create_index("ix_customers_deleted_by_id", "customers", ["deleted_by_id"])
    op.create_index("ix_customers_is_deleted", "customers", ["is_deleted"])
    op.create_index("ix_customers_deleted_at", "customers", ["deleted_at"])

    op.create_table(
        "leads",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("lead_stage", lead_stage_enum, nullable=False),
        sa.Column("value", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("probability", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expected_close_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("assigned_to_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint("probability >= 0 AND probability <= 100", name="ck_leads_probability_range"),
        sa.CheckConstraint("value >= 0", name="ck_leads_value_non_negative"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["assigned_to_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["deleted_by_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_leads_customer_id", "leads", ["customer_id"])
    op.create_index("ix_leads_expected_close_date", "leads", ["expected_close_date"])
    op.create_index("ix_leads_assigned_to_id", "leads", ["assigned_to_id"])
    op.create_index("ix_leads_created_by_id", "leads", ["created_by_id"])
    op.create_index("ix_leads_updated_by_id", "leads", ["updated_by_id"])
    op.create_index("ix_leads_deleted_by_id", "leads", ["deleted_by_id"])
    op.create_index("ix_leads_is_deleted", "leads", ["is_deleted"])
    op.create_index("ix_leads_deleted_at", "leads", ["deleted_at"])
    op.create_index("ix_leads_stage_assigned_to", "leads", ["lead_stage", "assigned_to_id"])

    op.create_table(
        "tasks",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("assigned_to_id", sa.Uuid(), nullable=True),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("priority", task_priority_enum, nullable=False, server_default="medium"),
        sa.Column("status", task_status_enum, nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["assigned_to_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["deleted_by_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_tasks_assigned_to_id", "tasks", ["assigned_to_id"])
    op.create_index("ix_tasks_due_date", "tasks", ["due_date"])
    op.create_index("ix_tasks_created_by_id", "tasks", ["created_by_id"])
    op.create_index("ix_tasks_updated_by_id", "tasks", ["updated_by_id"])
    op.create_index("ix_tasks_deleted_by_id", "tasks", ["deleted_by_id"])
    op.create_index("ix_tasks_is_deleted", "tasks", ["is_deleted"])
    op.create_index("ix_tasks_deleted_at", "tasks", ["deleted_at"])
    op.create_index("ix_tasks_assigned_due_date", "tasks", ["assigned_to_id", "due_date"])
    op.create_index("ix_tasks_status_priority", "tasks", ["status", "priority"])

    op.create_table(
        "activities",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("type", activity_type_enum, nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["deleted_by_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_activities_customer_id", "activities", ["customer_id"])
    op.create_index("ix_activities_created_by_id", "activities", ["created_by_id"])
    op.create_index("ix_activities_updated_by_id", "activities", ["updated_by_id"])
    op.create_index("ix_activities_deleted_by_id", "activities", ["deleted_by_id"])
    op.create_index("ix_activities_is_deleted", "activities", ["is_deleted"])
    op.create_index("ix_activities_deleted_at", "activities", ["deleted_at"])
    op.create_index("ix_activities_customer_created_at", "activities", ["customer_id", "created_at"])
    op.create_index("ix_activities_type", "activities", ["type"])

    op.create_table(
        "deals",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("stage", deal_stage_enum, nullable=False),
        sa.Column("expected_close", sa.Date(), nullable=True),
        sa.Column("status", deal_status_enum, nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint("amount >= 0", name="ck_deals_amount_non_negative"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["deleted_by_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_deals_customer_id", "deals", ["customer_id"])
    op.create_index("ix_deals_expected_close", "deals", ["expected_close"])
    op.create_index("ix_deals_created_by_id", "deals", ["created_by_id"])
    op.create_index("ix_deals_updated_by_id", "deals", ["updated_by_id"])
    op.create_index("ix_deals_deleted_by_id", "deals", ["deleted_by_id"])
    op.create_index("ix_deals_is_deleted", "deals", ["is_deleted"])
    op.create_index("ix_deals_deleted_at", "deals", ["deleted_at"])
    op.create_index("ix_deals_stage_status", "deals", ["stage", "status"])

    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("read_status", notification_status_enum, nullable=False, server_default="unread"),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["deleted_by_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_deleted_by_id", "notifications", ["deleted_by_id"])
    op.create_index("ix_notifications_is_deleted", "notifications", ["is_deleted"])
    op.create_index("ix_notifications_deleted_at", "notifications", ["deleted_at"])
    op.create_index("ix_notifications_user_read_created", "notifications", ["user_id", "read_status", "created_at"])

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_id", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_expires_at", "refresh_tokens", ["expires_at"])
    op.create_index("ix_refresh_tokens_revoked_at", "refresh_tokens", ["revoked_at"])
    op.create_index("ix_refresh_tokens_user_expires", "refresh_tokens", ["user_id", "expires_at"])
    op.create_index("uq_refresh_tokens_token_id", "refresh_tokens", ["token_id"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_refresh_tokens_token_id", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_user_expires", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_revoked_at", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_expires_at", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")

    op.drop_index("ix_notifications_user_read_created", table_name="notifications")
    op.drop_index("ix_notifications_deleted_at", table_name="notifications")
    op.drop_index("ix_notifications_is_deleted", table_name="notifications")
    op.drop_index("ix_notifications_deleted_by_id", table_name="notifications")
    op.drop_index("ix_notifications_user_id", table_name="notifications")
    op.drop_table("notifications")

    op.drop_index("ix_deals_stage_status", table_name="deals")
    op.drop_index("ix_deals_deleted_at", table_name="deals")
    op.drop_index("ix_deals_is_deleted", table_name="deals")
    op.drop_index("ix_deals_deleted_by_id", table_name="deals")
    op.drop_index("ix_deals_updated_by_id", table_name="deals")
    op.drop_index("ix_deals_created_by_id", table_name="deals")
    op.drop_index("ix_deals_expected_close", table_name="deals")
    op.drop_index("ix_deals_customer_id", table_name="deals")
    op.drop_table("deals")

    op.drop_index("ix_activities_type", table_name="activities")
    op.drop_index("ix_activities_customer_created_at", table_name="activities")
    op.drop_index("ix_activities_deleted_at", table_name="activities")
    op.drop_index("ix_activities_is_deleted", table_name="activities")
    op.drop_index("ix_activities_deleted_by_id", table_name="activities")
    op.drop_index("ix_activities_updated_by_id", table_name="activities")
    op.drop_index("ix_activities_created_by_id", table_name="activities")
    op.drop_index("ix_activities_customer_id", table_name="activities")
    op.drop_table("activities")

    op.drop_index("ix_tasks_status_priority", table_name="tasks")
    op.drop_index("ix_tasks_assigned_due_date", table_name="tasks")
    op.drop_index("ix_tasks_deleted_at", table_name="tasks")
    op.drop_index("ix_tasks_is_deleted", table_name="tasks")
    op.drop_index("ix_tasks_deleted_by_id", table_name="tasks")
    op.drop_index("ix_tasks_updated_by_id", table_name="tasks")
    op.drop_index("ix_tasks_created_by_id", table_name="tasks")
    op.drop_index("ix_tasks_due_date", table_name="tasks")
    op.drop_index("ix_tasks_assigned_to_id", table_name="tasks")
    op.drop_table("tasks")

    op.drop_index("ix_leads_stage_assigned_to", table_name="leads")
    op.drop_index("ix_leads_deleted_at", table_name="leads")
    op.drop_index("ix_leads_is_deleted", table_name="leads")
    op.drop_index("ix_leads_deleted_by_id", table_name="leads")
    op.drop_index("ix_leads_updated_by_id", table_name="leads")
    op.drop_index("ix_leads_created_by_id", table_name="leads")
    op.drop_index("ix_leads_assigned_to_id", table_name="leads")
    op.drop_index("ix_leads_expected_close_date", table_name="leads")
    op.drop_index("ix_leads_customer_id", table_name="leads")
    op.drop_table("leads")

    op.drop_index("ix_customers_deleted_at", table_name="customers")
    op.drop_index("ix_customers_is_deleted", table_name="customers")
    op.drop_index("ix_customers_deleted_by_id", table_name="customers")
    op.drop_index("ix_customers_updated_by_id", table_name="customers")
    op.drop_index("ix_customers_created_by_id", table_name="customers")
    op.drop_index("ix_customers_source_status", table_name="customers")
    op.drop_index("ix_customers_source", table_name="customers")
    op.drop_index("ix_customers_phone", table_name="customers")
    op.drop_index("ix_customers_email", table_name="customers")
    op.drop_index("ix_customers_company_name", table_name="customers")
    op.drop_table("customers")

    op.drop_index("uq_users_email_active", table_name="users")
    op.drop_index("ix_users_deleted_at", table_name="users")
    op.drop_index("ix_users_is_deleted", table_name="users")
    op.drop_index("ix_users_deleted_by_id", table_name="users")
    op.drop_index("ix_users_updated_by_id", table_name="users")
    op.drop_index("ix_users_created_by_id", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")

    for name, _ in reversed(_ENUM_DEFINITIONS):
        op.execute(f"DROP TYPE IF EXISTS {name};")
