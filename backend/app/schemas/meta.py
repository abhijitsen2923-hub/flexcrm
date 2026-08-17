"""Request/response schemas for the tenant Meta-integration connect flow.

The access token is only ever an INPUT — it is never returned in any response
(MetaConnectionRead deliberately omits it).
"""
from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.schemas.common import ORMModel


class MetaValidateRequest(ORMModel):
    page_id: str = Field(min_length=1, max_length=64)
    token: str = Field(min_length=1)


class MetaValidateResult(ORMModel):
    ok: bool
    page_name: str | None = None
    form_count: int | None = None
    # invalid_token | missing_lead_access | not_owned | error — drives the wizard's
    # specific guidance ("re-paste token" vs "grant Lead Access") instead of a generic fail.
    reason: str | None = None
    detail: str | None = None


class MetaConnectRequest(MetaValidateRequest):
    # Optional per-connection field mapping {meta_field_name: crm_lead_field}.
    field_map: dict | None = None


class MetaConnectionUpdate(ORMModel):
    token: str | None = Field(default=None, min_length=1)
    field_map: dict | None = None
    is_active: bool | None = None


class MetaConnectionRead(ORMModel):
    id: UUID
    provider: str
    page_id: str
    page_name: str | None = None
    # "byo" (pasted token) | "oauth" ("Connect Facebook"). Lets the UI badge how it
    # was connected; the token is never returned regardless.
    auth_type: str = "byo"
    default_industry: str
    field_map: dict | None = None
    status: str
    status_detail: str | None = None
    last_synced_at: datetime | None = None
    is_active: bool
    created_at: datetime


# --- OAuth "Connect Facebook" flow ---------------------------------------


class MetaOAuthStartResponse(ORMModel):
    """The Facebook OAuth dialog URL the frontend redirects the browser to."""
    authorize_url: str


class MetaOAuthPage(ORMModel):
    """A Page the user manages, offered for selection after OAuth. No token exposed."""
    id: str
    name: str | None = None
    has_instagram: bool = False


class MetaOAuthConnectRequest(ORMModel):
    """Finalize: connect the chosen Page(s) from a completed OAuth round-trip."""
    handle: str = Field(min_length=1)
    page_ids: list[str] = Field(min_length=1)
