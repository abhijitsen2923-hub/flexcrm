"""Public-schema Page → tenant router for Meta lead webhooks.

Meta lead webhooks (Phase 2) arrive UNauthenticated on ONE FlexCRM endpoint for
ALL tenants and carry only a `page_id`. This shared/public table maps a Facebook
page_id to its owning org + schema so the webhook handler can resolve the tenant
*before* touching any tenant schema (routing precedes auth). It holds NO secrets —
the token lives in the tenant's `MetaConnection`. The UNIQUE `page_id` also enforces
"one Page ↔ one tenant" across the whole platform, so two workspaces can't both
claim the same Page. Written on connect (BYO or OAuth) and REMOVED on disconnect,
which frees the Page to be reconnected — by the same org or, legitimately, another.

Lives in the public schema exactly like organizations / users / refresh_tokens.
"""
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, String, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class MetaPageRoute(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "meta_page_routes"

    # The Facebook Page id — the only key a webhook payload carries to identify a tenant.
    page_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Denormalised so the webhook can set_tenant_schema without a second lookup.
    schema_name: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
