"""Per-lead currency (multi-currency support).

Adds `leads.currency` (ISO 4217). Backfilled to INR for existing rows.
The allow-list per org lives in `app.core.currencies` — Education orgs
get INR + USD by default, Travel gets INR + USD + EUR. Per-org overrides
via `Organization.features["currency.options"]`.

Revision ID: 20260522_0008
Revises: 20260522_0007
Create Date: 2026-05-22 18:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260522_0008"
down_revision: str | None = "20260522_0007"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "leads",
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="INR"),
    )
    # Drop the server_default — application code sets the value explicitly
    # going forward (validated against the org's allow-list).
    op.alter_column("leads", "currency", server_default=None)


def downgrade() -> None:
    op.drop_column("leads", "currency")
