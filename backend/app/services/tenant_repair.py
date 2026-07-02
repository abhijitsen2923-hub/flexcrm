"""Idempotent repair for tenant schemas provisioned by the OLD migration.

Older tenants ran a migration that used `sa.Enum(..., create_type=False)`, which
(despite the flag) created a tenant-LOCAL copy of each enum type that shadows the
public one. Any INSERT/compare on those columns then fails with
`operator does not exist: <schema>.x_enum = x_enum` / DatatypeMismatch — breaking
create-customer, create-lead, dashboard, analytics, etc.

This converts every shadowed enum column to the public enum type and drops the
now-orphaned local type. Safe to re-run: columns already on `public` are skipped,
and tables missing from a tenant (e.g. real-estate tables on a non-RE tenant) are
skipped. All referenced public enum types already exist (migrations 0001/0005/0102).
"""
from sqlalchemy import text

from app.core.logging import get_logger
from app.database.session import db_manager
from app.services.tenant_provisioner import _SAFE_SCHEMA


logger = get_logger(__name__)


# (table, column, public_enum_type). leads.industry is intentionally excluded —
# it was always bound to public.lead_industry_enum.
_ENUM_COLUMNS: list[tuple[str, str, str]] = [
    # t001 — every tenant
    ("customers", "status", "customer_status_enum"),
    ("customers", "lifecycle_stage", "customer_lifecycle_stage_enum"),
    ("deals", "stage", "deal_stage_enum"),
    ("deals", "status", "deal_status_enum"),
    ("tasks", "priority", "task_priority_enum"),
    ("tasks", "status", "task_status_enum"),
    ("activities", "type", "activity_type_enum"),
    ("notifications", "read_status", "notification_status_enum"),
    ("referrals", "status", "referral_status_enum"),
    ("renewals", "status", "renewal_status_enum"),
    ("sales_orders", "payment_status", "payment_status_enum"),
    ("invoices", "status", "invoice_status_enum"),
    ("commission_ledger", "direction", "commission_direction_enum"),
    # t002 — real-estate tenants only (skipped when the table is absent)
    ("units", "status", "unit_status_enum"),
    ("site_visits", "feedback", "site_visit_feedback_enum"),
    ("bookings", "status", "booking_status_enum"),
]


async def _repair_schema(conn, schema: str, dry_run: bool) -> dict:
    repaired: list[str] = []
    skipped: list[str] = []
    local_enums: set[str] = set()

    for table, column, enum in _ENUM_COLUMNS:
        udt_schema = (
            await conn.execute(
                text(
                    "SELECT udt_schema FROM information_schema.columns "
                    "WHERE table_schema = :s AND table_name = :t AND column_name = :c"
                ),
                {"s": schema, "t": table, "c": column},
            )
        ).scalar_one_or_none()

        if udt_schema is None:
            skipped.append(f"{table}.{column} (absent)")
            continue
        if udt_schema == "public":
            skipped.append(f"{table}.{column} (already public)")
            continue

        # udt_schema == schema → tenant-local shadow → convert to the public type.
        repaired.append(f"{table}.{column}")
        local_enums.add(enum)
        if not dry_run:
            await conn.execute(
                text(
                    f'ALTER TABLE "{schema}"."{table}" '
                    f'ALTER COLUMN "{column}" TYPE public."{enum}" '
                    f'USING "{column}"::text::public."{enum}"'
                )
            )

    if not dry_run:
        for enum in sorted(local_enums):
            await conn.execute(text(f'DROP TYPE IF EXISTS "{schema}"."{enum}"'))

    return {
        "schema": schema,
        "repaired": repaired,
        "dropped_types": sorted(local_enums),
        "skipped": skipped,
    }


async def repair_tenant_enums(dry_run: bool = True) -> list[dict]:
    """Repair every tenant schema. Each tenant is done in its own transaction so
    one failure doesn't roll back the others. Returns a per-tenant report."""
    async with db_manager.engine.connect() as conn:
        rows = (
            await conn.execute(
                text("SELECT name, schema_name FROM organizations WHERE schema_name IS NOT NULL")
            )
        ).all()

    reports: list[dict] = []
    for name, schema in rows:
        if not schema or not _SAFE_SCHEMA.match(schema):
            reports.append({"org": name, "schema": schema, "error": "unsafe/empty schema name — skipped"})
            continue
        try:
            async with db_manager.engine.begin() as conn:
                exists = (
                    await conn.execute(
                        text("SELECT 1 FROM information_schema.schemata WHERE schema_name = :s"),
                        {"s": schema},
                    )
                ).scalar()
                if not exists:
                    reports.append({"org": name, "schema": schema, "skipped": "schema does not exist"})
                    continue
                report = await _repair_schema(conn, schema, dry_run)
            report["org"] = name
            reports.append(report)
            logger.info(
                "tenant_repair(dry_run=%s): %s repaired=%s dropped=%s",
                dry_run, schema, report["repaired"], report["dropped_types"],
            )
        except Exception as exc:  # noqa: BLE001 — report per-tenant, keep going
            logger.exception("tenant_repair failed for schema %s", schema)
            reports.append({"org": name, "schema": schema, "error": str(exc)})

    return reports
