"""Add `business_type` to users.

Lets each account record which industry (Education / Travel) the user's
business operates in. Set at registration; drives the default industry filter
on Leads (and later Customers/Finance/HR) so the CRM feels scoped to one
vertical without losing the ability to switch.

Revision ID: 20260521_0003
Revises: 20260521_0002
Create Date: 2026-05-21 13:30:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260521_0003"
down_revision: str | None = "20260521_0002"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # `lead_industry_enum` was created in 20260521_0002, so reuse it here.
    lead_industry_enum = postgresql.ENUM(
        "education", "travel", name="lead_industry_enum", create_type=False
    )
    op.add_column(
        "users",
        sa.Column("business_type", lead_industry_enum, nullable=True),
    )
    op.create_index("ix_users_business_type", "users", ["business_type"])


def downgrade() -> None:
    op.drop_index("ix_users_business_type", table_name="users")
    op.drop_column("users", "business_type")
