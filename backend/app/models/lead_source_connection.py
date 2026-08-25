"""Per-tenant inbound lead-source connection (99acres, and future push portals) — tenant schema.

Tenant-side config + status for a portal that PUSHES leads to us. The credential itself is not
stored here — it's the URL path token, whose hash lives in the public `lead_source_routes`
(see lead_source_route.py). This table holds what the ingest + UI need: which provider/account,
the industry to stamp on created leads, an optional field-name override map, the owning
integration service user, and a health status. Mirrors MetaConnection minus the token columns.
"""
from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    String,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import TenantBase
from app.models.base import (
    TenantAuditMixin,
    TenantSoftDeleteMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class LeadSourceConnection(
    TenantBase, UUIDPrimaryKeyMixin, TimestampMixin, TenantAuditMixin, TenantSoftDeleteMixin
):
    __tablename__ = "lead_source_connections"
    __table_args__ = ({"schema": "tenant"},)

    # "99acres" | future portals.
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    # SHA-256 (hex) of this connection's URL token — the join key to its PUBLIC
    # lead_source_routes row (routing lives in public; config lives here). Not a secret
    # (a hash); lets the inbound handler find THIS connection after switching schema, and
    # lets disconnect release the exact route. Globally unique via the public route.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # The portal account this connection represents (e.g. the 99acres Username). Nullable
    # until learned from the first delivered lead.
    external_account_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Human label the tenant gave this connection (e.g. "Vriddhi Landmart – 99acres").
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # The org's industry VALUE (e.g. "real_estate"), captured so the ingest sets
    # Lead.industry explicitly (the webhook has no logged-in user). Plain string to avoid
    # binding the cross-schema enum type here (same as MetaConnection.default_industry).
    default_industry: Mapped[str] = mapped_column(String(20), nullable=False)
    # {portal_field_name: crm_lead_field} — optional per-connection override; standard names
    # auto-map in the mapper, unmapped values go to notes.
    field_map: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # The per-org integration service user that OWNS ingested leads (their created_by).
    integration_user_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("public.users.id", ondelete="SET NULL"), nullable=True
    )
    # ok | error — surfaced in the UI; deliveries still persist regardless.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ok")
    status_detail: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_lead_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
