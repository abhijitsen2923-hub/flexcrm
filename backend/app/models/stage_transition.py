from datetime import date, datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import TenantBase
from app.models.base import UUIDPrimaryKeyMixin
from app.models.user import User  # direct ref to avoid cross-registry string lookup


class StageTransition(TenantBase, UUIDPrimaryKeyMixin):
    __tablename__ = "stage_transitions"
    __table_args__ = (
        Index("ix_stage_transitions_lead_performed_at", "lead_id", "performed_at"),
        {"schema": "tenant"},
    )

    lead_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("leads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    from_stage_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    to_stage_code: Mapped[str] = mapped_column(String(64), nullable=False)
    comment: Mapped[str] = mapped_column(Text, nullable=False)
    # Date + time of the next follow-up (drives reminders). Kept the historical
    # column name; type is now a timestamp so the "Time" is preserved.
    next_action_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attachment_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    performed_by_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("public.users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    performed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    mentions: Mapped[list | None] = mapped_column(JSON, nullable=True)

    lead = relationship("Lead", back_populates="stage_transitions")
    # Cross-schema relationship to public.users. The FK string "public.users.id"
    # registers a stub table in TenantBase.metadata distinct from the real User
    # mapper in Base.metadata, so SQLAlchemy can't infer the join — specify it
    # explicitly (same pattern as Lead.assigned_to). viewonly: the actor is
    # written via performed_by_id. Without this relationship, the repository's
    # selectinload(StageTransition.performed_by) raises and every stage-history
    # fetch 500s (shows as "No transitions yet" in the drawer).
    performed_by = relationship(
        User,
        primaryjoin=lambda: StageTransition.performed_by_id == User.id,
        foreign_keys=lambda: [StageTransition.performed_by_id],
        viewonly=True,
    )
