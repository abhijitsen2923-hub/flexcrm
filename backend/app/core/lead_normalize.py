"""Normalize free-text CSV values to the canonical lead dropdown labels.

The lead create/edit form uses controlled dropdowns for `source`,
`interest` (real-estate "Property Interest") and `property_type` — see
`frontend/src/utils/options.ts` (`leadSourceOptions`, `propertyInterestOptions`)
and the Property-type select in `LeadsPage.tsx`. CSV imports, however, carry
messy historical values ("2bhk", "walk in", "Magic Bricks", "flat"). Rather than
*reject* those rows, we snap each value to its canonical dropdown label when we
recognise it (case-insensitive, punctuation-insensitive, plus a small alias
table) and otherwise keep the original text verbatim — the same behaviour the UI
gives an "Other…" free-text entry.

Keep the canonical lists here in sync with `frontend/src/utils/options.ts`.
"""

from __future__ import annotations

import re

# Canonical labels — MUST match frontend/src/utils/options.ts exactly.
SOURCE_LABELS: tuple[str, ...] = (
    "Walk-in", "Reference", "Instagram", "Facebook / Meta", "WhatsApp",
    "Google Ads", "Website", "99acres", "MagicBricks", "Housing.com",
    "Cold call", "Newspaper / Print", "Hoarding", "Other",
)
PROPERTY_INTEREST_LABELS: tuple[str, ...] = (
    "1 BHK", "2 BHK", "3 BHK", "4 BHK", "5 BHK+", "Studio", "Penthouse",
    "Duplex", "Plot / Land", "Villa", "Commercial", "Other",
)
# Property type is *value*-keyed in the UI (value != label); imports store the value.
PROPERTY_TYPE_VALUES: tuple[str, ...] = ("apartment", "villa", "plot", "commercial")


def _norm_key(value: str) -> str:
    """Lowercase, strip, and collapse all non-alphanumerics so '2 BHK', '2bhk'
    and '2-bhk' all reduce to the same lookup key."""
    return re.sub(r"[^a-z0-9]+", "", value.strip().lower())


def _build_map(canonical: tuple[str, ...], aliases: dict[str, str]) -> dict[str, str]:
    """Map normalised-key → canonical label. Canonical labels seed the map so an
    exact (any-case) match snaps to the correct casing; aliases layer on top."""
    out: dict[str, str] = {}
    for label in canonical:
        out[_norm_key(label)] = label
    for alias, label in aliases.items():
        out[_norm_key(alias)] = label
    return out


_SOURCE_MAP = _build_map(
    SOURCE_LABELS,
    {
        "walk in": "Walk-in", "walkins": "Walk-in", "walkin": "Walk-in",
        "referral": "Reference", "ref": "Reference", "word of mouth": "Reference",
        "reffered": "Reference", "referred": "Reference",
        "insta": "Instagram", "ig": "Instagram",
        "fb": "Facebook / Meta", "facebook": "Facebook / Meta", "meta": "Facebook / Meta",
        "facebook ads": "Facebook / Meta", "meta ads": "Facebook / Meta",
        "wa": "WhatsApp", "whats app": "WhatsApp",
        "google": "Google Ads", "google ad": "Google Ads", "adwords": "Google Ads",
        "google adwords": "Google Ads", "gads": "Google Ads", "ppc": "Google Ads",
        "web": "Website", "site": "Website", "web form": "Website", "webform": "Website",
        "enquiry form": "Website",
        "99 acres": "99acres", "acres 99": "99acres",
        "magic bricks": "MagicBricks", "magic brick": "MagicBricks",
        "housing": "Housing.com", "housing com": "Housing.com",
        "coldcall": "Cold call", "cold calling": "Cold call", "telecall": "Cold call",
        "telecalling": "Cold call",
        "newspaper": "Newspaper / Print", "print": "Newspaper / Print",
        "print media": "Newspaper / Print", "news paper": "Newspaper / Print",
        "pamphlet": "Newspaper / Print",
        "hoardings": "Hoarding", "banner": "Hoarding", "billboard": "Hoarding",
        "outdoor": "Hoarding",
        "others": "Other", "misc": "Other", "na": "Other",
    },
)

_INTEREST_MAP = _build_map(
    PROPERTY_INTEREST_LABELS,
    {
        "1bhk": "1 BHK", "one bhk": "1 BHK",
        "2bhk": "2 BHK", "two bhk": "2 BHK",
        "3bhk": "3 BHK", "three bhk": "3 BHK",
        "4bhk": "4 BHK", "four bhk": "4 BHK",
        "5bhk": "5 BHK+", "5 bhk": "5 BHK+", "5bhkplus": "5 BHK+",
        "5plusbhk": "5 BHK+", "6bhk": "5 BHK+",
        "studio apartment": "Studio", "1rk": "Studio", "rk": "Studio",
        "pent house": "Penthouse",
        "plot": "Plot / Land", "land": "Plot / Land", "open plot": "Plot / Land",
        "na plot": "Plot / Land",
        "independent house": "Villa", "bungalow": "Villa", "row house": "Villa",
        "rowhouse": "Villa",
        "shop": "Commercial", "office": "Commercial", "office space": "Commercial",
        "retail": "Commercial", "showroom": "Commercial",
        "others": "Other",
    },
)

_PROPERTY_TYPE_MAP = _build_map(
    PROPERTY_TYPE_VALUES,
    {
        "flat": "apartment", "flats": "apartment", "apartments": "apartment",
        "residential": "apartment", "residential flat": "apartment",
        "independent house": "villa", "bungalow": "villa", "row house": "villa",
        "rowhouse": "villa", "villa independent house": "villa",
        "land": "plot", "open plot": "plot", "na plot": "plot", "plot land": "plot",
        "shop": "commercial", "office": "commercial", "retail": "commercial",
        "godown": "commercial", "warehouse": "commercial", "showroom": "commercial",
    },
)


def _normalize(value: str | None, lookup: dict[str, str]) -> str | None:
    """Snap `value` to a canonical label/value when recognised; otherwise return
    the original trimmed text (unknown → kept as free text). Empty → None."""
    if value is None:
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    return lookup.get(_norm_key(trimmed), trimmed)


def normalize_source(value: str | None) -> str | None:
    return _normalize(value, _SOURCE_MAP)


def normalize_property_interest(value: str | None) -> str | None:
    return _normalize(value, _INTEREST_MAP)


def normalize_property_type(value: str | None) -> str | None:
    return _normalize(value, _PROPERTY_TYPE_MAP)
