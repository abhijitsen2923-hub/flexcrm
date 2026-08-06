from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.database.enums import LeadIndustry
from app.schemas.common import ORMModel


# Toggleable module keys. Dashboard / Leads / Customers / Analytics / Users
# are always-on and not listed here.
MODULE_KEYS = (
    "deals", "tasks", "activities",               # Core CRM — any industry
    "finance", "hr",                              # Business operations — any industry
    "inventory", "bookings", "site_visits", "projects",  # Real Estate vertical
    "meta_facebook", "meta_instagram",            # Integrations — Meta Lead Ads, per platform
)


def get_modules(features: dict | None) -> dict[str, bool]:
    """Extract per-org module flags from the features JSON.

    Keys are stored as "module.<name>" in the features dict.
    Missing keys default to False (off until explicitly enabled).
    """
    f = features or {}
    return {key: bool(f.get(f"module.{key}", False)) for key in MODULE_KEYS}


class OrganizationRead(ORMModel):
    id: UUID
    name: str
    business_type: LeadIndustry
    plan: str
    features: dict | None = None
    # Computed at response time — ISO 4217 codes the org may use.
    allowed_currencies: list[str] = []
    # Computed at response time — which optional modules are enabled for this org.
    modules: dict[str, bool] = {}
    # Lifecycle state (platform admin): active = not suspended; is_deleted = archived.
    is_active: bool = True
    is_deleted: bool = False
    created_at: datetime
    updated_at: datetime


class OrganizationUpdate(ORMModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    plan: str | None = Field(default=None, max_length=32)
    features: dict | None = None


class UpdateModulesRequest(ORMModel):
    """Payload for PATCH /admin/organizations/{id}/modules."""
    modules: dict[str, bool]


class SetOrgStatusRequest(ORMModel):
    """Payload for PATCH /admin/organizations/{id}/status (disable/enable)."""
    is_active: bool
