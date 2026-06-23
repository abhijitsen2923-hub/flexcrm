"""Drop organization_id from the 20 tables that moved to per-tenant schemas.

Run AFTER the data backfill script has been executed and row counts validated.
This migration is irreversible — ensure the backfill has completed successfully
before running.

Revision ID: 20260623_0101
Revises: 20260623_0100
Create Date: 2026-06-23
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260623_0101"
down_revision: str | None = "20260623_0100"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

# Tables in public schema that carried organization_id for row-level tenancy.
# These 20 tables' data has been migrated to per-tenant schemas; organization_id
# is no longer the isolation mechanism and must be dropped.
_TABLES = [
    "leads",
    "customers",
    "deals",
    "tasks",
    "activities",
    "notifications",
    "stage_transitions",
    "referrals",
    "renewals",
    "lead_documents",
    "delivery_logs",
    "user_permission_grants",
    "sales_orders",
    "sales_order_assists",
    "invoices",
    "payments",
    "commission_ledger",
    "refunds",
    "employee_profiles",
    "performance_snapshots",
]

# Known index names on organization_id per table. Any missing index is silently
# skipped (if_exists handles that). Named constraints are listed explicitly so
# they can be restored in downgrade().
_ORG_ID_INDEXES = {
    "leads": "ix_leads_organization_id",
    "customers": "ix_customers_organization_id",
    "deals": "ix_deals_organization_id",
    "tasks": "ix_tasks_organization_id",
    "activities": "ix_activities_organization_id",
    "notifications": "ix_notifications_organization_id",
    "stage_transitions": "ix_stage_transitions_organization_id",
    "referrals": "ix_referrals_organization_id",
    "renewals": "ix_renewals_organization_id",
    "lead_documents": "ix_lead_documents_organization_id",
    "delivery_logs": "ix_delivery_logs_organization_id",
    "user_permission_grants": "ix_user_permission_grants_organization_id",
    "sales_orders": "ix_sales_orders_organization_id",
    "sales_order_assists": "ix_sales_order_assists_organization_id",
    "invoices": "ix_invoices_organization_id",
    "payments": "ix_payments_organization_id",
    "commission_ledger": "ix_commission_ledger_organization_id",
    "refunds": "ix_refunds_organization_id",
    "employee_profiles": "ix_employee_profiles_organization_id",
    "performance_snapshots": "ix_performance_snapshots_organization_id",
}


def upgrade() -> None:
    for table in _TABLES:
        # 1. Drop index on organization_id if it exists.
        idx = _ORG_ID_INDEXES.get(table)
        if idx:
            op.drop_index(idx, table_name=table, if_exists=True)

        # 2. Drop the FK constraint referencing public.organizations.
        #    The constraint name follows the pattern set by Alembic autogenerate.
        op.drop_constraint(
            f"fk_{table}_organization_id_organizations",
            table,
            type_="foreignkey",
            # mssql_drop_constraint: handled via if_exists in some dialects;
            # on PG this raises if absent — use try/except in case name differs.
        ) if _fk_exists(table, f"fk_{table}_organization_id_organizations") else None

        # 3. Drop the column.
        op.drop_column(table, "organization_id")


def downgrade() -> None:
    """Restore organization_id columns and indexes.

    IMPORTANT: This does NOT restore data. After downgrade, public tables will
    have the column but it will be NULL for all rows. The backfill script must
    be re-run in reverse (or from a backup) to restore the original values.
    """
    for table in reversed(_TABLES):
        op.add_column(
            table,
            sa.Column(
                "organization_id",
                sa.Uuid(),
                sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                nullable=True,
            ),
        )
        idx = _ORG_ID_INDEXES.get(table)
        if idx:
            op.create_index(idx, table, ["organization_id"])


def _fk_exists(table: str, constraint_name: str) -> bool:
    """Check if a FK constraint exists on the table in the current DB."""
    bind = op.get_bind()
    result = bind.execute(sa.text("""
        SELECT 1
        FROM information_schema.table_constraints
        WHERE constraint_type = 'FOREIGN KEY'
          AND table_name = :table
          AND constraint_name = :name
          AND table_schema = 'public'
    """), {"table": table, "name": constraint_name})
    return result.fetchone() is not None
