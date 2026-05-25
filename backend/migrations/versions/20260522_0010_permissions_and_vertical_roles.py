"""Phase 8 — fine-grained permissions + vertical-locked roles.

Three steps:

1. **Extend `user_role_enum`** with the six new vertical-aware values plus the
   universal `owner`. This step runs in an `autocommit_block` so the new enum
   values are COMMITTED before the UPDATE statements below reference them —
   Postgres rejects "unsafe use of new enum value" if you try to add a value
   and use it in the same transaction.

2. **Backfill** existing user rows:
       admin                                    → owner
       manager  (org.business_type=education)   → academic_admin
       manager  (org.business_type=travel)      → ops_manager
       sales    (org.business_type=education)   → counselor
       sales    (org.business_type=travel)      → travel_agent
   `support` and `analyst` rows are untouched (those roles still exist
   universally). The legacy enum members stay defined; application code
   refuses to assign them after this migration.

3. **Create `user_permission_grants`** for per-user explicit overrides.
   Empty at creation — every user's effective permissions come from
   `ROLE_PERMISSION_DEFAULTS[their_new_role]` until an admin grants something.

Revision ID: 20260522_0010
Revises: 20260522_0009
Create Date: 2026-05-22 20:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260522_0010"
down_revision: str | None = "20260522_0009"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


NEW_ROLE_VALUES = (
    "owner",
    "academic_admin",
    "counselor",
    "fee_admin",
    "ops_manager",
    "travel_agent",
    "visa_coordinator",
)


def upgrade() -> None:
    # 1. Extend the enum — autocommit_block so each ALTER TYPE commits before
    #    the backfill UPDATE references the new value (Postgres rule).
    #    `ADD VALUE IF NOT EXISTS` is idempotent on Postgres 9.6+, so a partial
    #    re-run of this migration is safe.
    with op.get_context().autocommit_block():
        for value in NEW_ROLE_VALUES:
            op.execute(
                sa.text(
                    f"ALTER TYPE user_role_enum ADD VALUE IF NOT EXISTS '{value}';"
                )
            )

    # 2. Backfill — runs in the normal migration transaction now that the
    #    enum extension is committed.
    op.execute(
        sa.text(
            """
            UPDATE users
            SET role = 'owner'
            WHERE role = 'admin';
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE users u
            SET role = CASE
                WHEN o.business_type = 'education' AND u.role = 'manager' THEN 'academic_admin'
                WHEN o.business_type = 'travel'    AND u.role = 'manager' THEN 'ops_manager'
                WHEN o.business_type = 'education' AND u.role = 'sales'   THEN 'counselor'
                WHEN o.business_type = 'travel'    AND u.role = 'sales'   THEN 'travel_agent'
                ELSE u.role
            END
            FROM organizations o
            WHERE u.organization_id = o.id;
            """
        )
    )

    # 3. Create the explicit-grants table.
    op.create_table(
        "user_permission_grants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("permission_code", sa.String(length=64), nullable=False),
        sa.Column("granted_by_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["granted_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "permission_code", name="uq_user_permission_grants_user_code"
        ),
    )
    op.create_index(
        "ix_user_permission_grants_user_id",
        "user_permission_grants",
        ["user_id"],
    )
    op.create_index(
        "ix_user_permission_grants_organization_id",
        "user_permission_grants",
        ["organization_id"],
    )


def downgrade() -> None:
    # Drop the table; the new enum values stay defined (Postgres can't drop
    # enum values without rebuilding the type — out of scope for a downgrade).
    op.drop_index("ix_user_permission_grants_organization_id", table_name="user_permission_grants")
    op.drop_index("ix_user_permission_grants_user_id", table_name="user_permission_grants")
    op.drop_table("user_permission_grants")

    # Best-effort reverse of the backfill so users can be downgraded to the
    # old role names. Won't fully restore admin if multiple new roles map onto
    # one old role, but for a fresh dev DB this is symmetrical enough.
    op.execute(
        sa.text(
            """
            UPDATE users
            SET role = CASE
                WHEN role = 'owner' THEN 'admin'
                WHEN role IN ('academic_admin', 'ops_manager') THEN 'manager'
                WHEN role IN ('counselor', 'travel_agent') THEN 'sales'
                ELSE role
            END;
            """
        )
    )
