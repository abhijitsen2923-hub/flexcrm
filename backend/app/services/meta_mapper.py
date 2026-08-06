"""Map a Meta Lead Ads lead object → a FlexCRM ingest `fields` dict.

Pure, side-effect-free (easy to unit-test). The Graph lead object carries top-level
metadata (id=leadgen_id, created_time, platform, campaign/ad names) plus `field_data`
(the form questions). Standard question names auto-map; the connection's `field_map`
overrides/extends; every UNMAPPED answer is appended to `notes` so nothing is lost.
`title` is synthesized (Meta provides none). `platform` gives the FB-vs-IG source
label directly — no extra Graph call.
"""
from __future__ import annotations

from datetime import datetime

# Standard Meta prefill/question names → CRM Lead fields. `None` = deliberately ignore.
_STANDARD_MAP: dict[str, str | None] = {
    "full_name": "contact_name",
    "first_name": "contact_name",   # split-name forms accumulate (see below)
    "last_name": "contact_name",
    "phone_number": "contact_phone",
    "email": "contact_email",
    "city": "preferred_location",
    "company_name": "company_name",
    "job_title": None,
}
_IGNORE = "__ignore__"


def source_for_platform(platform: str | None) -> str:
    p = (platform or "").strip().lower()
    if p in ("ig", "instagram"):
        return "Instagram"
    return "Facebook / Meta"


def _first_value(entry: dict) -> str:
    values = entry.get("values") or []
    return (str(values[0]).strip() if values else "")


def _humanize(name: str) -> str:
    return name.replace("_", " ").strip().rstrip("?").strip().capitalize()


def created_unix(created_time: str | None) -> int | None:
    """Meta created_time is ISO-8601 with a '+0000' offset (no colon). Normalize and
    return a unix timestamp for the per-form poll cursor. None if unparseable."""
    if not created_time:
        return None
    s = created_time.strip().replace("Z", "+00:00")
    # Insert the missing colon in a '+0000' / '-0530' style offset.
    if len(s) >= 5 and s[-5] in "+-" and s[-3] != ":":
        s = s[:-2] + ":" + s[-2:]
    try:
        return int(datetime.fromisoformat(s).timestamp())
    except (ValueError, TypeError):
        return None


def map_meta_lead(lead: dict, field_map: dict | None, *, provider: str = "facebook") -> tuple[str, int | None, dict]:
    """Return (external_id, created_unix, crm_fields). external_id = the leadgen_id."""
    external_id = str(lead.get("id") or "")
    fm = dict(field_map or {})
    fields: dict = {}
    unmapped: list[str] = []

    for entry in lead.get("field_data") or []:
        name = (entry.get("name") or "").strip()
        if not name:
            continue
        value = _first_value(entry)
        # Connection mapping wins, then the standard defaults; else it's unmapped.
        target = fm.get(name, _STANDARD_MAP.get(name, _IGNORE))
        if target is None:
            continue  # explicitly ignored
        if target == _IGNORE:
            if value:
                unmapped.append(f"{_humanize(name)}: {value}")
            continue
        if not value:
            continue
        # Accumulate when two questions map to the same field (first + last name).
        prev = fields.get(target)
        fields[target] = f"{prev} {value}".strip() if prev else value

    fields["source"] = source_for_platform(lead.get("platform"))
    if lead.get("campaign_name"):
        fields["campaign"] = lead["campaign_name"]

    contact = fields.get("contact_name") or ""
    form_name = lead.get("form_name") or "Meta Lead"
    fields["title"] = (f"{form_name} — {contact}".strip(" —") or form_name)

    notes: list[str] = list(unmapped)
    attribution = [
        f"{k.replace('_', ' ')}: {lead[k]}"
        for k in ("ad_name", "adset_name", "campaign_name")
        if lead.get(k)
    ]
    if lead.get("is_organic") is not None:
        attribution.append(f"organic: {bool(lead.get('is_organic'))}")
    if attribution:
        notes.append("— Meta attribution —")
        notes.extend(attribution)
    if notes:
        fields["notes"] = "\n".join(notes)

    return external_id, created_unix(lead.get("created_time")), fields
