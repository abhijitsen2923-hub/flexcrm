"""Generic CRM v2 — Leads Management restructure.

Replaces the flat `lead_stage` enum on leads with the spec's industry-aware
15-stage pipeline driven by a new `pipeline_stages` lookup table. Adds the
`stage_transitions` audit log that backs the mandatory-comment workflow from
spec §3.2.

Wipe-and-reseed: existing `leads` rows are dropped per the user decision
recorded in the plan. Other tables (customers, users, deals, activities,
tasks, notifications, refresh_tokens) are untouched.

Revision ID: 20260521_0002
Revises: 20260519_0001
Create Date: 2026-05-21 12:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.database.pipeline_seed import as_dicts as pipeline_stage_seed_rows


revision: str = "20260521_0002"
down_revision: str | None = "20260519_0001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


_NEW_ENUMS: list[tuple[str, list[str]]] = [
    ("lead_industry_enum", ["education", "travel"]),
    ("pipeline_stage_category_enum", ["active", "closed_won", "closed_lost"]),
]


def _create_enum_sql(name: str, values: list[str]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return (
        "DO $$ BEGIN "
        f"CREATE TYPE {name} AS ENUM ({quoted}); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
    )


def upgrade() -> None:
    # --- Drop the old leads table & its enum -------------------------------
    op.drop_index("ix_leads_stage_assigned_to", table_name="leads")
    op.drop_index("ix_leads_deleted_at", table_name="leads")
    op.drop_index("ix_leads_is_deleted", table_name="leads")
    op.drop_index("ix_leads_deleted_by_id", table_name="leads")
    op.drop_index("ix_leads_updated_by_id", table_name="leads")
    op.drop_index("ix_leads_created_by_id", table_name="leads")
    op.drop_index("ix_leads_assigned_to_id", table_name="leads")
    op.drop_index("ix_leads_expected_close_date", table_name="leads")
    op.drop_index("ix_leads_customer_id", table_name="leads")
    op.drop_table("leads")
    op.execute("DROP TYPE IF EXISTS lead_stage_enum;")

    # --- Create the new enums ----------------------------------------------
    for name, values in _NEW_ENUMS:
        op.execute(_create_enum_sql(name, values))

    lead_industry_enum = postgresql.ENUM(
        "education", "travel", name="lead_industry_enum", create_type=False
    )
    pipeline_stage_category_enum = postgresql.ENUM(
        "active", "closed_won", "closed_lost",
        name="pipeline_stage_category_enum",
        create_type=False,
    )

    # --- pipeline_stages ---------------------------------------------------
    pipeline_stages_table = op.create_table(
        "pipeline_stages",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("industry", lead_industry_enum, nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("category", pipeline_stage_category_enum, nullable=False),
        sa.Column("comment_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("industry", "code", name="uq_pipeline_stages_industry_code"),
        sa.UniqueConstraint("industry", "position", name="uq_pipeline_stages_industry_position"),
        sa.CheckConstraint("position >= 1 AND position <= 15", name="ck_pipeline_stages_position_range"),
    )
    op.create_index("ix_pipeline_stages_industry", "pipeline_stages", ["industry"])

    # Seed all 30 stages (15 Education + 15 Travel) — spec §3.3 and §3.4.
    op.bulk_insert(pipeline_stages_table, pipeline_stage_seed_rows())

    # --- leads (new shape) -------------------------------------------------
    op.create_table(
        "leads",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("industry", lead_industry_enum, nullable=False),
        sa.Column("stage_code", sa.String(length=64), nullable=False),
        sa.Column("lead_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("value", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("probability", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expected_close_date", sa.Date(), nullable=True),
        sa.Column("source", sa.String(length=120), nullable=True),
        sa.Column("interest", sa.String(length=255), nullable=True),
        sa.Column("last_comment_preview", sa.Text(), nullable=True),
        sa.Column("last_comment_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assigned_to_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint("probability >= 0 AND probability <= 100", name="ck_leads_probability_range"),
        sa.CheckConstraint("value >= 0", name="ck_leads_value_non_negative"),
        sa.UniqueConstraint("lead_number", name="uq_leads_lead_number"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["assigned_to_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["deleted_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["industry", "stage_code"],
            ["pipeline_stages.industry", "pipeline_stages.code"],
            name="fk_leads_pipeline_stage",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_leads_customer_id", "leads", ["customer_id"])
    op.create_index("ix_leads_industry", "leads", ["industry"])
    op.create_index("ix_leads_stage_code", "leads", ["stage_code"])
    op.create_index("ix_leads_source", "leads", ["source"])
    op.create_index("ix_leads_expected_close_date", "leads", ["expected_close_date"])
    op.create_index("ix_leads_assigned_to_id", "leads", ["assigned_to_id"])
    op.create_index("ix_leads_created_by_id", "leads", ["created_by_id"])
    op.create_index("ix_leads_updated_by_id", "leads", ["updated_by_id"])
    op.create_index("ix_leads_deleted_by_id", "leads", ["deleted_by_id"])
    op.create_index("ix_leads_is_deleted", "leads", ["is_deleted"])
    op.create_index("ix_leads_deleted_at", "leads", ["deleted_at"])
    op.create_index("ix_leads_industry_stage_code", "leads", ["industry", "stage_code"])
    op.create_index("ix_leads_stage_assigned_to", "leads", ["stage_code", "assigned_to_id"])

    # --- stage_transitions -------------------------------------------------
    op.create_table(
        "stage_transitions",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("from_stage_code", sa.String(length=64), nullable=True),
        sa.Column("to_stage_code", sa.String(length=64), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("next_action_date", sa.Date(), nullable=True),
        sa.Column("attachment_path", sa.String(length=512), nullable=True),
        sa.Column("performed_by_id", sa.Uuid(), nullable=True),
        sa.Column("performed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        # JSONB on Postgres, JSON in tests — SQLAlchemy's JSON type maps both.
        sa.Column("mentions", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["performed_by_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_stage_transitions_lead_id", "stage_transitions", ["lead_id"])
    op.create_index("ix_stage_transitions_performed_by_id", "stage_transitions", ["performed_by_id"])
    op.create_index(
        "ix_stage_transitions_lead_performed_at",
        "stage_transitions",
        ["lead_id", "performed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_stage_transitions_lead_performed_at", table_name="stage_transitions")
    op.drop_index("ix_stage_transitions_performed_by_id", table_name="stage_transitions")
    op.drop_index("ix_stage_transitions_lead_id", table_name="stage_transitions")
    op.drop_table("stage_transitions")

    for index in [
        "ix_leads_stage_assigned_to",
        "ix_leads_industry_stage_code",
        "ix_leads_deleted_at",
        "ix_leads_is_deleted",
        "ix_leads_deleted_by_id",
        "ix_leads_updated_by_id",
        "ix_leads_created_by_id",
        "ix_leads_assigned_to_id",
        "ix_leads_expected_close_date",
        "ix_leads_source",
        "ix_leads_stage_code",
        "ix_leads_industry",
        "ix_leads_customer_id",
    ]:
        op.drop_index(index, table_name="leads")
    op.drop_table("leads")

    op.drop_index("ix_pipeline_stages_industry", table_name="pipeline_stages")
    op.drop_table("pipeline_stages")

    op.execute("DROP TYPE IF EXISTS pipeline_stage_category_enum;")
    op.execute("DROP TYPE IF EXISTS lead_industry_enum;")

    # Recreate the old lead_stage enum + leads table shape (for symmetry).
    op.execute(_create_enum_sql("lead_stage_enum", ["new", "qualified", "proposal", "negotiation", "won", "lost"]))
    lead_stage_enum = postgresql.ENUM(
        "new", "qualified", "proposal", "negotiation", "won", "lost",
        name="lead_stage_enum",
        create_type=False,
    )
    op.create_table(
        "leads",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("lead_stage", lead_stage_enum, nullable=False),
        sa.Column("value", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("probability", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expected_close_date", sa.Date(), nullable=True),
        sa.Column("assigned_to_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["assigned_to_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["deleted_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.CheckConstraint("probability >= 0 AND probability <= 100", name="ck_leads_probability_range"),
        sa.CheckConstraint("value >= 0", name="ck_leads_value_non_negative"),
    )
    op.create_index("ix_leads_customer_id", "leads", ["customer_id"])
    op.create_index("ix_leads_expected_close_date", "leads", ["expected_close_date"])
    op.create_index("ix_leads_assigned_to_id", "leads", ["assigned_to_id"])
    op.create_index("ix_leads_created_by_id", "leads", ["created_by_id"])
    op.create_index("ix_leads_updated_by_id", "leads", ["updated_by_id"])
    op.create_index("ix_leads_deleted_by_id", "leads", ["deleted_by_id"])
    op.create_index("ix_leads_is_deleted", "leads", ["is_deleted"])
    op.create_index("ix_leads_deleted_at", "leads", ["deleted_at"])
    op.create_index("ix_leads_stage_assigned_to", "leads", ["lead_stage", "assigned_to_id"])
