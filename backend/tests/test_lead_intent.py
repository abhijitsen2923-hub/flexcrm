"""Lead intent (High / Medium / Low): chosen on a stage change, fixed from "Booked / Token" onward and on
closed stages, changeable from the lead details (quick set), set on create / bulk move / CSV import, kept as
a history, and searchable in the leads list (with "none" = not rated).

Where two changes can share a timestamp (SQLite's now() has 1-second resolution) the history is compared as a
set, not in order.
"""
from __future__ import annotations

import csv
import io

import pytest
import pytest_asyncio

LEADS = "/api/v1/leads"
_seq = iter(range(1, 100_000))


@pytest_asyncio.fixture
async def owner_headers(client) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/register",
        json={"first_name": "Rita", "last_name": "Owner", "email": "owner@intent.example.com",
              "password": "StrongPass123", "role": "owner", "business_type": "real_estate",
              "organization_name": "Intent Realty"},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _add_user(client, owner_headers, email: str, role: str) -> dict[str, str]:
    created = await client.post(
        "/api/v1/users", headers=owner_headers,
        json={"first_name": "Staff", "last_name": role.title(), "email": email, "password": "StrongPass123",
              "phone": f"+9199004{next(_seq):05d}", "role": role, "status": "active"},
    )
    assert created.status_code == 201, created.text
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": "StrongPass123"})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _lead(client, headers, name: str = "Asha Roy", **extra) -> dict:
    body = {"title": f"{name} enquiry", "contact_name": name, "contact_phone": f"+9199005{next(_seq):05d}", **extra}
    response = await client.post(LEADS, headers=headers, json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def _move(client, headers, lead_id: str, stage: str, intent: str | None = None, expect: int = 201) -> dict:
    body = {"to_stage_code": stage, "comment": f"Moved to {stage} after the call today."}
    if intent is not None:
        body["intent"] = intent
    response = await client.post(f"{LEADS}/{lead_id}/transitions", headers=headers, json=body)
    assert response.status_code == expect, response.text
    return response.json()


async def _get(client, headers, lead_id: str) -> dict:
    response = await client.get(LEADS, headers=headers, params={"page_size": 200})
    assert response.status_code == 200, response.text
    return next(item for item in response.json()["items"] if item["id"] == lead_id)


async def _changes(client, headers, lead_id: str) -> list[tuple]:
    response = await client.get(f"{LEADS}/{lead_id}/intent-changes", headers=headers)
    assert response.status_code == 200, response.text
    return [(c["from_intent"], c["to_intent"], c["source"]) for c in response.json()]


async def _transitions(client, headers, lead_id: str) -> list[dict]:
    response = await client.get(f"{LEADS}/{lead_id}/transitions", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()  # newest first


async def _row(client, headers, lead_id: str, stage: str) -> dict:
    """The stage-history row of the move to `stage` (found by stage, not position: same-second ties)."""
    return next(t for t in await _transitions(client, headers, lead_id) if t["to_stage_code"] == stage)


async def _set(client, headers, lead_id: str, intent: str, expect: int = 200):
    response = await client.put(f"{LEADS}/{lead_id}/intent", headers=headers, json={"intent": intent})
    assert response.status_code == expect, response.text
    return response.json()


async def _ids(client, headers, **params) -> set[str]:
    response = await client.get(LEADS, headers=headers, params={"page_size": 200, **params})
    assert response.status_code == 200, response.text
    return {item["id"] for item in response.json()["items"]}


@pytest.mark.asyncio
async def test_a_stage_change_sets_the_intent_and_records_it(client, owner_headers):
    lead = await _lead(client, owner_headers)
    assert lead["intent"] is None

    await _move(client, owner_headers, lead["id"], "call", intent="high")

    assert (await _get(client, owner_headers, lead["id"]))["intent"] == "high"
    assert (await _row(client, owner_headers, lead["id"], "call"))["intent"] == "high"
    assert await _changes(client, owner_headers, lead["id"]) == [(None, "high", "stage_change")]

    # The same intent again is not a change; a different one is.
    await _move(client, owner_headers, lead["id"], "follow_up", intent="high")
    await _move(client, owner_headers, lead["id"], "site_visit_confirmed", intent="medium")
    assert set(await _changes(client, owner_headers, lead["id"])) == {
        ("high", "medium", "stage_change"), (None, "high", "stage_change")
    }


@pytest.mark.asyncio
async def test_a_move_without_intent_keeps_the_leads_intent(client, owner_headers):
    # Older clients (a tab still open during a deploy) send no intent — nothing breaks, nothing is lost.
    lead = await _lead(client, owner_headers)
    await _move(client, owner_headers, lead["id"], "call", intent="medium")
    row = await _move(client, owner_headers, lead["id"], "follow_up")

    assert row["intent"] is None
    assert (await _get(client, owner_headers, lead["id"]))["intent"] == "medium"
    assert len(await _changes(client, owner_headers, lead["id"])) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("fixed_stage", ["booked", "not_interested", "disqualified"])
async def test_intent_is_fixed_from_booked_onward_and_on_lost_stages(client, owner_headers, fixed_stage):
    lead = await _lead(client, owner_headers)
    await _move(client, owner_headers, lead["id"], "call", intent="medium")

    row = await _move(client, owner_headers, lead["id"], fixed_stage, intent="low")

    assert row["intent"] == "medium"  # the row records the intent as it stood
    assert (await _get(client, owner_headers, lead["id"]))["intent"] == "medium"
    assert await _changes(client, owner_headers, lead["id"]) == [(None, "medium", "stage_change")]
    body = await _set(client, owner_headers, lead["id"], "high", expect=409)
    assert "can't be changed" in body["error"]["detail"]


@pytest.mark.asyncio
async def test_intent_stays_fixed_after_booked(client, owner_headers):
    lead = await _lead(client, owner_headers)
    await _move(client, owner_headers, lead["id"], "interested", intent="high")
    await _move(client, owner_headers, lead["id"], "booked")
    row = await _move(client, owner_headers, lead["id"], "agreement_payment", intent="low")

    assert row["intent"] == "high"
    assert (await _get(client, owner_headers, lead["id"]))["intent"] == "high"


@pytest.mark.asyncio
async def test_quick_set_changes_intent_without_a_stage_change(client, owner_headers):
    lead = await _lead(client, owner_headers)
    await _move(client, owner_headers, lead["id"], "call", intent="medium")
    transitions_before = len(await _transitions(client, owner_headers, lead["id"]))

    updated = await _set(client, owner_headers, lead["id"], "high")
    await _set(client, owner_headers, lead["id"], "high")  # unchanged → nothing recorded

    assert updated["intent"] == "high" and updated["stage_code"] == "call"
    assert set(await _changes(client, owner_headers, lead["id"])) == {
        ("medium", "high", "quick_set"), (None, "medium", "stage_change")
    }
    assert len(await _changes(client, owner_headers, lead["id"])) == 2
    # Not a stage change: the stage history (which feeds commission and scorecards) is untouched.
    assert len(await _transitions(client, owner_headers, lead["id"])) == transitions_before
    for bad in ("urgent", "HIGH", ""):
        await _set(client, owner_headers, lead["id"], bad, expect=422)


@pytest.mark.asyncio
async def test_quick_set_follows_lead_access_and_permissions(client, owner_headers):
    rep = await _add_user(client, owner_headers, "rep@intent.example.com", "sales_executive")
    accounts = await _add_user(client, owner_headers, "books@intent.example.com", "accounts")
    others = await _lead(client, owner_headers, "Not Yours")

    await _set(client, rep, others["id"], "high", expect=404)  # another rep's / unassigned lead: hidden
    await _set(client, accounts, others["id"], "high", expect=403)  # no LEAD_MANAGE
    response = await client.get(f"{LEADS}/{others['id']}/intent-changes", headers=rep)
    assert response.status_code == 404
    assert (await _get(client, owner_headers, others["id"]))["intent"] is None


@pytest.mark.asyncio
async def test_bulk_move_sets_every_leads_intent(client, owner_headers):
    first, second = await _lead(client, owner_headers, "One"), await _lead(client, owner_headers, "Two")
    response = await client.post(
        f"{LEADS}/bulk-transition", headers=owner_headers,
        json={"lead_ids": [first["id"], second["id"]], "to_stage_code": "follow_up",
              "comment": "Follow up after the weekend.", "intent": "high"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["updated"] == 2
    for lead in (first, second):
        assert (await _get(client, owner_headers, lead["id"]))["intent"] == "high"
        assert await _changes(client, owner_headers, lead["id"]) == [(None, "high", "bulk")]
        assert (await _row(client, owner_headers, lead["id"], "follow_up"))["intent"] == "high"


@pytest.mark.asyncio
async def test_a_new_lead_can_start_with_an_intent(client, owner_headers):
    lead = await _lead(client, owner_headers, intent="medium")

    assert lead["intent"] == "medium"
    assert (await _transitions(client, owner_headers, lead["id"]))[0]["intent"] == "medium"  # first entry
    assert await _changes(client, owner_headers, lead["id"]) == [(None, "medium", "created")]
    response = await client.post(
        LEADS, headers=owner_headers,
        json={"title": "x", "contact_name": "Bad", "contact_phone": "+919900400000", "intent": "urgent"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_leads_list_filters_by_intent(client, owner_headers):
    high = await _lead(client, owner_headers, "Hari High", intent="high")
    medium = await _lead(client, owner_headers, "Mala Medium", intent="medium")
    low = await _lead(client, owner_headers, "Lata Low", intent="low")
    unrated = await _lead(client, owner_headers, "Nina None")
    await _move(client, owner_headers, high["id"], "call", intent="high")

    assert await _ids(client, owner_headers, intent="high") == {high["id"]}
    assert await _ids(client, owner_headers, intent="high,low") == {high["id"], low["id"]}
    assert await _ids(client, owner_headers, intent="none") == {unrated["id"]}
    assert await _ids(client, owner_headers, intent=" Medium , NONE ") == {medium["id"], unrated["id"]}
    # Combined with search, stage and exact lead number.
    assert await _ids(client, owner_headers, intent="high,medium", search="Mala") == {medium["id"]}
    assert await _ids(client, owner_headers, intent="high", stage_code="new_enquiry") == set()
    assert await _ids(client, owner_headers, intent="high", stage_code="call") == {high["id"]}
    assert await _ids(client, owner_headers, intent="low", search=str(low["lead_number"])) == {low["id"]}
    assert await _ids(client, owner_headers) == {high["id"], medium["id"], low["id"], unrated["id"]}

    response = await client.get(LEADS, headers=owner_headers, params={"intent": "urgent"})
    assert response.status_code == 422
    assert "use high, medium, low or none" in response.json()["error"]["detail"]


@pytest.mark.asyncio
async def test_rep_sees_only_their_own_leads_when_filtering_by_intent(client, owner_headers):
    rep = await _add_user(client, owner_headers, "rep2@intent.example.com", "sales_executive")
    rep_id = next(
        u["id"] for u in (await client.get("/api/v1/users", headers=owner_headers)).json()["items"]
        if u["email"] == "rep2@intent.example.com"
    )
    mine = await _lead(client, owner_headers, "Mine", intent="high", assigned_to_id=rep_id)
    await _lead(client, owner_headers, "Theirs", intent="high")

    assert await _ids(client, rep, intent="high") == {mine["id"]}


@pytest.mark.asyncio
async def test_csv_import_reads_intent_and_export_writes_it(client, owner_headers):
    rows = [
        "Title,Contact name,Phone,Intent,Stage",
        f"A,Anil,+9199006{next(_seq):05d},High,",
        f"B,Bela,+9199006{next(_seq):05d}, low ,Follow-up",
        f"C,Chitra,+9199006{next(_seq):05d},,",
        f"D,Dev,+9199006{next(_seq):05d},Maybe,",
        f"E,Esha,+9199006{next(_seq):05d},Warm,",
    ]
    response = await client.post(
        f"{LEADS}/import", headers=owner_headers,
        files={"file": ("leads.csv", io.BytesIO(("\n".join(rows) + "\n").encode()), "text/csv")},
    )
    assert response.status_code == 200, response.text
    summary = response.json()
    # A sheet's own "Intent" column with other values never fails the row: imported, not rated, and said so.
    assert summary["created"] == 5
    [warning] = summary["errors"]
    assert warning["row"] == 5 and "'Maybe' isn't High, Medium or Low — the lead was imported without an intent" in warning["error"]

    listed = (await client.get(LEADS, headers=owner_headers, params={"page_size": 200})).json()["items"]
    by_name = {item["contact_name"]: item for item in listed}
    assert [by_name[n]["intent"] for n in ("Anil", "Bela", "Chitra", "Dev", "Esha")] == ["high", "low", None, None, "medium"]
    assert by_name["Bela"]["stage_code"] == "follow_up"
    assert (await _row(client, owner_headers, by_name["Bela"]["id"], "follow_up"))["intent"] == "low"
    assert await _changes(client, owner_headers, by_name["Anil"]["id"]) == [(None, "high", "import")]

    exported = await client.get("/api/v1/exports/leads.csv", headers=owner_headers)
    assert exported.status_code == 200, exported.text
    table = list(csv.DictReader(io.StringIO(exported.text)))
    assert {r["Contact name"]: r["Intent"] for r in table} == {
        "Anil": "High", "Bela": "Low", "Chitra": "", "Dev": "", "Esha": "Medium"
    }

    template = await client.get(f"{LEADS}/import/template.csv", headers=owner_headers)
    assert "Intent" in template.text.splitlines()[0]
