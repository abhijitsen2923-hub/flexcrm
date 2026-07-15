"""stage_transitions.next_action_date: DATE -> TIMESTAMPTZ.

Follow-ups now capture a date AND time (FR-4), so the column becomes a timestamp.
Existing date values cast to midnight.

Revision ID: 20260715_t014
Revises: 20260710_t013
Create Date: 2026-07-15 10:00:00.000000
"""

from collections.abc import Sequence

from alembic import op


revision: str = "20260715_t014"
down_revision: str | None = "20260710_t013"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE stage_transitions "
        "ALTER COLUMN next_action_date TYPE timestamptz USING next_action_date::timestamptz"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE stage_transitions "
        "ALTER COLUMN next_action_date TYPE date USING next_action_date::date"
    )
