"""Per-tenant Meta (Facebook / Instagram) Lead Ads connection — per-tenant schema.

Bring-your-own-token: the business generates a never-expiring System-User token in
their OWN Meta Business Manager and pastes it in; we store it Fernet-encrypted
(see app/core/crypto.py) and POLL the Graph API for new leadgen leads on a cron.
Instagram lead ads flow through the same connected Facebook Page's leadgen edges,
so ONE connection covers both FB and IG. No Meta App Review — the business acts on
its own app + own Page (Meta "Standard Access").
"""
from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
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


class MetaConnection(
    TenantBase, UUIDPrimaryKeyMixin, TimestampMixin, TenantAuditMixin, TenantSoftDeleteMixin
):
    __tablename__ = "meta_connections"
    __table_args__ = (
        # One connection per (provider, page) within a tenant.
        UniqueConstraint("provider", "page_id", name="uq_meta_connections_provider_page"),
        {"schema": "tenant"},
    )

    provider: Mapped[str] = mapped_column(String(20), nullable=False, default="facebook")
    page_id: Mapped[str] = mapped_column(String(64), nullable=False)
    page_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # How the token was obtained. "byo" = the admin pasted their own never-expiring
    # System-User token (poll-only). "oauth" = connected via FlexCRM's app
    # ("Connect Facebook") — the token can expire and webhooks apply. The downstream
    # ingest is identical either way; this just drives refresh + webhook behaviour.
    auth_type: Mapped[str] = mapped_column(
        String(10), nullable=False, default="byo", server_default=text("'byo'")
    )
    # Fernet ciphertext of the PAGE access token used to read leads — NEVER plaintext.
    # (BYO: the System-User token. OAuth: the Page token derived from the user token.)
    token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    # OAuth only: Fernet ciphertext of the long-lived USER token (to refresh/re-derive
    # the page token) and when it expires. Null for BYO (never expires).
    user_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # The scopes the user actually granted (they can decline some on Meta's screen).
    granted_scopes: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Webhook subscription state (Phase 2): pending | subscribed | error.
    subscription_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default=text("'pending'")
    )
    # The org's industry VALUE (e.g. "real_estate"), captured so the ingest sets
    # Lead.industry explicitly (the poll job has no logged-in user to fall back on).
    # Stored as a plain string to avoid binding the cross-schema enum type here.
    default_industry: Mapped[str] = mapped_column(String(20), nullable=False)
    # {meta_field_name: crm_lead_field} — the per-connection form-field mapping the
    # admin configures. Standard names auto-map; unmapped answers go to notes.
    field_map: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # {form_id: last_created_unix} — per-form poll cursor, advanced only post-commit.
    form_cursors: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # The per-org integration service user that OWNS ingested leads (their created_by).
    integration_user_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("public.users.id", ondelete="SET NULL"), nullable=True
    )
    # ok | needs_reauth | error — polling stops for this connection on needs_reauth
    # (e.g. token revoked → Graph code 190) until the admin re-pastes a token.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ok")
    status_detail: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
