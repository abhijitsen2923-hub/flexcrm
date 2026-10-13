"""Leads list — "Assigned today / yesterday" (assigned_from / assigned_to on Lead.assigned_at).

Owners and managers check, at end of day or the next morning, the leads handed to someone that day and how
far each got. `assigned_at` is when the lead was given to its CURRENT owner: set on create-with-owner,
reassign, bulk reassign and the Booked / Token salesperson pick; unchanged when the same owner is picked
again; cleared when unassigned. The client sends local-day UTC bounds, half-open (SQLite keeps wall clock).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy import update

from app.database.session import db_manager
from app.models.lead import Lead

LEADS = "/api/v1/leads"
_seq = iter(range(1, 100_000))
# 10 Oct 2026 in IST (UTC+05:30) as the client sends it: [2026-10-09T18:30Z, 2026-10-10T18:30Z).
IST_OCT_10 = {"assigned_from": "2026-10-09T18:30:00Z", "assigned_to": "2026-10-10T18:30:00Z"}


@pytest_asyncio.fixture
async def org(client) -> dict:
    reg = await client.post(
        "/api/v1/auth/register",
        json={"first_name": "Rita", "last_name": "Owner", "email": "owner@assigned.example.com",
              "password": "StrongPass123", "role": "owner", "business_type": "real_estate",
              "organization_name": "Assigned Realty"},
    )
    assert reg.status_code == 201, reg.text
    owner = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    reps = {}
    for name in ("rinku", "sonu"):
        email = f"{name}@assigned.example.com"
        created = await client.post(
            "/api/v1/users", headers=owner,
            json={"first_name": name.title(), "last_name": "Rep", "email": email, "password": "StrongPass123",
                  "phone": f"+9199007{next(_seq):05d}", "role": "sales_executive", "status": "active"},
        )
        assert created.status_code == 201, created.text
        login = await client.post("/api/v1/auth/login", json={"email": email, "password": "StrongPass123"})
        reps[name] = {"id": created.json()["id"], "headers": {"Authorization": f"Bearer {login.json()['access_token']}"}}
    users = (await client.get("/api/v1/users", headers=owner)).json()["items"]
    owner_id = next(u["id"] for u in users if u["email"] == "owner@assigned.example.com")
    return {"owner": owner, "owner_id": owner_id, "reps": reps}


async def _lead(client, headers, owner_id: str | None = None, name: str = "Asha Roy") -> dict:
    body = {"title": f"{name} enquiry", "contact_name": name, "contact_phone": f"+9199008{next(_seq):05d}"}
    if owner_id:
        body["assigned_to_id"] = owner_id
    response = await client.post(LEADS, headers=headers, json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def _get(client, headers, lead_id: str) -> dict:
    response = await client.get(LEADS, headers=headers, params={"page_size": 200})
    assert response.status_code == 200, response.text
    return next(item for item in response.json()["items"] if item["id"] == lead_id)


async def _ids(client, headers, **params) -> list[str]:
    response = await client.get(LEADS, headers=headers, params={"page_size": 200, **params})
    assert response.status_code == 200, response.text
    return [item["id"] for item in response.json()["items"]]


async def _set_assigned_at(lead_id: str, when: datetime | None) -> None:
    async with db_manager.session_factory() as session:
        await session.execute(update(Lead).where(Lead.id == UUID(lead_id)).values(assigned_at=when))
        await session.commit()


async def _reassign(client, headers, lead_id: str, owner_id: str | None) -> dict:
    response = await client.put(f"{LEADS}/{lead_id}", headers=headers, json={"assigned_to_id": owner_id})
    assert response.status_code == 200, response.text
    return response.json()


def _at(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


@pytest.mark.asyncio
async def test_created_with_an_owner_is_assigned_now_without_one_is_not(client, org):
    owned = await _lead(client, org["owner"], org["reps"]["rinku"]["id"])
    unowned = await _lead(client, org["owner"])

    assert owned["assigned_at"] is not None
    assert unowned["assigned_at"] is None


@pytest.mark.asyncio
async def test_reassign_moves_the_date_same_owner_keeps_it_unassign_clears_it(client, org):
    rinku, sonu = org["reps"]["rinku"]["id"], org["reps"]["sonu"]["id"]
    lead = await _lead(client, org["owner"], rinku)
    old = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
    await _set_assigned_at(lead["id"], old)

    same = await _reassign(client, org["owner"], lead["id"], rinku)
    assert _at(same["assigned_at"]).replace(tzinfo=UTC) == old  # the same owner picked again: unchanged

    moved = await _reassign(client, org["owner"], lead["id"], sonu)
    assert _at(moved["assigned_at"]).replace(tzinfo=UTC) > old  # a fresh lead for Sonu

    cleared = await _reassign(client, org["owner"], lead["id"], None)
    assert cleared["assigned_at"] is None


@pytest.mark.asyncio
async def test_bulk_reassign_stamps_only_the_leads_that_change_hands(client, org):
    rinku, sonu = org["reps"]["rinku"]["id"], org["reps"]["sonu"]["id"]
    already_sonus = await _lead(client, org["owner"], sonu, "Already Sonu")
    from_rinku = await _lead(client, org["owner"], rinku, "From Rinku")
    unassigned = await _lead(client, org["owner"], None, "Unassigned")
    old = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
    for lead in (already_sonus, from_rinku):
        await _set_assigned_at(lead["id"], old)

    response = await client.post(
        f"{LEADS}/bulk-reassign", headers=org["owner"],
        json={"lead_ids": [already_sonus["id"], from_rinku["id"], unassigned["id"]], "assigned_to_id": sonu},
    )
    assert response.status_code == 200, response.text

    assert _at((await _get(client, org["owner"], already_sonus["id"]))["assigned_at"]).replace(tzinfo=UTC) == old
    assert _at((await _get(client, org["owner"], from_rinku["id"]))["assigned_at"]).replace(tzinfo=UTC) > old
    assert (await _get(client, org["owner"], unassigned["id"]))["assigned_at"] is not None


@pytest.mark.asyncio
async def test_booking_salesperson_pick_is_a_fresh_assignment(client, org):
    rinku = org["reps"]["rinku"]["id"]
    created = await client.post(
        "/api/v1/inventory/projects/full", headers=org["owner"],
        json={"name": "Heritage", "builder_name": "B", "location": "L", "city": "C",
              "towers": [{"name": "A", "total_floors": 1,
                          "unit_specs": [{"floors": [{"floor": 1, "count": 1}], "area": 1000, "base_price": 3500000}]}]},
    )
    assert created.status_code == 201, created.text
    unit_id = created.json()["towers"][0]["units"][0]["id"]
    lead = await _lead(client, org["owner"], org["owner_id"])
    old = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
    await _set_assigned_at(lead["id"], old)

    response = await client.post(
        f"{LEADS}/{lead['id']}/transitions", headers=org["owner"],
        json={"to_stage_code": "booked", "comment": "Token received for unit A-101.", "assigned_to_id": rinku,
              "booking": {"unit_id": unit_id, "token_amount": 11000, "token_mode": "neft",
                          "token_received_on": "2026-10-10"}},
    )
    assert response.status_code == 201, response.text

    after = await _get(client, org["owner"], lead["id"])
    assert after["assigned_to_id"] == rinku
    assert _at(after["assigned_at"]).replace(tzinfo=UTC) > old


@pytest.mark.asyncio
async def test_assigned_day_filter_bounds_combinations_and_order(client, org):
    rinku, sonu = org["reps"]["rinku"]["id"], org["reps"]["sonu"]["id"]
    morning = await _lead(client, org["owner"], rinku, "Morning")
    evening = await _lead(client, org["owner"], sonu, "Evening")
    next_day = await _lead(client, org["owner"], rinku, "Next Day")
    day_before = await _lead(client, org["owner"], rinku, "Day Before")
    unassigned = await _lead(client, org["owner"], None, "Unassigned")
    await _set_assigned_at(morning["id"], datetime(2026, 10, 10, 4, 30, tzinfo=UTC))      # 10:00 IST
    await _set_assigned_at(evening["id"], datetime(2026, 10, 10, 18, 29, tzinfo=UTC))     # 23:59 IST
    await _set_assigned_at(next_day["id"], datetime(2026, 10, 10, 18, 30, tzinfo=UTC))    # 00:00 IST 11 Oct
    await _set_assigned_at(day_before["id"], datetime(2026, 10, 9, 18, 29, tzinfo=UTC))   # 23:59 IST 9 Oct
    await _set_assigned_at(unassigned["id"], datetime(2026, 10, 10, 6, 0, tzinfo=UTC))    # stale stamp, no owner

    # Newest assignment first (sort_by=assigned_at), only the 10th, never an unassigned lead.
    assert await _ids(client, org["owner"], sort_by="assigned_at", sort_order="desc", **IST_OCT_10) == [
        evening["id"], morning["id"]
    ]
    # Combines with the owner filter, stage and search.
    assert await _ids(client, org["owner"], assigned_to_id=rinku, **IST_OCT_10) == [morning["id"]]
    assert await _ids(client, org["owner"], stage_code="call", **IST_OCT_10) == []
    assert await _ids(client, org["owner"], search="Evening", **IST_OCT_10) == [evening["id"]]
    # Open-ended bounds.
    assert set(await _ids(client, org["owner"], assigned_from="2026-10-10T18:30:00Z")) == {next_day["id"]}


@pytest.mark.asyncio
async def test_a_rep_sees_only_their_own_assignments(client, org):
    rinku, sonu = org["reps"]["rinku"], org["reps"]["sonu"]
    mine = await _lead(client, org["owner"], rinku["id"], "Mine")
    theirs = await _lead(client, org["owner"], sonu["id"], "Theirs")
    for lead in (mine, theirs):
        await _set_assigned_at(lead["id"], datetime(2026, 10, 10, 5, 0, tzinfo=UTC))

    assert await _ids(client, rinku["headers"], **IST_OCT_10) == [mine["id"]]
    # Even asking for someone else's leads only returns their own.
    assert await _ids(client, rinku["headers"], assigned_to_id=sonu["id"], **IST_OCT_10) == [mine["id"]]


@pytest.mark.asyncio
async def test_assigned_today_finds_a_lead_assigned_just_now(client, org):
    lead = await _lead(client, org["owner"], None, "Fresh")
    await _reassign(client, org["owner"], lead["id"], org["reps"]["rinku"]["id"])
    now = datetime.now(UTC)
    window = {"assigned_from": (now - timedelta(hours=1)).isoformat(), "assigned_to": (now + timedelta(hours=1)).isoformat()}

    assert await _ids(client, org["owner"], **window) == [lead["id"]]


@pytest.mark.asyncio
async def test_a_bulk_hand_off_pages_through_without_repeats_or_gaps(client, org):
    # Leads reassigned in one bulk action share one assigned_at: paging must still show each exactly once.
    leads = [await _lead(client, org["owner"], None, f"Batch {i:02d}") for i in range(7)]
    response = await client.post(
        f"{LEADS}/bulk-reassign", headers=org["owner"],
        json={"lead_ids": [lead["id"] for lead in leads], "assigned_to_id": org["reps"]["sonu"]["id"]},
    )
    assert response.status_code == 200, response.text
    now = datetime.now(UTC)
    window = {"assigned_from": (now - timedelta(hours=1)).isoformat(), "assigned_to": (now + timedelta(hours=1)).isoformat()}

    seen: list[str] = []
    for page in (1, 2, 3):
        response = await client.get(
            LEADS, headers=org["owner"],
            params={"page": page, "page_size": 3, "sort_by": "assigned_at", "sort_order": "desc", **window},
        )
        assert response.status_code == 200, response.text
        seen += [item["id"] for item in response.json()["items"]]
    assert sorted(seen) == sorted(lead["id"] for lead in leads)
