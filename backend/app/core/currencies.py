"""Per-vertical currency allow-lists.

Each Organization's `business_type` implies a default set of allowed
currencies. A user landing on an Education org sees INR + USD by default; a
Travel user sees INR + USD + EUR. Per-org overrides via
`Organization.features["currency.options"]` (a list of ISO codes) let
admins customise further without changing code.

Symbols (₹, $, €, …) live on the frontend — the backend deals in ISO codes.
"""
from __future__ import annotations

from app.database.enums import LeadIndustry
from app.models.organization import Organization


DEFAULT_CURRENCY = "INR"


# Defaults by vertical. The user's request:
# - Education clients are mostly India-based → INR + USD.
# - Travel deals often cross borders → INR + USD + EUR.
DEFAULT_ALLOWED_CURRENCIES: dict[LeadIndustry, list[str]] = {
    LeadIndustry.education: ["INR", "USD"],
    LeadIndustry.travel: ["INR", "USD", "EUR"],
}


def allowed_currencies_for_org(organization: Organization) -> list[str]:
    """Return the ISO codes this org may use on Lead.value / SalesOrder.amount.

    Resolution order:
    1. Explicit `Organization.features["currency.options"]` override.
    2. Vertical default from `DEFAULT_ALLOWED_CURRENCIES`.
    3. `[DEFAULT_CURRENCY]` as the final safety net.
    """
    features = organization.features or {}
    override = features.get("currency.options")
    if isinstance(override, list) and override:
        return [str(code).upper() for code in override]
    return list(DEFAULT_ALLOWED_CURRENCIES.get(organization.business_type, [DEFAULT_CURRENCY]))
