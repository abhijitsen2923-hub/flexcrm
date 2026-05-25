"""Phase 7 — multi-tenancy.

Creates the `organizations` table and adds an `organization_id` FK to every
domain table. Existing rows are backfilled to a "Default Organization" so
nothing breaks; the column is then promoted to NOT NULL.

Tables touched (20+):
- users (FK + index)
- customers, leads, deals, tasks, activities, notifications
- stage_transitions, lead_documents
- delivery_logs, renewals, referrals
- sales_orders, sales_order_assists, invoices, payments,
  commission_ledger, refunds
- employee_profiles, performance_snapshots

`pipeline_stages` and `refresh_tokens` stay global (config + token tables).

Revision ID: 20260522_0006
Revises: 20260522_0005
Create Date: 2026-05-22 16:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260522_0006"
down_revision: str | None = "20260522_0005"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


# Tables that participate in tenancy. The order matters: users + customers
# come early because they're referenced by FKs from other tables.
SCOPED_TABLES: list[str] = [
    "users",
    "customers",
    "leads",
    "deals",
    "tasks",
    "activities",
    "notifications",
    "stage_transitions",
    "lead_documents",
    "delivery_logs",
    "renewals",
    "referrals",
    "sales_orders",
    "sales_order_assists",
    "invoices",
    "payments",
    "commission_ledger",
    "refunds",
    "employee_profiles",
    "performance_snapshots",
]


def upgrade() -> None:
    lead_industry_enum = postgresql.ENUM(
        "education", "travel", name="lead_industry_enum", create_type=False
    )

    # --- 1. Create the organizations table -----------------------------
    op.create_table(
        "organizations",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("business_type", lead_industry_enum, nullable=False),
        sa.Column("plan", sa.String(length=32), nullable=False, server_default="free"),
        sa.Column("features", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_id", sa.Uuid(), nullable=True),
    )
    op.create_index("ix_organizations_name", "organizations", ["name"])

    # FKs from organizations → users are added at the end (after users gets
    # its organization_id), to avoid a chicken/egg between the two tables.

    # --- 2. Detect whether backfill is needed --------------------------
    # On a fresh deploy (e.g. production against a clean Neon DB) there are
    # no existing rows to backfill, so we skip the placeholder-org insert
    # and the UPDATE. This keeps `organizations` empty until the first real
    # `/auth/register` call creates a tenant.
    #
    # On an existing dev DB upgrading through this migration, `users` has
    # rows that pre-date the multi-tenancy column; we plant a Default
    # Organization, stamp every scoped row to it, and let the dev later
    # rename/migrate as needed.
    bind = op.get_bind()
    existing_user_count = bind.execute(sa.text("SELECT COUNT(*) FROM users")).scalar() or 0
    needs_backfill = existing_user_count > 0

    if needs_backfill:
        op.execute(
            """
            INSERT INTO organizations (id, name, business_type, plan)
            VALUES (
                '00000000-0000-0000-0000-000000000001',
                'Default Organization',
                'education',
                'free'
            )
            """
        )

    # --- 3. Add organization_id columns ---------------------------------
    # Nullable first, backfill only if needed, then promote to NOT NULL +
    # add the FK. Empty tables go straight to NOT NULL safely.
    for table in SCOPED_TABLES:
        op.add_column(table, sa.Column("organization_id", sa.Uuid(), nullable=True))
        if needs_backfill:
            op.execute(
                f"UPDATE {table} SET organization_id = '00000000-0000-0000-0000-000000000001'"
            )
        op.alter_column(table, "organization_id", nullable=False)
        op.create_index(f"ix_{table}_organization_id", table, ["organization_id"])
        op.create_foreign_key(
            f"fk_{table}_organization",
            table,
            "organizations",
            ["organization_id"],
            ["id"],
            ondelete="CASCADE",
        )

    # NOTE: per-org uniqueness for lead_number / customer_number is applied
    # in migration 0007 (kept separate so this migration is purely the
    # tenancy column additions).

    # --- 4. Organization audit FKs (after users has organization_id) ---
    op.create_foreign_key(
        "fk_organizations_created_by",
        "organizations",
        "users",
        ["created_by_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_organizations_updated_by",
        "organizations",
        "users",
        ["updated_by_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_organizations_deleted_by",
        "organizations",
        "users",
        ["deleted_by_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_organizations_deleted_by", "organizations", type_="foreignkey")
    op.drop_constraint("fk_organizations_updated_by", "organizations", type_="foreignkey")
    op.drop_constraint("fk_organizations_created_by", "organizations", type_="foreignkey")

    for table in reversed(SCOPED_TABLES):
        op.drop_constraint(f"fk_{table}_organization", table, type_="foreignkey")
        op.drop_index(f"ix_{table}_organization_id", table_name=table)
        op.drop_column(table, "organization_id")

    op.drop_index("ix_organizations_name", table_name="organizations")
    op.drop_table("organizations")
