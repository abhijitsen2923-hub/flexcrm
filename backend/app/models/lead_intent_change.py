"""Intent history for a lead — every change of its High / Medium / Low intent, who made it, and how.

A stage change also records the intent chosen with it on the stage_transitions row (shown on that history
entry); this table additionally keeps changes made WITHOUT a stage change (the lead details' quick set), so
the Stage History can show them too.
"""
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import TenantBase
from app.models.base import UUIDPrimaryKeyMixin
from app.models.user import User  # direct ref to avoid cross-registry string lookup


class LeadIntentChange(TenantBase, UUIDPrimaryKeyMixin):
    __tablename__ = "lead_intent_changes"
    __table_args__ = (
        Index("ix_lead_intent_changes_lead_performed_at", "lead_id", "performed_at"),
        {"schema": "tenant"},
    )

    lead_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("leads.id", ondelete="CASCADE"), nullable=False)
    # NULL = not rated.
    from_intent: Mapped[str | None] = mapped_column(String(8), nullable=True)
    to_intent: Mapped[str | None] = mapped_column(String(8), nullable=True)
    # stage_change | bulk | quick_set | created | import (app/core/lead_intent.py INTENT_SOURCES)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    performed_by_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("public.users.id", ondelete="SET NULL"), nullable=True
    )
    performed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Cross-schema relationship to public.users: lambda + the imported class (a string join can't resolve
    # User from the other registry). viewonly — written via the id.
    performed_by = relationship(
        User,
        primaryjoin=lambda: LeadIntentChange.performed_by_id == User.id,
        foreign_keys=lambda: [LeadIntentChange.performed_by_id],
        viewonly=True,
    )
