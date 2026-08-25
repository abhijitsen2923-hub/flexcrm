"""Public-schema router for inbound lead-source webhooks (99acres, and future portals).

Generalised sibling of `meta_page_route.py`. An inbound portal webhook arrives UNauth'd on
ONE public endpoint per provider and carries only an opaque token in the URL path. This
shared/public table maps that token → its owning org + schema so the handler can resolve the
tenant BEFORE touching any tenant schema (routing precedes auth), exactly like MetaPageRoute.

Auth model (99acres): the URL path token IS the credential (secret-in-URL). We store only its
SHA-256 hash here — never the plaintext — so this public table holds NO usable secret and no
PII. Lookups hash the incoming token and match `token_hash`. Rotating = issue a new token
(new hash, new URL); the old row is replaced.

`provider` keeps this reusable for MagicBricks / Housing.com later without another migration.
Written on connect, removed on disconnect.
"""
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class LeadSourceRoute(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "lead_source_routes"
    __table_args__ = (
        # One 99acres (or other portal) account maps to exactly one tenant. NULLs are
        # distinct in Postgres, so accounts we don't know yet don't collide.
        UniqueConstraint(
            "provider", "external_account_id", name="uq_lead_source_routes_provider_account"
        ),
    )

    # "99acres" | future: "magicbricks" | "housing".
    provider: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    # SHA-256 (hex) of the URL path token — the credential lookup key. Never the plaintext.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    # The portal's account/client id (e.g. 99acres Username), used only as a sanity check.
    # Nullable — we may not learn it until the first delivered lead.
    external_account_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Denormalised so the webhook can set_tenant_schema without a second lookup.
    schema_name: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
