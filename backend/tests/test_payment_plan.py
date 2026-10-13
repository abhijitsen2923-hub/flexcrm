"""Project payment plan → each booking's demands (app/real_estate/payment_plan.py, t048).

A booking takes its project's plan (its own copy) and gets a demand per milestone due on booking / N days after /
a date — a % of the booking's price (box price + GST; the unit's base price until pricing is saved). Stage,
possession and registration milestones stay pending until the builder marks them reached (whole project or per
tower) or raises one on a booking. Demands follow the price until money is paid or an invoice is raised on them;
one demand per (booking, milestone) — raising twice never double-bills; undo removes only untouched demands.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database.session import db_manager
from app.real_estate import payment_plan as payment_plan_module
from app.real_estate.models import Booking, PaymentSchedule, Unit
from app.real_estate.payment_plan import plan_base, reached_on_for

API = "/api/v1"
TODAY = date.today()

PLAN = [
    {"key": "bk", "label": "Booking amount", "percent": 10, "due_on": "on_booking"},
    {"key": "agr", "label": "Agreement", "percent": 20, "due_on": "days_after_booking", "days": 30},
    {"key": "fix", "label": "Plinth (fixed date)", "percent": 15, "due_on": "on_date", "due_date": "2027-03-31"},
    {"key": "fnd", "label": "Foundation complete", "percent": 15, "due_on": "on_stage"},
    {"key": "pos", "label": "Possession", "percent": 30, "due_on": "on_possession"},
    {"key": "reg", "label": "Registration", "percent": 10, "due_on": "on_registration"},
]
EVENT_KEYS = {"fnd", "pos", "reg"}

# boxPrice + GST = 63,00,000 — stamp duty and registration are NOT part of the plan's base.
SNAPSHOT = {
    "boxPrice": 6_000_000, "gstRate": 5, "gstAmount": 300_000,
    "stampDutyRate": 6, "stampDutyAmount": 360_000, "registrationRate": 1, "registrationAmount": 60_000,
    "subtotal": 6_000_000, "total": 6_720_000, "lineItems": [],
}


@pytest_asyncio.fixture
async def owner_headers(client) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "Riya", "last_name": "Builder", "email": "owner@plan.example.com",
            "password": "StrongPass123", "phone": "+1555000201", "role": "owner",
            "business_type": "real_estate", "organization_name": "Plan Realty",
        },
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _flats(floors: int, per_floor: int, price: int) -> dict:
    return {
        "unit_type": "residential",
        "floors": [{"floor": f, "count": per_floor} for f in range(1, floors + 1)],
        "area": 1200,
        "base_price": price,
    }


async def _project(client, headers, name: str = "Skyline", plan: list | None = PLAN, **details) -> dict:
    """Tower A: 2 floors × 2 flats at ₹50L; Tower B: 1 floor × 2 flats at ₹40L. The plan is saved by Edit."""
    body = {
        "name": name, "builder_name": "Acme", "location": "Salt Lake", "city": "Kolkata", **details,
        "towers": [
            {"name": "Tower A", "total_floors": 2, "unit_specs": [_flats(2, 2, 5_000_000)]},
            {"name": "Tower B", "total_floors": 1, "unit_specs": [_flats(1, 2, 4_000_000)]},
        ],
        "parking": {},
    }
    created = await client.post(f"{API}/inventory/projects/full", headers=headers, json=body)
    assert created.status_code == 201, created.text
    project = created.json()
    if plan is not None:
        patched = await client.patch(
            f"{API}/inventory/projects/{project['id']}", headers=headers, json={"payment_plan": plan}
        )
        assert patched.status_code == 200, patched.text
    towers = {t["name"]: t for t in project["towers"]}
    return {
        "id": project["id"],
        "towers": {name: t["id"] for name, t in towers.items()},
        "units": {name: sorted((u["id"] for u in t["units"]), key=str) for name, t in towers.items()},
    }


async def _book(client, headers, unit_id: str) -> dict:
    response = await client.post(f"{API}/bookings", headers=headers, json={"unit_id": unit_id})
    assert response.status_code == 201, response.text
    return response.json()


async def _booking(client, headers, booking_id: str) -> dict:
    response = await client.get(f"{API}/bookings/{booking_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _rows(booking: dict) -> dict[str, dict]:
    return {r["milestone_key"]: r for r in booking["payment_schedules"] if r["milestone_key"]}


def _amount(row: dict) -> Decimal:
    return Decimal(str(row["demand_amount"]))


async def _confirm(client, headers, booking_id: str) -> None:
    response = await client.post(f"{API}/bookings/{booking_id}/step/4", headers=headers, json={"confirm": True})
    assert response.status_code == 200, response.text


async def _mark(client, headers, project_id: str, key: str, reached_on: str = "2026-10-01", tower_ids=None,
                expect: int = 200) -> dict:
    body: dict = {"reached_on": reached_on}
    if tower_ids is not None:
        body["tower_ids"] = tower_ids
    response = await client.post(
        f"{API}/inventory/projects/{project_id}/payment-plan/{key}/reached", headers=headers, json=body
    )
    assert response.status_code == expect, response.text
    return response.json()


async def _undo(client, headers, project_id: str, key: str, tower_id: str | None = None, expect: int = 200) -> dict:
    params = {"tower_id": tower_id} if tower_id else None
    response = await client.delete(
        f"{API}/inventory/projects/{project_id}/payment-plan/{key}/reached", headers=headers, params=params
    )
    assert response.status_code == expect, response.text
    return response.json()


async def _pay(client, headers, booking_id: str, schedule_id: str, amount: int = 1000) -> None:
    response = await client.post(
        f"{API}/bookings/{booking_id}/payments", headers=headers,
        json={"schedule_id": schedule_id, "amount": amount, "paid_on": TODAY.isoformat(), "mode": "neft"},
    )
    assert response.status_code == 200, response.text


async def _invoice(client, headers, booking_id: str, schedule_id: str) -> None:
    response = await client.post(
        f"{API}/bookings/{booking_id}/invoices", headers=headers, json={"schedule_id": schedule_id}
    )
    assert response.status_code == 201, response.text


# ---------------------------------------------------------------------------
# A booking takes the plan
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_new_booking_gets_dated_demands_and_leaves_event_milestones_pending(client, owner_headers):
    project = await _project(client, owner_headers)
    booking = await _book(client, owner_headers, project["units"]["Tower A"][0])

    assert [m["key"] for m in booking["payment_plan"]] == [m["key"] for m in PLAN]
    rows = _rows(booking)
    assert set(rows) == {"bk", "agr", "fix"}  # stage / possession / registration wait until reached
    assert len(booking["payment_schedules"]) == 3
    # % of the unit's base price (₹50L) until the booking's price is worked out.
    assert {k: _amount(r) for k, r in rows.items()} == {
        "bk": Decimal("500000.00"), "agr": Decimal("1000000.00"), "fix": Decimal("750000.00"),
    }
    assert rows["bk"]["due_date"] == TODAY.isoformat()
    assert rows["agr"]["due_date"] == (TODAY + timedelta(days=30)).isoformat()
    assert rows["fix"]["due_date"] == "2027-03-31"
    assert rows["agr"]["installment_name"] == "Agreement"
    assert {k: Decimal(str(r["percent"])) for k, r in rows.items()} == {
        "bk": Decimal(10), "agr": Decimal(20), "fix": Decimal(15),
    }
    for row in rows.values():
        assert Decimal(str(row["outstanding"])) == _amount(row)
        assert Decimal(str(row["paid_amount"])) == 0


@pytest.mark.asyncio
async def test_booking_keeps_its_own_copy_when_the_project_plan_changes(client, owner_headers):
    project = await _project(client, owner_headers)
    booking = await _book(client, owner_headers, project["units"]["Tower A"][0])
    new_plan = [{"key": "all", "label": "Everything", "percent": 100, "due_on": "on_booking"}]
    patched = await client.patch(
        f"{API}/inventory/projects/{project['id']}", headers=owner_headers, json={"payment_plan": new_plan}
    )
    assert patched.status_code == 200, patched.text

    again = await _booking(client, owner_headers, booking["id"])
    assert [m["key"] for m in again["payment_plan"]] == [m["key"] for m in PLAN]
    later = await _book(client, owner_headers, project["units"]["Tower A"][1])
    assert set(_rows(later)) == {"all"}
    assert _amount(_rows(later)["all"]) == Decimal("5000000.00")


@pytest.mark.asyncio
async def test_legacy_demand_schedule_project_is_unchanged(client, owner_headers):
    project = await _project(
        client, owner_headers, plan=None,
        demand_schedule=[{"label": "On booking", "percent": 25, "due_date": "2027-01-10"}],
    )
    booking = await _book(client, owner_headers, project["units"]["Tower A"][0])

    assert booking["payment_plan"] is None
    [row] = booking["payment_schedules"]
    assert (row["installment_name"], row["due_date"]) == ("On booking", "2027-01-10")
    assert _amount(row) == Decimal("1250000.00")
    assert row["milestone_key"] is None and row["percent"] is None
    # A legacy row has no % — a price save leaves it alone.
    priced = await client.put(
        f"{API}/bookings/{booking['id']}/pricing", headers=owner_headers, json={"pricing_snapshot": SNAPSHOT}
    )
    assert priced.status_code == 200, priced.text
    assert _amount(priced.json()["payment_schedules"][0]) == Decimal("1250000.00")


@pytest.mark.asyncio
async def test_project_without_any_plan_gives_no_demands(client, owner_headers):
    project = await _project(client, owner_headers, plan=None)
    booking = await _book(client, owner_headers, project["units"]["Tower A"][0])
    assert booking["payment_plan"] is None
    assert booking["payment_schedules"] == []


@pytest.mark.asyncio
async def test_stage_transition_booking_gets_the_plan(client, owner_headers):
    project = await _project(client, owner_headers)
    lead = await client.post(
        f"{API}/leads", headers=owner_headers,
        json={"title": "Asha enquiry", "contact_name": "Asha Roy", "contact_phone": "+919900800001"},
    )
    assert lead.status_code == 201, lead.text
    moved = await client.post(
        f"{API}/leads/{lead.json()['id']}/transitions", headers=owner_headers,
        json={"to_stage_code": "booked", "comment": "Token received for the flat.",
              "booking": {"unit_id": project["units"]["Tower A"][0], "token_amount": 11000, "token_mode": "neft",
                          "token_received_on": TODAY.isoformat()}},
    )
    assert moved.status_code == 201, moved.text

    listed = await client.get(f"{API}/bookings", headers=owner_headers, params={"lead_id": lead.json()["id"]})
    assert listed.status_code == 200, listed.text
    [booking] = listed.json()
    assert booking["status"] == "draft"
    assert [m["key"] for m in booking["payment_plan"]] == [m["key"] for m in PLAN]
    assert {k: _amount(r) for k, r in _rows(booking).items()} == {
        "bk": Decimal("500000.00"), "agr": Decimal("1000000.00"), "fix": Decimal("750000.00"),
    }


@pytest.mark.asyncio
async def test_stage_transition_reusing_a_wizard_booking_does_not_add_the_plan_again(client, owner_headers):
    project = await _project(client, owner_headers)
    lead = await client.post(
        f"{API}/leads", headers=owner_headers,
        json={"title": "Bina enquiry", "contact_name": "Bina Das", "contact_phone": "+919900800002"},
    )
    assert lead.status_code == 201, lead.text
    started = await client.post(
        f"{API}/bookings", headers=owner_headers,
        json={"unit_id": project["units"]["Tower A"][0], "lead_id": lead.json()["id"]},
    )
    assert started.status_code == 201, started.text
    moved = await client.post(
        f"{API}/leads/{lead.json()['id']}/transitions", headers=owner_headers,
        json={"to_stage_code": "booked", "comment": "Token received for the flat.",
              "booking": {"unit_id": project["units"]["Tower A"][0], "token_amount": 11000, "token_mode": "upi",
                          "token_received_on": TODAY.isoformat()}},
    )
    assert moved.status_code == 201, moved.text

    booking = await _booking(client, owner_headers, started.json()["id"])
    assert booking["token_amount"] is not None
    assert len(booking["payment_schedules"]) == 3
    assert set(_rows(booking)) == {"bk", "agr", "fix"}


@pytest.mark.asyncio
async def test_fractional_percent_is_billed_from_the_stored_percent(client, owner_headers):
    thirds = [
        {"key": "t1", "label": "First third", "percent": 33.333, "due_on": "on_booking"},
        {"key": "t2", "label": "Second third", "percent": 33.333, "due_on": "days_after_booking", "days": 60},
        {"key": "t3", "label": "Last third", "percent": 33.334, "due_on": "on_possession"},
    ]
    project = await _project(client, owner_headers, plan=thirds)
    booking = await _book(client, owner_headers, project["units"]["Tower A"][0])
    rows = _rows(booking)
    assert _amount(rows["t1"]) == Decimal("1666650.00")  # 33.333% of ₹50L
    priced = await client.put(
        f"{API}/bookings/{booking['id']}/pricing", headers=owner_headers, json={"pricing_snapshot": SNAPSHOT}
    )
    assert _amount(_rows(priced.json())["t2"]) == Decimal("2099979.00")  # 33.333% of ₹63L
    raised = await client.post(
        f"{API}/bookings/{booking['id']}/payment-plan/t3/raise", headers=owner_headers,
        json={"due_date": TODAY.isoformat()},
    )
    assert _amount(_rows(raised.json())["t3"]) == Decimal("2100042.00")
    assert sum(_amount(r) for r in _rows(raised.json()).values()) == Decimal("6300000.00")


# ---------------------------------------------------------------------------
# Demands follow the booking's price
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pricing_save_reprices_plan_rows_on_box_price_plus_gst(client, owner_headers):
    project = await _project(client, owner_headers)
    booking = await _book(client, owner_headers, project["units"]["Tower A"][0])

    priced = await client.put(
        f"{API}/bookings/{booking['id']}/pricing", headers=owner_headers, json={"pricing_snapshot": SNAPSHOT}
    )
    assert priced.status_code == 200, priced.text
    rows = _rows(priced.json())
    assert {k: _amount(r) for k, r in rows.items()} == {
        "bk": Decimal("630000.00"), "agr": Decimal("1260000.00"), "fix": Decimal("945000.00"),
    }
    assert {k: Decimal(str(r["outstanding"])) for k, r in rows.items()} == {k: _amount(r) for k, r in rows.items()}

    # The booking wizard's step save re-prices the same way.
    cheaper = {**SNAPSHOT, "boxPrice": 4_000_000, "gstAmount": 200_000}
    stepped = await client.post(
        f"{API}/bookings/{booking['id']}/step/2", headers=owner_headers, json={"pricing_snapshot": cheaper}
    )
    assert stepped.status_code == 200, stepped.text
    assert _amount(_rows(stepped.json())["bk"]) == Decimal("420000.00")
    # A step save without a price leaves the demands alone.
    other_step = await client.post(f"{API}/bookings/{booking['id']}/step/3", headers=owner_headers, json={})
    assert _amount(_rows(other_step.json())["bk"]) == Decimal("420000.00")


@pytest.mark.asyncio
async def test_paid_receipted_and_invoiced_rows_are_never_repriced(client, owner_headers):
    project = await _project(client, owner_headers)
    booking = await _book(client, owner_headers, project["units"]["Tower A"][0])
    rows = _rows(booking)
    await _pay(client, owner_headers, booking["id"], rows["bk"]["id"], amount=100_000)
    await _invoice(client, owner_headers, booking["id"], rows["agr"]["id"])

    priced = await client.put(
        f"{API}/bookings/{booking['id']}/pricing", headers=owner_headers, json={"pricing_snapshot": SNAPSHOT}
    )
    assert priced.status_code == 200, priced.text
    after = _rows(priced.json())
    assert _amount(after["bk"]) == Decimal("500000.00")
    assert Decimal(str(after["bk"]["outstanding"])) == Decimal("400000.00")
    assert _amount(after["agr"]) == Decimal("1000000.00")
    assert _amount(after["fix"]) == Decimal("945000.00")


@pytest.mark.asyncio
async def test_hand_edited_amount_stops_following_the_price(client, owner_headers):
    project = await _project(client, owner_headers)
    booking = await _book(client, owner_headers, project["units"]["Tower A"][0])
    rows = _rows(booking)
    base = f"{API}/bookings/{booking['id']}/payment-schedules"

    # Only the date changes (the amount sent unchanged): the row still follows the price.
    same = await client.patch(
        f"{base}/{rows['agr']['id']}", headers=owner_headers,
        json={"due_date": "2026-12-31", "demand_amount": rows["agr"]["demand_amount"]},
    )
    assert same.status_code == 200, same.text
    assert Decimal(str(same.json()["percent"])) == Decimal(20)

    edited = await client.patch(f"{base}/{rows['bk']['id']}", headers=owner_headers, json={"demand_amount": 123456})
    assert edited.status_code == 200, edited.text
    assert edited.json()["percent"] is None

    priced = await client.put(
        f"{API}/bookings/{booking['id']}/pricing", headers=owner_headers, json={"pricing_snapshot": SNAPSHOT}
    )
    after = _rows(priced.json())
    assert _amount(after["bk"]) == Decimal("123456.00")
    assert _amount(after["agr"]) == Decimal("1260000.00")


@pytest.mark.asyncio
async def test_manual_plan_replaces_the_project_plan(client, owner_headers):
    project = await _project(client, owner_headers)
    booking = await _book(client, owner_headers, project["units"]["Tower A"][0])

    manual = await client.post(
        f"{API}/bookings/{booking['id']}/payment-plan", headers=owner_headers,
        json={"installments": [{"installment_name": "Full payment", "due_date": "2027-01-01", "percentage": 100}]},
    )
    assert manual.status_code == 200, manual.text
    body = manual.json()
    assert body["payment_plan"] is None
    [row] = body["payment_schedules"]
    assert row["milestone_key"] is None and row["percent"] is None

    # Nothing is pending on it any more: marking a stage reached skips it, and it can't be raised.
    marked = await _mark(client, owner_headers, project["id"], "fnd")
    assert (marked["raised"], marked["already_raised"]) == (0, 0)
    raised = await client.post(
        f"{API}/bookings/{booking['id']}/payment-plan/fnd/raise", headers=owner_headers,
        json={"due_date": TODAY.isoformat()},
    )
    assert raised.status_code == 404, raised.text


# ---------------------------------------------------------------------------
# Marking an event milestone reached
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mark_reached_raises_on_live_bookings_in_scope_only(client, owner_headers):
    project = await _project(client, owner_headers)
    a1, a2, a3, a4 = project["units"]["Tower A"]
    confirmed = await _book(client, owner_headers, a1)
    await _confirm(client, owner_headers, confirmed["id"])
    draft = await _book(client, owner_headers, a2)
    cancelled = await _book(client, owner_headers, a3)
    cancel = await client.post(f"{API}/bookings/{cancelled['id']}/cancel", headers=owner_headers, json={})
    assert cancel.status_code == 200, cancel.text
    manual = await _book(client, owner_headers, a4)
    replaced = await client.post(
        f"{API}/bookings/{manual['id']}/payment-plan", headers=owner_headers,
        json={"installments": [{"installment_name": "Full", "due_date": "2027-01-01", "percentage": 100}]},
    )
    assert replaced.status_code == 200, replaced.text
    tower_b = await _book(client, owner_headers, project["units"]["Tower B"][0])
    other = await _project(client, owner_headers, name="Other Project")
    elsewhere = await _book(client, owner_headers, other["units"]["Tower A"][0])

    # Tower A only.
    result = await _mark(client, owner_headers, project["id"], "fnd", "2026-10-05", [project["towers"]["Tower A"]])
    assert (result["raised"], result["already_raised"]) == (2, 0)
    assert Decimal(str(result["amount"])) == Decimal("1500000.00")  # 15% of ₹50L × 2
    assert result["project"]["milestones_reached"] == [
        {"key": "fnd", "tower_id": project["towers"]["Tower A"], "reached_on": "2026-10-05"}
    ]
    for booking in (confirmed, draft):
        row = _rows(await _booking(client, owner_headers, booking["id"]))["fnd"]
        assert (row["due_date"], _amount(row), row["installment_name"]) == (
            "2026-10-05", Decimal("750000.00"), "Foundation complete",
        )
    for booking in (cancelled, manual, tower_b, elsewhere):
        assert "fnd" not in _rows(await _booking(client, owner_headers, booking["id"]))

    # Marking again never double-bills.
    again = await _mark(client, owner_headers, project["id"], "fnd", "2026-10-06", [project["towers"]["Tower A"]])
    assert (again["raised"], again["already_raised"], Decimal(str(again["amount"]))) == (0, 2, Decimal(0))
    assert again["project"]["milestones_reached"] == [
        {"key": "fnd", "tower_id": project["towers"]["Tower A"], "reached_on": "2026-10-06"}
    ]
    assert len([r for r in (await _booking(client, owner_headers, draft["id"]))["payment_schedules"]
                if r["milestone_key"] == "fnd"]) == 1

    # The whole project picks up Tower B; the other project is never touched.
    whole = await _mark(client, owner_headers, project["id"], "fnd", "2026-10-07")
    assert (whole["raised"], whole["already_raised"]) == (1, 2)
    assert Decimal(str(whole["amount"])) == Decimal("600000.00")  # 15% of ₹40L
    assert _rows(await _booking(client, owner_headers, tower_b["id"]))["fnd"]["due_date"] == "2026-10-07"
    assert "fnd" not in _rows(await _booking(client, owner_headers, elsewhere["id"]))


@pytest.mark.asyncio
async def test_raised_amount_uses_the_booking_price_and_its_own_plan_copy(client, owner_headers):
    project = await _project(client, owner_headers)
    booking = await _book(client, owner_headers, project["units"]["Tower A"][0])
    priced = await client.put(
        f"{API}/bookings/{booking['id']}/pricing", headers=owner_headers, json={"pricing_snapshot": SNAPSHOT}
    )
    assert priced.status_code == 200, priced.text
    # The builder later edits the project's % for this stage — the buyer keeps the booked terms.
    edited = [dict(m, percent=20) if m["key"] == "fnd" else dict(m, percent=25) if m["key"] == "pos" else m
              for m in PLAN]
    patched = await client.patch(
        f"{API}/inventory/projects/{project['id']}", headers=owner_headers, json={"payment_plan": edited}
    )
    assert patched.status_code == 200, patched.text

    result = await _mark(client, owner_headers, project["id"], "fnd")
    assert Decimal(str(result["amount"])) == Decimal("945000.00")  # 15% of (box ₹60L + GST ₹3L)
    row = _rows(await _booking(client, owner_headers, booking["id"]))["fnd"]
    assert Decimal(str(row["percent"])) == Decimal(15)


@pytest.mark.asyncio
async def test_booking_made_after_the_mark_gets_the_demand_straight_away(client, owner_headers):
    project = await _project(client, owner_headers)
    await _mark(client, owner_headers, project["id"], "fnd", "2026-09-01")
    await _mark(client, owner_headers, project["id"], "pos", "2026-09-01", [project["towers"]["Tower B"]])

    booking = await _book(client, owner_headers, project["units"]["Tower A"][0])
    rows = _rows(booking)
    assert set(rows) == {"bk", "agr", "fix", "fnd"}  # possession was reached for Tower B only
    assert rows["fnd"]["due_date"] == TODAY.isoformat()  # reached before the booking → due on booking
    assert _amount(rows["fnd"]) == Decimal("750000.00")

    in_b = await _book(client, owner_headers, project["units"]["Tower B"][0])
    assert set(_rows(in_b)) == {"bk", "agr", "fix", "fnd", "pos"}


@pytest.mark.asyncio
async def test_mark_reached_rejects_bad_requests(client, owner_headers):
    project = await _project(client, owner_headers)
    other = await _project(client, owner_headers, name="Other Project")

    not_event = await _mark(client, owner_headers, project["id"], "bk", expect=422)
    assert "on booking or on a date" in not_event["error"]["detail"]
    await _mark(client, owner_headers, project["id"], "nope", expect=404)
    await _mark(client, owner_headers, project["id"], "fnd", tower_ids=[other["towers"]["Tower A"]], expect=422)
    await _mark(client, owner_headers, "00000000-0000-0000-0000-000000000000", "fnd", expect=404)
    archived = await client.delete(f"{API}/inventory/projects/{other['id']}", headers=owner_headers)
    assert archived.status_code == 204, archived.text
    await _mark(client, owner_headers, other["id"], "fnd", expect=404)
    # Nothing was recorded by the rejected calls.
    fetched = await client.get(f"{API}/inventory/projects/{project['id']}", headers=owner_headers)
    assert fetched.json()["milestones_reached"] in (None, [])


# ---------------------------------------------------------------------------
# Undo a mark
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_undo_removes_untouched_demands_and_keeps_paid_or_invoiced_ones(client, owner_headers):
    project = await _project(client, owner_headers)
    a1, a2, a3, _a4 = project["units"]["Tower A"]
    paid, invoiced, untouched = [await _book(client, owner_headers, u) for u in (a1, a2, a3)]
    in_b = await _book(client, owner_headers, project["units"]["Tower B"][0])
    await _mark(client, owner_headers, project["id"], "fnd")
    await _pay(client, owner_headers, paid["id"], _rows(await _booking(client, owner_headers, paid["id"]))["fnd"]["id"])
    await _invoice(
        client, owner_headers, invoiced["id"], _rows(await _booking(client, owner_headers, invoiced["id"]))["fnd"]["id"]
    )

    result = await _undo(client, owner_headers, project["id"], "fnd")
    assert (result["removed"], result["kept"]) == (2, 2)
    assert result["project"]["milestones_reached"] in (None, [])
    assert "fnd" in _rows(await _booking(client, owner_headers, paid["id"]))
    assert "fnd" in _rows(await _booking(client, owner_headers, invoiced["id"]))
    assert "fnd" not in _rows(await _booking(client, owner_headers, untouched["id"]))
    assert "fnd" not in _rows(await _booking(client, owner_headers, in_b["id"]))
    # Other milestones' demands are untouched.
    assert set(_rows(await _booking(client, owner_headers, untouched["id"]))) == {"bk", "agr", "fix"}

    await _undo(client, owner_headers, project["id"], "fnd", expect=404)


@pytest.mark.asyncio
async def test_undo_respects_other_marks_of_the_same_milestone(client, owner_headers):
    project = await _project(client, owner_headers)
    in_a = await _book(client, owner_headers, project["units"]["Tower A"][0])
    in_b = await _book(client, owner_headers, project["units"]["Tower B"][0])
    tower_a, tower_b = project["towers"]["Tower A"], project["towers"]["Tower B"]
    await _mark(client, owner_headers, project["id"], "fnd", "2026-10-01", [tower_b])
    await _mark(client, owner_headers, project["id"], "fnd", "2026-10-02")

    # Undo the whole-project mark: Tower B still has its own mark, so its demand stays.
    whole = await _undo(client, owner_headers, project["id"], "fnd")
    assert (whole["removed"], whole["kept"]) == (1, 0)
    assert whole["project"]["milestones_reached"] == [{"key": "fnd", "tower_id": tower_b, "reached_on": "2026-10-01"}]
    assert "fnd" not in _rows(await _booking(client, owner_headers, in_a["id"]))
    assert "fnd" in _rows(await _booking(client, owner_headers, in_b["id"]))

    # A tower undo while the whole-project mark stands removes nothing.
    await _mark(client, owner_headers, project["id"], "fnd", "2026-10-03")
    tower_undo = await _undo(client, owner_headers, project["id"], "fnd", tower_b)
    assert (tower_undo["removed"], tower_undo["kept"]) == (0, 0)
    assert "fnd" in _rows(await _booking(client, owner_headers, in_b["id"]))
    await _undo(client, owner_headers, project["id"], "fnd", tower_a, expect=404)


# ---------------------------------------------------------------------------
# Raise one milestone on one booking
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_raise_on_one_booking_then_409_on_the_second_raise(client, owner_headers):
    project = await _project(client, owner_headers)
    booking = await _book(client, owner_headers, project["units"]["Tower A"][0])
    url = f"{API}/bookings/{booking['id']}/payment-plan"

    raised = await client.post(f"{url}/reg/raise", headers=owner_headers, json={"due_date": "2027-02-01"})
    assert raised.status_code == 200, raised.text
    row = _rows(raised.json())["reg"]
    assert (row["due_date"], row["installment_name"]) == ("2027-02-01", "Registration")
    assert _amount(row) == Decimal("500000.00")

    second = await client.post(f"{url}/reg/raise", headers=owner_headers, json={"due_date": "2027-02-02"})
    assert second.status_code == 409, second.text
    assert "already raised" in second.json()["error"]["detail"]
    # A later project-wide mark counts it as already raised.
    marked = await _mark(client, owner_headers, project["id"], "reg")
    assert (marked["raised"], marked["already_raised"]) == (0, 1)

    # A dated demand that was deleted is pending again and can be re-raised.
    agr = _rows(raised.json())["agr"]
    deleted = await client.delete(
        f"{API}/bookings/{booking['id']}/payment-schedules/{agr['id']}", headers=owner_headers
    )
    assert deleted.status_code == 204, deleted.text
    again = await client.post(f"{url}/agr/raise", headers=owner_headers, json={"due_date": "2026-11-15"})
    assert again.status_code == 200, again.text
    assert _rows(again.json())["agr"]["due_date"] == "2026-11-15"

    missing = await client.post(f"{url}/nope/raise", headers=owner_headers, json={"due_date": "2026-11-15"})
    assert missing.status_code == 404, missing.text


@pytest.mark.asyncio
async def test_raise_on_a_cancelled_booking_is_refused(client, owner_headers):
    project = await _project(client, owner_headers)
    booking = await _book(client, owner_headers, project["units"]["Tower A"][0])
    cancel = await client.post(f"{API}/bookings/{booking['id']}/cancel", headers=owner_headers, json={})
    assert cancel.status_code == 200, cancel.text
    raised = await client.post(
        f"{API}/bookings/{booking['id']}/payment-plan/fnd/raise", headers=owner_headers, json={"due_date": "2027-01-01"}
    )
    assert raised.status_code == 409, raised.text


@pytest.mark.asyncio
async def test_a_concurrent_duplicate_is_a_409_not_a_500(client, owner_headers, monkeypatch):
    """The unique (booking, milestone) index is the last guard: simulate the other request's row landing first."""
    project = await _project(client, owner_headers)
    booking = await _book(client, owner_headers, project["units"]["Tower A"][0])
    real_new_row = payment_plan_module._new_row

    def _collides(booking_id, milestone, due, base, today):
        row = real_new_row(booking_id, milestone, due, base, today)
        row.milestone_key = "bk"  # already on the booking
        return row

    monkeypatch.setattr(payment_plan_module, "_new_row", _collides)
    raised = await client.post(
        f"{API}/bookings/{booking['id']}/payment-plan/fnd/raise", headers=owner_headers, json={"due_date": "2027-01-01"}
    )
    assert raised.status_code == 409, raised.text
    marked = await _mark(client, owner_headers, project["id"], "pos", expect=409)
    assert "refresh" in marked["error"]["detail"]
    monkeypatch.setattr(payment_plan_module, "_new_row", real_new_row)

    after = await _booking(client, owner_headers, booking["id"])
    assert set(_rows(after)) == {"bk", "agr", "fix"}
    fetched = await client.get(f"{API}/inventory/projects/{project['id']}", headers=owner_headers)
    assert fetched.json()["milestones_reached"] in (None, [])  # the failed mark was rolled back


@pytest.mark.asyncio
async def test_database_refuses_a_second_row_for_the_same_milestone(client, owner_headers):
    project = await _project(client, owner_headers)
    booking = await _book(client, owner_headers, project["units"]["Tower A"][0])
    async with db_manager.session_factory() as session:
        session.add(PaymentSchedule(
            booking_id=UUID(booking["id"]), installment_name="Dup", due_date=TODAY, demand_amount=Decimal(1),
            paid_amount=Decimal(0), outstanding=Decimal(1), milestone_key="bk",
        ))
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()
        # Rows without a key are not constrained (manual / legacy demands).
        for _ in range(2):
            session.add(PaymentSchedule(
                booking_id=UUID(booking["id"]), installment_name="Manual", due_date=TODAY,
                demand_amount=Decimal(1), paid_amount=Decimal(0), outstanding=Decimal(1),
            ))
        await session.commit()


# ---------------------------------------------------------------------------
# Permissions + plan validation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_milestone_actions_need_record_payment_permission(client, owner_headers):
    project = await _project(client, owner_headers)
    booking = await _book(client, owner_headers, project["units"]["Tower A"][0])
    created = await client.post(
        f"{API}/users", headers=owner_headers,
        json={"first_name": "Sam", "last_name": "Exec", "email": "exec@plan.example.com", "password": "StrongPass123",
              "phone": "+919900700001", "role": "sales_executive", "status": "active"},
    )
    assert created.status_code == 201, created.text
    login = await client.post(f"{API}/auth/login", json={"email": "exec@plan.example.com", "password": "StrongPass123"})
    executive = {"Authorization": f"Bearer {login.json()['access_token']}"}

    await _mark(client, executive, project["id"], "fnd", expect=403)
    await _mark(client, owner_headers, project["id"], "fnd")
    await _undo(client, executive, project["id"], "fnd", expect=403)
    raised = await client.post(
        f"{API}/bookings/{booking['id']}/payment-plan/reg/raise", headers=executive, json={"due_date": "2027-01-01"}
    )
    assert raised.status_code == 403, raised.text
    assert "reg" not in _rows(await _booking(client, owner_headers, booking["id"]))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("plan", "message"),
    [
        ([{"key": "a", "label": "A", "percent": 60, "due_on": "on_booking"},
          {"key": "b", "label": "B", "percent": 30, "due_on": "on_possession"}], "must add up to 100%"),
        ([{"key": "a", "label": "A", "percent": 50, "due_on": "on_booking"},
          {"key": "a", "label": "B", "percent": 50, "due_on": "on_possession"}], "same key"),
        ([{"key": "a", "label": "Agreement", "percent": 100, "due_on": "days_after_booking"}], "how many days"),
        ([{"key": "a", "label": "Fixed", "percent": 100, "due_on": "on_date"}], "pick the date"),
    ],
)
async def test_payment_plan_validation(client, owner_headers, plan, message):
    project = await _project(client, owner_headers, plan=None)
    response = await client.patch(
        f"{API}/inventory/projects/{project['id']}", headers=owner_headers, json={"payment_plan": plan}
    )
    assert response.status_code == 422, response.text
    assert message in response.text


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def _booking_obj(snapshot) -> Booking:
    return Booking(pricing_snapshot=snapshot)


def test_plan_base_is_box_price_plus_gst_then_total_less_duties_then_unit_price():
    unit = Unit(base_price=Decimal("5000000"))
    assert plan_base(_booking_obj(SNAPSHOT), unit) == Decimal("6300000.00")
    # An older snapshot without boxPrice: total − stamp duty − registration.
    assert plan_base(_booking_obj({"total": "6720000", "stampDutyAmount": 360000, "registrationAmount": "60000"}),
                     unit) == Decimal("6300000.00")
    assert plan_base(_booking_obj({"total": 6_300_000}), unit) == Decimal("6300000.00")
    # No usable price yet → the unit's base price.
    for snap in (None, {}, {"boxPrice": "abc", "total": None}, {"boxPrice": True, "gstAmount": 1},
                 {"boxPrice": 0, "gstAmount": 0, "total": 0}, {"total": "NaN"}, "not a dict"):
        assert plan_base(_booking_obj(snap), unit) == Decimal("5000000.00"), snap
    assert plan_base(_booking_obj(None), None) == Decimal("0")


def test_reached_on_for_uses_the_earliest_mark_covering_the_tower():
    tower, other = UUID(int=1), UUID(int=2)
    marks = [
        {"key": "fnd", "tower_id": str(other), "reached_on": "2026-09-01"},
        {"key": "fnd", "tower_id": str(tower), "reached_on": "2026-10-05"},
        {"key": "fnd", "tower_id": None, "reached_on": "2026-10-09"},
        {"key": "pos", "tower_id": None, "reached_on": "2026-08-01"},
    ]
    assert reached_on_for(marks, "fnd", tower) == date(2026, 10, 5)
    assert reached_on_for(marks, "fnd", UUID(int=3)) == date(2026, 10, 9)
    assert reached_on_for(marks, "reg", tower) is None
    assert reached_on_for(None, "fnd", tower) is None


@pytest.mark.asyncio
async def test_apply_payment_plan_twice_never_doubles_a_demand(client, owner_headers):
    from app.real_estate.models import Project
    from app.real_estate.payment_plan import apply_payment_plan

    project = await _project(client, owner_headers)
    booking = await _book(client, owner_headers, project["units"]["Tower A"][0])
    async with db_manager.session_factory() as session:
        row = await session.get(Booking, UUID(booking["id"]))
        unit = await session.get(Unit, row.unit_id)
        proj = await session.get(Project, unit.project_id)
        assert await apply_payment_plan(session, row, unit, proj, TODAY) == []
        await session.commit()
        count = len((await session.scalars(
            select(PaymentSchedule).where(PaymentSchedule.booking_id == row.id)
        )).all())
    assert count == 3
