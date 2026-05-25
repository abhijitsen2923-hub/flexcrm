from datetime import date, datetime
from uuid import UUID

from pydantic import Field

from app.schemas.common import ORMModel
from app.schemas.user import UserSummary


# Spec §3.2: mandatory comment box, "stays disabled until at least 10 characters
# are entered." We enforce the same floor server-side, in addition to the UI gate.
MIN_COMMENT_LENGTH = 10


class StageTransitionCreate(ORMModel):
    to_stage_code: str = Field(min_length=1, max_length=64)
    comment: str = Field(min_length=MIN_COMMENT_LENGTH, max_length=4000)
    next_action_date: date | None = None
    attachment_path: str | None = Field(default=None, max_length=512)
    mentions: list[UUID] | None = None
    # Phase 2 — Education-only optional field captured on the Sold transition.
    # Ignored for Travel; persisted on Lead.batch_code so the auto-created
    # Customer can record which cohort/batch the student joined.
    batch_code: str | None = Field(default=None, max_length=64)


class StageTransitionRead(ORMModel):
    id: UUID
    lead_id: UUID
    from_stage_code: str | None
    to_stage_code: str
    comment: str
    next_action_date: date | None = None
    attachment_path: str | None = None
    performed_by_id: UUID | None = None
    performed_at: datetime
    mentions: list[UUID] | None = None
    performed_by: UserSummary | None = None
