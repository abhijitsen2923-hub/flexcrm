from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import TenantBase
from app.models.base import UUIDPrimaryKeyMixin


TRAVEL_REQUIRED_DOC_TYPES = ("passport", "visa_form", "hotel_voucher", "flight_ticket")


class LeadDocument(TenantBase, UUIDPrimaryKeyMixin):
    __tablename__ = "lead_documents"
    __table_args__ = (
        Index("ix_lead_documents_lead_doc_type", "lead_id", "doc_type"),
        {"schema": "tenant"},
    )

    lead_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("leads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    doc_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    uploaded_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    lead = relationship("Lead", back_populates="documents")
