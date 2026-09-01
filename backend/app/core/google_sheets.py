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
    """Read the first worksheet of `sheet_id` as a list of row dicts (header row → cell values).
    Raises SheetNotConfigured (feature off) or SheetAccessError (not shared / bad id / API error)."""
    gc = _client()
    try:
        worksheet = gc.open_by_key(sheet_id).sheet1
        return worksheet.get_all_records()  # list[dict], keyed by the header row
    except SheetNotConfigured:
        raise
    except Exception as exc:  # noqa: BLE001 — normalize every gspread/google error to one type
        raise SheetAccessError(
            "Could not read the sheet — check that it is shared (Viewer) with the service account "
            "and that the Sheet ID is correct."
        ) from exc


def verify_access(sheet_id: str) -> int:
    """Confirm the SA can read the sheet (used by the tenant connect flow); returns the row count.
    Raises SheetNotConfigured or SheetAccessError with a tenant-friendly message."""
    return len(read_rows(sheet_id))
