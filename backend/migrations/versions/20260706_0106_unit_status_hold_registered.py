"""Revise unit_status_enum: reserved -> hold, add registered.

Real-estate inventory now uses a 5-status model:
available · hold · booked · registered · sold.

Revision ID: 20260706_0106
Revises: 20260701_0105
Create Date: 2026-07-06 12:00:00.000000
"""

from collections.abc import Sequence

from alembic import op


revision: str = "20260706_0106"
down_revision: str | None = "20260701_0105"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # No units exist yet, so no data migration is needed. Rename the old
    # 'reserved' value to 'hold' and add 'registered' between booked and sold.
    op.execute("ALTER TYPE unit_status_enum RENAME VALUE 'reserved' TO 'hold'")
    op.execute("ALTER TYPE unit_status_enum ADD VALUE IF NOT EXISTS 'registered' AFTER 'booked'")


def downgrade() -> None:
    # Enum value removal isn't supported cleanly; just reverse the rename.
    op.execute("ALTER TYPE unit_status_enum RENAME VALUE 'hold' TO 'reserved'")
