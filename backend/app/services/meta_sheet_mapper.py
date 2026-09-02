"""Map a Meta-lead-pattern Google Sheet row → a FlexCRM ingest `fields` dict + dedup `external_id`.

Pure and side-effect-free (unit-testable), mirroring `lead_source_mapper.map_99acres_lead`. The sheet is
fed by the tenant's Meta→Sheets automation, so rows carry Meta lead-ad columns (a leadgen id,
`created_time`, `full_name`/`email`/`phone_number`, campaign/ad/form, and form-question columns). We map the
recognised columns and preserve everything else in `notes`; `source` snaps to facebook/instagram.

Dedup: `external_id` = the Meta leadgen id (stable per lead) when present, else a fingerprint of
normalised phone + created_time. Idempotent re-polls rely on the `(source_provider, external_id)` index.

Reuses the pure `normalize_phone` + `parse_received_date` helpers (they happen to live in
`lead_source_mapper`); this is source-agnostic utility reuse, not the 99acres connector.
"""
from __future__ import annotations

import hashlib

from app.services.lead_source_mapper import normalize_phone, parse_received_date

# Recognised Meta columns → CRM lead field (case-insensitive; add aliases here when a connector
# renames a header — finalize against the tenant's real sheet).
_NAME_KEYS = ("full_name", "name", "fullname")
_EMAIL_KEYS = ("email", "email_address", "work_email")
_PHONE_KEYS = ("phone_number", "phone", "mobile", "contact_number")
_ID_KEYS = ("id", "lead_id", "leadgen_id", "lead id")
_CREATED_KEYS = ("created_time", "created", "created_at", "date", "timestamp")
_PLATFORM_KEYS = ("platform", "source_platform")
_CAMPAIGN_KEYS = ("campaign_name", "campaign")

# Meta form-question columns we recognise → CRM fields. Anything not listed (campaign/ad/form
# names + any custom question) is preserved in notes.
_QUESTION_MAP: tuple[tuple[tuple[str, ...], str], ...] = (
    (("city", "location", "preferred_location", "preferred_city"), "preferred_location"),
    (("what_are_you_looking_for", "interest", "interested_in", "requirement", "looking_for"), "interest"),
)

# Columns surfaced as attribution in notes (in order), if present + non-empty.
_ATTRIBUTION_KEYS: tuple[tuple[str, str], ...] = (
    ("campaign_name", "campaign"),
    ("adset_name", "ad set"),
    ("ad_name", "ad"),
    ("form_name", "form"),
    ("form_id", "form id"),
    ("created_time", "received on"),
    ("platform", "platform"),
)


def _get(row: dict, *keys: str) -> str:
    """First non-empty stringified value among case-insensitive header variants."""
    lowered = {str(k).strip().lower(): v for k, v in row.items() if isinstance(k, str)}
    for key in keys:
        val = lowered.get(key.lower())
        if val is not None and str(val).strip():
            return str(val).strip()
    return ""


def _fingerprint(phone: str | None, created: str) -> str:
    raw = f"{phone or ''}|{created}"
    return "fp_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def map_sheet_row(row: dict) -> tuple[str, dict]:
    """Return (external_id, crm_fields) for one Meta-pattern sheet row (header→cell dict)."""
    name = _get(row, *_NAME_KEYS)
    if not name:
        first = _get(row, "first_name", "firstname")
        last = _get(row, "last_name", "lastname")
        name = " ".join(p for p in (first, last) if p)
    phone = normalize_phone(_get(row, *_PHONE_KEYS))
    email = _get(row, *_EMAIL_KEYS) or None

    platform = _get(row, *_PLATFORM_KEYS).lower()
    source = "instagram" if ("instagram" in platform or platform == "ig") else "facebook"
    campaign = _get(row, *_CAMPAIGN_KEYS)

    fields: dict = {
        "contact_name": name or None,
        "contact_phone": phone,
        "contact_email": email,
        "source": source,
        # Map the Meta campaign name onto the dedicated CRM `campaign` column (not just
        # notes) so it shows in the Leads list column and drives the Campaign filter.
        "campaign": campaign or None,
    }
    for aliases, target in _QUESTION_MAP:
        val = _get(row, *aliases)
        if val:
            fields[target] = val

    created_raw = _get(row, *_CREATED_KEYS)
    created_dt = parse_received_date(created_raw)
    if created_dt is not None:
        fields["source_created_at"] = created_dt

    # Title (Meta gives none): "<interest/campaign> — <Name>" / fallbacks.
    lead_for = fields.get("interest") or campaign
    title = f"{lead_for} — {name}".strip(" —") if (lead_for or name) else "Meta Lead"
    fields["title"] = title

    # Notes: Meta attribution first, then any unrecognised columns — nothing dropped.
    notes: list[str] = []
    attribution = [f"{label}: {_get(row, key)}" for key, label in _ATTRIBUTION_KEYS if _get(row, key)]
    if attribution:
        notes.append("— Meta —")
        notes.extend(attribution)
    known: set[str] = set()
    for group in (_NAME_KEYS, _EMAIL_KEYS, _PHONE_KEYS, _ID_KEYS, _CREATED_KEYS, _PLATFORM_KEYS, _CAMPAIGN_KEYS):
        known.update(k.lower() for k in group)
    for aliases, _t in _QUESTION_MAP:
        known.update(k.lower() for k in aliases)
    known.update(k.lower() for k, _l in _ATTRIBUTION_KEYS)
    known.update(("first_name", "firstname", "last_name", "lastname"))
    extras = [
        f"{str(k).strip()}: {str(v).strip()}"
        for k, v in row.items()
        if isinstance(k, str) and str(k).strip().lower() not in known and v is not None and str(v).strip()
    ]
    if extras:
        notes.append("— extra fields —")
        notes.extend(extras)
    if notes:
        fields["notes"] = "\n".join(notes)

    lead_id = _get(row, *_ID_KEYS)
    external_id = lead_id or _fingerprint(phone, created_raw)
    return external_id, fields
