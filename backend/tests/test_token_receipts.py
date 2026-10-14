"""The token as a real payment (app/real_estate/token_receipts.py, t049).

Recording a token — at the lead's "Booked / Token" move or with PUT /bookings/{id}/token — keeps exactly ONE receipt
(is_token) that mirrors it and pays the booking's first instalment: the plan's "on booking" row, else the earliest
unpaid row, else a "Booking amount" row made for it. Updating the token edits that receipt (never a second one), a
manual plan may still replace a plan that only holds the token (the token moves to its first row), the refund's gross
paid counts the token once, and a row whose only money is the token still follows the booking's price. Once recorded,
the token's amount / date are accounts' to change; a booking whose only money is the token may still be cancelled (the
token is kept), and a cancelled booking's token never changes.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import ConflictError
from app.database.session import db_manager
from app.real_estate.models import Booking, PaymentReceipt
from app.real_estate.token_receipts import sync_token_receipt

API = "/api/v1"
TODAY = date.today()
TOKEN_KEY = "__token__"

PLAN = [
    {"key": "bk", "label": "Booking amount", "percent": 10, "due_on": "on_booking"},
    {"key": "agr", "label": "Agreement", "percent": 20, "due_on": "days_after_booking", "days": 30},
    {"key": "fix", "label": "Plinth (fixed date)", "percent": 15, "due_on": "on_date", "due_date": "2027-03-31"},
    {"key": "pos", "label": "Possession", "percent": 55, "due_on": "on_possession"},
]
# boxPrice + GST = 63,00,000 (the plan's base).
SNAPSHOT = {
    "boxPrice": 6_000_000, "gstRate": 5, "gstAmount": 300_000, "stampDutyAmount": 360_000,
    "registrationAmount": 60_000, "subtotal": 6_000_000, "total": 6_720_000, "lineItems": [],
}


@pytest_asyncio.fixture
async def owner(client) -> dict[str, str]:
    response = await client.post(
        f"{API}/auth/register",
        json={"first_name": "Riya", "last_name": "Builder", "email": "owner@token.example.com",
              "password": "StrongPass123", "phone": "+1555000301", "role": "owner",
              "business_type": "real_estate", "organization_name": "Token Realty"},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _units(client, headers, *, plan: list | None = None, name: str = "Skyline", **details) -> list[str]:
    """One tower, 2 floors × 2 flats at ₹50L."""
    created = await client.post(f"{API}/inventory/projects/full", headers=headers, json={
        "name": name, "builder_name": "Acme", "location": "Salt Lake", "city": "Kolkata", **details,
        "towers": [{"name": "Tower A", "total_floors": 2, "unit_specs": [
            {"unit_type": "residential", "floors": [{"floor": 1, "count": 2}, {"floor": 2, "count": 2}],
             "area": 1200, "base_price": 5_000_000}]}],
        "parking": {},
    })
    assert created.status_code == 201, created.text
    project = created.json()
    if plan is not None:
        patched = await client.patch(
            f"{API}/inventory/projects/{project['id']}", headers=headers, json={"payment_plan": plan}
        )
        assert patched.status_code == 200, patched.text
    return sorted((u["id"] for t in project["towers"] for u in t["units"]), key=str)


async def _lead(client, headers, phone: str) -> str:
    response = await client.post(
        f"{API}/leads", headers=headers,
        json={"title": "Flat enquiry", "contact_name": "Asha Roy", "contact_phone": phone},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _token_move(client, headers, lead_id: str, unit_id: str, amount=11000, mode="neft", on=TODAY) -> dict:
    moved = await client.post(
        f"{API}/leads/{lead_id}/transitions", headers=headers,
        json={"to_stage_code": "booked", "comment": "Token received for the flat.",
              "booking": {"unit_id": unit_id, "token_amount": amount, "token_mode": mode,
                          "token_received_on": on.isoformat(), "token_reference": "UTR-1"}},
    )
    assert moved.status_code == 201, moved.text
    listed = await client.get(f"{API}/bookings", headers=headers, params={"lead_id": lead_id})
    assert listed.status_code == 200, listed.text
    [booking] = listed.json()
    return booking


async def _booking(client, headers, booking_id: str) -> dict:
    response = await client.get(f"{API}/bookings/{booking_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


async def _put_token(client, headers, booking_id: str, amount, on=TODAY, mode="upi", expect: int = 200) -> dict:
    response = await client.put(
        f"{API}/bookings/{booking_id}/token", headers=headers,
        json={"token_amount": amount, "token_received_on": on.isoformat(), "token_mode": mode},
    )
    assert response.status_code == expect, response.text
    return response.json()


async def _pay(client, headers, booking_id: str, amount, schedule_id: str | None = None, expect: int = 200) -> dict:
    response = await client.post(
        f"{API}/bookings/{booking_id}/payments", headers=headers,
        json={"schedule_id": schedule_id, "amount": amount, "paid_on": TODAY.isoformat(), "mode": "neft"},
    )
    assert response.status_code == expect, response.text
    return response.json()


def _tokens(booking: dict) -> list[dict]:
    return [r for r in booking["payment_receipts"] if r["is_token"]]


def _row(booking: dict, *, key: str | None = None, row_id: str | None = None) -> dict:
    return next(
        r for r in booking["payment_schedules"]
        if (key is not None and r["milestone_key"] == key) or (row_id is not None and r["id"] == row_id)
    )


def _d(value) -> Decimal:
    return Decimal(str(value))


def _paid(booking: dict) -> Decimal:
    return sum((_d(r["amount"]) for r in booking["payment_receipts"]), Decimal("0"))


# ---------------------------------------------------------------------------
# Recording the token
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_token_without_instalments_becomes_a_paid_booking_amount_row(client, owner):
    [unit, *_] = await _units(client, owner)
    booking = await _token_move(client, owner, await _lead(client, owner, "+919900810001"), unit)

    [token] = _tokens(booking)
    [row] = booking["payment_schedules"]
    assert (_d(token["amount"]), token["paid_on"], token["mode"], token["reference"], token["notes"]) == (
        Decimal("11000.00"), TODAY.isoformat(), "neft", "UTR-1", "Token / booking amount",
    )
    assert token["schedule_id"] == row["id"]
    assert (row["installment_name"], row["milestone_key"], row["percent"], row["due_date"]) == (
        "Booking amount", TOKEN_KEY, None, TODAY.isoformat(),
    )
    assert (_d(row["demand_amount"]), _d(row["paid_amount"]), _d(row["outstanding"]), row["is_overdue"]) == (
        Decimal("11000.00"), Decimal("11000.00"), Decimal("0.00"), False,
    )
    assert _paid(booking) == Decimal("11000.00")


@pytest.mark.asyncio
async def test_token_pays_the_plans_on_booking_row(client, owner):
    [unit, *_] = await _units(client, owner, plan=PLAN)
    booking = await _token_move(client, owner, await _lead(client, owner, "+919900810002"), unit)

    assert {r["milestone_key"] for r in booking["payment_schedules"]} == {"bk", "agr", "fix"}  # no extra row
    [token] = _tokens(booking)
    bk = _row(booking, key="bk")
    assert token["schedule_id"] == bk["id"]
    assert (_d(bk["demand_amount"]), _d(bk["paid_amount"]), _d(bk["outstanding"])) == (
        Decimal("500000.00"), Decimal("11000.00"), Decimal("489000.00"),
    )
    for key in ("agr", "fix"):
        assert _d(_row(booking, key=key)["paid_amount"]) == 0


@pytest.mark.asyncio
async def test_token_without_a_plan_pays_the_earliest_unpaid_row(client, owner):
    # A legacy demand schedule: two rows, the later-listed one falls due first.
    [unit, *_] = await _units(client, owner, demand_schedule=[
        {"label": "Second", "percent": 50, "due_date": "2027-06-01"},
        {"label": "First", "percent": 50, "due_date": "2027-01-10"},
    ])
    created = await client.post(f"{API}/bookings", headers=owner, json={"unit_id": unit})
    assert created.status_code == 201, created.text
    booking = await _put_token(client, owner, created.json()["id"], 25000)

    [token] = _tokens(booking)
    first = next(r for r in booking["payment_schedules"] if r["installment_name"] == "First")
    assert token["schedule_id"] == first["id"]
    assert _d(first["paid_amount"]) == Decimal("25000.00")
    assert len(booking["payment_schedules"]) == 2


@pytest.mark.asyncio
async def test_updating_the_token_edits_its_one_receipt_and_moves_the_row_by_the_difference(client, owner):
    units = await _units(client, owner, plan=PLAN)
    lead = await _lead(client, owner, "+919900810003")
    booking = await _token_move(client, owner, lead, units[0])
    bk_id = _row(booking, key="bk")["id"]
    # A real payment on the same row first: the token update must leave it in place.
    await _pay(client, owner, booking["id"], 100000, schedule_id=bk_id)

    updated = await _put_token(client, owner, booking["id"], 51000, on=TODAY - timedelta(days=2), mode="cheque")
    [token] = _tokens(updated)
    assert (_d(token["amount"]), token["paid_on"], token["mode"], token["schedule_id"]) == (
        Decimal("51000.00"), (TODAY - timedelta(days=2)).isoformat(), "cheque", bk_id,
    )
    bk = _row(updated, key="bk")
    assert (_d(bk["paid_amount"]), _d(bk["outstanding"])) == (Decimal("151000.00"), Decimal("349000.00"))
    assert len(updated["payment_receipts"]) == 2
    assert _paid(updated) == Decimal("151000.00")

    # The same token again, and a second Booked / Token move on the lead (it reuses the booking): still one receipt.
    again = await _put_token(client, owner, booking["id"], 51000, on=TODAY - timedelta(days=2), mode="cheque")
    assert _d(_row(again, key="bk")["paid_amount"]) == Decimal("151000.00")
    rebooked = await _token_move(client, owner, lead, units[0], amount=60000)
    assert [(_d(t["amount"]), t["schedule_id"]) for t in _tokens(rebooked)] == [(Decimal("60000.00"), bk_id)]
    assert _d(_row(rebooked, key="bk")["paid_amount"]) == Decimal("160000.00")
    assert len(rebooked["payment_receipts"]) == 2


@pytest.mark.asyncio
async def test_updating_the_token_moves_the_booking_amount_rows_demand_too(client, owner):
    [unit, *_] = await _units(client, owner)
    booking = await _token_move(client, owner, await _lead(client, owner, "+919900810004"), unit)
    updated = await _put_token(client, owner, booking["id"], 7000, on=TODAY - timedelta(days=1))
    [row] = updated["payment_schedules"]
    assert (_d(row["demand_amount"]), _d(row["paid_amount"]), _d(row["outstanding"]), row["due_date"]) == (
        Decimal("7000.00"), Decimal("7000.00"), Decimal("0.00"), (TODAY - timedelta(days=1)).isoformat(),
    )
    assert [_d(t["amount"]) for t in _tokens(updated)] == [Decimal("7000.00")]


@pytest.mark.asyncio
async def test_token_stays_a_receipt_when_every_row_already_has_money(client, owner):
    [unit, *_] = await _units(client, owner, demand_schedule=[
        {"label": "Only", "percent": 10, "due_date": "2027-01-10"},
    ])
    created = (await client.post(f"{API}/bookings", headers=owner, json={"unit_id": unit})).json()
    await _pay(client, owner, created["id"], 1000, schedule_id=created["payment_schedules"][0]["id"])

    booking = await _put_token(client, owner, created["id"], 25000)
    [token] = _tokens(booking)
    assert token["schedule_id"] is None  # unapplied, but still money received
    assert _d(booking["payment_schedules"][0]["paid_amount"]) == Decimal("1000.00")
    assert _paid(booking) == Decimal("26000.00")


@pytest.mark.asyncio
async def test_a_cancelled_bookings_token_cannot_be_changed(client, owner):
    [unit, *_] = await _units(client, owner)
    created = (await client.post(f"{API}/bookings", headers=owner, json={"unit_id": unit})).json()
    cancelled = await client.post(f"{API}/bookings/{created['id']}/cancel", headers=owner, json={})
    assert cancelled.status_code == 200, cancelled.text
    await _put_token(client, owner, created["id"], 5000, expect=409)
    assert (await _booking(client, owner, created["id"]))["payment_receipts"] == []


@pytest.mark.asyncio
async def test_database_allows_one_token_receipt_per_booking(client, owner):
    [unit, *_] = await _units(client, owner)
    booking = await _token_move(client, owner, await _lead(client, owner, "+919900810005"), unit)
    async with db_manager.session_factory() as session:
        session.add(PaymentReceipt(booking_id=UUID(booking["id"]), amount=Decimal(1), paid_on=TODAY, mode="cash",
                                   is_token=True))
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()
        # Ordinary receipts are not limited.
        for _ in range(2):
            session.add(PaymentReceipt(booking_id=UUID(booking["id"]), amount=Decimal(1), paid_on=TODAY, mode="cash"))
        await session.commit()
        count = len((await session.scalars(
            select(PaymentReceipt).where(PaymentReceipt.booking_id == UUID(booking["id"]))
        )).all())
    assert count == 3


@pytest.mark.asyncio
async def test_a_plan_cannot_use_the_reserved_token_key(client, owner):
    [unit, *_] = await _units(client, owner)
    project_id = (await client.get(f"{API}/inventory/units/{unit}", headers=owner)).json()["project_id"]
    response = await client.patch(
        f"{API}/inventory/projects/{project_id}", headers=owner,
        json={"payment_plan": [{"key": TOKEN_KEY, "label": "All", "percent": 100, "due_on": "on_booking"}]},
    )
    assert response.status_code == 422, response.text
    assert "reserved" in response.text


# ---------------------------------------------------------------------------
# Manual plan, refund, receivables, re-pricing
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_manual_plan_after_a_token_moves_the_token_to_its_first_row(client, owner):
    [unit, *_] = await _units(client, owner)
    booking = await _token_move(client, owner, await _lead(client, owner, "+919900810006"), unit)

    manual = await client.post(
        f"{API}/bookings/{booking['id']}/payment-plan", headers=owner,
        json={"installments": [
            {"installment_name": "Agreement", "due_date": "2027-02-01", "percentage": 20},
            {"installment_name": "On booking", "due_date": "2026-11-01", "amount": 500000},
            {"installment_name": "Same day, listed later", "due_date": "2026-11-01", "amount": 100},
        ]},
    )
    assert manual.status_code == 200, manual.text
    body = manual.json()
    assert TOKEN_KEY not in {r["milestone_key"] for r in body["payment_schedules"]}  # the Booking amount row is gone
    assert len(body["payment_schedules"]) == 3
    [token] = _tokens(body)
    first = next(r for r in body["payment_schedules"] if r["installment_name"] == "On booking")
    assert token["schedule_id"] == first["id"]
    assert (_d(first["paid_amount"]), _d(first["outstanding"])) == (Decimal("11000.00"), Decimal("489000.00"))
    assert sum(_d(r["paid_amount"]) for r in body["payment_schedules"]) == Decimal("11000.00")
    assert len(body["payment_receipts"]) == 1

    # Replaced again (still only the token on it): the token follows to the newest plan.
    again = await client.post(
        f"{API}/bookings/{booking['id']}/payment-plan", headers=owner,
        json={"installments": [{"installment_name": "Full", "due_date": "2027-01-01", "percentage": 100}]},
    )
    assert again.status_code == 200, again.text
    [row] = again.json()["payment_schedules"]
    assert (_d(row["paid_amount"]), _tokens(again.json())[0]["schedule_id"]) == (Decimal("11000.00"), row["id"])


@pytest.mark.asyncio
async def test_manual_plan_is_blocked_when_a_payment_other_than_the_token_exists(client, owner):
    [unit, *_] = await _units(client, owner, plan=PLAN)
    booking = await _token_move(client, owner, await _lead(client, owner, "+919900810007"), unit)
    agr = _row(booking, key="agr")["id"]
    await _pay(client, owner, booking["id"], 2000, schedule_id=agr)

    blocked = await client.post(
        f"{API}/bookings/{booking['id']}/payment-plan", headers=owner,
        json={"installments": [{"installment_name": "Full", "due_date": "2027-01-01", "percentage": 100}]},
    )
    assert blocked.status_code == 409, blocked.text
    after = await _booking(client, owner, booking["id"])
    assert {r["milestone_key"] for r in after["payment_schedules"]} == {"bk", "agr", "fix"}
    assert _tokens(after)[0]["schedule_id"] == _row(after, key="bk")["id"]
    assert _d(_row(after, key="bk")["paid_amount"]) == Decimal("11000.00")

    # A second payment on the token's own row blocks it too.
    other_units = await _units(client, owner, plan=PLAN, name="Second")
    other = await _token_move(client, owner, await _lead(client, owner, "+919900810008"), other_units[0])
    await _pay(client, owner, other["id"], 5, schedule_id=_row(other, key="bk")["id"])
    blocked_too = await client.post(
        f"{API}/bookings/{other['id']}/payment-plan", headers=owner,
        json={"installments": [{"installment_name": "Full", "due_date": "2027-01-01", "percentage": 100}]},
    )
    assert blocked_too.status_code == 409, blocked_too.text


@pytest.mark.asyncio
async def test_refund_counts_the_token_once(client, owner):
    units = await _units(client, owner, plan=PLAN)
    booking = await _token_move(client, owner, await _lead(client, owner, "+919900810009"), units[0])
    await _pay(client, owner, booking["id"], 50000, schedule_id=_row(booking, key="agr")["id"])

    refunded = await client.post(
        f"{API}/bookings/{booking['id']}/refund", headers=owner,
        json={"deduction_amount": 1000, "mode": "neft", "refunded_on": TODAY.isoformat()},
    )
    assert refunded.status_code == 200, refunded.text
    [refund] = refunded.json()["refunds"]
    assert (_d(refund["gross_paid"]), _d(refund["refund_amount"])) == (Decimal("61000.00"), Decimal("60000.00"))
    assert refunded.json()["status"] == "cancelled"

    # A token-only booking refunded: the token is its whole gross paid (here all of it withheld).
    token_only = await _token_move(client, owner, await _lead(client, owner, "+919900810010"), units[1])
    forfeited = await client.post(
        f"{API}/bookings/{token_only['id']}/refund", headers=owner,
        json={"deduction_amount": 11000, "mode": "neft", "refunded_on": TODAY.isoformat()},
    )
    assert forfeited.status_code == 200, forfeited.text
    [refund] = forfeited.json()["refunds"]
    assert (_d(refund["gross_paid"]), _d(refund["refund_amount"])) == (Decimal("11000.00"), Decimal("0.00"))


@pytest.mark.asyncio
async def test_receivables_ledger_shows_the_token_row_paid(client, owner):
    [unit, *_] = await _units(client, owner)
    booking = await _token_move(client, owner, await _lead(client, owner, "+919900810011"), unit)
    ledger = await client.get(f"{API}/bookings/collection-ledger", headers=owner)
    assert ledger.status_code == 200, ledger.text
    [entry] = [e for e in ledger.json() if e["booking_id"] == booking["id"]]
    assert (entry["installment_name"], _d(entry["demand_amount"]), _d(entry["paid_amount"]),
            _d(entry["outstanding"]), entry["is_overdue"]) == (
        "Booking amount", Decimal("11000.00"), Decimal("11000.00"), Decimal("0.00"), False,
    )


@pytest.mark.asyncio
async def test_a_row_paid_only_by_the_token_still_follows_the_price(client, owner):
    [unit, *_] = await _units(client, owner, plan=PLAN)
    booking = await _token_move(client, owner, await _lead(client, owner, "+919900810012"), unit)
    await _pay(client, owner, booking["id"], 1000, schedule_id=_row(booking, key="agr")["id"])

    priced = await client.put(
        f"{API}/bookings/{booking['id']}/pricing", headers=owner, json={"pricing_snapshot": SNAPSHOT}
    )
    assert priced.status_code == 200, priced.text
    body = priced.json()
    bk, agr, fix = (_row(body, key=k) for k in ("bk", "agr", "fix"))
    # The token's row: 10% of ₹63L now, its paid amount untouched.
    assert (_d(bk["demand_amount"]), _d(bk["paid_amount"]), _d(bk["outstanding"])) == (
        Decimal("630000.00"), Decimal("11000.00"), Decimal("619000.00"),
    )
    assert _d(agr["demand_amount"]) == Decimal("1000000.00")  # a real payment pins its row
    assert _d(fix["demand_amount"]) == Decimal("945000.00")
    assert [_d(t["amount"]) for t in _tokens(body)] == [Decimal("11000.00")]


@pytest.mark.asyncio
async def test_a_token_row_with_a_payment_on_it_no_longer_follows_the_price(client, owner):
    [unit, *_] = await _units(client, owner, plan=PLAN)
    booking = await _token_move(client, owner, await _lead(client, owner, "+919900810013"), unit)
    await _pay(client, owner, booking["id"], 1000, schedule_id=_row(booking, key="bk")["id"])
    priced = await client.put(
        f"{API}/bookings/{booking['id']}/pricing", headers=owner, json={"pricing_snapshot": SNAPSHOT}
    )
    assert _d(_row(priced.json(), key="bk")["demand_amount"]) == Decimal("500000.00")


@pytest.mark.asyncio
async def test_the_token_row_cannot_be_deleted(client, owner):
    [unit, *_] = await _units(client, owner)
    booking = await _token_move(client, owner, await _lead(client, owner, "+919900810014"), unit)
    [row] = booking["payment_schedules"]
    deleted = await client.delete(f"{API}/bookings/{booking['id']}/payment-schedules/{row['id']}", headers=owner)
    assert deleted.status_code == 409, deleted.text



# ---------------------------------------------------------------------------
# Who may change the token, cancelling, finance's own figures
# ---------------------------------------------------------------------------

async def _sales_rep(client, owner) -> tuple[dict, str]:
    """A sales executive: LEAD_MANAGE, no FINANCE_RECORD_PAYMENT."""
    created = await client.post(f"{API}/users", headers=owner, json={
        "first_name": "Rinku", "last_name": "Kayal", "email": "rep@token.example.com", "password": "StrongPass123",
        "phone": "+919900819999", "role": "sales_executive", "status": "active"})
    assert created.status_code == 201, created.text
    login = await client.post(f"{API}/auth/login", json={"email": "rep@token.example.com", "password": "StrongPass123"})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}, created.json()["id"]


@pytest.mark.asyncio
async def test_only_accounts_change_a_recorded_tokens_amount_or_date(client, owner):
    units = await _units(client, owner)
    rep, _rep_id = await _sales_rep(client, owner)
    created = (await client.post(f"{API}/bookings", headers=owner, json={"unit_id": units[0]})).json()
    url = f"{API}/bookings/{created['id']}/token"

    # The first token needs only LEAD_MANAGE.
    first = await _put_token(client, rep, created["id"], 11000, mode="neft")
    assert [_d(t["amount"]) for t in _tokens(first)] == [Decimal("11000.00")]
    # Mode / reference are details: still the rep's to fix.
    fixed = await client.put(url, headers=rep, json={
        "token_amount": 11000, "token_received_on": TODAY.isoformat(), "token_mode": "upi", "token_reference": "UTR-9"})
    assert fixed.status_code == 200, fixed.text
    [token] = _tokens(fixed.json())
    assert (token["mode"], token["reference"]) == ("upi", "UTR-9")

    # The amount or the date: a recorded payment, so only accounts change it.
    for change in ({"token_amount": 12000, "token_received_on": TODAY.isoformat()},
                   {"token_amount": 11000, "token_received_on": (TODAY - timedelta(days=1)).isoformat()}):
        refused = await client.put(url, headers=rep, json={**change, "token_mode": "upi"})
        assert refused.status_code == 403, refused.text
        assert "ask an owner or sales manager to change its amount or date" in refused.text
    after = await _booking(client, owner, created["id"])
    assert (_d(after["token_amount"]), after["token_received_on"]) == (Decimal("11000.00"), TODAY.isoformat())
    [token] = _tokens(after)
    assert (_d(token["amount"]), token["paid_on"]) == (Decimal("11000.00"), TODAY.isoformat())

    # Someone with FINANCE_RECORD_PAYMENT (the owner here) may.
    changed = await _put_token(client, owner, created["id"], 12000)
    assert [_d(t["amount"]) for t in _tokens(changed)] == [Decimal("12000.00")]


@pytest.mark.asyncio
async def test_a_repeated_booked_capture_cannot_change_a_recorded_token_without_accounts(client, owner):
    units = await _units(client, owner)
    rep, rep_id = await _sales_rep(client, owner)
    lead = await client.post(f"{API}/leads", headers=owner, json={
        "title": "Flat enquiry", "contact_name": "Asha Roy", "contact_phone": "+919900810020",
        "assigned_to_id": rep_id})
    assert lead.status_code == 201, lead.text
    lead_id = lead.json()["id"]
    booking = await _token_move(client, rep, lead_id, units[0])  # the first capture: LEAD_MANAGE is enough

    refused = await client.post(f"{API}/leads/{lead_id}/transitions", headers=rep, json={
        "to_stage_code": "booked", "comment": "Token received for the flat.",
        "booking": {"unit_id": units[0], "token_amount": 20000, "token_mode": "neft",
                    "token_received_on": TODAY.isoformat()}})
    assert refused.status_code == 403, refused.text
    assert "ask an owner or sales manager to change its amount or date" in refused.text
    after = await _booking(client, owner, booking["id"])
    assert _d(after["token_amount"]) == Decimal("11000.00")
    assert [_d(t["amount"]) for t in _tokens(after)] == [Decimal("11000.00")]

    # The same amount and date with another mode goes through.
    again = await _token_move(client, rep, lead_id, units[0], mode="cash")
    assert [(_d(t["amount"]), t["mode"]) for t in _tokens(again)] == [(Decimal("11000.00"), "cash")]


@pytest.mark.asyncio
async def test_a_booking_whose_only_money_is_the_token_can_still_be_cancelled_and_keeps_it(client, owner):
    units = await _units(client, owner)
    booking = await _token_move(client, owner, await _lead(client, owner, "+919900810015"), units[0])
    cancelled = await client.post(f"{API}/bookings/{booking['id']}/cancel", headers=owner, json={})
    assert cancelled.status_code == 200, cancelled.text
    body = cancelled.json()
    assert (body["status"], body["refunds"]) == ("cancelled", [])
    # The token stays a kept (forfeited) payment, as it was before it became a receipt.
    assert [_d(t["amount"]) for t in _tokens(body)] == [Decimal("11000.00")]
    unit = await client.get(f"{API}/inventory/units/{units[0]}", headers=owner)
    assert unit.json()["status"] == "available"

    # Any other payment still has to be refunded first.
    other = await _token_move(client, owner, await _lead(client, owner, "+919900810016"), units[1])
    await _pay(client, owner, other["id"], 5000)
    refused = await client.post(f"{API}/bookings/{other['id']}/cancel", headers=owner, json={})
    assert refused.status_code == 409, refused.text
    assert (await _booking(client, owner, other["id"]))["status"] != "cancelled"


@pytest.mark.asyncio
async def test_a_token_sync_that_waited_for_a_cancel_is_refused(client, owner):
    [unit, *_] = await _units(client, owner)
    created = (await client.post(f"{API}/bookings", headers=owner, json={"unit_id": unit})).json()
    async with db_manager.session_factory() as session:
        booking = await session.get(Booking, UUID(created["id"]))  # read before the cancel commits
        cancelled = await client.post(f"{API}/bookings/{created['id']}/cancel", headers=owner, json={})
        assert cancelled.status_code == 200, cancelled.text
        booking.token_amount = Decimal("5000")
        booking.token_received_on = TODAY
        with pytest.raises(ConflictError, match="cancelled"):
            await sync_token_receipt(session, booking, can_record_payment=True)
        await session.rollback()
    after = await _booking(client, owner, created["id"])
    assert (after["payment_receipts"], after["token_amount"]) == ([], None)


@pytest.mark.asyncio
async def test_manual_plan_is_refused_while_an_instalment_has_a_live_invoice(client, owner):
    [unit, *_] = await _units(client, owner, plan=PLAN)
    created = (await client.post(f"{API}/bookings", headers=owner, json={"unit_id": unit})).json()
    invoiced = await client.post(
        f"{API}/bookings/{created['id']}/invoices", headers=owner, json={"schedule_id": _row(created, key="agr")["id"]}
    )
    assert invoiced.status_code == 201, invoiced.text

    refused = await client.post(
        f"{API}/bookings/{created['id']}/payment-plan", headers=owner,
        json={"installments": [{"installment_name": "Full", "due_date": "2027-01-01", "percentage": 100}]},
    )
    assert refused.status_code == 409, refused.text
    assert "An invoice is raised on an instalment" in refused.text
    after = await _booking(client, owner, created["id"])
    assert {r["milestone_key"] for r in after["payment_schedules"]} == {"bk", "agr", "fix"}


@pytest.mark.asyncio
async def test_a_booking_amount_row_finance_changed_keeps_its_figures_when_the_token_changes(client, owner):
    units = await _units(client, owner)
    booking = await _token_move(client, owner, await _lead(client, owner, "+919900810017"), units[0])
    [row] = booking["payment_schedules"]
    patched = await client.patch(
        f"{API}/bookings/{booking['id']}/payment-schedules/{row['id']}", headers=owner, json={"demand_amount": 500000}
    )
    assert patched.status_code == 200, patched.text

    def figures(body: dict) -> tuple:
        [r] = body["payment_schedules"]
        return _d(r["demand_amount"]), _d(r["paid_amount"]), _d(r["outstanding"]), r["due_date"]

    # Finance's demand stays, whether the token is saved again unchanged or with a new amount and date: only the
    # paid amount (and so the outstanding) follows the token.
    same = await _put_token(client, owner, booking["id"], 11000, mode="neft")
    assert figures(same) == (Decimal("500000.00"), Decimal("11000.00"), Decimal("489000.00"), TODAY.isoformat())
    moved = await _put_token(client, owner, booking["id"], 15000, on=TODAY - timedelta(days=3))
    assert figures(moved) == (Decimal("500000.00"), Decimal("15000.00"), Decimal("485000.00"), TODAY.isoformat())

    # Only its due date set by finance: the demand still mirrors the token and follows it; the date stays.
    other = await _token_move(client, owner, await _lead(client, owner, "+919900810018"), units[1])
    [row] = other["payment_schedules"]
    patched = await client.patch(
        f"{API}/bookings/{other['id']}/payment-schedules/{row['id']}", headers=owner, json={"due_date": "2026-12-01"}
    )
    assert patched.status_code == 200, patched.text
    updated = await _put_token(client, owner, other["id"], 9000, on=TODAY - timedelta(days=1))
    assert figures(updated) == (Decimal("9000.00"), Decimal("9000.00"), Decimal("0.00"), "2026-12-01")
