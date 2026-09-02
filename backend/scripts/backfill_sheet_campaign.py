#!/usr/bin/env python3
"""One-off backfill: populate leads.campaign for Meta-sheet-imported leads whose
campaign name currently lives only in the notes blob.

Context
    Before the meta_sheet_mapper fix, sheet-imported leads got their campaign name
    written only into notes ("campaign: <name>"), not the dedicated `campaign`
    column — so the Leads list shows "—" and the Campaign filter can't see them.
    New imports are fixed at the mapper; re-syncing is idempotent (it skips leads
    already ingested, keyed on external_id), so it will NOT retro-fill the rows
    already in the DB. This script does that one-time retro-fill.

    It reads the "campaign: <value>" line from each lead's notes and writes it to
    the campaign column, ONLY where campaign IS NULL and source_provider =
    'google_sheets'. Manually-set campaigns are never touched.

Usage
    cd backend
    python scripts/backfill_sheet_campaign.py            # PREVIEW only (no writes)
    python scripts/backfill_sheet_campaign.py --apply     # perform the update

Environment (no app deps required — only psycopg2)
    Reads the DB URL from SYNC_DATABASE_URL or DATABASE_URL (an env var, or a
    KEY=VALUE line in backend/.env). An async URL (postgresql+asyncpg://...) is
    accepted and normalised for psycopg2. In Cloud Shell:
        pip install psycopg2-binary
        export DATABASE_URL='postgresql://USER:PASS@HOST/DB?sslmode=require'

Safety
    - Preview (default) counts + prints samples; writes NOTHING.
    - --apply wraps each tenant schema's updates in its own transaction.
    - Only touches live leads (is_deleted = false) with campaign IS NULL and
      source_provider = 'google_sheets'. Only the tenant(s) using the Sheet
      integration have such rows, so other tenants are naturally untouched.
"""
from __future__ import annotations

import argparse
import logging
import os
import re
from contextlib import contextmanager
from typing import Iterator

import psycopg2
from psycopg2.extras import RealDictCursor

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _resolve_db_url() -> str:
    """DB URL from SYNC_DATABASE_URL / DATABASE_URL (env, then backend/.env),
    normalised to a plain sync URL psycopg2 accepts (async driver suffix stripped).
    Kept dependency-free on purpose so this runs in a bare Cloud Shell."""
    values: dict[str, str] = {}
    for key in ("SYNC_DATABASE_URL", "DATABASE_URL"):
        if os.environ.get(key):
            values[key] = os.environ[key]
    env_path = os.path.join(os.getcwd(), ".env")
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                if key in ("SYNC_DATABASE_URL", "DATABASE_URL") and key not in values:
                    values[key] = val.strip().strip('"').strip("'")
    url = values.get("SYNC_DATABASE_URL") or values.get("DATABASE_URL")
    if not url:
        raise SystemExit(
            "No DB URL found. Set SYNC_DATABASE_URL or DATABASE_URL, e.g.\n"
            "  export DATABASE_URL='postgresql://USER:PASS@HOST/DB?sslmode=require'"
        )
    for driver in ("+asyncpg", "+psycopg2", "+psycopg"):
        url = url.replace(driver, "")
    return url

# The attribution line the mapper writes into notes is exactly "campaign: <value>"
# on its own line — match it line-anchored so we never pick up a substring from a
# custom-question answer elsewhere in the blob. Use horizontal whitespace ([^\S\n])
# after the colon, NOT \s, so an empty value can't let \s* swallow the newline and
# capture the following line's text.
_CAMPAIGN_LINE = re.compile(r"^campaign:[^\S\n]*(.+)$", re.MULTILINE)
_MAX_LEN = 120  # leads.campaign is String(120)
_PROVIDER = "google_sheets"


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


def extract_campaign(notes: str | None) -> str | None:
    """Pull the campaign value from a lead's notes ("campaign: <value>" line)."""
    if not notes:
        return None
    match = _CAMPAIGN_LINE.search(notes)
    if not match:
        return None
    value = match.group(1).strip()
    return value[:_MAX_LEN] if value else None


def backfill_schema(cur, schema: str, apply: bool) -> tuple[int, int, list[tuple[str, str]]]:
    """Return (candidate_rows, extractable, samples) for one tenant schema."""
    cur.execute(
        f'''
        SELECT id, notes
        FROM "{schema}".leads
        WHERE source_provider = %s
          AND campaign IS NULL
          AND is_deleted = false
          AND notes IS NOT NULL
          AND notes LIKE %s
        ''',
        (_PROVIDER, "%campaign:%"),
    )
    rows = cur.fetchall()

    pairs: list[tuple[str, str]] = []
    for row in rows:
        campaign = extract_campaign(row["notes"])
        if campaign:
            pairs.append((str(row["id"]), campaign))

    samples = pairs[:5]

    if apply and pairs:
        for lead_id, campaign in pairs:
            cur.execute(
                f'UPDATE "{schema}".leads SET campaign = %s WHERE id = %s',
                (campaign, lead_id),
            )
    return len(rows), len(pairs), samples


def run(apply: bool = False) -> None:
    url = _resolve_db_url()
    logger.info("Connecting to %s", url.split("@")[-1])  # mask credentials
    logger.info("Mode: %s", "APPLY (writing)" if apply else "PREVIEW (no writes)")

    grand_candidates = grand_updated = 0
    with get_conn(url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name, schema_name FROM organizations WHERE is_deleted = false")
            orgs = cur.fetchall()
        logger.info("Found %d active organizations", len(orgs))

        for org in orgs:
            schema = org["schema_name"]
            name = org["name"]
            with conn.cursor() as cur:
                if not schema_exists(cur, schema):
                    continue
                try:
                    candidates, extractable, samples = backfill_schema(cur, schema, apply)
                    if candidates == 0:
                        continue
                    logger.info("--- Org: %s (schema: %s)", name, schema)
                    logger.info(
                        "  %d sheet leads with NULL campaign + a campaign: note line; %d extractable",
                        candidates,
                        extractable,
                    )
                    for lead_id, campaign in samples:
                        logger.info("    e.g. %s -> %r", lead_id, campaign)
                    if apply:
                        conn.commit()
                        logger.info("  Committed %d campaign updates for %s", extractable, name)
                    else:
                        logger.info("  (preview) would update %d leads for %s", extractable, name)
                    grand_candidates += candidates
                    grand_updated += extractable
                except Exception as exc:
                    conn.rollback()
                    logger.error("  ROLLBACK for %s: %s", name, exc)
                    raise

    logger.info(
        "Done. candidates=%d, %s=%d",
        grand_candidates,
        "updated" if apply else "would-update",
        grand_updated,
    )
    if not apply:
        logger.info("Preview only — no changes made. Re-run with --apply to write.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Backfill leads.campaign from notes for Meta-sheet-imported leads."
    )
    parser.add_argument("--apply", action="store_true", help="Write updates (default: preview only).")
    args = parser.parse_args()
    run(apply=args.apply)
