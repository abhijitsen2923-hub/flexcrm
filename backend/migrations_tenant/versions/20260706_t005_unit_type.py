"""Add units.unit_type (residential / parking / shop / godown).

Revision ID: 20260706_t005
Revises: 20260702_t004
Create Date: 2026-07-06 12:05:00.000000
"""

from collections.abc import Sequence

from alembic import op


revision: str = "20260706_t005"
down_revision: str | None = "20260702_t004"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # Plain string column (not a Postgres enum) — validated in the app layer via
    # UnitType. IF NOT EXISTS keeps it idempotent across tenant schemas.
    op.execute(
        "ALTER TABLE units ADD COLUMN IF NOT EXISTS unit_type VARCHAR(32) NOT NULL DEFAULT 'residential'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE units DROP COLUMN IF EXISTS unit_type")
