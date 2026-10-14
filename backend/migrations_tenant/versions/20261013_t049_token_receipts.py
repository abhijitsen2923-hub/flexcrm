"""The token becomes a real payment: payment_receipts.is_token (+ one token receipt per booking), and a one-time,
careful catch-up of tokens recorded before it.

Until now a booking's token / booking amount lived only in bookings.token_* — never a receipt — so it was left out of
"paid", Customer Receivables and the refund's gross paid. From now on the app keeps exactly one receipt with
is_token = true per booking that mirrors the token (app/real_estate/token_receipts.py); a partial unique index makes a
second one impossible.

Catch-up (per tenant, idempotent — a second run finds nothing to do):
1. Link: a booking with a token but no token receipt whose receipt sits on a "Booking amount" row this catch-up made
   on an earlier run (milestone_key "__token__"), else whose receipt has the SAME amount and date as the token (staff
   entered the token as a payment too) → that receipt is marked is_token. No money changes. Any booking, cancelled or
   not (the flag only says which receipt is the token).
2. Create: a live (not deleted, not cancelled) booking with a token and NO receipts and NO instalments gets a "Booking
   amount" row (demand = paid = the token, milestone_key "__token__", due on the token's date — else the booking's
   created date) and its token receipt applied to it. Except a DRAFT whose lead has another live CONFIRMED booking:
   that draft is a leftover the confirmed booking replaced (staff may have recorded the same money there), so it is
   left alone and listed in the log ("left: superseded draft") for review — never counted as money twice.
3. Everything else is left as it was (the app still shows such a token from bookings.token_*).
Counts are printed per tenant.

Also adds payment_schedules.raised_by_mark: the id of the "reached" mark (projects.milestones_reached entry) that
raised a demand, so undoing a mark removes demands a mark raised — never one raised by hand on a single booking.
Marks made before this revision get an id here, and the plan demands of their milestone in their scope that name no
mark yet (a % set) are stamped with it — a tower's own mark first, then the whole-project mark. Those are exactly the
demands the old undo would have taken back, so undoing an old mark still takes them back, and so does a newer mark of
another scope that overlaps it (without the stamp, undoing the old whole-project mark while a new tower mark stands,
then the tower mark, would leave that tower's demands behind for good). A mark the old code makes after this ran (during
the rollout) has no id; undoing it keeps the old rule (app/real_estate/payment_plan.py).

Downgrade drops the index and the columns only: rows and receipts the catch-up created stay (they are real money; code
from before this revision reads them as an ordinary paid row + receipt).

Runs per tenant via the migration search_path.

Revision ID: 20261013_t049
Revises: 20261013_t048
Create Date: 2026-10-13 14:00:00.000000
"""

import json
import logging
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text


revision: str = "20261013_t049"
down_revision: str | None = "20261013_t048"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

TOKEN_KEY = "__token__"

# Step 2's bookings (over `bookings b`): live, with a token, and with no receipts and no instalments at all.
_CREATE_CANDIDATE = """(
    b.is_deleted = false
    AND b.status <> 'cancelled'
    AND b.token_amount IS NOT NULL AND b.token_amount > 0
    AND NOT EXISTS (SELECT 1 FROM payment_receipts r WHERE r.booking_id = b.id)
    AND NOT EXISTS (SELECT 1 FROM payment_schedules s WHERE s.booking_id = b.id)
)"""
# A draft whose lead has another live, confirmed booking — the booking that replaced it.
_SUPERSEDED_DRAFT = """(
    b.status = 'draft'
    AND EXISTS (
        SELECT 1 FROM bookings o
        WHERE o.lead_id = b.lead_id AND o.id <> b.id AND o.is_deleted = false AND o.status = 'confirmed'
    )
)"""


def _mark_id_ok(value) -> bool:
    return isinstance(value, str) and 0 < len(value) <= 32  # payment_schedules.raised_by_mark is VARCHAR(32)


def _stamp_marks(conn) -> tuple[int, int]:
    """Give every "reached" mark without an id one, and stamp it on the plan demands it covers (module docstring).
    Returns (marks given an id, demands stamped). Odd JSON (not a list, entries that aren't marks, a tower id that
    isn't one) is left as it is — it never fails the upgrade."""
    given = stamped = 0
    projects = conn.execute(
        text("SELECT id, milestones_reached FROM projects WHERE milestones_reached IS NOT NULL")
    ).fetchall()
    for project in projects:
        marks = project.milestones_reached
        if isinstance(marks, str):
            try:
                marks = json.loads(marks)
            except ValueError:
                continue
        if not isinstance(marks, list):
            continue
        changed = False
        for entry in marks:
            if isinstance(entry, dict) and isinstance(entry.get("key"), str) and not _mark_id_ok(entry.get("id")):
                entry["id"] = uuid.uuid4().hex
                given += 1
                changed = True
        if changed:
            conn.execute(
                text(
                    "UPDATE projects SET milestones_reached = CAST(:marks AS json), updated_at = now() WHERE id = :id"
                ),
                {"marks": json.dumps(marks), "id": project.id},
            )
        # A tower's own mark first: a demand both marks cover then names the tower mark (either may take it back —
        # the undo's coverage rules decide), and the whole-project mark stamps the rest.
        scoped = [
            e for e in marks if isinstance(e, dict) and isinstance(e.get("key"), str) and _mark_id_ok(e.get("id"))
        ]
        for entry in sorted(scoped, key=lambda e: not e.get("tower_id")):
            params = {"mark": entry["id"], "key": entry["key"], "project": project.id}
            tower_term = ""
            if entry.get("tower_id"):
                try:
                    params["tower"] = str(uuid.UUID(str(entry["tower_id"])))
                except ValueError:
                    continue
                tower_term = "AND u.tower_id = CAST(:tower AS uuid)"
            stamped += conn.execute(
                text(
                    f"""
                    UPDATE payment_schedules s
                    SET raised_by_mark = :mark, updated_at = now()
                    FROM bookings b JOIN units u ON u.id = b.unit_id
                    WHERE s.booking_id = b.id AND u.project_id = :project AND b.is_deleted = false {tower_term}
                      AND s.milestone_key = :key AND s.raised_by_mark IS NULL AND s.percent IS NOT NULL
                    """
                ),
                params,
            ).rowcount
    return given, stamped


def upgrade() -> None:
    op.add_column(
        "payment_receipts", sa.Column("is_token", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.add_column("payment_schedules", sa.Column("raised_by_mark", sa.String(32), nullable=True))
    op.create_index(
        "uq_payment_receipts_booking_token",
        "payment_receipts",
        ["booking_id"],
        unique=True,
        postgresql_where=sa.text("is_token"),
        sqlite_where=sa.text("is_token"),
    )

    conn = op.get_bind()
    # 1. Link — at most one receipt per booking (DISTINCT ON): the catch-up's own row first, then the oldest match.
    linked = conn.execute(
        text(
            """
            WITH picked AS (
                SELECT DISTINCT ON (r.booking_id) r.id
                FROM payment_receipts r
                JOIN bookings b ON b.id = r.booking_id
                LEFT JOIN payment_schedules s ON s.id = r.schedule_id
                WHERE b.token_amount IS NOT NULL AND b.token_amount > 0
                  AND NOT EXISTS (
                      SELECT 1 FROM payment_receipts t WHERE t.booking_id = b.id AND t.is_token
                  )
                  AND (
                      s.milestone_key = :key
                      OR (r.amount = b.token_amount AND r.paid_on = b.token_received_on)
                  )
                ORDER BY r.booking_id, COALESCE(s.milestone_key = :key, false) DESC, r.created_at, r.id
            )
            UPDATE payment_receipts r
            SET is_token = true, updated_at = now()
            FROM picked
            WHERE r.id = picked.id
            RETURNING r.id
            """
        ),
        {"key": TOKEN_KEY},
    ).fetchall()

    # 2. Create — the paid "Booking amount" row and its token receipt, in one statement (the row's id is made once,
    # in the MATERIALIZED step, and used by both inserts). A draft superseded by a confirmed booking of the same lead
    # is left out — listed first so the log can name it.
    superseded = [
        str(row.id)
        for row in conn.execute(
            text(
                f"""
                SELECT b.id FROM bookings b
                WHERE {_CREATE_CANDIDATE} AND {_SUPERSEDED_DRAFT}
                ORDER BY b.id
                """
            )
        ).fetchall()
    ]
    created = conn.execute(
        text(
            f"""
            WITH target AS MATERIALIZED (
                SELECT b.id AS booking_id,
                       b.token_amount AS amount,
                       COALESCE(b.token_received_on, b.created_at::date) AS paid_on,
                       COALESCE(NULLIF(b.token_mode, ''), 'other') AS mode,
                       b.token_reference AS reference,
                       gen_random_uuid() AS schedule_id
                FROM bookings b
                WHERE {_CREATE_CANDIDATE} AND NOT {_SUPERSEDED_DRAFT}
            ),
            new_rows AS (
                INSERT INTO payment_schedules (
                    id, created_at, updated_at, booking_id, installment_name, due_date,
                    demand_amount, paid_amount, outstanding, is_overdue, milestone_key, percent
                )
                SELECT schedule_id, now(), now(), booking_id, 'Booking amount', paid_on,
                       amount, amount, 0, false, :key, NULL
                FROM target
                RETURNING id
            )
            INSERT INTO payment_receipts (
                id, created_at, updated_at, booking_id, schedule_id, amount, paid_on, mode, reference, notes, is_token
            )
            SELECT gen_random_uuid(), now(), now(), t.booking_id, t.schedule_id, t.amount, t.paid_on, t.mode,
                   t.reference, 'Token / booking amount', true
            FROM target t
            RETURNING booking_id
            """
        ),
        {"key": TOKEN_KEY},
    ).fetchall()

    # 3. Marks: ids for the "reached" marks made before this revision, stamped on the demands they cover.
    marks_given, demands_stamped = _stamp_marks(conn)

    left = conn.execute(
        text(
            """
            SELECT count(*) FROM bookings b
            WHERE b.token_amount IS NOT NULL AND b.token_amount > 0
              AND NOT EXISTS (SELECT 1 FROM payment_receipts r WHERE r.booking_id = b.id AND r.is_token)
            """
        )
    ).scalar()
    schema = conn.execute(text("SELECT current_schema()")).scalar()
    # The migration logger, so the counts land in the server log next to "Running upgrade …" for each workspace.
    drafts = f"left: superseded draft: {len(superseded)}"
    if superseded:
        shown = ", ".join(superseded[:20]) + (f" (+{len(superseded) - 20} more)" if len(superseded) > 20 else "")
        drafts += f" (bookings {shown})"
    logging.getLogger("alembic.runtime.migration").info(
        f"[t049] {schema}: token receipts linked to an existing receipt: {len(linked)}; "
        f"created with a paid 'Booking amount' row: {len(created)}; tokens left as they were: {left}; {drafts}; "
        f"reached marks given an id: {marks_given}; demands stamped with their mark: {demands_stamped}"
    )


def downgrade() -> None:
    # Only the flag goes: rows / receipts the catch-up created stay (see the module docstring).
    op.drop_index("uq_payment_receipts_booking_token", table_name="payment_receipts")
    op.drop_column("payment_receipts", "is_token")
    op.drop_column("payment_schedules", "raised_by_mark")
