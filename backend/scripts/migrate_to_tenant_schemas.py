#!/usr/bin/env python3
"""One-time data migration: move all rows from public.* tables into per-tenant schemas.

Run ONCE after all tenants have been provisioned (schemas exist and tenant
Alembic migrations have run). Run with --dry-run first to validate counts.

Usage:
    cd backend
    python scripts/migrate_to_tenant_schemas.py [--dry-run]

Environment:
    SYNC_DATABASE_URL  Synchronous PostgreSQL URL (read from .env automatically).

Safety:
    - Reads organizations to get the list of tenants.
    - For each org, wraps the full INSERT-SELECT in a transaction.
    - On --dry-run: counts only, no writes.
    - Checks the target tenant schema exists before migrating.
    - Does NOT drop or truncate public tables — run the Alembic migration
      20260623_0101_drop_organization_id.py separately after validation.
"""
from __future__ import annotations

import argparse
import logging
import sys
from contextlib import contextmanager
from typing import Iterator

import psycopg2
from psycopg2.extras import RealDictCursor

# Ensure the app package is importable (run from backend/ directory).
sys.path.insert(0, ".")
from app.core.config import get_settings  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


# FK-safe table insertion order. Each table is migrated in this sequence so
# FK constraints in the tenant schema are satisfied when rows are inserted.
TABLE_ORDER = [
    "user_permission_grants",
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
    "sales_orders",
    "sales_order_assists",
    "invoices",
    "payments",
    "commission_ledger",
    "refunds",
    "employee_profiles",
    "performance_snapshots",
]

# Columns to SELECT from each public table (organization_id is excluded —
# it's removed from the tenant schema). Only list the columns that exist
# in both the source (public) and destination (tenant schema) tables.
TABLE_COLUMNS: dict[str, list[str]] = {
    "leads": [
        "id", "created_at", "updated_at", "created_by_id", "updated_by_id",
        "is_deleted", "deleted_at", "deleted_by_id",
        "customer_id", "industry", "stage_code", "lead_number", "title", "value",
        "currency", "probability", "expected_close_date", "source", "interest",
        "contact_name", "contact_email", "contact_phone", "company_name",
        "last_comment_preview", "last_comment_at", "assigned_to_id", "batch_code",
    ],
    "customers": [
        "id", "created_at", "updated_at", "created_by_id", "updated_by_id",
        "is_deleted", "deleted_at", "deleted_by_id",
        "company_name", "contact_name", "email", "phone", "address", "source",
        "status", "lifecycle_stage", "customer_number", "onboarding_started_at",
        "renewal_due_at", "ltv", "churn_reason",
        "original_owner_id", "current_owner_id", "source_lead_id",
    ],
    "deals": [
        "id", "created_at", "updated_at", "created_by_id", "updated_by_id",
        "is_deleted", "deleted_at", "deleted_by_id",
        "customer_id", "title", "amount", "stage", "expected_close", "status",
    ],
    "tasks": [
        "id", "created_at", "updated_at", "created_by_id", "updated_by_id",
        "is_deleted", "deleted_at", "deleted_by_id",
        "title", "description", "assigned_to_id", "due_date", "priority", "status",
    ],
    "activities": [
        "id", "created_at", "updated_at", "created_by_id", "updated_by_id",
        "is_deleted", "deleted_at", "deleted_by_id",
        "customer_id", "type", "note",
    ],
    "notifications": [
        "id", "created_at", "updated_at",
        "is_deleted", "deleted_at", "deleted_by_id",
        "user_id", "message", "read_status", "read_at",
    ],
    "stage_transitions": [
        "id", "lead_id", "from_stage_code", "to_stage_code", "comment",
        "next_action_date", "attachment_path", "performed_by_id", "performed_at", "mentions",
    ],
    "referrals": [
        "id", "referring_customer_id", "referred_lead_id",
        "awarded_credit", "status", "created_at",
    ],
    "renewals": [
        "id", "customer_id", "due_date", "amount", "status", "renewed_at", "created_at",
    ],
    "lead_documents": [
        "id", "lead_id", "doc_type", "status", "uploaded_path", "uploaded_at", "created_at",
    ],
    "delivery_logs": [
        "id", "customer_id", "item", "delivered_at", "delivered_by_id", "notes", "created_at",
    ],
    "user_permission_grants": [
        "id", "created_at", "updated_at",
        "user_id", "permission_code", "granted_by_id",
    ],
    "sales_orders": [
        "id", "created_at", "updated_at", "created_by_id", "updated_by_id",
        "is_deleted", "deleted_at", "deleted_by_id",
        "order_number", "lead_id", "customer_id", "primary_owner_id",
        "title", "deal_value", "currency", "payment_status", "closed_at",
    ],
    "sales_order_assists": [
        "id", "sales_order_id", "user_id", "percent", "reason",
    ],
    "invoices": [
        "id", "created_at", "updated_at", "created_by_id", "updated_by_id",
        "is_deleted", "deleted_at", "deleted_by_id",
        "invoice_number", "sales_order_id", "amount", "due_date", "status",
    ],
    "payments": [
        "id", "invoice_id", "amount", "received_at", "method", "txn_ref", "recorded_by_id",
    ],
    "commission_ledger": [
        "id", "user_id", "sales_order_id", "direction", "amount", "note", "recorded_at",
    ],
    "refunds": [
        "id", "payment_id", "amount", "reason", "refunded_at", "refunded_by_id",
    ],
    "employee_profiles": [
        "id", "created_at", "updated_at",
        "user_id", "target_revenue_monthly", "commission_rate", "manager_id", "score_weights",
    ],
    "performance_snapshots": [
        "id", "user_id", "snapshot_date", "deals_closed", "revenue", "collections",
        "conversion_rate", "pipeline_velocity_days", "activity_quality",
        "retention", "score", "grade", "computed_at",
    ],
}


@contextmanager
def get_conn(url: str) -> Iterator[psycopg2.extensions.connection]:
    conn = psycopg2.connect(url, cursor_factory=RealDictCursor)
    conn.autocommit = False
    try:
        yield conn
    finally:
        conn.close()


def schema_exists(cur, schema_name: str) -> bool:
    cur.execute(
        "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s",
        (schema_name,),
    )
    return cur.fetchone() is not None


def count_rows_in_public(cur, table: str, org_id: str) -> int:
    cur.execute(f"SELECT COUNT(*) AS n FROM public.{table} WHERE organization_id = %s", (org_id,))
    return cur.fetchone()["n"]


def migrate_table(cur, table: str, org_id: str, schema: str, dry_run: bool) -> int:
    columns = TABLE_COLUMNS[table]
    col_list = ", ".join(f'"{c}"' for c in columns)
    count = count_rows_in_public(cur, table, org_id)

    if dry_run or count == 0:
        return count

    cur.execute(f"""
        INSERT INTO "{schema}".{table} ({col_list})
        SELECT {col_list}
        FROM public.{table}
        WHERE organization_id = %s
        ON CONFLICT (id) DO NOTHING
    """, (org_id,))
    return count


def run(dry_run: bool = False) -> None:
    settings = get_settings()
    url = settings.sync_database_url
    logger.info("Connecting to %s", url.split("@")[-1])  # mask credentials

    with get_conn(url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name, schema_name FROM organizations WHERE is_deleted = false")
            orgs = cur.fetchall()

        logger.info("Found %d active organizations", len(orgs))

        for org in orgs:
            org_id = str(org["id"])
            schema = org["schema_name"]
            name = org["name"]

            logger.info("--- Org: %s (schema: %s)", name, schema)

            with conn.cursor() as cur:
                if not schema_exists(cur, schema):
                    logger.warning("  SKIP: schema %r does not exist — run provision_tenant first", schema)
                    continue

                total = 0
                try:
                    for table in TABLE_ORDER:
                        n = migrate_table(cur, table, org_id, schema, dry_run)
                        if n:
                            action = "WOULD copy" if dry_run else "Copied"
                            logger.info("  %s %d rows: %s", action, n, table)
                        total += n

                    if not dry_run:
                        conn.commit()
                        logger.info("  Committed %d total rows for %s", total, name)
                    else:
                        logger.info("  Dry-run total: %d rows would be copied for %s", total, name)
                except Exception as exc:
                    conn.rollback()
                    logger.error("  ROLLBACK for %s: %s", name, exc)
                    raise

    logger.info("Done. %s", "No changes made (dry-run)." if dry_run else "All orgs migrated.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate public row-level data to per-tenant schemas.")
    parser.add_argument("--dry-run", action="store_true", help="Count rows only; do not write.")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
