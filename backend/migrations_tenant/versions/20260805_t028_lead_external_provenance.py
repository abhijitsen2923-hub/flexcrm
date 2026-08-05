"""Add leads.source_provider + leads.external_id — external-ingest idempotency anchor.

External lead sources (Meta Lead Ads now; WhatsApp later) need an idempotency key
so re-polling / retrying the same record can't create duplicate leads. Adds two
nullable columns plus a PARTIAL UNIQUE index on (source_provider, external_id)
WHERE external_id IS NOT NULL — so ingest can insert with ON CONFLICT DO NOTHING
and the DB (not an app-level check) guarantees exactly-once. Both columns are NULL
for manually-created leads. Runs per-tenant via the migration search_path.

Revision ID: 20260805_t028
Revises: 20260728_t027
Create Date: 2026-08-05 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260805_t028"
down_revision: str | None = "20260728_t027"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("source_provider", sa.String(32), nullable=True))
    op.add_column("leads", sa.Column("external_id", sa.String(128), nullable=True))
    op.create_index(
        "uq_leads_provider_external_id",
        "leads",
        ["source_provider", "external_id"],
        unique=True,
        postgresql_where=sa.text("external_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_leads_provider_external_id", table_name="leads")
    op.drop_column("leads", "external_id")
    op.drop_column("leads", "source_provider")
