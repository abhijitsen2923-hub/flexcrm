"""Read-only Google Sheets access via a single platform-owned service account (SA).

`settings.google_sa_key_json` (the SA's JSON key) authorizes read access to any sheet a tenant has
shared (Viewer) with `settings.google_sa_email`. Unset key => the feature is inert (`SheetNotConfigured`).
We only ever read a sheet BY ID (no Drive listing), so the SA needs no GCP project roles and only the
`spreadsheets.readonly` scope — least privilege by construction.
"""
from __future__ import annotations

import json
from functools import lru_cache

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


class SheetNotConfigured(RuntimeError):
    """The Google service-account key is not set — the feature is disabled."""


class SheetAccessError(RuntimeError):
    """The sheet couldn't be read (not shared with the SA, wrong id, or an API error)."""


@lru_cache(maxsize=1)
def _client_for(key_json: str):
    """Build + cache a gspread client from the SA key (cached by key so we don't re-parse JSON /
    rebuild credentials every poll). Google libs are imported lazily so the app still boots in an
    environment that never uses this feature / doesn't have them installed."""
    import gspread
    from google.oauth2.service_account import Credentials

    creds = Credentials.from_service_account_info(json.loads(key_json), scopes=_SCOPES)
    return gspread.authorize(creds)


def _client():
    settings = get_settings()
    if not settings.google_sa_key_json:
        raise SheetNotConfigured("GOOGLE_SA_KEY_JSON is not set.")
    return _client_for(settings.google_sa_key_json)


def read_rows(sheet_id: str) -> list[dict]:
    """Read EVERY worksheet (tab) of `sheet_id` as a combined list of row dicts (each tab's header row
    → cell values), so a multi-form sheet (FORM1 + FORM2 + …) is fully ingested. A tab whose header is
    unusable (no header row, or duplicate/blank column names — e.g. a summary tab) is skipped rather than
    failing the whole sync. Raises SheetNotConfigured (feature off) or SheetAccessError (not shared / bad
    id / can't open the spreadsheet)."""
    gc = _client()
    try:
        worksheets = gc.open_by_key(sheet_id).worksheets()
    except SheetNotConfigured:
        raise
    except Exception as exc:  # noqa: BLE001 — normalize every gspread/google error to one type
        raise SheetAccessError(
            "Could not read the sheet — check that it is shared (Viewer) with the service account "
            "and that the Sheet ID is correct."
        ) from exc
    rows: list[dict] = []
    for ws in worksheets:
        try:
            rows.extend(ws.get_all_records())  # list[dict], keyed by this tab's header row
        except Exception:  # noqa: BLE001 — skip a tab with an unusable header; keep the other tabs
            logger.warning("google_sheets: skipped worksheet %r (unreadable header)", getattr(ws, "title", "?"))
            continue
    return rows


# ---- Header-less "agency" sheets (e.g. AntTech) --------------------------------------------------
# Some agencies deliver a Meta Lead Ads export with NO header row: the lead data sits positionally in
# the LEFT columns in Meta's fixed order, while the real field-name header block is shifted FAR RIGHT of
# each row. We read such a tab with get_all_values() and rebuild header→value dicts by DETECTING that
# header block and zipping its field order onto the left data columns.

# Meta's fixed leading column order (col0..col11) — the anchor we detect the header block by.
_META_FIXED_TOKENS: tuple[str, ...] = (
    "id", "created_time", "ad_id", "ad_name", "adset_id", "adset_name",
    "campaign_id", "campaign_name", "form_id", "form_name", "is_organic", "platform",
)
# Trailing data fields (their per-tab order varies). Everything from col0 through the LAST of these is
# left-column data; `lead_status` is NOT left-column data (it's an outlier just before the header block).
_META_TAIL_DATA: frozenset[str] = frozenset({"full_name", "phone", "street_address", "email"})


def _norm(cell: object) -> str:
    return str(cell).strip() if cell is not None else ""


def _detect_meta_schema(values: list[list]) -> list[str] | None:
    """Find the misplaced header block: the contiguous run of cells that STARTS with the fixed Meta
    tokens (id, created_time, …, platform). Return the ordered field names from there rightward (until a
    blank cell), preserving their original text; or None if no row contains the run."""
    fixed = list(_META_FIXED_TOKENS)
    n = len(fixed)
    for row in values:
        low = [_norm(c).lower() for c in row]
        for i in range(0, max(0, len(low) - n + 1)):
            if low[i:i + n] == fixed:
                names: list[str] = []
                for c in row[i:]:
                    tok = _norm(c)
                    if not tok:
                        break
                    names.append(tok)
                if len(names) >= n:
                    return names
    return None


def _data_schema(schema: list[str]) -> list[str]:
    """The LEFT-column data field order: the schema truncated to end at the LAST trailing-data field
    (full_name/phone/street_address/email), dropping `lead_status` and anything after it."""
    last = -1
    for idx, name in enumerate(schema):
        if name.lower() in _META_TAIL_DATA:
            last = idx
    return schema[: last + 1] if last >= 0 else schema


def _parse_positional_values(values: list[list]) -> list[dict]:
    """Rebuild header→value dicts from a positional (header-less) Meta export grid. Pure + testable: no
    gspread/network. Returns [] when the tab doesn't match the format (no detectable header block)."""
    schema = _detect_meta_schema(values)
    if not schema:
        return []
    names = _data_schema(schema)
    width = len(names)
    out: list[dict] = []
    for row in values:
        if not row:
            continue
        first = _norm(row[0]).lower()
        if not first or first == "id":  # blank row, or a stray literal header row
            continue
        d = {names[i]: (_norm(row[i]) if i < len(row) else "") for i in range(width)}
        # Re-anchor id/phone by their Meta prefixes (robust to column drift and the "Pan India" tab's
        # decoy phone-answer column — the real phone is the value carrying the `p:` prefix).
        for cell in row[:width]:
            c = _norm(cell)
            head = c[:2].lower()
            if head == "l:":
                d["id"] = c
            elif head == "p:":
                d["phone"] = c
        out.append(d)
    return out


def read_rows_positional(sheet_id: str) -> list[dict]:
    """Like read_rows, but for agency sheets with NO header row (data positional in the left columns,
    field-name block shifted far right). Reads each tab via get_all_values() → _parse_positional_values."""
    gc = _client()
    try:
        worksheets = gc.open_by_key(sheet_id).worksheets()
    except SheetNotConfigured:
        raise
    except Exception as exc:  # noqa: BLE001 — normalize every gspread/google error to one type
        raise SheetAccessError(
            "Could not read the sheet — check that it is shared (Viewer) with the service account "
            "and that the Sheet ID is correct."
        ) from exc
    rows: list[dict] = []
    for ws in worksheets:
        try:
            parsed = _parse_positional_values(ws.get_all_values())
            if not parsed:
                logger.warning(
                    "google_sheets: positional format not detected in worksheet %r", getattr(ws, "title", "?")
                )
            rows.extend(parsed)
        except Exception:  # noqa: BLE001 — skip a tab we can't parse; keep the others
            logger.warning(
                "google_sheets: positional parse failed for worksheet %r", getattr(ws, "title", "?"), exc_info=True
            )
            continue
    return rows


def verify_access(sheet_id: str, *, fmt: str = "standard") -> int:
    """Confirm the SA can read the sheet (used by the tenant connect flow); returns the parsed row count.
    `fmt="anttech_positional"` uses the header-less positional reader, else the standard header reader.
    Raises SheetNotConfigured or SheetAccessError with a tenant-friendly message."""
    reader = read_rows_positional if fmt == "anttech_positional" else read_rows
    return len(reader(sheet_id))
