"""CSV import behaves as ONE bulk operation.

Reported: uploading the template sheet made the screen flicker and freeze and showed errors. Each row fired
its own realtime event and reporting-cache wipe (every open Leads page / Dashboard in the org refetched
every ~2.5 s for the whole import), checked duplicates with a full-table scan per row, and reported some row
problems as raw technical text. Covers: one event + one cache wipe per import, one assignee notification,
blank rows, readable row errors, stage checks before a lead is created, row numbers for chunked uploads,
duplicates found in one lookup, and the fixed rate-limit window.
"""
from __future__ import annotations

import asyncio
import io
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.exc import IntegrityError

from app.core.cache import CacheClient, InMemoryCache, cache_client
from app.database.session import db_manager
from app.models.lead import Lead
from app.models.notification import Notification
from app.repositories.leads import LeadRepository
from app.services.bulk_scope import bulk_side_effects
from app.services.realtime import realtime_manager
from app.services.stage_transitions import StageTransitionService

_seq = iter(range(1, 100_000))


def _phone() -> str:
    return f"+9199006{next(_seq):05d}"


def _csv(header: str, rows: list[str]) -> bytes:
    return ("\n".join([header, *rows]) + "\n").encode("utf-8")


async def _import(client, headers, payload: bytes, **params) -> dict:
    response = await client.post(
        "/api/v1/leads/import", headers=headers, params=params,
        files={"file": ("leads.csv", io.BytesIO(payload), "text/csv")},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _lead_count() -> int:
    async with db_manager.session_factory() as session:
        return (await session.execute(select(func.count()).select_from(Lead).where(Lead.is_deleted.is_(False)))).scalar_one()


@pytest.fixture
def sent(monkeypatch) -> list[dict]:
    """Every envelope actually fanned out to sockets."""
    envelopes: list[dict] = []
    real = realtime_manager._fan_out

    async def _spy(sockets, envelope):
        envelopes.append(envelope)
        await real(sockets, envelope)

    monkeypatch.setattr(realtime_manager, "_fan_out", _spy)
    return envelopes


@pytest.fixture
def purges(monkeypatch) -> list[str]:
    calls: list[str] = []
    real = cache_client.delete_pattern

    async def _spy(prefix):
        calls.append(prefix)
        await real(prefix)

    monkeypatch.setattr(cache_client, "delete_pattern", _spy)
    return calls


# ---- one event + one cache wipe per import --------------------------------------------------------------

@pytest.mark.asyncio
async def test_an_import_sends_one_event_per_kind_and_wipes_the_cache_once(client, auth_headers, sent, purges):
    rows = [f"P{i},{_phone()},Lead {i},{'Qualified' if i < 2 else ''}" for i in range(5)]
    summary = await _import(client, auth_headers, _csv("contact_name,contact_phone,title,stage", rows))
    assert summary["created"] == 5 and summary["errors"] == []

    events = [(e["event"], e["payload"]) for e in sent if e["event"].startswith("lead.")]
    assert sorted(name for name, _ in events) == ["lead.created", "lead.stage_changed"]
    payloads = dict(events)
    assert payloads["lead.created"] == {"bulk": True, "count": 5}
    assert payloads["lead.stage_changed"]["bulk"] is True and payloads["lead.stage_changed"]["count"] == 2
    assert sorted(purges) == ["analytics:", "dashboard:"]


@pytest.mark.asyncio
async def test_a_single_new_lead_still_announces_itself_immediately(client, auth_headers, sent, purges):
    response = await client.post(
        "/api/v1/leads", headers=auth_headers, json={"title": "One", "contact_name": "Asha", "contact_phone": _phone()}
    )
    assert response.status_code == 201
    created = [e for e in sent if e["event"] == "lead.created"]
    assert len(created) == 1 and created[0]["payload"]["id"] == response.json()["id"]
    assert sorted(purges) == ["analytics:", "dashboard:"]


@pytest.mark.asyncio
async def test_bulk_scope_flushes_on_error_and_leaves_other_tasks_alone(sent, purges):
    from app.services.base import ServiceBase

    org = uuid4()
    other_task_may_send = asyncio.Event()

    async def _other_request():
        await other_task_may_send.wait()
        await realtime_manager.broadcast({"event": "lead.updated", "payload": {"id": "x"}}, org_id=org)

    other = asyncio.create_task(_other_request())  # its own context, like a concurrent request
    with pytest.raises(RuntimeError):
        async with bulk_side_effects():
            await realtime_manager.broadcast({"event": "lead.created", "payload": {"id": "1"}}, org_id=org)
            await realtime_manager.broadcast({"event": "lead.created", "payload": {"id": "2"}}, org_id=org)
            await ServiceBase(None).invalidate_reporting_cache()
            other_task_may_send.set()
            await other
            assert [e["event"] for e in sent] == ["lead.updated"]  # the other task wasn't held back
            assert purges == []
            raise RuntimeError("row 3 blew up")
    # Rows committed before the failure still get their (merged) event and cache wipe.
    assert [(e["event"], e["payload"]) for e in sent] == [
        ("lead.updated", {"id": "x"}), ("lead.created", {"bulk": True, "count": 2}),
    ]
    assert sorted(purges) == ["analytics:", "dashboard:"]


# ---- notifications ------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_an_assignee_gets_one_summary_notification(client, auth_headers, sales_headers):
    rows = [f"P{i},{_phone()},Lead {i},sales@example.com" for i in range(3)]
    summary = await _import(client, auth_headers, _csv("contact_name,contact_phone,title,owner_email", rows))
    assert summary["created"] == 3
    async with db_manager.session_factory() as session:
        messages = list((await session.execute(select(Notification.message))).scalars())
    assert messages == ["3 leads assigned to you (CSV import)."]


# ---- rows ---------------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_blank_rows_are_skipped_and_row_numbers_still_match_the_sheet(client, auth_headers):
    payload = _csv("contact_name,contact_phone,title", [f"Asha,{_phone()},A", ",,", " , , ", "Bina,,B"])
    summary = await _import(client, auth_headers, payload)
    assert summary["created"] == 1
    assert summary["errors"] == [{"row": 5, "error": "Phone is required."}]  # sheet row 5, blanks counted


@pytest.mark.asyncio
async def test_row_errors_are_plain_sentences(client, auth_headers):
    payload = _csv("contact_name,contact_phone,contact_email,title", [f"Asha,{_phone()},not-an-email,A"])
    summary = await _import(client, auth_headers, payload)
    assert summary["created"] == 0
    [error] = summary["errors"]
    assert error["row"] == 2
    assert error["error"].startswith("Email:"), error
    assert "LeadCreate" not in error["error"] and "validation error" not in error["error"]


@pytest.mark.asyncio
async def test_a_database_error_on_one_row_is_a_plain_message_and_the_rest_import(client, auth_headers, monkeypatch):
    real_create = LeadRepository.create
    calls = {"n": 0}

    async def _flaky(self, payload):
        calls["n"] += 1
        if calls["n"] == 1:
            raise IntegrityError("INSERT INTO leads ...", {}, Exception("duplicate key value violates unique constraint"))
        return await real_create(self, payload)

    monkeypatch.setattr(LeadRepository, "create", _flaky)
    payload = _csv("contact_name,contact_phone,title", [f"Asha,{_phone()},A", f"Bina,{_phone()},B"])
    summary = await _import(client, auth_headers, payload)
    assert summary["created"] == 1
    [error] = summary["errors"]
    assert error["row"] == 2
    assert "INSERT" not in error["error"] and "[SQL" not in error["error"] and "duplicate key" not in error["error"]
    assert error["error"].startswith("Couldn't save this row")


@pytest.mark.asyncio
async def test_amounts_the_column_cannot_hold_are_labelled_row_errors(client, auth_headers):
    rows = [f"Asha,{_phone()},A,99999999999", f"Bina,{_phone()},B,NaN", f"Chitra,{_phone()},C,9999999999.99"]
    summary = await _import(client, auth_headers, _csv("contact_name,contact_phone,title,value", rows))
    assert summary["created"] == 1  # the largest value that fits Numeric(12, 2)
    assert summary["errors"] == [
        {"row": 2, "error": "Value '99999999999' is too large."},
        {"row": 3, "error": "Value 'NaN' is not a valid number."},
    ]


@pytest.mark.asyncio
async def test_an_unknown_stage_creates_no_lead(client, auth_headers):
    before = await _lead_count()
    summary = await _import(client, auth_headers, _csv("contact_name,contact_phone,title,stage", [f"Asha,{_phone()},A,Nonsense"]))
    assert summary["created"] == 0 and summary["errors"][0]["row"] == 2
    assert "Stage 'Nonsense' is not valid" in summary["errors"][0]["error"]
    assert await _lead_count() == before


@pytest.mark.asyncio
async def test_a_stage_the_role_cannot_set_creates_no_lead(client):
    owner = await client.post(
        "/api/v1/auth/register",
        json={"first_name": "Rita", "last_name": "Owner", "email": "owner@bulk.example.com", "password": "StrongPass123",
              "role": "owner", "business_type": "real_estate", "organization_name": "Bulk Realty"},
    )
    owner_headers = {"Authorization": f"Bearer {owner.json()['access_token']}"}
    created = await client.post(
        "/api/v1/users", headers=owner_headers,
        json={"first_name": "Rinku", "last_name": "Kayal", "email": "rep@bulk.example.com", "password": "StrongPass123",
              "phone": "+919900699999", "role": "sales_executive", "status": "active"},
    )
    assert created.status_code == 201, created.text
    login = await client.post("/api/v1/auth/login", json={"email": "rep@bulk.example.com", "password": "StrongPass123"})
    rep_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    before = await _lead_count()
    summary = await _import(client, rep_headers, _csv("contact_name,contact_phone,title,stage", [f"Asha,{_phone()},A,sold"]))
    assert summary["created"] == 0
    assert summary["errors"][0]["error"].startswith("Stage: your role can't set")
    assert await _lead_count() == before


@pytest.mark.asyncio
async def test_a_stage_that_fails_after_the_lead_is_saved_counts_the_lead(client, auth_headers, monkeypatch):
    from app.core.exceptions import ValidationError

    async def _refuse(self, *args, **kwargs):
        raise ValidationError("Booking details are required for this stage.")

    monkeypatch.setattr(StageTransitionService, "create_transition", _refuse)
    summary = await _import(client, auth_headers, _csv("contact_name,contact_phone,title,stage", [f"Asha,{_phone()},A,Qualified"]))
    assert summary["created"] == 1
    [warning] = summary["errors"]
    assert "was created at the first stage" in warning["error"] and "Booking details are required" in warning["error"]


@pytest.mark.asyncio
async def test_row_numbers_follow_the_chunk_offset(client, auth_headers):
    summary = await _import(client, auth_headers, _csv("contact_name,contact_phone,title", ["Asha,,A"]), row_offset=100)
    assert summary["errors"] == [{"row": 102, "error": "Phone is required."}]


# ---- duplicates -----------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_duplicates_inside_the_file_are_still_caught(client, auth_headers):
    phone = _phone()
    summary = await _import(
        client, auth_headers, _csv("contact_name,contact_phone,title", [f"Asha,{phone},A", f"Asha again,{phone},B"]),
        skip_duplicates="true",
    )
    assert summary["created"] == 1 and summary["skipped"] == 1
    [dup] = summary["duplicates"]
    assert dup["row"] == 3 and dup["matched"].startswith("#") and dup["skipped"] is True


@pytest.mark.asyncio
async def test_existing_leads_are_matched_with_one_lookup_for_the_whole_file(client, auth_headers):
    existing = _phone()
    first = await client.post(
        "/api/v1/leads", headers=auth_headers, json={"title": "Old", "contact_name": "Old", "contact_phone": existing}
    )
    number = first.json()["lead_number"]
    statements: list[str] = []

    def _record(_conn, _cursor, statement, *_args):
        statements.append(statement)

    engine = db_manager.engine.sync_engine
    event.listen(engine, "before_cursor_execute", _record)
    try:
        rows = [f"P{i},{_phone()},Lead {i}" for i in range(30)] + [f"Dup,{existing},Dup"]
        summary = await _import(client, auth_headers, _csv("contact_name,contact_phone,title", rows), skip_duplicates="true")
    finally:
        event.remove(engine, "before_cursor_execute", _record)
    assert summary["created"] == 30 and summary["skipped"] == 1
    assert summary["duplicates"][0]["matched"] == f"#{number}"
    assert sum("regexp_replace" in s for s in statements) == 1


# ---- rate limiter window ---------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rate_limit_window_is_fixed_in_memory():
    cache = InMemoryCache()
    assert await cache.increment("k", ttl_seconds=60) == 1
    first_expiry = cache._store["k"][1]
    assert await cache.increment("k", ttl_seconds=60) == 2
    assert cache._store["k"][1] == first_expiry  # later hits don't push the window out
    cache._store["k"] = (7, datetime(2000, 1, 1, tzinfo=UTC))  # expired window
    assert await cache.increment("k", ttl_seconds=60) == 1


@pytest.mark.asyncio
async def test_rate_limit_window_is_fixed_in_redis():
    calls: list[tuple] = []

    class _Pipeline:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        def set(self, key, value, ex=None, nx=False):
            calls.append(("set", key, value, ex, nx))

        def incr(self, key):
            calls.append(("incr", key))

        def expire(self, key, ttl):
            calls.append(("expire", key, ttl))

        async def execute(self):
            return [None, 5]

    class _Redis:
        def pipeline(self, transaction=True):
            return _Pipeline()

    client = CacheClient()
    client._redis = _Redis()
    assert await client.increment("ratelimit:ip:/x", ttl_seconds=60) == 5
    assert calls == [("set", "ratelimit:ip:/x", 0, 60, True), ("incr", "ratelimit:ip:/x")]
