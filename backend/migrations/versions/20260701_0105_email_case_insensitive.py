"""Case-insensitive, globally-unique user emails.

Lowercase existing emails and replace the case-sensitive unique index
`uq_users_email_active` (on `email`) with a functional one on `lower(email)`,
so an email is unique across all tenants regardless of case. Pairs with the
`NormalizedEmail` type that lowercases inbound emails at the schema layer.

Revision ID: 20260701_0105
Revises: 20260630_0104
Create Date: 2026-07-01 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op


revision: str = "20260701_0105"
down_revision: str | None = "20260630_0104"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # Drop the old case-sensitive unique index.
    op.execute("DROP INDEX IF EXISTS public.uq_users_email_active")
    # Normalize existing emails to lowercase. If two ACTIVE users already differ
    # only by case, the unique index below will fail to build — resolve the
    # duplicate manually and re-run. (Unlikely; the old index only allowed
    # exact-case duplicates.)
    op.execute("UPDATE public.users SET email = lower(email) WHERE email <> lower(email)")
    # Recreate it as a case-insensitive unique index over active users.
    op.execute(
        "CREATE UNIQUE INDEX uq_users_email_active "
        "ON public.users (lower(email)) WHERE is_deleted = false"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS public.uq_users_email_active")
    op.execute(
        "CREATE UNIQUE INDEX uq_users_email_active "
        "ON public.users (email) WHERE is_deleted = false"
    )
