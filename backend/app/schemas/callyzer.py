"""Schemas for the Callyzer call-tracking integration."""
from datetime import date, datetime
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


# --- Per-employee call stats (Calls → Performance tab + scorecard factor) ---

class EmployeeCallStats(ORMModel):
    user_id: UUID | None = None          # matched FlexCRM user, if any
    name: str                            # the user's name, else emp_name / emp_number
    emp_number: str | None = None
    unmatched: bool = False              # no FlexCRM user matched this device number
    total: int = 0
    outgoing: int = 0
    incoming: int = 0
    missed: int = 0
    rejected: int = 0
    connected: int = 0                   # calls with talk time > 0
    connect_rate: float = 0.0            # connected / total
    total_talk_seconds: int = 0
    avg_talk_seconds: int = 0            # averaged over connected calls
    unique_clients: int = 0
    last_call_at: datetime | None = None


class CallStatsTotals(ORMModel):
    callers: int = 0
    total: int = 0
    connected: int = 0
    missed: int = 0
    total_talk_seconds: int = 0
    unique_clients: int = 0


class CallStatsResponse(ORMModel):
    date_from: datetime
    date_to: datetime
    totals: CallStatsTotals
    rows: list[EmployeeCallStats]


# --- Caller → user mapping (fix unmatched attribution) ---------------------

class CallAgentAssignRequest(ORMModel):
    emp_number: str = Field(min_length=1, max_length=32)
    emp_name: str | None = Field(default=None, max_length=160)
    user_id: UUID


class CallAgentMappingRead(ORMModel):
    id: UUID
    emp_key: str
    emp_number: str | None = None
    emp_name: str | None = None
    user_id: UUID
    user_name: str | None = None  # resolved in the endpoint
    created_at: datetime


# --- Per-employee daily call trend (Performance drill-down) -----------------

class CallTrendPoint(ORMModel):
    date: date
    calls: int = 0
    connected: int = 0
    missed: int = 0


class CallTrendResponse(ORMModel):
    user_id: UUID
    date_from: datetime
    date_to: datetime
    points: list[CallTrendPoint]
