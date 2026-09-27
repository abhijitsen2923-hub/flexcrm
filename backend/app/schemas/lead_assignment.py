from datetime import datetime
from uuid import UUID

from app.schemas.common import ORMModel
from app.schemas.stage_transition import TransitionActor


class LeadAssignmentEventRead(ORMModel):
    """One owner change in a lead's history. Users are the lean TransitionActor (id + name, no email)
    for the same reason as the stage history: a placeholder email must never 500 the response."""

    id: UUID
    lead_id: UUID
    source: str
    performed_at: datetime
    from_user_id: UUID | None = None
    to_user_id: UUID | None = None
    performed_by_id: UUID | None = None
    from_user: TransitionActor | None = None
    to_user: TransitionActor | None = None
    performed_by: TransitionActor | None = None
