"""Callyzer perf: external_calls aggregate indexes + performance_snapshots.call_activity.

Two GROUP-BY-friendly composite indexes on external_calls (per-employee aggregation
filters by call_at and groups by user_id / emp_number — today only call_at is indexed),
and a nullable call_activity factor column on performance_snapshots (NULL = the call
factor was not applied for that snapshot, e.g. an org without the callyzer module, so
its grade is unchanged). Per-tenant schema (search_path).

Revision ID: 20260915_t041
Revises: 20260914_t040
Create Date: 2026-09-15 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260915_t041"
down_revision: str | None = "20260914_t040"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_external_calls_user_call_at", "external_calls", ["user_id", "call_at"])
    op.create_index("ix_external_calls_emp_call_at", "external_calls", ["emp_number", "call_at"])
    op.add_column(
        "performance_snapshots",
        sa.Column("call_activity", sa.Numeric(5, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("performance_snapshots", "call_activity")
    op.drop_index("ix_external_calls_emp_call_at", table_name="external_calls")
    op.drop_index("ix_external_calls_user_call_at", table_name="external_calls")
