"""Lead incentive exemption — "Others / owner's reference" sales earn no incentive.

Adds `leads.incentive_exempt` (bool, default false). When true, the Sold accrual
skips BOTH the internal salesperson commission and the channel-partner brokerage.

Revision ID: 20260905_t039
Revises: 20260904_t038
Create Date: 2026-09-05 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260905_t039"
down_revision: str | None = "20260904_t038"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "leads",
        sa.Column("incentive_exempt", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("leads", "incentive_exempt")
