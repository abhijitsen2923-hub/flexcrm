"""Finance Phase 3 — add employee_profiles.monthly_salary (payroll → expense).

Revision ID: 20260904_t036
Revises: 20260904_t035
Create Date: 2026-09-04 11:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260904_t036"
down_revision: str | None = "20260904_t035"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "employee_profiles",
        sa.Column("monthly_salary", sa.Numeric(12, 2), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("employee_profiles", "monthly_salary")
