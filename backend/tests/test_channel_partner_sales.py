"""Channel-partner sales + the partner funnel.

- A sale credited to a channel partner pays the partner's brokerage and NO salesperson incentive — even when a
  salesperson is picked (on record only). The salesperson is optional on such a Booked / Token move.
- "Others (owner's reference)" means no salesperson incentive; a channel partner on the sale still earns.
- An internal sale (no partner) still pays its salesperson; owner's reference without a partner pays nobody.
- Partner stats: referred → site visits done → bookings done → sales closed (cumulative: a lead that reached a
  stage, or has the record, counts even if it moved on since).
"""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select

from app.database.session import db_manager
from app.finance.models import CommissionLedger, SalesOrder
from app.models.channel_partner import BrokeragePayout
from app.models.lead import Lead

DEAL = 5_000_000  # ₹50L
BUDGET = 4_000_000


async def _owner(client) -> dict[str, str]:
    r = await client.post(
        "/api/v1/auth/register",
        json={"first_name": "Rita", "last_name": "Owner", "email": "owner@cp.example.com", "password": "StrongPass123",
              "role": "owner", "business_type": "real_estate", "organization_name": "CP Realty"},
    )
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _user_id(client, headers, email: str) -> str:
    users = (await client.get("/api/v1/users", headers=headers)).json()
    items = users["items"] if isinstance(users, dict) else users
    return next(u["id"] for u in items if u["email"] == email)


async def _rep(client, headers) -> str:
    r = await client.post("/api/v1/users", headers=headers, json={
        "first_name": "Rinku", "last_name": "Kayal", "email": "rinku@cp.example.com", "password": "StrongPass123",
        "phone": "+919900399991", "role": "sales_executive", "status": "active"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _partner(client, headers, name: str = "NK Realtor") -> str:
    r = await client.post("/api/v1/channel-partners", headers=headers, json={
        "company_name": name, "contact_name": "S Agarwal", "brokerage_type": "percent", "brokerage_rate": 2})
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _units(client, headers, count: int) -> list[str]:
    r = await client.post("/api/v1/inventory/projects/full", headers=headers, json={
        "name": "abc green", "builder_name": "Abhijit", "location": "Kolkata", "city": "Kolkata",
        "towers": [{"name": "A", "total_floors": 1,
                    "unit_specs": [{"floors": [{"floor": 1, "count": count}], "area": 1000, "base_price": DEAL}]}],
    })
    assert r.status_code == 201, r.text
    return [u["id"] for t in r.json()["towers"] for u in t["units"]]


async def _lead(client, headers, phone: str, *, owner_id: str, partner_id: str | None = None) -> str:
    body = {"title": "CP lead", "contact_name": "Asha Roy", "contact_phone": phone, "value": DEAL,
            "budget_max": BUDGET, "assigned_to_id": owner_id}
    if partner_id:
        body["partner_id"] = partner_id
    r = await client.post("/api/v1/leads", headers=headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _move(client, headers, lead_id: str, stage: str, **extra) -> dict:
    r = await client.post(f"/api/v1/leads/{lead_id}/transitions", headers=headers,
                          json={"to_stage_code": stage, "comment": f"Moving to {stage} now.", **extra})
    assert r.status_code == 201, r.text
    return r.json()


def _booking(unit_id: str) -> dict:
    return {"unit_id": unit_id, "token_amount": 500000, "token_mode": "neft", "token_received_on": "2026-10-11"}


async def _money(lead: str) -> tuple[list[CommissionLedger], list[BrokeragePayout]]:
    lead_id = UUID(lead)
    async with db_manager.session_factory() as session:
        order = (await session.execute(select(SalesOrder).where(SalesOrder.lead_id == lead_id))).scalar_one()
        commissions = list((await session.scalars(
            select(CommissionLedger).where(CommissionLedger.sales_order_id == order.id))).all())
        payouts = list((await session.scalars(select(BrokeragePayout).where(BrokeragePayout.lead_id == lead_id))).all())
        return commissions, payouts


@pytest.mark.asyncio
async def test_cp_sale_pays_brokerage_and_no_salesperson_incentive(client):
    h = await _owner(client)
    owner_id = await _user_id(client, h, "owner@cp.example.com")
    rep_id = await _rep(client, h)
    cp = await _partner(client, h)
    [unit] = await _units(client, h, 1)
    lead = await _lead(client, h, "+919900500001", owner_id=owner_id)

    # A salesperson IS picked — on record only.
    await _move(client, h, lead, "booked", assigned_to_id=rep_id, partner_id=cp, booking=_booking(unit))
    await _move(client, h, lead, "sold")

    commissions, payouts = await _money(lead)
    assert commissions == []
    assert [(str(p.partner_id), p.amount, p.status) for p in payouts] == [(cp, Decimal("100000.00"), "accrued")]


@pytest.mark.asyncio
async def test_cp_sale_needs_no_salesperson(client):
    h = await _owner(client)
    owner_id = await _user_id(client, h, "owner@cp.example.com")
    await _rep(client, h)
    cp = await _partner(client, h)
    [unit] = await _units(client, h, 1)
    lead = await _lead(client, h, "+919900500002", owner_id=owner_id)

    await _move(client, h, lead, "booked", partner_id=cp, booking=_booking(unit))  # no assigned_to_id
    # Nobody picked: the lead keeps its owner (who also owns the new customer).
    async with db_manager.session_factory() as session:
        assert str((await session.get(Lead, UUID(lead))).assigned_to_id) == owner_id
    await _move(client, h, lead, "sold")

    commissions, payouts = await _money(lead)
    assert commissions == []
    assert len(payouts) == 1 and payouts[0].amount == Decimal("100000.00")


@pytest.mark.asyncio
async def test_owner_reference_still_pays_the_channel_partner(client):
    h = await _owner(client)
    owner_id = await _user_id(client, h, "owner@cp.example.com")
    cp = await _partner(client, h)
    [unit] = await _units(client, h, 1)
    lead = await _lead(client, h, "+919900500003", owner_id=owner_id)

    await _move(client, h, lead, "booked", partner_id=cp, incentive_exempt=True, booking=_booking(unit))
    await _move(client, h, lead, "sold")

    commissions, payouts = await _money(lead)
    assert commissions == []
    assert [(str(p.partner_id), p.amount) for p in payouts] == [(cp, Decimal("100000.00"))]


@pytest.mark.asyncio
async def test_referred_lead_counts_as_cp_sale_without_a_pick_at_booking(client):
    """A partner-referred lead (partner set when it came in) is a CP sale even if the booking step doesn't re-pick
    the partner."""
    h = await _owner(client)
    owner_id = await _user_id(client, h, "owner@cp.example.com")
    rep_id = await _rep(client, h)
    cp = await _partner(client, h)
    [unit] = await _units(client, h, 1)
    lead = await _lead(client, h, "+919900500004", owner_id=owner_id, partner_id=cp)

    await _move(client, h, lead, "booked", assigned_to_id=rep_id, booking=_booking(unit))
    await _move(client, h, lead, "sold")

    commissions, payouts = await _money(lead)
    assert commissions == []
    assert len(payouts) == 1


@pytest.mark.asyncio
async def test_internal_sale_still_pays_the_salesperson(client):
    h = await _owner(client)
    owner_id = await _user_id(client, h, "owner@cp.example.com")
    rep_id = await _rep(client, h)
    [unit] = await _units(client, h, 1)
    lead = await _lead(client, h, "+919900500005", owner_id=owner_id)

    await _move(client, h, lead, "booked", assigned_to_id=rep_id, booking=_booking(unit))
    await _move(client, h, lead, "sold")

    commissions, payouts = await _money(lead)
    assert payouts == []
    assert any(str(c.user_id) == rep_id and c.amount > 0 for c in commissions), commissions


@pytest.mark.asyncio
async def test_owner_reference_without_a_partner_pays_nobody(client):
    h = await _owner(client)
    owner_id = await _user_id(client, h, "owner@cp.example.com")
    [unit] = await _units(client, h, 1)
    lead = await _lead(client, h, "+919900500006", owner_id=owner_id)

    await _move(client, h, lead, "booked", incentive_exempt=True, booking=_booking(unit))
    await _move(client, h, lead, "sold")

    commissions, payouts = await _money(lead)
    assert commissions == [] and payouts == []


@pytest.mark.asyncio
async def test_partner_funnel_counts(client):
    h = await _owner(client)
    owner_id = await _user_id(client, h, "owner@cp.example.com")
    cp = await _partner(client, h)
    other = await _partner(client, h, "Somani Realtor")
    units = await _units(client, h, 2)
    phones = iter(f"+9199006000{i:02d}" for i in range(1, 30))

    referred_only = await _lead(client, h, next(phones), owner_id=owner_id, partner_id=cp)
    visited_then_lost = await _lead(client, h, next(phones), owner_id=owner_id, partner_id=cp)
    await _move(client, h, visited_then_lost, "site_visit_done")
    await _move(client, h, visited_then_lost, "not_interested")
    booked = await _lead(client, h, next(phones), owner_id=owner_id, partner_id=cp)
    await _move(client, h, booked, "booked", booking=_booking(units[0]))
    sold = await _lead(client, h, next(phones), owner_id=owner_id, partner_id=cp)
    await _move(client, h, sold, "booked", booking=_booking(units[1]))
    await _move(client, h, sold, "sold")
    # A visit recorded on the site-visit calendar (completed) counts even if the stage never moved there.
    recorded_visit = await _lead(client, h, next(phones), owner_id=owner_id, partner_id=cp)
    project_id = (await client.get("/api/v1/inventory/projects", headers=h)).json()[0]["id"]
    visit = await client.post("/api/v1/site-visits", headers=h, json={
        "lead_id": recorded_visit, "project_id": project_id, "scheduled_at": "2026-10-10T10:00:00+05:30"})
    assert visit.status_code == 201, visit.text
    done = await client.patch(f"/api/v1/site-visits/{visit.json()['id']}", headers=h,
                              json={"status": "completed", "attended": True})
    assert done.status_code == 200, done.text
    # A scheduled (not yet done) visit doesn't count.
    scheduled_only = await _lead(client, h, next(phones), owner_id=owner_id, partner_id=cp)
    r = await client.post("/api/v1/site-visits", headers=h, json={
        "lead_id": scheduled_only, "project_id": project_id, "scheduled_at": "2026-10-20T10:00:00+05:30"})
    assert r.status_code == 201, r.text
    # Another partner's lead and an internal lead stay out of this partner's numbers.
    await _lead(client, h, next(phones), owner_id=owner_id, partner_id=other)
    await _lead(client, h, next(phones), owner_id=owner_id)

    roster = {p["id"]: p["stats"] for p in (await client.get("/api/v1/channel-partners", headers=h)).json()}
    stats = roster[cp]
    assert (stats["leads_total"], stats["leads_visited"], stats["leads_booked"], stats["leads_sold"]) == (6, 4, 2, 1), stats
    assert (roster[other]["leads_total"], roster[other]["leads_visited"]) == (1, 0)
    single = (await client.get(f"/api/v1/channel-partners/{cp}", headers=h)).json()["stats"]
    assert (single["leads_visited"], single["leads_booked"]) == (4, 2)
    assert referred_only  # (counted only in leads_total)
