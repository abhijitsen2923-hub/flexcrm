"""Finance vertical Phase 1 — public enum types + organizations.finance_business_mode.

Creates the shared PG enum types used by the new tenant finance tables (expenses,
vendors, vendor_bills, finance_categories) in the PUBLIC schema, and adds the
org-level business-mode column (general/re_builder/re_broker/hybrid) chosen at
signup. Must run BEFORE the tenant migration t033, which references these types
with create_type=False.

Revision ID: 20260903_0114
Revises: 20260902_0113
Create Date: 2026-09-03 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20260903_0114"
down_revision: str | None = "20260902_0113"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


# enum name -> values (must match app.database.enums StrEnum members exactly)
_ENUMS: dict[str, tuple[str, ...]] = {
    "finance_business_mode_enum": ("general", "re_builder", "re_broker", "hybrid"),
    "expense_status_enum": ("draft", "submitted", "approved", "rejected", "paid"),
    "vendor_bill_status_enum": ("open", "partially_paid", "paid", "cancelled"),
    "gst_treatment_enum": ("intra_state", "inter_state"),
    "finance_category_kind_enum": ("expense", "income"),
}


def upgrade() -> None:
    # Idempotent CREATE TYPE in public (safe on re-run / pre-existing type).
    for name, values in _ENUMS.items():
        vals = ", ".join(f"'{v}'" for v in values)
        op.execute(
            sa.text(
                f"DO $$ BEGIN CREATE TYPE {name} AS ENUM ({vals}); "
                "EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
            )
        )

    op.add_column(
        "organizations",
        sa.Column(
            "finance_business_mode",
            postgresql.ENUM(
                *_ENUMS["finance_business_mode_enum"],
                name="finance_business_mode_enum",
                create_type=False,
            ),
            server_default=sa.text("'general'"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("organizations", "finance_business_mode")
    for name in _ENUMS:
        op.execute(sa.text(f"DROP TYPE IF EXISTS {name};"))
