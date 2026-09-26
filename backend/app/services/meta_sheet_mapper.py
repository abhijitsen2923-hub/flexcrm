"""Map a Meta-lead-pattern Google Sheet row → a FlexCRM ingest `fields` dict + dedup `external_id`.

Pure and side-effect-free (unit-testable), mirroring `lead_source_mapper.map_99acres_lead`. The sheet is
fed by the tenant's Meta→Sheets automation, so rows carry Meta lead-ad columns (a leadgen id,
`created_time`, `full_name`/`email`/`phone_number`, campaign/ad/form, and form-question columns). We map the
recognised columns and preserve everything else in `notes`; `source` snaps to facebook/instagram.

Campaign: the Meta `campaign_name` by default. Agency (AntTech) sheets split ONE Meta campaign into
per-product tabs, so for those connections the sheet tab is the campaign (`campaign_from_tab=True`) and the
Meta names stay in notes. Meta's "You don't have enough permission…" stand-in text is never a real name —
it's treated as empty wherever a campaign/ad set/ad/form name is read.

Dedup: `external_id` = the Meta leadgen id (stable per lead) when present, else a fingerprint of
normalised phone + created_time. Idempotent re-polls rely on the `(source_provider, external_id)` index.
Already-ingested leads are brought in line by `relabel_changes` (the sync's self-heal).

Reuses the pure `normalize_phone` + `parse_received_date` helpers (they happen to live in
`lead_source_mapper`); this is source-agnostic utility reuse, not the 99acres connector.
"""
from __future__ import annotations

import hashlib
import re

from app.core.google_sheets import SHEET_TAB_KEY
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

# Lead column bounds (models/lead.py). The mapper clamps campaign itself so the self-heal compares the
# exact value the DB would hold (LeadIngestService clamps the same way on create).
CAMPAIGN_MAX_LEN = 120
TITLE_MAX_LEN = 255

# Meta's Sheets integration writes this sentence INSTEAD of a campaign/ad set/ad/form name when the
# connection can't read the ad account ("You don't have enough permission(s). Please refer to this help…").
# Anchored at the start so a value already clamped to 120 chars in the DB still matches.
_META_PERMISSION_PLACEHOLDER = re.compile(
    r"^\s*you\s+do(?:n[’']?t|\s+not)\s+have\s+enough\s+permissions?\b", re.IGNORECASE
)

# Meta form-question columns we recognise → CRM fields. Anything not listed (campaign/ad/form
# names + any custom question) is preserved in notes.
_QUESTION_MAP: tuple[tuple[tuple[str, ...], str], ...] = (
    (("city", "location", "preferred_location", "preferred_city"), "preferred_location"),
    (("what_are_you_looking_for", "interest", "interested_in", "requirement", "looking_for"), "interest"),
)

# Columns surfaced as attribution in notes (in order), if present + non-empty.
_ATTRIBUTION_KEYS: tuple[tuple[str, str], ...] = (
    (SHEET_TAB_KEY, "sheet tab"),
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


def is_meta_permission_placeholder(value: str | None) -> bool:
    """True for Meta's "You don't have enough permission…" stand-in text (never a real name)."""
    return bool(value) and bool(_META_PERMISSION_PLACEHOLDER.match(value))


def _get_clean(row: dict, *keys: str) -> str:
    """Like `_get`, but skips Meta's permission placeholder — key by key, so a junk `campaign_name`
    still falls through to a real `campaign` alias."""
    for key in keys:
        val = _get(row, key)
        if val and not is_meta_permission_placeholder(val):
            return val
    return ""


def _fingerprint(phone: str | None, created: str) -> str:
    raw = f"{phone or ''}|{created}"
    return "fp_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def map_sheet_row(row: dict, *, campaign_from_tab: bool = False) -> tuple[str, dict]:
    """Return (external_id, crm_fields) for one Meta-pattern sheet row (header→cell dict).
    `campaign_from_tab` makes the row's sheet tab (SHEET_TAB_KEY) the campaign — agency sheets."""
    name = _get(row, *_NAME_KEYS)
    if not name:
        first = _get(row, "first_name", "firstname")
        last = _get(row, "last_name", "lastname")
        name = " ".join(p for p in (first, last) if p)
    phone = normalize_phone(_get(row, *_PHONE_KEYS))
    email = _get(row, *_EMAIL_KEYS) or None

    platform = _get(row, *_PLATFORM_KEYS).lower()
    # Emit the CANONICAL source labels (see core.lead_normalize.SOURCE_LABELS) so the ingested lead's
    # source matches the Leads source filter — a bare "facebook"/"instagram" would not.
    source = "Instagram" if ("instagram" in platform or platform == "ig") else "Facebook / Meta"
    # A blank tab falls back to the (placeholder-free) Meta campaign name.
    campaign = (_get(row, SHEET_TAB_KEY) if campaign_from_tab else "") or _get_clean(row, *_CAMPAIGN_KEYS)

    fields: dict = {
        "contact_name": name or None,
        "contact_phone": phone,
        "contact_email": email,
        "source": source,
        # Map the campaign onto the dedicated CRM `campaign` column (not just notes) so it shows in
        # the Leads list column and drives the Campaign filter.
        "campaign": campaign[:CAMPAIGN_MAX_LEN] or None,
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

    # Notes: Meta attribution first, then any unrecognised columns — nothing dropped (except Meta's
    # permission placeholder, which carries no information).
    notes: list[str] = []
    attribution = [f"{label}: {val}" for key, label in _ATTRIBUTION_KEYS if (val := _get_clean(row, key))]
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


# ---- Self-heal of already-ingested leads (#46) ---------------------------------------------------
# FROZEN copy of the pre-#46 mapper inputs — deliberately NOT the live constants, so legacy matching keeps
# reproducing exactly what older syncs stored however the live mapper changes later.
_LEGACY_NAME_KEYS = ("full_name", "name", "fullname")
_LEGACY_INTEREST_KEYS = ("what_are_you_looking_for", "interest", "interested_in", "requirement", "looking_for")
_LEGACY_CAMPAIGN_KEYS = ("campaign_name", "campaign")


def legacy_campaign_and_title(row: dict) -> tuple[str | None, str | None]:
    """(campaign, title) exactly as the pre-#46 mapper + LeadIngestService stored them for `row`: the RAW
    campaign_name (placeholder included) and "<interest or campaign> — <name>", clamped like ingest. Title
    is None when ingest would have substituted its own fallback (not reproducible → never heal it)."""
    name = _get(row, *_LEGACY_NAME_KEYS)
    if not name:
        name = " ".join(p for p in (_get(row, "first_name", "firstname"), _get(row, "last_name", "lastname")) if p)
    campaign = _get(row, *_LEGACY_CAMPAIGN_KEYS)
    lead_for = _get(row, *_LEGACY_INTEREST_KEYS) or campaign
    title = (f"{lead_for} — {name}".strip(" —") if (lead_for or name) else "Meta Lead").strip()
    return (campaign[:CAMPAIGN_MAX_LEN] or None), (title[:TITLE_MAX_LEN] or None)


def relabel_changes(
    row: dict, fields: dict, *, current_campaign: str | None, current_title: str | None
) -> dict[str, str | None]:
    """Column changes that bring an ALREADY-ingested lead in line with the current mapping of its row
    (`fields` = map_sheet_row output). A column is rewritten only while it still holds exactly what an
    older sync stored (so any edit that changed it is left alone) or starts with Meta's permission
    placeholder. {} when nothing should change — the steady state after one relabel (idempotent)."""
    legacy_campaign, legacy_title = legacy_campaign_and_title(row)
    changes: dict[str, str | None] = {}

    new_campaign = (fields.get("campaign") or "")[:CAMPAIGN_MAX_LEN] or None
    cur_campaign = current_campaign or None
    if new_campaign != cur_campaign and (
        cur_campaign == legacy_campaign or is_meta_permission_placeholder(cur_campaign)
    ):
        changes["campaign"] = new_campaign

    new_title = (fields.get("title") or "").strip()[:TITLE_MAX_LEN]
    if new_title and current_title and new_title != current_title and (
        (legacy_title is not None and current_title == legacy_title)
        or is_meta_permission_placeholder(current_title)
    ):
        changes["title"] = new_title
    return changes
