"""Calls page list (GET /api/v1/calls).

Regression: the endpoint called ``pagination.offset()``, but ``PaginationParams.offset`` is a property (an
int), so every request raised TypeError → 500 and the Calls page never loaded. Covers the list itself, page
by page (newest first), and matching a call to its lead by the last 10 digits of the phone.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.database.session import db_manager
from app.models.external_call import ExternalCall

_T0 = datetime(2026, 9, 20, 10, 0, tzinfo=UTC)


async def _add_calls(*calls: dict) -> None:
    async with db_manager.session_factory() as session:
        for index, fields in enumerate(calls):
            session.add(ExternalCall(provider="callyzer", external_id=f"call-{index}", **fields))
        await session.commit()


async def _list(client, headers, **params) -> dict:
    response = await client.get("/api/v1/calls", headers=headers, params=params)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_calls_page_loads_with_no_calls(client, auth_headers):
    body = await _list(client, auth_headers)
    assert body["items"] == []
    assert body["pagination"]["total"] == 0


@pytest.mark.asyncio
async def test_calls_are_listed_newest_first_page_by_page(client, auth_headers):
    await _add_calls(*[
        {"client_number": f"+91990041000{i}", "call_type": "Outgoing", "call_at": _T0 + timedelta(minutes=i)}
        for i in range(5)
    ])
    pages = [await _list(client, auth_headers, page=page, page_size=2) for page in (1, 2, 3)]
    assert [[item["client_number"][-1] for item in page["items"]] for page in pages] == [["4", "3"], ["2", "1"], ["0"]]
    assert {page["pagination"]["total"] for page in pages} == {5}
    assert pages[0]["pagination"]["total_pages"] == 3


@pytest.mark.asyncio
async def test_calls_show_their_lead_and_filter_by_match(client, auth_headers):
    created = await client.post(
        "/api/v1/leads",
        headers=auth_headers,
        json={"title": "Enquiry", "contact_name": "Asha Roy", "contact_phone": "+91 99004 11111"},
    )
    assert created.status_code == 201, created.text
    lead = created.json()
    await _add_calls(
        {"client_number": "09900411111", "client_number_key": "9900411111", "call_at": _T0},
        {"client_number": "09900422222", "client_number_key": "9900422222", "call_at": _T0 + timedelta(minutes=1)},
    )

    items = {item["client_number"]: item for item in (await _list(client, auth_headers))["items"]}
    assert items["09900411111"]["lead"] == {
        "id": lead["id"], "lead_number": lead["lead_number"], "contact_name": "Asha Roy",
    }
    assert items["09900422222"]["lead"] is None

    matched = await _list(client, auth_headers, matched="true")
    unmatched = await _list(client, auth_headers, matched="false")
    assert [item["client_number"] for item in matched["items"]] == ["09900411111"]
    assert [item["client_number"] for item in unmatched["items"]] == ["09900422222"]
