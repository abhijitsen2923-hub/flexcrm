"""Finance: a flat's sales order is worth its booking's sale value (not the lead's hidden ₹0 value), the sales-order
list names the buyer, and the finance summary breaks booking collections down by what they were paid for."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.real_estate.sale_value import booking_sale_value

UNIT_PRICE = 5_000_000


async def _owner(client) -> dict[str, str]:
    r = await client.post(
        "/api/v1/auth/register",
        json={"first_name": "Abhijit", "last_name": "Sen", "email": "owner@sv.example.com", "password": "StrongPass123",
              "role": "owner", "business_type": "real_estate", "organization_name": "Sale Value Realty"},
    )
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _units(client, headers, count: int) -> list[str]:
    r = await client.post("/api/v1/inventory/projects/full", headers=headers, json={
        "name": "abc green", "builder_name": "Abhijit", "location": "Kolkata", "city": "Kolkata",
        "towers": [{"name": "A", "total_floors": 1,
                    "unit_specs": [{"floors": [{"floor": 1, "count": count}], "area": 1000, "base_price": UNIT_PRICE}]}],
    })
    assert r.status_code == 201, r.text
    return [u["id"] for t in r.json()["towers"] for u in t["units"]]


async def _lead(client, headers, phone: str, name: str, *, partner_id: str | None = None) -> str:
    body = {"title": "flat", "contact_name": name, "contact_phone": phone, "budget_max": 4_000_000}
    if partner_id:
        body["partner_id"] = partner_id
    r = await client.post("/api/v1/leads", headers=headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _move(client, headers, lead_id: str, stage: str, **extra) -> None:
    r = await client.post(f"/api/v1/leads/{lead_id}/transitions", headers=headers,
                          json={"to_stage_code": stage, "comment": f"Moving to {stage} now.", **extra})
    assert r.status_code == 201, r.text


def _booking_payload(unit_id: str) -> dict:
    return {"unit_id": unit_id, "token_amount": 500000, "token_mode": "neft", "token_received_on": date.today().isoformat()}


async def _booking_id(client, headers, lead_id: str) -> str:
    rows = (await client.get(f"/api/v1/bookings?lead_id={lead_id}", headers=headers)).json()
    assert len(rows) == 1, rows
    return rows[0]["id"]


async def _order_for(client, headers, name: str) -> dict:
    orders = (await client.get("/api/v1/finance/sales-orders", headers=headers)).json()
    return next(o for o in orders if o["customer_name"] == name)


def test_sale_value_rule():
    # Box price wins; else total less GST / stamp duty / registration; else the unit's price; junk is ignored.
    assert booking_sale_value({"boxPrice": 6_000_000, "total": 7_000_000}, UNIT_PRICE) == Decimal("6000000.00")
    assert booking_sale_value(
        {"total": 7_000_000, "gstAmount": 300_000, "stampDutyAmount": 420_000, "registrationAmount": 80_000}, UNIT_PRICE
    ) == Decimal("6200000.00")
    assert booking_sale_value({"boxPrice": "abc", "total": None}, UNIT_PRICE) == Decimal("5000000.00")
    assert booking_sale_value(None, None) == Decimal("0")
    assert booking_sale_value({"boxPrice": True}, 0) == Decimal("0")


def test_a_sale_value_too_large_to_store_counts_as_no_price():
    # sales_orders.deal_value is NUMERIC(12,2): ₹1000 crore or more is a typo in the pricing, never a failed Sold.
    assert booking_sale_value({"boxPrice": "9999999999.99"}, UNIT_PRICE) == Decimal("9999999999.99")
    assert booking_sale_value({"boxPrice": 10_000_000_000}, UNIT_PRICE) == Decimal("0")
    assert booking_sale_value({"boxPrice": "9999999999.996"}, UNIT_PRICE) == Decimal("0")  # rounds up to 1e10
    assert booking_sale_value({"total": "1e40"}, UNIT_PRICE) == Decimal("0")
    assert booking_sale_value({"total": "1e1000000"}, UNIT_PRICE) == Decimal("0")  # too large even to subtract
    assert booking_sale_value(None, 10_000_000_000) == Decimal("0")


@pytest.mark.asyncio
async def test_flat_sale_is_worth_its_booking_price_and_names_the_buyer(client):
    h = await _owner(client)
    units = await _units(client, h, 2)

    priced = await _lead(client, h, "+919900700001", "IVA Dutta")
    await _move(client, h, priced, "booked", booking=_booking_payload(units[0]))
    booking = await _booking_id(client, h, priced)
    r = await client.put(f"/api/v1/bookings/{booking}/pricing", headers=h, json={"pricing_snapshot": {
        "boxPrice": 6_000_000, "gstAmount": 300_000, "total": 6_300_000, "subtotal": 6_000_000, "lineItems": []}})
    assert r.status_code == 200, r.text
    await _move(client, h, priced, "sold")

    unpriced = await _lead(client, h, "+919900700002", "Katappa")
    await _move(client, h, unpriced, "booked", booking=_booking_payload(units[1]))
    await _move(client, h, unpriced, "sold")

    first = await _order_for(client, h, "IVA Dutta")
    assert Decimal(first["deal_value"]) == Decimal("6000000.00")  # box price, not the ₹0 lead value nor GST
    assert first["title"] == "flat"
    second = await _order_for(client, h, "Katappa")
    assert Decimal(second["deal_value"]) == Decimal(UNIT_PRICE)  # no price saved yet → the unit's price
    single = (await client.get(f"/api/v1/finance/sales-orders/{first['id']}", headers=h)).json()
    assert single["customer_name"] == "IVA Dutta"


@pytest.mark.asyncio
async def test_cp_brokerage_follows_the_sale_value(client):
    h = await _owner(client)
    [unit] = await _units(client, h, 1)
    cp = (await client.post("/api/v1/channel-partners", headers=h, json={
        "company_name": "NK Realtor", "contact_name": "S Agarwal", "brokerage_type": "percent", "brokerage_rate": 2})).json()["id"]
    lead = await _lead(client, h, "+919900700003", "Riya Das", partner_id=cp)
    await _move(client, h, lead, "booked", booking=_booking_payload(unit))
    await _move(client, h, lead, "sold")
    payouts = (await client.get(f"/api/v1/channel-partners/{cp}/payouts", headers=h)).json()
    assert [Decimal(p["amount"]) for p in payouts] == [Decimal("100000.00")]  # 2% of ₹50L (was 2% of the ₹40L budget)


@pytest.mark.asyncio
async def test_collections_by_purpose(client):
    h = await _owner(client)
    [unit] = await _units(client, h, 1)
    # A booking made on the Bookings page (no token), so only the payments below are collected.
    created = await client.post("/api/v1/bookings", headers=h, json={"unit_id": unit})
    assert created.status_code == 201, created.text
    booking = created.json()["id"]
    assert (await client.get("/api/v1/finance/summary", headers=h)).json()["collections_by_purpose"] == []

    plan = await client.post(f"/api/v1/bookings/{booking}/payment-plan", headers=h, json={"installments": [
        {"installment_name": "Agreement", "due_date": date.today().isoformat(), "amount": 1_000_000},
        {"installment_name": "Plinth done", "due_date": date.today().isoformat(), "amount": 750_000},
    ]})
    assert plan.status_code == 200, plan.text
    rows = {s["installment_name"]: s["id"] for s in plan.json()["payment_schedules"]}
    for schedule, amount in ((rows["Agreement"], 600_000), (rows["Agreement"], 400_000), (rows["Plinth done"], 250_000), (None, 5_000)):
        r = await client.post(f"/api/v1/bookings/{booking}/payments", headers=h, json={
            "schedule_id": schedule, "amount": amount, "paid_on": date.today().isoformat(), "mode": "neft"})
        assert r.status_code == 200, r.text

    summary = (await client.get("/api/v1/finance/summary", headers=h)).json()
    got = {row["label"]: (Decimal(row["value"]), row["count"]) for row in summary["collections_by_purpose"]}
    assert got["Agreement"] == (Decimal("1000000.00"), 2)
    assert got["Plinth done"] == (Decimal("250000.00"), 1)
    assert got["Not linked to an instalment"] == (Decimal("5000.00"), 1)
    assert list(got) == ["Agreement", "Plinth done", "Not linked to an instalment"]  # largest first
    assert Decimal(summary["collections_total"]) == Decimal("1255000.00")
