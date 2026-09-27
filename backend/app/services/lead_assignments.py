"""Record + read a lead's owner-assignment history (who it moved from, to, by whom, how).

Writers only ADD rows to the caller's session — the caller commits them in the same transaction as the
owner change, so the history can never disagree with `Lead.assigned_to_id`. Never written into
`stage_transitions` (see models/lead_assignment_event.py for why).
"""
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.lead_assignment_event import ASSIGNMENT_SOURCES, LeadAssignmentEvent
from app.services.base import ServiceBase


class LeadAssignmentService(ServiceBase):
    def record(
        self,
        *,
        lead_id: UUID,
        from_user_id: UUID | None,
        to_user_id: UUID | None,
        actor_id: UUID | None,
        source: str,
    ) -> bool:
        """Stage one owner-change row (no commit). A no-op change (same owner) records nothing.
        Returns True if a row was added."""
        if source not in ASSIGNMENT_SOURCES:
            raise ValueError(f"Unknown assignment source: {source!r}")
        if from_user_id == to_user_id:
            return False
        self.session.add(
            LeadAssignmentEvent(
                lead_id=lead_id,
                from_user_id=from_user_id,
                to_user_id=to_user_id,
                performed_by_id=actor_id,
                source=source,
            )
        )
        return True

    async def list_for_lead(self, lead_id: UUID) -> list[LeadAssignmentEvent]:
        """Newest first (same order as the stage history), with the three users' names loaded."""
        result = await self.session.execute(
            select(LeadAssignmentEvent)
            .where(LeadAssignmentEvent.lead_id == lead_id)
            .options(
                selectinload(LeadAssignmentEvent.from_user),
                selectinload(LeadAssignmentEvent.to_user),
                selectinload(LeadAssignmentEvent.performed_by),
            )
            .order_by(LeadAssignmentEvent.performed_at.desc(), LeadAssignmentEvent.id.desc())
        )
        return list(result.scalars().all())
