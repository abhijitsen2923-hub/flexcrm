"""A tenant's own lead-campaign list, plus the old spellings merged/renamed into each campaign.

Per tenant (schema-per-tenant) — no campaign names are shared across tenants or hard-coded. A campaign is
matched by `name_key` (services/campaigns.py; key = trimmed, whitespace-collapsed, lower-cased name). When a
manager merges or renames, the old spelling is kept as a `CampaignAlias` so future typed / CSV / sheet /
Meta values land on the canonical campaign. A key lives in exactly one of the two tables (enforced by the
service). `leads.campaign` stays a plain string (no FK), so every existing reader keeps working.
"""
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Index, String, UniqueConstraint, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import TenantBase
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin

# How a campaign first entered the list.
CAMPAIGN_SOURCES: tuple[str, ...] = ("existing", "manual", "import", "sheet", "meta", "integration")


class Campaign(TenantBase, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "campaigns"
    __table_args__ = (
        UniqueConstraint("name_key", name="uq_campaigns_name_key"),
        {"schema": "tenant"},
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # 160 > 120: lower-casing can lengthen some Unicode text.
    name_key: Mapped[str] = mapped_column(String(240), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    # Added automatically (upload by a non-manager, sheet / Meta sync) — waiting for a manager to keep or merge.
    needs_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    created_by_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("public.users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("public.users.id", ondelete="SET NULL"), nullable=True
    )


class CampaignAlias(TenantBase, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "campaign_aliases"
    __table_args__ = (
        UniqueConstraint("alias_key", name="uq_campaign_aliases_alias_key"),
        Index("ix_campaign_aliases_campaign_id", "campaign_id"),
        {"schema": "tenant"},
    )

    campaign_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    alias: Mapped[str] = mapped_column(String(120), nullable=False)  # the old spelling, for display
    alias_key: Mapped[str] = mapped_column(String(240), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # merge | rename
    created_by_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("public.users.id", ondelete="SET NULL"), nullable=True
    )
