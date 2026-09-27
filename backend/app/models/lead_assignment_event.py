"""Owner-assignment history for a lead — who it moved from, to, who did it, and how.

Deliberately NOT stored in `stage_transitions`: that table is read for money and scoring (commission
re-attribution credits every transition performer; the HR scorecard counts transition rows), so owner
changes written there would silently change payouts and scores. The Stage History UI merges both.
"""
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import TenantBase
from app.models.base import UUIDPrimaryKeyMixin
from app.models.user import User  # direct ref to avoid cross-registry string lookup

# How the owner changed: set on a manual create / CSV upload, a single or bulk reassign, or the
# salesperson picked on the real-estate "Booked / Token" move.
ASSIGNMENT_SOURCES: tuple[str, ...] = ("created", "import", "reassign", "bulk_reassign", "booking")


class LeadAssignmentEvent(TenantBase, UUIDPrimaryKeyMixin):
    __tablename__ = "lead_assignment_events"
    __table_args__ = (
        Index("ix_lead_assignment_events_lead_performed_at", "lead_id", "performed_at"),
        {"schema": "tenant"},
    )

    lead_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("leads.id", ondelete="CASCADE"), nullable=False
    )
    # NULL = unassigned (or a user later hard-deleted by archival — SET NULL keeps the event).
    from_user_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("public.users.id", ondelete="SET NULL"), nullable=True
    )
    to_user_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("public.users.id", ondelete="SET NULL"), nullable=True
    )
    performed_by_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("public.users.id", ondelete="SET NULL"), nullable=True
    )
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    performed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Cross-schema relationships to public.users: lambda + the imported class (a string join can't
    # resolve User from the other registry and fails at mapper init). viewonly — written via the ids.
    from_user = relationship(
        User,
        primaryjoin=lambda: LeadAssignmentEvent.from_user_id == User.id,
        foreign_keys=lambda: [LeadAssignmentEvent.from_user_id],
        viewonly=True,
    )
    to_user = relationship(
        User,
        primaryjoin=lambda: LeadAssignmentEvent.to_user_id == User.id,
        foreign_keys=lambda: [LeadAssignmentEvent.to_user_id],
        viewonly=True,
    )
    performed_by = relationship(
        User,
        primaryjoin=lambda: LeadAssignmentEvent.performed_by_id == User.id,
        foreign_keys=lambda: [LeadAssignmentEvent.performed_by_id],
        viewonly=True,
    )
