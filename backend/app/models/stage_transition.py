from datetime import date, datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.tenancy import OrgScopedMixin
from app.database.base import Base
from app.models.base import UUIDPrimaryKeyMixin


class StageTransition(Base, UUIDPrimaryKeyMixin, OrgScopedMixin):
    __tablename__ = "stage_transitions"
    __table_args__ = (
        Index("ix_stage_transitions_lead_performed_at", "lead_id", "performed_at"),
    )

    lead_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("leads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # null for the auto-stamped initial transition at lead creation
    from_stage_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    to_stage_code: Mapped[str] = mapped_column(String(64), nullable=False)
    comment: Mapped[str] = mapped_column(Text, nullable=False)
    next_action_date: Mapped[date | None] = mapped_column(nullable=True)
    attachment_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    performed_by_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    performed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # list of user UUIDs serialized as strings; in Postgres this is JSONB at the
    # column-type level (SQLAlchemy maps JSON → JSONB for the PG dialect).
    mentions: Mapped[list | None] = mapped_column(JSON, nullable=True)

    lead = relationship("Lead", back_populates="stage_transitions")
    performed_by = relationship("User", foreign_keys=[performed_by_id])
