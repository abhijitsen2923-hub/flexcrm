"""Real estate vertical — public schema changes.

1. Extend `lead_industry_enum` with `real_estate`.
2. Extend `user_role_enum` with 7 real-estate roles.
3. Create `unit_status_enum`, `booking_status_enum`, `site_visit_feedback_enum`
   in the public schema (shared across all tenant schemas).
4. Seed 12 real-estate pipeline stages.

All enum extensions run in `autocommit_block` (Postgres requires the new value
to be committed before any DML can reference it in the same session).

Revision ID: 20260623_0102
Revises: 20260623_0101
Create Date: 2026-06-23 14:00:00.000000
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from alembic import op


revision: str = "20260623_0102"
down_revision: str | None = "20260623_0101"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


NEW_INDUSTRY_VALUES = ("real_estate",)

NEW_ROLE_VALUES = (
    "sales_manager",
    "sales_executive",
    "telecaller",
    "accounts",
    "crm_team",
    "broker",
    "customer",
)

REAL_ESTATE_STAGES = [
    ("real_estate", 1,  "new_enquiry",         "New Enquiry",          "active",      False),
    ("real_estate", 2,  "prospect",             "Prospect",             "active",      True),
    ("real_estate", 3,  "site_visit_scheduled", "Site Visit Scheduled", "active",      True),
    ("real_estate", 4,  "site_visit_done",      "Site Visit Done",      "active",      True),
    ("real_estate", 5,  "negotiation",          "Negotiation",          "active",      True),
    ("real_estate", 6,  "booking_initiated",    "Booking Initiated",    "active",      True),
    ("real_estate", 7,  "token_collected",      "Token Collected",      "active",      True),
    ("real_estate", 8,  "agreement_signed",     "Agreement Signed",     "active",      True),
    ("real_estate", 9,  "loan_processing",      "Loan Processing",      "active",      True),
    ("real_estate", 10, "registration",         "Registration",         "active",      True),
    ("real_estate", 11, "sold",                 "Sold",                 "closed_won",  True),
    ("real_estate", 12, "lost",                 "Lost",                 "closed_lost", True),
]


def upgrade() -> None:
    # 1. Extend lead_industry_enum and user_role_enum — must auto-commit.
    with op.get_context().autocommit_block():
        for v in NEW_INDUSTRY_VALUES:
            op.execute(sa.text(f"ALTER TYPE lead_industry_enum ADD VALUE IF NOT EXISTS '{v}';"))
        for v in NEW_ROLE_VALUES:
            op.execute(sa.text(f"ALTER TYPE user_role_enum ADD VALUE IF NOT EXISTS '{v}';"))

    # 2. Create new enum types for real estate tables (public schema so all
    #    tenant schemas can reference them without schema-prefix).
    with op.get_context().autocommit_block():
        op.execute(sa.text(
            "DO $$ BEGIN "
            "CREATE TYPE unit_status_enum AS ENUM ('available', 'reserved', 'booked', 'sold'); "
            "EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
        ))
        op.execute(sa.text(
            "DO $$ BEGIN "
            "CREATE TYPE booking_status_enum AS ENUM ('draft', 'confirmed', 'cancelled'); "
            "EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
        ))
        op.execute(sa.text(
            "DO $$ BEGIN "
            "CREATE TYPE site_visit_feedback_enum AS ENUM ('hot', 'warm', 'cold'); "
            "EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
        ))

    # 3. Seed the 12 real-estate pipeline stages.
    for industry, position, code, name, category, comment_required in REAL_ESTATE_STAGES:
        op.execute(
            sa.text(
                "INSERT INTO public.pipeline_stages "
                "(id, industry, position, code, name, category, comment_required) "
                "VALUES (:id, :industry, :position, :code, :name, :category, :comment_required) "
                "ON CONFLICT (industry, code) DO NOTHING;"
            ).bindparams(
                id=str(uuid4()),
                industry=industry,
                position=position,
                code=code,
                name=name,
                category=category,
                comment_required=comment_required,
            )
        )


def downgrade() -> None:
    # Delete seeded stages (enum values cannot be removed from Postgres enums).
    op.execute(
        sa.text("DELETE FROM public.pipeline_stages WHERE industry = 'real_estate';")
    )
