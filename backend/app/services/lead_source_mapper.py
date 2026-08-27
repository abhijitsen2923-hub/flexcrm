"""Map a 99acres push payload → a FlexCRM ingest `fields` dict + a dedup `external_id`.

Pure and side-effect-free (easy to unit-test), mirroring `meta_mapper.map_meta_lead`. 99acres
posts its native export field names (see docs/integrations/99acres/flexcrm-lead-api.md); we parse
their quirks here — phone `91-<10d>`, `InterestedIn` = `Project|Locality|City`, `ResCom` R/C — and
snap `source` to the canonical `"99acres"` label so it matches the list filter. Unmapped answers
are appended to `notes` so nothing is lost.

Dedup: `external_id` = the portal's `lead_id` when present, else a stable fingerprint of
normalised phone + ReceivedDate + ProductCode (the sample export carries no per-lead id). This
makes a redelivery of the SAME enquiry idempotent; a genuinely new enquiry (different
ReceivedDate) is a new lead and picks up the existing "!" duplicate marker automatically.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone

# 99acres sends India-local naive datetimes; IST is a fixed +05:30 (no DST), so a fixed
# offset avoids any tzdata/zoneinfo dependency in the slim runtime image.
_IST = timezone(timedelta(hours=5, minutes=30))
_RECEIVED_FORMATS = ("%Y-%m-%d %H:%M:%S", "%m/%d/%Y %I:%M %p", "%m/%d/%Y %I:%M:%S %p")

# 99acres columns we surface as attribution in notes (in this order), if present + non-empty.
_ATTRIBUTION_FIELDS: tuple[tuple[str, str], ...] = (
    ("ProductCode", "listing"),
    ("Type", "enquirer type"),
    ("LeadScore", "99acres score"),
    ("ResponseType", "response type"),
    ("ProductType", "product type"),
    ("FollowupCurrentStatus", "99acres status"),
    ("Duplicate", "99acres duplicate flag"),
    ("PhoneVerificationStatus", "phone verification"),
    ("ReceivedDate", "received on"),
    ("Username", "99acres account"),
)


def normalize_phone(raw: str | None) -> str | None:
    """99acres sends `91-9830427197` (country code, hyphen, 10 digits). Reduce to E.164 `+91…`.
    Tolerates plain 10-digit, leading-0, and already-+prefixed values. None if no digits."""
    digits = re.sub(r"\D", "", raw or "")
    if not digits:
        return None
    if len(digits) == 10:
        return f"+91{digits}"
    if len(digits) == 12 and digits.startswith("91"):
        return f"+{digits}"
    if len(digits) == 11 and digits.startswith("0"):
        return f"+91{digits[1:]}"
    return f"+{digits}"


def parse_received_date(raw: str | None) -> datetime | None:
    """Parse 99acres' `ReceivedDate` → an aware UTC datetime, so an ingested lead can be dated
    to the actual enquiry time (not our ingestion time). Accepts the live-push format
    `YYYY-MM-DD HH:MM:SS`, the dashboard-export `MM/DD/YYYY hh:mm AM/PM`, and ISO-8601. Naive
    values are read as IST. Returns None when empty/unparseable (→ caller falls back to
    ingestion time); the raw value is also kept verbatim in notes, so nothing is lost."""
    raw = (raw or "").strip()
    if not raw:
        return None
    dt: datetime | None = None
    for fmt in _RECEIVED_FORMATS:
        try:
            dt = datetime.strptime(raw, fmt)
            break
        except ValueError:
            dt = None
    if dt is None:
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_IST)
    return dt.astimezone(timezone.utc)


def _get(payload: dict, *keys: str) -> str:
    """First non-empty stringified value among case-insensitive key variants."""
    lowered = {k.lower(): v for k, v in payload.items() if isinstance(k, str)}
    for key in keys:
        val = lowered.get(key.lower())
        if val is not None and str(val).strip():
            return str(val).strip()
    return ""


def _fingerprint(phone: str | None, received: str, product_code: str) -> str:
    raw = f"{phone or ''}|{received}|{product_code}"
    return "fp_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def map_99acres_lead(payload: dict) -> tuple[str, dict]:
    """Return (external_id, crm_fields). `payload` is 99acres' native JSON body."""
    name = _get(payload, "Name", "name")
    phone = normalize_phone(_get(payload, "ContactNo", "contact_no", "phone"))
    email = _get(payload, "EmailId", "email") or None

    # InterestedIn = "Project|Locality|City"
    project = locality = city = ""
    interested_in = _get(payload, "InterestedIn", "interested_in")
    if interested_in:
        parts = [p.strip() for p in interested_in.split("|")]
        project = parts[0] if len(parts) > 0 else ""
        locality = parts[1] if len(parts) > 1 else ""
        city = parts[2] if len(parts) > 2 else ""
    city = city or _get(payload, "City", "city")

    preferred_location = ", ".join(p for p in (locality, city) if p) or None

    fields: dict = {
        "contact_name": name or None,
        "contact_phone": phone,
        "contact_email": email,
        "source": "99acres",
    }
    # Bhk → property interest (e.g. "3 BHK"); ResCom C → commercial property type.
    bhk = _get(payload, "Bhk", "bhk")
    if bhk:
        fields["interest"] = bhk
    if _get(payload, "ResCom", "res_com").upper() == "C":
        fields["property_type"] = "commercial"
    if preferred_location:
        fields["preferred_location"] = preferred_location

    # Title (99acres provides none): "<Project> — <Name>" / fallbacks.
    title = f"{project} — {name}".strip(" —") if (project or name) else "99acres Lead"
    fields["title"] = title

    # Notes: the enquirer's message first, then attribution lines. Nothing dropped.
    notes: list[str] = []
    query = _get(payload, "Query", "query", "message")
    if query:
        notes.append(query)
    attribution = [
        f"{label}: {_get(payload, key)}" for key, label in _ATTRIBUTION_FIELDS if _get(payload, key)
    ]
    if attribution:
        notes.append("— 99acres —")
        notes.extend(attribution)
    if notes:
        fields["notes"] = "\n".join(notes)

    # Date the lead to the enquiry time (ReceivedDate) when parseable — the ingest layer maps
    # `source_created_at` onto the lead's created_at. Falls back to ingestion time otherwise.
    received_dt = parse_received_date(_get(payload, "ReceivedDate", "received_date"))
    if received_dt is not None:
        fields["source_created_at"] = received_dt

    # external_id: portal lead_id if given, else fingerprint.
    lead_id = _get(payload, "lead_id", "leadId", "LeadId")
    external_id = lead_id or _fingerprint(
        phone, _get(payload, "ReceivedDate", "received_date"), _get(payload, "ProductCode", "product_code")
    )
    return external_id, fields
