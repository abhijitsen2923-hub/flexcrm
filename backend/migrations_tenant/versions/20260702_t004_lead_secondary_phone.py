"""Add leads.contact_phone_alt (optional secondary phone).

Revision ID: 20260702_t004
Revises: 20260623_t003
Create Date: 2026-07-02 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260702_t004"
down_revision: str | None = "20260623_t003"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # IF NOT EXISTS keeps this idempotent when replayed across tenant schemas
    # that may already have been patched out-of-band.
    op.execute('ALTER TABLE leads ADD COLUMN IF NOT EXISTS contact_phone_alt VARCHAR(32)')


def downgrade() -> None:
    op.execute('ALTER TABLE leads DROP COLUMN IF EXISTS contact_phone_alt')
