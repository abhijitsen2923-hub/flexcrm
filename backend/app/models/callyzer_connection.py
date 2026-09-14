"""Per-tenant Callyzer (call-tracking) connection — per-tenant schema.

Bring-your-own-key: the tenant admin generates an API access token in their own
Callyzer account (Connectors → API & Webhook → API Config) and pastes it in; we
store it Fernet-encrypted (see app/core/crypto.py) and POLL Callyzer's callHistory
API on a cron, ingesting call records into `external_calls`. The token itself scopes
the data to that Callyzer company — one connection per tenant. Recordings live on
Callyzer's cloud; we only keep the link.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import TenantBase
from app.models.base import (
    TenantAuditMixin,
    TenantSoftDeleteMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class CallyzerConnection(
    TenantBase, UUIDPrimaryKeyMixin, TimestampMixin, TenantAuditMixin, TenantSoftDeleteMixin
):
    __tablename__ = "callyzer_connections"
    __table_args__ = ({"schema": "tenant"},)

    # Optional friendly label the admin can set.
    label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Fernet ciphertext of the Callyzer API access token — NEVER plaintext.
    token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    # ok | needs_reauth | error — the poll stops for this connection on needs_reauth
    # (token revoked/expired) until the admin re-pastes a token.
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ok", server_default=text("'ok'")
    )
    status_detail: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # High-water marks so the poll only fetches new calls.
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_call_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
