"""Booking events move the buyer's lead forward (app/real_estate/lead_sync.py).

A payment → Agreement / Payment, the registration → Registration, a fully ticked possession checklist → Possession.
Forward only (never backward, never a closed lead, nothing when already there — so no duplicate history row), never
Sold, recorded as the system (performed_by NULL) with a comment naming who recorded it, the follow-up date kept, and a
move that fails never fails or undoes the payment / registration / checklist. Only a lead already at Booked / Token or
later moves, and only when the user who recorded the event could make that move by hand. The accounts role
(FINANCE_VIEW, no LEAD_VIEW) can list a customer's purchases but still can't move stages.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions import ValidationError
from app.database.session import db_manager
from app.models.lead import Lead
from app.models.stage_transition import StageTransition
from app.real_estate import lead_sync
from app.real_estate.models import PaymentReceipt
from app.services import base as service_base
from app.services.stage_transitions import StageTransitionService

API = "/api/v1"
TODAY = date.today()
FOLLOW_UP = "2027-01-15T10:30:00+00:00"
FULL_CHECKLIST = [True] * lead_sync.POSSESSION_CHECKLIST_ITEMS


@pytest_asyncio.fixture
async def owner(client) -> dict[str, str]:
    response = await client.post(
        f"{API}/auth/register",
        json={"first_name": "Riya", "last_name": "Builder", "email": "owner@sync.example.com",
              "password": "StrongPass123", "phone": "+1555000401", "role": "owner",
              "business_type": "real_estate", "organization_name": "Sync Realty"},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _units(client, headers) -> list[dict]:
    created = await client.post(f"{API}/inventory/projects/full", headers=headers, json={
        "name": "Skyline", "builder_name": "Acme", "location": "Salt Lake", "city": "Kolkata",
        "towers": [{"name": "Tower A", "total_floors": 2, "unit_specs": [
            {"unit_type": "residential", "floors": [{"floor": 1, "count": 3}, {"floor": 2, "count": 3}],
             "area": 1200, "base_price": 5_000_000}]}],
        "parking": {},
    })
    assert created.status_code == 201, created.text
    return sorted((u for t in created.json()["towers"] for u in t["units"]), key=lambda u: u["unit_number"])


async def _booked_lead(
    client, headers, unit_id: str, phone: str, assigned_to: str | None = None
) -> tuple[str, dict]:
    """A lead moved to Booked / Token (with a follow-up date) → (lead id, its booking). Owned by `assigned_to`, else
    by whoever moved it."""
    lead = await client.post(
        f"{API}/leads", headers=headers,
        json={"title": "Flat enquiry", "contact_name": "Asha Roy", "contact_phone": phone,
              **({"assigned_to_id": assigned_to} if assigned_to else {})},
    )
    assert lead.status_code == 201, lead.text
    lead_id = lead.json()["id"]
    await _move(client, headers, lead_id, "booked", next_action_date=FOLLOW_UP,
                booking={"unit_id": unit_id, "token_amount": 11000, "token_mode": "neft",
                         "token_received_on": TODAY.isoformat()})
    [booking] = (await client.get(f"{API}/bookings", headers=headers, params={"lead_id": lead_id})).json()
    return lead_id, booking


async def _move(client, headers, lead_id: str, stage: str, expect: int = 201, **extra):
    response = await client.post(
        f"{API}/leads/{lead_id}/transitions", headers=headers,
        json={"to_stage_code": stage, "comment": f"Moving to {stage} by hand.", **extra},
    )
    assert response.status_code == expect, response.text
    return response


async def _pay(client, headers, booking_id: str, amount=50000, expect: int = 200) -> dict:
    response = await client.post(
        f"{API}/bookings/{booking_id}/payments", headers=headers,
        json={"amount": amount, "paid_on": TODAY.isoformat(), "mode": "neft"},
    )
    assert response.status_code == expect, response.text
    return response.json()


async def _lead(lead_id: str) -> Lead:
    async with db_manager.session_factory() as session:
        return await session.get(Lead, UUID(lead_id))


async def _history(lead_id: str) -> list[StageTransition]:
    async with db_manager.session_factory() as session:
        return list((await session.scalars(
            select(StageTransition).where(StageTransition.lead_id == UUID(lead_id))
            .order_by(StageTransition.performed_at)
        )).all())


async def _auto_rows(lead_id: str) -> list[StageTransition]:
    return [t for t in await _history(lead_id) if t.comment.startswith("Auto:")]


async def _confirm(client, headers, booking_id: str) -> None:
    response = await client.post(f"{API}/bookings/{booking_id}/step/4", headers=headers, json={"confirm": True})
    assert response.status_code == 200, response.text


# ---------------------------------------------------------------------------
# Payment → Agreement / Payment
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_payment_moves_the_lead_to_agreement_payment_once(client, owner, monkeypatch):
    wipes: list[int] = []

    async def _count_wipe():
        wipes.append(1)

    monkeypatch.setattr(service_base, "invalidate_reporting_cache_now", _count_wipe)
    [unit, *_] = await _units(client, owner)
    lead_id, booking = await _booked_lead(client, owner, unit["id"], "+919900820001")
    wipes.clear()

    await _pay(client, owner, booking["id"], 500000)
    lead = await _lead(lead_id)
    assert lead.stage_code == "agreement_payment"
    assert lead.next_action_date is not None and lead.next_action_date.isoformat().startswith("2027-01-15T10:30")
    [auto] = await _auto_rows(lead_id)
    assert (auto.from_stage_code, auto.to_stage_code, auto.performed_by_id) == ("booked", "agreement_payment", None)
    assert auto.comment == f"Auto: ₹5,00,000 received on unit {unit['unit_number']} — recorded by Riya Builder."
    assert wipes == [1]  # the reporting cache was wiped by the move

    # A second payment: the lead is already there — no second history row.
    await _pay(client, owner, booking["id"], 25000)
    assert len(await _auto_rows(lead_id)) == 1
    assert (await _lead(lead_id)).stage_code == "agreement_payment"

    # The stage history API shows the system move with no performer.
    listed = await client.get(f"{API}/leads/{lead_id}/transitions", headers=owner)
    assert listed.status_code == 200, listed.text
    auto_entry = next(t for t in listed.json() if t["to_stage_code"] == "agreement_payment")
    assert (auto_entry["performed_by_id"], auto_entry["performed_by"]) == (None, None)


@pytest.mark.asyncio
async def test_no_move_when_the_lead_is_past_the_target_or_lost(client, owner):
    units = await _units(client, owner)
    past, past_booking = await _booked_lead(client, owner, units[0]["id"], "+919900820002")
    await _move(client, owner, past, "registration")
    lost, lost_booking = await _booked_lead(client, owner, units[1]["id"], "+919900820003")
    await _move(client, owner, lost, "not_interested")

    await _pay(client, owner, past_booking["id"])
    await _pay(client, owner, lost_booking["id"])
    assert (await _lead(past)).stage_code == "registration"
    assert (await _lead(lost)).stage_code == "not_interested"
    assert await _auto_rows(past) == [] and await _auto_rows(lost) == []


@pytest.mark.asyncio
async def test_a_failed_move_never_fails_or_undoes_the_payment(client, owner, monkeypatch):
    units = await _units(client, owner)
    lead_id, booking = await _booked_lead(client, owner, units[0]["id"], "+919900820004")

    async def _half_done_then_boom(self, lead_id, payload, **kwargs):
        lead = await self.session.get(Lead, lead_id)
        lead.stage_code = "possession"  # a half-written move that must be rolled back
        await self.session.flush()
        raise RuntimeError("boom")

    monkeypatch.setattr(StageTransitionService, "create_transition", _half_done_then_boom)
    paid = await _pay(client, owner, booking["id"], 70000)
    assert sum(Decimal(str(r["amount"])) for r in paid["payment_receipts"]) == Decimal("81000.00")
    assert (await _lead(lead_id)).stage_code == "booked"

    for error in (ValidationError("Not allowed."), SQLAlchemyError("db hiccup")):
        async def _raise(self, lead_id, payload, _error=error, **kwargs):
            raise _error

        monkeypatch.setattr(StageTransitionService, "create_transition", _raise)
        await _pay(client, owner, booking["id"], 1000)
    async with db_manager.session_factory() as session:
        amounts = sorted((await session.scalars(
            select(PaymentReceipt.amount).where(PaymentReceipt.booking_id == UUID(booking["id"]))
        )).all())
    assert amounts == [Decimal("1000.00"), Decimal("1000.00"), Decimal("11000.00"), Decimal("70000.00")]
    assert (await _lead(lead_id)).stage_code == "booked"
    assert await _auto_rows(lead_id) == []


# ---------------------------------------------------------------------------
# Registration, possession, never Sold
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_registration_moves_the_lead_to_registration(client, owner):
    [unit, *_] = await _units(client, owner)
    lead_id, booking = await _booked_lead(client, owner, unit["id"], "+919900820005")
    await _confirm(client, owner, booking["id"])

    registered = await client.post(
        f"{API}/bookings/{booking['id']}/register", headers=owner,
        json={"registration_date": TODAY.isoformat(), "registration_number": "REG-77"},
    )
    assert registered.status_code == 200, registered.text
    assert (await _lead(lead_id)).stage_code == "registration"
    [auto] = await _auto_rows(lead_id)
    assert (auto.from_stage_code, auto.performed_by_id) == ("booked", None)
    assert auto.comment == (
        f"Auto: unit {unit['unit_number']} registered (registration no. REG-77) — recorded by Riya Builder."
    )
    # A payment after registration never moves it back to Agreement / Payment.
    await _pay(client, owner, booking["id"])
    assert (await _lead(lead_id)).stage_code == "registration"
    assert len(await _auto_rows(lead_id)) == 1


@pytest.mark.asyncio
async def test_full_checklist_moves_to_possession_partial_does_not(client, owner):
    [unit, *_] = await _units(client, owner)
    lead_id, booking = await _booked_lead(client, owner, unit["id"], "+919900820006")
    url = f"{API}/bookings/{booking['id']}/possession"

    for partial in ([True] * 6 + [False], [True] * 3, []):
        saved = await client.put(url, headers=owner, json={"checklist": partial})
        assert saved.status_code == 200, saved.text
        assert (await _lead(lead_id)).stage_code == "booked"

    done = await client.put(url, headers=owner, json={"checklist": FULL_CHECKLIST})
    assert done.status_code == 200, done.text
    assert done.json()["possession_checklist"] == FULL_CHECKLIST
    assert (await _lead(lead_id)).stage_code == "possession"
    [auto] = await _auto_rows(lead_id)
    assert auto.comment == (
        f"Auto: possession handed over on unit {unit['unit_number']} (checklist complete) — recorded by Riya Builder."
    )


@pytest.mark.asyncio
async def test_nothing_ever_moves_a_lead_to_sold(client, owner):
    [unit, *_] = await _units(client, owner)
    lead_id, booking = await _booked_lead(client, owner, unit["id"], "+919900820007")
    await _move(client, owner, lead_id, "possession")

    await _pay(client, owner, booking["id"])
    saved = await client.put(f"{API}/bookings/{booking['id']}/possession", headers=owner,
                             json={"checklist": FULL_CHECKLIST})
    assert saved.status_code == 200, saved.text
    assert (await _lead(lead_id)).stage_code == "possession"
    assert "sold" not in lead_sync.AUTO_STAGE_TARGETS

    async with db_manager.session_factory() as session:
        assert await lead_sync.advance_lead_after(
            session, UUID(booking["id"]), "sold", "Auto: close the sale now.", actor=None
        ) is False
    assert (await _lead(lead_id)).stage_code == "possession"
    assert await _auto_rows(lead_id) == []


@pytest.mark.asyncio
async def test_payment_on_a_booking_without_a_lead_is_unaffected(client, owner):
    [unit, *_] = await _units(client, owner)
    created = await client.post(f"{API}/bookings", headers=owner, json={"unit_id": unit["id"]})
    assert created.status_code == 201, created.text
    paid = await _pay(client, owner, created.json()["id"], 1234)
    assert [Decimal(str(r["amount"])) for r in paid["payment_receipts"]] == [Decimal("1234.00")]


# ---------------------------------------------------------------------------
# Only moves the recording user could make, only from Booked / Token on
# ---------------------------------------------------------------------------

async def _user(client, owner, role: str, email: str, phone: str) -> tuple[dict, str]:
    created = await client.post(f"{API}/users", headers=owner, json={
        "first_name": "Team", "last_name": role.replace("_", " ").title(), "email": email,
        "password": "StrongPass123", "phone": phone, "role": role, "status": "active"})
    assert created.status_code == 201, created.text
    login = await client.post(f"{API}/auth/login", json={"email": email, "password": "StrongPass123"})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}, created.json()["id"]


async def _register(client, headers, booking_id: str) -> None:
    registered = await client.post(
        f"{API}/bookings/{booking_id}/register", headers=headers,
        json={"registration_date": TODAY.isoformat(), "registration_number": "REG-1"},
    )
    assert registered.status_code == 200, registered.text
    assert registered.json()["registration_number"] == "REG-1"  # the write itself always stands


async def _tick_all(client, headers, booking_id: str) -> None:
    saved = await client.put(f"{API}/bookings/{booking_id}/possession", headers=headers,
                             json={"checklist": FULL_CHECKLIST})
    assert saved.status_code == 200, saved.text
    assert saved.json()["possession_checklist"] == FULL_CHECKLIST


@pytest.mark.asyncio
async def test_no_move_unless_the_recording_user_could_make_it_by_hand(client, owner):
    units = await _units(client, owner)
    telecaller, _ = await _user(client, owner, "telecaller", "tele@sync.example.com", "+919900820091")
    rep, rep_id = await _user(client, owner, "sales_executive", "rep@sync.example.com", "+919900820092")
    crm, _ = await _user(client, owner, "crm_team", "crm@sync.example.com", "+919900820093")

    # A telecaller can't set Registration or Possession by hand: recording them moves nothing.
    lead_id, booking = await _booked_lead(client, owner, units[0]["id"], "+919900820011")
    await _confirm(client, owner, booking["id"])
    await _register(client, telecaller, booking["id"])
    await _tick_all(client, telecaller, booking["id"])
    assert (await _lead(lead_id)).stage_code == "booked"
    assert await _auto_rows(lead_id) == []

    # A sales executive works only their own leads: another owner's lead isn't moved, their own is.
    others, others_booking = await _booked_lead(client, owner, units[1]["id"], "+919900820012")
    own, own_booking = await _booked_lead(client, owner, units[2]["id"], "+919900820013", assigned_to=rep_id)
    await _tick_all(client, rep, others_booking["id"])
    await _tick_all(client, rep, own_booking["id"])
    assert (await _lead(others)).stage_code == "booked"
    assert await _auto_rows(others) == []
    assert (await _lead(own)).stage_code == "possession"
    [auto] = await _auto_rows(own)
    assert auto.performed_by_id is None
    assert auto.comment.endswith("— recorded by Team Sales Executive.")

    # CRM may set Registration and isn't limited to its own leads.
    crm_lead, crm_booking = await _booked_lead(client, owner, units[3]["id"], "+919900820014")
    await _confirm(client, owner, crm_booking["id"])
    await _register(client, crm, crm_booking["id"])
    assert (await _lead(crm_lead)).stage_code == "registration"
    [auto] = await _auto_rows(crm_lead)
    assert auto.performed_by_id is None


@pytest.mark.asyncio
async def test_no_move_for_a_lead_that_never_reached_booked(client, owner):
    units = await _units(client, owner)
    for stage, unit, phone in (("new_enquiry", units[0], "+919900820021"), ("interested", units[1], "+919900820022")):
        lead = await client.post(f"{API}/leads", headers=owner, json={
            "title": "Flat enquiry", "contact_name": "Asha Roy", "contact_phone": phone})
        assert lead.status_code == 201, lead.text
        lead_id = lead.json()["id"]
        if stage != "new_enquiry":
            await _move(client, owner, lead_id, stage)
        created = await client.post(f"{API}/bookings", headers=owner, json={"unit_id": unit["id"], "lead_id": lead_id})
        assert created.status_code == 201, created.text
        booking_id = created.json()["id"]

        await _pay(client, owner, booking_id, 50000)
        await _confirm(client, owner, booking_id)
        await _register(client, owner, booking_id)
        await _tick_all(client, owner, booking_id)
        assert (await _lead(lead_id)).stage_code == stage
        assert await _auto_rows(lead_id) == []


# ---------------------------------------------------------------------------
# The accounts role
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_finance_view_only_user_lists_purchases_but_cannot_move_stages(client, owner):
    [unit, *_] = await _units(client, owner)
    lead_id, booking = await _booked_lead(client, owner, unit["id"], "+919900820008")
    customer_id = booking["customer_id"]
    assert customer_id

    created = await client.post(f"{API}/users", headers=owner, json={
        "first_name": "Asha", "last_name": "Accounts", "email": "accounts@sync.example.com",
        "password": "StrongPass123", "phone": "+919900820099", "role": "accounts", "status": "active"})
    assert created.status_code == 201, created.text
    login = await client.post(f"{API}/auth/login",
                              json={"email": "accounts@sync.example.com", "password": "StrongPass123"})
    accounts = {"Authorization": f"Bearer {login.json()['access_token']}"}

    listed = await client.get(f"{API}/bookings", headers=accounts, params={"customer_id": customer_id})
    assert listed.status_code == 200, listed.text
    assert [b["id"] for b in listed.json()] == [booking["id"]]
    # Nothing else widened: no lead stage moves, no single-booking read, no booking edits.
    await _move(client, accounts, lead_id, "agreement_payment", expect=403)
    assert (await client.get(f"{API}/bookings/{booking['id']}", headers=accounts)).status_code == 403
    assert (await client.put(f"{API}/bookings/{booking['id']}/possession", headers=accounts,
                             json={"checklist": FULL_CHECKLIST})).status_code == 403

    # Recording a payment (their job) still moves the lead — as the system, naming them.
    await _pay(client, accounts, booking["id"], 200000)
    assert (await _lead(lead_id)).stage_code == "agreement_payment"
    [auto] = await _auto_rows(lead_id)
    assert auto.performed_by_id is None
    assert auto.comment.endswith("— recorded by Asha Accounts.")


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def test_format_inr_uses_indian_grouping():
    assert lead_sync.format_inr(500000) == "₹5,00,000"
    assert lead_sync.format_inr(Decimal("10000000")) == "₹1,00,00,000"
    assert lead_sync.format_inr(Decimal("999")) == "₹999"
    assert lead_sync.format_inr(Decimal("1234.5")) == "₹1,234.50"
    assert lead_sync.format_inr("abc") == "₹abc"


def test_possession_is_complete_only_when_every_item_is_ticked():
    assert lead_sync.possession_complete([True] * 7)
    assert lead_sync.possession_complete([True] * 8)
    assert not lead_sync.possession_complete([True] * 6)
    assert not lead_sync.possession_complete([True] * 6 + [False])
    assert not lead_sync.possession_complete(None)
    assert not lead_sync.possession_complete([1] * 7)
