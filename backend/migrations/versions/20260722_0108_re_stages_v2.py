"""Real-estate pipeline stages v2 — replace the 12 old RE stages with the 13
lifecycle stages (Call → Follow-up → Site visit → Interested → Booked/Token →
Agreement/Payment → Registration → Possession → Sold + Not Interested +
Disqualified).

`pipeline_stages` is a PUBLIC/global table, but `leads` is per-tenant with a
composite FK `(industry, stage_code) → pipeline_stages(industry, code)` that is
`ondelete=RESTRICT`. So before any old stage row can be deleted, every tenant's
leads sitting on a retired code must be remapped. This migration therefore
iterates the tenant schemas (from public.organizations.schema_name) and remaps
`leads.stage_code` before deleting the retired public stage rows.

`sold` is kept (closed_won terminal, side-effects keyed off it). `not_interested`
+ `disqualified` are added for real_estate (codes already exist for other
verticals but pipeline_stages is unique per (industry, code)).

Revision ID: 20260722_0108
Revises: 20260715_0107
Create Date: 2026-07-22 10:00:00.000000
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from alembic import op


revision: str = "20260722_0108"
down_revision: str | None = "20260715_0107"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


# code -> (final_position, name, category)
NEW_STAGES = [
    ("call", 2, "Call", "active"),
    ("follow_up", 3, "Follow-up", "active"),
    ("site_visit_confirmed", 4, "Site Visit Confirmed", "active"),
    ("interested", 6, "Interested", "active"),
    ("booked", 7, "Booked / Token", "active"),
    ("agreement_payment", 8, "Agreement / Payment", "active"),
    ("possession", 10, "Possession", "active"),
    ("not_interested", 12, "Not Interested", "closed_lost"),
    ("disqualified", 13, "Disqualified", "closed_lost"),
]

# kept code -> (final_position, name, category)
KEPT_STAGES = {
    "new_enquiry": (1, "New Enquiry", "active"),
    "site_visit_done": (5, "Site Visit Done", "active"),
    "registration": (9, "Registration", "active"),
    "sold": (11, "Sold / Closed", "closed_won"),
}

# retired code -> surviving code (leads on the left are moved to the right)
REMAP = {
    "prospect": "call",
    "site_visit_scheduled": "site_visit_confirmed",
    "negotiation": "interested",
    "booking_initiated": "booked",
    "token_collected": "booked",
    "agreement_signed": "agreement_payment",
    "loan_processing": "agreement_payment",
    "lost": "not_interested",
}


def upgrade() -> None:
    conn = op.get_bind()

    # 0. The 1..15 position CHECK would reject the temporary +100 parking
    #    positions used below, so drop it for the duration of the reseed and
    #    re-add it at the end (the final state is positions 1..13, in range).
    conn.execute(sa.text(
        "ALTER TABLE public.pipeline_stages DROP CONSTRAINT IF EXISTS ck_pipeline_stages_position_range;"
    ))

    # 1. Free the final positions: park existing RE rows at +100 (avoids the
    #    UNIQUE(industry, position) collision while we insert/reposition).
    conn.execute(sa.text(
        "UPDATE public.pipeline_stages SET position = position + 100 "
        "WHERE industry = 'real_estate';"
    ))

    # 2. Insert the new stage codes at their final positions.
    for code, position, name, category in NEW_STAGES:
        conn.execute(
            sa.text(
                "INSERT INTO public.pipeline_stages "
                "(id, industry, position, code, name, category, comment_required) "
                "VALUES (:id, 'real_estate', :position, :code, :name, :category, true) "
                "ON CONFLICT (industry, code) DO NOTHING;"
            ).bindparams(id=str(uuid4()), position=position, code=code, name=name, category=category)
        )

    # 3. Reposition + rename the kept stages to their final slots.
    for code, (position, name, category) in KEPT_STAGES.items():
        conn.execute(
            sa.text(
                "UPDATE public.pipeline_stages "
                "SET position = :position, name = :name, category = :category "
                "WHERE industry = 'real_estate' AND code = :code;"
            ).bindparams(position=position, name=name, category=category, code=code)
        )

    # 4. Remap every tenant's leads off retired codes (must precede the DELETE
    #    because of the RESTRICT FK). Skip schemas without a leads table.
    schemas = conn.execute(
        sa.text("SELECT schema_name FROM public.organizations WHERE schema_name IS NOT NULL;")
    ).scalars().all()
    for schema in schemas:
        exists = conn.execute(
            sa.text("SELECT to_regclass(:t);").bindparams(t=f'"{schema}".leads')
        ).scalar()
        if exists is None:
            continue
        for old_code, new_code in REMAP.items():
            conn.execute(
                sa.text(
                    f'UPDATE "{schema}".leads SET stage_code = :new '
                    "WHERE industry = 'real_estate' AND stage_code = :old;"
                ).bindparams(new=new_code, old=old_code)
            )

    # 5. Delete the retired stage rows (now unreferenced).
    conn.execute(
        sa.text(
            "DELETE FROM public.pipeline_stages "
            "WHERE industry = 'real_estate' AND code = ANY(:codes);"
        ).bindparams(codes=list(REMAP.keys()))
    )

    # 6. Re-add the position CHECK — every row is now within 1..15.
    conn.execute(sa.text(
        "ALTER TABLE public.pipeline_stages "
        "ADD CONSTRAINT ck_pipeline_stages_position_range CHECK (position BETWEEN 1 AND 15);"
    ))


def downgrade() -> None:
    # Forward-only reseed — recreating the old stages + reverse-remapping tenant
    # leads is not supported. No-op.
    pass
