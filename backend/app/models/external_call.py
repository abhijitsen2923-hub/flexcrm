"""A call synced from an external call-tracking provider (Callyzer) — per-tenant schema.

We do NOT store the recording audio — only Callyzer's link to it. A call is matched
to leads at READ time by `client_number_key` (normalised last-10 digits), so one call
surfaces on every lead sharing that number (and on leads created later). Idempotent on
`(provider, external_id)` — re-syncing the same Callyzer call updates the row in place.
"""
from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import TenantBase
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class ExternalCall(TenantBase, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "external_calls"
    __table_args__ = (
        UniqueConstraint("provider", "external_id", name="uq_external_calls_provider_external_id"),
        {"schema": "tenant"},
    )

    provider: Mapped[str] = mapped_column(String(20), nullable=False, default="callyzer")
    # The provider's own call id — the idempotency anchor.
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)

    # The client / customer side (the lead's number).
    client_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Normalised last-10 digits of the client number — indexed; the lead-match key.
    client_number_key: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    client_name: Mapped[str | None] = mapped_column(String(160), nullable=True)

    # The business / employee side (who called).
    emp_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    emp_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    # Best-effort match of the employee number to a FlexCRM user.
    user_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("public.users.id", ondelete="SET NULL"), nullable=True
    )

    call_type: Mapped[str | None] = mapped_column(String(20), nullable=True)  # Incoming/Outgoing/Missed/Rejected
    # Callyzer v2.2 also classifies method (PhoneCall / WhatsAppCall) and mode
    # (Voice / Video) — kept generic so future providers (Exotel/Twilio) map here too.
    call_method: Mapped[str | None] = mapped_column(String(20), nullable=True)
    call_mode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # The provider's OWN lead id for this call, if any (Callyzer `lead_id`) — kept for
    # future association without making it the match key (we match by phone).
    provider_lead_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    call_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    crm_status: Mapped[str | None] = mapped_column(String(64), nullable=True)  # Callyzer disposition
    reminder_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recording_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The raw provider record, for forward-compat / debugging.
    raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)
