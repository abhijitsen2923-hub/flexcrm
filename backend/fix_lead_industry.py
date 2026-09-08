#!/usr/bin/env python3
"""One-off repair: pin every lead's industry to its organisation's business_type.

Fixes leads that were stamped with the WRONG vertical (e.g. a real-estate lead
marked "education") by the old manual-create path, which trusted a client value /
the deprecated per-user business_type instead of the org's. An org is
single-industry, so every lead must match `organizations.business_type`.

For each tenant schema it sets `leads.industry = org.business_type` for every
mismatched lead, keeping the (industry, stage_code) composite FK valid — the
stage_code is preserved when it's valid for the target industry, else reset to
the position-1 stage `new_enquiry` (shared by all verticals). It also heals the
deprecated `public.users.business_type` to match each user's org so the UI shows
the right industry.

Idempotent — re-running once clean changes nothing.

Usage (from backend/ in Cloud Shell, with DATABASE_URL set to the prod DB):
    python fix_lead_industry.py            # DRY RUN — report only, no changes
    python fix_lead_industry.py --apply    # perform the fix (commits)
"""
import os
import re
import sys

try:
    import psycopg2
    from psycopg2 import sql
except ImportError:
    sys.exit("psycopg2 not installed. In Cloud Shell run:  pip install psycopg2-binary")

APPLY = "--apply" in sys.argv
INITIAL_STAGE = "new_enquiry"  # position-1 stage code, shared by all verticals


def resolve_database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        for path in (".env", "backend/.env"):
            if os.path.exists(path):
                with open(path) as fh:
                    for line in fh:
                        line = line.strip()
                        if line.startswith("DATABASE_URL="):
                            url = line.split("=", 1)[1].strip().strip('"').strip("'")
                            break
            if url:
                break
    if not url:
        sys.exit("Set DATABASE_URL (e.g. export DATABASE_URL=postgresql://USER:PASS@HOST/DB?sslmode=require)")
    # psycopg2 is a sync driver — strip any async driver suffix.
    url = re.sub(r"\+asyncpg", "", url)
    url = re.sub(r"\+psycopg2?", "", url)
    return url


def main() -> None:
    conn = psycopg2.connect(resolve_database_url())
    conn.autocommit = False
    cur = conn.cursor()

    print(f"Mode: {'APPLY (will commit)' if APPLY else 'DRY RUN (no changes)'}\n")

    # Only tenant schemas that actually have a `leads` table. The internal
    # "FlexCRM Platform" org (business_type=education) owns a schema but no tenant
    # tables, and a partially-provisioned org might too — without this JOIN the
    # first such schema raises UndefinedTable and aborts the whole run.
    cur.execute(
        "SELECT o.schema_name, o.business_type "
        "FROM organizations o "
        "JOIN information_schema.tables t "
        "  ON t.table_schema = o.schema_name AND t.table_name = 'leads' "
        "WHERE o.schema_name IS NOT NULL AND o.business_type IS NOT NULL "
        "ORDER BY o.schema_name"
    )
    orgs = cur.fetchall()

    total_leads_fixed = 0
    for schema_name, business_type in orgs:
        # Isolate each schema in a savepoint so one bad tenant can't abort the rest.
        cur.execute("SAVEPOINT org_sp")
        try:
            count_q = sql.SQL(
                "SELECT count(*) FROM {}.leads WHERE industry <> %s::lead_industry_enum"
            ).format(sql.Identifier(schema_name))
            cur.execute(count_q, (business_type,))
            n = cur.fetchone()[0]
            if n == 0:
                cur.execute("RELEASE SAVEPOINT org_sp")
                continue
            print(f"[{schema_name}] org={business_type}: {n} lead(s) with a mismatched industry")
            if APPLY:
                update_q = sql.SQL(
                    "UPDATE {}.leads l "
                    "SET industry = %s::lead_industry_enum, "
                    "    stage_code = CASE WHEN EXISTS ("
                    "        SELECT 1 FROM public.pipeline_stages ps "
                    "        WHERE ps.industry = %s::lead_industry_enum AND ps.code = l.stage_code"
                    "    ) THEN l.stage_code ELSE %s END "
                    "WHERE l.industry <> %s::lead_industry_enum"
                ).format(sql.Identifier(schema_name))
                cur.execute(update_q, (business_type, business_type, INITIAL_STAGE, business_type))
                print(f"    -> corrected {cur.rowcount} lead(s) to {business_type}")
                total_leads_fixed += cur.rowcount
            cur.execute("RELEASE SAVEPOINT org_sp")
        except Exception as exc:  # noqa: BLE001 — skip a bad schema, keep the run going
            cur.execute("ROLLBACK TO SAVEPOINT org_sp")
            print(f"    !! skipped {schema_name}: {exc}")

    # Heal the deprecated per-user business_type so it matches each user's org.
    cur.execute(
        "SELECT count(*) FROM users u JOIN organizations o ON u.organization_id = o.id "
        "WHERE u.business_type IS DISTINCT FROM o.business_type"
    )
    n_users = cur.fetchone()[0]
    print(f"\n[users] {n_users} user(s) whose business_type != their org")
    if APPLY and n_users:
        cur.execute(
            "UPDATE users u SET business_type = o.business_type FROM organizations o "
            "WHERE u.organization_id = o.id AND u.business_type IS DISTINCT FROM o.business_type"
        )
        print(f"    -> healed {cur.rowcount} user(s)")

    if APPLY:
        conn.commit()
        print(f"\nDONE. Leads corrected: {total_leads_fixed}. Users healed: {n_users}.")
    else:
        conn.rollback()
        print("\nDRY RUN complete — nothing changed. Re-run with --apply to perform the fix.")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
