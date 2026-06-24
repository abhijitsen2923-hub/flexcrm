"""Add schema_name to organizations for per-tenant schema routing.

Phase 0 of the schema-per-tenant migration. Additive only — safe to deploy
without a maintenance window. Existing orgs are backfilled using:
    {business_type}_{slugified_name}  (truncated to 63 chars, Postgres's limit)

Revision ID: 20260623_0100
Revises: 20260623_0011
Create Date: 2026-06-23 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260623_0100"
down_revision: str | None = "20260623_0011"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # Step 1: Add nullable so existing rows don't violate NOT NULL immediately.
    op.add_column("organizations", sa.Column("schema_name", sa.Text(), nullable=True))

    # Step 2: Backfill — derive schema name from business_type + name.
    # If two orgs normalise to the same base name, rank them by (created_at, id)
    # and append _2, _3, … so the unique index below can always be created.
    op.execute("""
        WITH base AS (
            SELECT
                id,
                created_at,
                left(
                    regexp_replace(
                        lower(business_type::text || '_' || name),
                        '[^a-z0-9]+',
                        '_',
                        'g'
                    ),
                    63
                ) AS base_name
            FROM organizations
        ),
        ranked AS (
            SELECT
                id,
                base_name,
                ROW_NUMBER() OVER (
                    PARTITION BY base_name
                    ORDER BY created_at, id
                ) AS rn
            FROM base
        )
        UPDATE organizations o
        SET schema_name = CASE
            WHEN r.rn = 1 THEN r.base_name
            ELSE left(r.base_name, 59) || '_' || r.rn::text
        END
        FROM ranked r
        WHERE o.id = r.id
    """)

    # Step 3: Tighten — NOT NULL + unique constraint now that every row has a value.
    op.alter_column("organizations", "schema_name", nullable=False)
    op.create_unique_constraint("uq_organizations_schema_name", "organizations", ["schema_name"])
    op.create_index("ix_organizations_schema_name", "organizations", ["schema_name"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_organizations_schema_name", table_name="organizations")
    op.drop_constraint("uq_organizations_schema_name", "organizations", type_="unique")
    op.drop_column("organizations", "schema_name")
