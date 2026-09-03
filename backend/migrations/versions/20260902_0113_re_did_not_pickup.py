"""Real-estate pipeline: add the "Did Not Pickup" stage at position 3.

A new ACTIVE real-estate stage inserted right after `call` — the call outcome
when a lead can't be reached. The lead stays in the funnel (category `active`,
NOT closed_lost), so it uses a distinct code `did_not_pickup` (the
education/travel `did_not_pick` is closed_lost and lives in the shared
CLOSED_LOST_STAGE_CODES set — we must stay out of it).

Inserting at position 3 shifts `follow_up`..`disqualified` down by one (→ 4..14).
`pipeline_stages` is a PUBLIC/global table, so this single reseed reaches every
tenant. Repositioning is invisible to `leads` (the composite FK is on
`(industry, code)`, not position), so no tenant `leads` remap is needed on
upgrade — only the new row is inserted, nothing retired.

Mirrors the parking pattern of 20260722_0108 (drop the 1..15 position CHECK, park
existing rows at +100 to dodge the UNIQUE(industry, position) collision, place
final positions, re-add the CHECK).

Revision ID: 20260902_0113
Revises: 20260825_0112
Create Date: 2026-09-02 10:00:00.000000
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from alembic import op


revision: str = "20260902_0113"
down_revision: str | None = "20260825_0112"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


# The new stage.
NEW_CODE = "did_not_pickup"
NEW_POSITION = 3
NEW_NAME = "Did Not Pickup"
NEW_CATEGORY = "active"

# Final positions of the existing real-estate stages AFTER inserting the new one
# at position 3 (new_enquiry/call keep their slots; everything from follow_up down
# shifts +1).
FINAL_POSITIONS = {
    "new_enquiry": 1,
    "call": 2,
    "follow_up": 4,
    "site_visit_confirmed": 5,
    "site_visit_done": 6,
    "interested": 7,
    "booked": 8,
    "agreement_payment": 9,
    "registration": 10,
    "possession": 11,
    "sold": 12,
    "not_interested": 13,
    "disqualified": 14,
}

# Pre-insert positions (used by downgrade to restore the 13-stage layout).
ORIGINAL_POSITIONS = {
    "new_enquiry": 1,
    "call": 2,
    "follow_up": 3,
    "site_visit_confirmed": 4,
    "site_visit_done": 5,
    "interested": 6,
    "booked": 7,
    "agreement_payment": 8,
    "registration": 9,
    "possession": 10,
    "sold": 11,
    "not_interested": 12,
    "disqualified": 13,
}


def _drop_position_check(conn) -> None:
    conn.execute(sa.text(
        "ALTER TABLE public.pipeline_stages DROP CONSTRAINT IF EXISTS ck_pipeline_stages_position_range;"
    ))


def _readd_position_check(conn) -> None:
    conn.execute(sa.text(
        "ALTER TABLE public.pipeline_stages "
        "ADD CONSTRAINT ck_pipeline_stages_position_range CHECK (position BETWEEN 1 AND 15);"
    ))


def _park(conn) -> None:
    # Park existing RE rows at +100 so the final positions are free (the +100
    # values exceed the 1..15 CHECK, hence the drop/re-add around this).
    conn.execute(sa.text(
        "UPDATE public.pipeline_stages SET position = position + 100 WHERE industry = 'real_estate';"
    ))


def _reposition(conn, positions: dict[str, int]) -> None:
    for code, position in positions.items():
        conn.execute(
            sa.text(
                "UPDATE public.pipeline_stages SET position = :position "
                "WHERE industry = 'real_estate' AND code = :code;"
            ).bindparams(position=position, code=code)
        )


def upgrade() -> None:
    conn = op.get_bind()

    _drop_position_check(conn)
    _park(conn)

    # Insert the new stage at its final position (idempotent on re-run).
    conn.execute(
        sa.text(
            "INSERT INTO public.pipeline_stages "
            "(id, industry, position, code, name, category, comment_required) "
            "VALUES (:id, 'real_estate', :position, :code, :name, :category, true) "
            "ON CONFLICT (industry, code) DO NOTHING;"
        ).bindparams(
            id=str(uuid4()), position=NEW_POSITION, code=NEW_CODE, name=NEW_NAME, category=NEW_CATEGORY
        )
    )

    # Reposition the existing rows off their parked (+100) slots to their final
    # positions. No leads remap needed — nothing is retired on upgrade.
    _reposition(conn, FINAL_POSITIONS)

    _readd_position_check(conn)


def downgrade() -> None:
    conn = op.get_bind()

    # Any tenant lead sitting on the new stage must be moved off it before the row
    # can be deleted (the leads → pipeline_stages FK is ondelete=RESTRICT). Send
    # them back to `call`, the stage the outcome followed from.
    schemas = conn.execute(
        sa.text("SELECT schema_name FROM public.organizations WHERE schema_name IS NOT NULL;")
    ).scalars().all()
    for schema in schemas:
        exists = conn.execute(
            sa.text("SELECT to_regclass(:t);").bindparams(t=f'"{schema}".leads')
        ).scalar()
        if exists is None:
            continue
        conn.execute(
            sa.text(
                f'UPDATE "{schema}".leads SET stage_code = \'call\' '
                "WHERE industry = 'real_estate' AND stage_code = :old;"
            ).bindparams(old=NEW_CODE)
        )

    _drop_position_check(conn)
    _park(conn)

    # Remove the new stage, then restore the original 13-stage positions.
    conn.execute(
        sa.text(
            "DELETE FROM public.pipeline_stages WHERE industry = 'real_estate' AND code = :code;"
        ).bindparams(code=NEW_CODE)
    )
    _reposition(conn, ORIGINAL_POSITIONS)

    _readd_position_check(conn)
