"""Record + read a lead's intent history (High / Medium / Low changes, who made them, how).

Writers only ADD rows to the caller's session — the caller commits them in the same transaction as the
change to `Lead.intent`, so the history can never disagree with the lead.
"""
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.lead_intent import INTENT_SOURCES
from app.models.lead_intent_change import LeadIntentChange
from app.services.base import ServiceBase


class LeadIntentService(ServiceBase):
    def record(
        self,
        *,
        lead_id: UUID,
        from_intent: str | None,
        to_intent: str | None,
        actor_id: UUID | None,
        source: str,
    ) -> bool:
        """Stage one intent-change row (no commit). An unchanged intent records nothing.
        Returns True if a row was added."""
        if source not in INTENT_SOURCES:
            raise ValueError(f"Unknown intent source: {source!r}")
        if from_intent == to_intent:
            return False
        self.session.add(
            LeadIntentChange(
                lead_id=lead_id,
                from_intent=from_intent,
                to_intent=to_intent,
                performed_by_id=actor_id,
                source=source,
                # Stamped now — after the caller took the lead's row lock — not by the DB default, which is the
                # transaction's START time: simultaneous changes queue on the lock, and the history must list
                # them in the order they were really made.
                performed_at=datetime.now(UTC),
            )
        )
        return True

    async def list_for_lead(self, lead_id: UUID) -> list[LeadIntentChange]:
        """Newest first (same order as the stage history), with the actor's name loaded."""
        result = await self.session.execute(
            select(LeadIntentChange)
            .where(LeadIntentChange.lead_id == lead_id)
            .options(selectinload(LeadIntentChange.performed_by))
            .order_by(LeadIntentChange.performed_at.desc(), LeadIntentChange.id.desc())
        )
        return list(result.scalars().all())
