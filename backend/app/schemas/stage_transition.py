from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas.common import ORMModel
from app.schemas.user import UserSummary


# Spec §3.2: mandatory comment box, "stays disabled until at least 10 characters
# are entered." We enforce the same floor server-side, in addition to the UI gate.
MIN_COMMENT_LENGTH = 10

# Mirrors PaymentMode in app/real_estate/schemas.py — kept local so the lead
# schema doesn't import the real-estate package.
PaymentMode = Literal["upi", "neft", "cheque", "cash", "card", "other"]


class BookedTokenCapture(ORMModel):
    """Booking + token captured when a real-estate lead moves to 'Booked / Token'.
    create_transition creates/updates a Booking with this token and promotes the
    lead to a Customer."""

    unit_id: UUID
    token_amount: Decimal = Field(gt=0)
    token_mode: PaymentMode
    token_received_on: date


class StageTransitionCreate(ORMModel):
    to_stage_code: str = Field(min_length=1, max_length=64)
    comment: str = Field(min_length=MIN_COMMENT_LENGTH, max_length=4000)
    next_action_date: datetime | None = None
    attachment_path: str | None = Field(default=None, max_length=512)
    mentions: list[UUID] | None = None
    # Phase 2 — Education-only optional field captured on the Sold transition.
    # Ignored for Travel; persisted on Lead.batch_code so the auto-created
    # Customer can record which cohort/batch the student joined.
    batch_code: str | None = Field(default=None, max_length=64)
    # Salesperson (assigned owner) set on the lead during the move, carried onto
    # the promoted Customer's owner. Used on the 'Booked / Token' move.
    assigned_to_id: UUID | None = None
    # Real-estate 'Booked / Token' capture — property unit + token. When present,
    # create_transition creates/updates the lead's Booking with the token.
    booking: BookedTokenCapture | None = None


class StageTransitionRead(ORMModel):
    id: UUID
    lead_id: UUID
    from_stage_code: str | None
    to_stage_code: str
    comment: str
    next_action_date: datetime | None = None
    attachment_path: str | None = None
    performed_by_id: UUID | None = None
    performed_at: datetime
    mentions: list[UUID] | None = None
    performed_by: UserSummary | None = None
