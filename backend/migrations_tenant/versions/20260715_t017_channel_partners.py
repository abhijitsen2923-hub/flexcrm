"""Channel partners — broker profiles, brokerage payouts, lead attribution.

Adds channel_partners (broker profile + brokerage rate + payout details),
brokerage_payouts (auto-accrued on Sold), and leads.partner_id (which partner
referred a lead).

Revision ID: 20260715_t017
Revises: 20260715_t016
Create Date: 2026-07-15 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260715_t017"
down_revision: str | None = "20260715_t016"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "channel_partners",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_id", sa.Uuid(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("company_name", sa.String(255), nullable=False),
        sa.Column("contact_name", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(40), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("rera_number", sa.String(64), nullable=True),
        sa.Column("pan", sa.String(20), nullable=True),
        sa.Column("brokerage_type", sa.String(10), server_default="percent", nullable=False),
        sa.Column("brokerage_rate", sa.Numeric(12, 2), server_default="0", nullable=False),
        sa.Column("payout_bank_account", sa.String(64), nullable=True),
        sa.Column("payout_ifsc", sa.String(20), nullable=True),
        sa.Column("payout_upi", sa.String(120), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["deleted_by_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_channel_partners_user_id", "channel_partners", ["user_id"])

    op.create_table(
        "brokerage_payouts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("partner_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=True),
        sa.Column("sales_order_id", sa.Uuid(), nullable=True),
        sa.Column("deal_value", sa.Numeric(14, 2), nullable=True),
        sa.Column("rate_type", sa.String(10), nullable=False),
        sa.Column("rate_snapshot", sa.Numeric(12, 2), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("status", sa.String(12), server_default="accrued", nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("paid_on", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(["partner_id"], ["channel_partners.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_brokerage_payouts_partner", "brokerage_payouts", ["partner_id"])
    op.create_index("ix_brokerage_payouts_lead", "brokerage_payouts", ["lead_id"])

    op.add_column("leads", sa.Column("partner_id", sa.Uuid(), nullable=True))
    op.create_index("ix_leads_partner_id", "leads", ["partner_id"])
    op.create_foreign_key(
        "fk_leads_partner_id", "leads", "channel_partners", ["partner_id"], ["id"], ondelete="SET NULL"
    )


def downgrade() -> None:
    op.drop_constraint("fk_leads_partner_id", "leads", type_="foreignkey")
    op.drop_index("ix_leads_partner_id", table_name="leads")
    op.drop_column("leads", "partner_id")
    op.drop_table("brokerage_payouts")
    op.drop_table("channel_partners")
