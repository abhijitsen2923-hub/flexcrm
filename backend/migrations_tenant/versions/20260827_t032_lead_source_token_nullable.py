"""Make lead_source_connections.token_hash nullable — for PULL providers (Google Sheets).

99acres is a PUSH provider whose credential is a URL token (its hash lives here + in the public
lead_source_routes). A PULL provider (Google Sheets) mints no token — the tenant just stores a sheet
id in external_account_id — so token_hash must be nullable. Existing 99acres rows are unaffected
(they keep their hash). The non-unique index on token_hash is retained.

Revision ID: 20260827_t032
Revises: 20260825_t031
Create Date: 2026-08-27 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260827_t032"
down_revision: str | None = "20260825_t031"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "lead_source_connections", "token_hash", existing_type=sa.String(64), nullable=True
    )


def downgrade() -> None:
    # Best-effort revert; will fail if any PULL connection rows have a NULL token_hash.
    op.alter_column(
        "lead_source_connections", "token_hash", existing_type=sa.String(64), nullable=False
    )
