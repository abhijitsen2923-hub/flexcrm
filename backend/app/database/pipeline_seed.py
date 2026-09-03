"""Canonical pipeline-stage seed data.

Education and Travel each get a 15-stage pipeline matching the Generic CRM v2
spec (§3.3 and §3.4). The data lives here so the Alembic migration AND the
test fixture's `Base.metadata.create_all` path can share one source of truth.

Each entry is `(industry, position, code, name, category, comment_required)`.
The only `comment_required = False` row per industry is position 1 — the auto
stamp written by the service when a Lead is created.
"""
from typing import Iterable


PipelineStageSeed = tuple[str, int, str, str, str, bool]


EDUCATION_STAGES: list[PipelineStageSeed] = [
    ("education", 1, "new_enquiry", "New Enquiry", "active", False),
    ("education", 2, "prospect", "Prospect", "active", True),
    ("education", 3, "qualified", "Qualified", "active", True),
    ("education", 4, "counseling_session_booked", "Counseling Session Booked", "active", True),
    ("education", 5, "counseling_session_done", "Counseling Session Done", "active", True),
    ("education", 6, "follow_up", "Follow Up", "active", True),
    ("education", 7, "demo_booked", "Demo/Session Booked", "active", True),
    ("education", 8, "demo_done", "Demo/Session Done", "active", True),
    ("education", 9, "course_suggested", "Course Suggested", "active", True),
    ("education", 10, "admission_process_started", "Admission Process Started", "active", True),
    ("education", 11, "fee_pending", "Fee Pending", "active", True),
    ("education", 12, "sold", "Sold", "closed_won", True),
    ("education", 13, "did_not_pick", "Did Not Pick", "closed_lost", True),
    ("education", 14, "not_interested", "Not Interested", "closed_lost", True),
    ("education", 15, "disqualified", "Disqualified", "closed_lost", True),
]


TRAVEL_STAGES: list[PipelineStageSeed] = [
    ("travel", 1, "new_enquiry", "New Enquiry", "active", False),
    ("travel", 2, "prospect", "Prospect", "active", True),
    ("travel", 3, "qualified", "Qualified", "active", True),
    ("travel", 4, "requirement_discussion", "Requirement Discussion", "active", True),
    ("travel", 5, "package_shared", "Package Shared", "active", True),
    ("travel", 6, "demo_booked", "Demo/Session Booked", "active", True),
    ("travel", 7, "demo_done", "Demo/Session Done", "active", True),
    ("travel", 8, "follow_up", "Follow Up", "active", True),
    ("travel", 9, "visa_documentation_pending", "Visa/Documentation Pending", "active", True),
    ("travel", 10, "payment_pending", "Payment Pending", "active", True),
    ("travel", 11, "booking_confirmed", "Booking Confirmed", "active", True),
    ("travel", 12, "sold", "Sold", "closed_won", True),
    ("travel", 13, "did_not_pick", "Did Not Pick", "closed_lost", True),
    ("travel", 14, "not_interested", "Not Interested", "closed_lost", True),
    ("travel", 15, "disqualified", "Disqualified", "closed_lost", True),
]


# Real-estate lifecycle v2 (14 stages). Codes are stable identifiers; `sold` is
# kept as the closed_won terminal so the promotion / sales-order / brokerage
# side-effects keyed off SOLD_STAGE_CODE keep working. `not_interested` +
# `disqualified` reuse the shared closed_lost codes so reopen logic works.
# `did_not_pickup` (position 3, the call outcome when a lead can't be reached) is
# an ACTIVE stage — the lead stays in the funnel and is re-worked once reached, so
# it must NOT go into stage_transitions.CLOSED_LOST_STAGE_CODES. It uses a distinct
# code (not the education/travel `did_not_pick`, which is closed_lost) precisely to
# stay out of that shared, industry-agnostic closed-lost set.
REAL_ESTATE_STAGES: list[PipelineStageSeed] = [
    ("real_estate", 1,  "new_enquiry",          "New Enquiry",          "active",      False),
    ("real_estate", 2,  "call",                 "Call",                 "active",      True),
    ("real_estate", 3,  "did_not_pickup",       "Did Not Pickup",       "active",      True),
    ("real_estate", 4,  "follow_up",            "Follow-up",            "active",      True),
    ("real_estate", 5,  "site_visit_confirmed", "Site Visit Confirmed", "active",      True),
    ("real_estate", 6,  "site_visit_done",      "Site Visit Done",      "active",      True),
    ("real_estate", 7,  "interested",           "Interested",           "active",      True),
    ("real_estate", 8,  "booked",               "Booked / Token",       "active",      True),
    ("real_estate", 9,  "agreement_payment",    "Agreement / Payment",  "active",      True),
    ("real_estate", 10, "registration",         "Registration",         "active",      True),
    ("real_estate", 11, "possession",           "Possession",           "active",      True),
    ("real_estate", 12, "sold",                 "Sold / Closed",        "closed_won",  True),
    ("real_estate", 13, "not_interested",       "Not Interested",       "closed_lost", True),
    ("real_estate", 14, "disqualified",         "Disqualified",         "closed_lost", True),
]


ALL_STAGES: list[PipelineStageSeed] = [*EDUCATION_STAGES, *TRAVEL_STAGES, *REAL_ESTATE_STAGES]


def as_dicts() -> list[dict]:
    return [
        {
            "industry": industry,
            "position": position,
            "code": code,
            "name": name,
            "category": category,
            "comment_required": comment_required,
        }
        for industry, position, code, name, category, comment_required in ALL_STAGES
    ]


def initial_stage_code(industry: str) -> str:
    """Position-1 code for an industry — the auto stamp target on lead create."""
    for entry in ALL_STAGES:
        if entry[0] == industry and entry[1] == 1:
            return entry[2]
    raise ValueError(f"Unknown industry: {industry}")


def stage_lookup(rows: Iterable[PipelineStageSeed]) -> dict[tuple[str, str], PipelineStageSeed]:
    return {(industry, code): row for row in rows for (industry, _, code, _, _, _) in [row]}
