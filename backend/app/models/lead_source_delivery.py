"""Per-tenant raw delivery log for inbound lead-source webhooks — tenant schema.

The persist-first-process-second store that makes push-only portals (99acres) safe. Meta can
ACK 200 and swallow errors because its poll re-fetches any lead; 99acres is push-only with no
backstop, so we durably store every delivery BEFORE processing, ACK 200, then map + ingest. A
reconcile cron drains anything left `received`/`failed`. This is also the dead-letter + replay
log. Tenant-scoped, not public, because payloads carry lead PII.
"""
from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, DateTime, String, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import TenantBase
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class LeadSourceDelivery(TenantBase, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "lead_source_deliveries"
    __table_args__ = ({"schema": "tenant"},)

    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    # The connection this delivery routed to (loose ref, not FK — the log outlives connections).
    connection_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    # Dedup key once computed: the portal's lead_id, else our fingerprint. Indexed for the
    # idempotency lookup + reconcile scans. Nullable until the mapper derives it.
    external_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    # The exact JSON body 99acres posted — the replay source of truth.
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    # received | processed | failed | ignored (duplicate/no-op).
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="received", server_default=text("'received'"), index=True
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The created lead (traceability); null until/unless a lead is created.
    lead_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
