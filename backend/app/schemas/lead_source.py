"""Schemas for tenant-facing inbound lead-source (99acres) connection management."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class LeadSourceConnectionRead(ORMModel):
    id: UUID
    provider: str
    label: str | None = None
    external_account_id: str | None = None
    default_industry: str
    status: str
    status_detail: str | None = None
    last_lead_at: datetime | None = None
    is_active: bool
    created_at: datetime
    # NOTE: token_hash is deliberately NOT exposed (internal join key).


class LeadSourceConnectRequest(BaseModel):
    # Optional human label, e.g. "Vriddhi Landmart – 99acres".
    label: str | None = None


class LeadSourceConnectResponse(BaseModel):
    """Returned once on connect. `token`/`webhook_url` are shown to the admin a SINGLE time —
    only the token's hash is stored, so it cannot be retrieved again (rotate to get a new one)."""
    connection: LeadSourceConnectionRead
    webhook_url: str
    token: str


# --- Google Sheets (pull) lead source -------------------------------------

class GoogleSheetConnectRequest(BaseModel):
    # The Sheet ID (the `/d/<ID>/` segment of the sheet URL) — distinct per tenant.
    sheet_id: str = Field(min_length=1, max_length=64)
    label: str | None = None


class GoogleSheetConnectResponse(BaseModel):
    connection: LeadSourceConnectionRead
    # The platform service-account email the tenant must share their sheet with (Viewer).
    service_account_email: str | None = None

