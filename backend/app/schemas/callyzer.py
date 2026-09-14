"""Schemas for the Callyzer call-tracking integration."""
from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.schemas.common import ORMModel


# --- Connection (tenant-facing) -------------------------------------------

class CallyzerConnectRequest(ORMModel):
    token: str = Field(min_length=10, max_length=4000)
    label: str | None = Field(default=None, max_length=120)


class CallyzerConnectionRead(ORMModel):
    id: UUID
    label: str | None = None
    status: str = "ok"
    status_detail: str | None = None
    last_synced_at: datetime | None = None
    last_call_at: datetime | None = None
    is_active: bool = True
    created_at: datetime
    # NB: the token is NEVER returned.


# --- Synced call records ---------------------------------------------------

class CallLeadMini(ORMModel):
    id: UUID
    lead_number: int
    contact_name: str


class ExternalCallRead(ORMModel):
    id: UUID
    provider: str = "callyzer"
    external_id: str
    client_number: str | None = None
    client_name: str | None = None
    emp_number: str | None = None
    emp_name: str | None = None
    call_type: str | None = None
    call_method: str | None = None
    call_mode: str | None = None
    duration_seconds: int | None = None
    call_at: datetime | None = None
    note: str | None = None
    crm_status: str | None = None
    reminder_at: datetime | None = None
    recording_url: str | None = None
    created_at: datetime
    # Resolved in the list endpoint (the most-recent lead whose number matches).
    lead: CallLeadMini | None = None
