"""Add project_media table (brochures / floor plans / images / video).

Stores S3-compatible object keys (file_path); the API serves them via presigned
GET URLs. Wires the previously-empty project "Media Repository".

Revision ID: 20260710_t007
Revises: 20260708_t006
Create Date: 2026-07-10 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260710_t007"
down_revision: str | None = "20260708_t006"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "project_media",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("media_type", sa.String(32), nullable=False),
        sa.Column("file_path", sa.String(512), nullable=False),
        sa.Column("label", sa.String(255), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_project_media_project_id", "project_media", ["project_id"])


def downgrade() -> None:
    op.drop_table("project_media")
