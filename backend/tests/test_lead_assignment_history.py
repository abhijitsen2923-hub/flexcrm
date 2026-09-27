"""Owner-assignment history (GET /leads/{id}/assignments): every real owner change is logged with
from → to, who did it and how — on create / CSV upload, single + bulk reassign, and the Booked / Token
salesperson pick — while no-op changes log nothing and the stage history (which feeds commission and
the HR scorecard) is never touched.

Event order is not asserted where events can share a timestamp (SQLite's now() has 1-second
resolution); sets of (source, from, to) are compared instead.
"""
from __future__ import annotations

import io

import pytest


async def _user_id(client, headers, email: str) -> str:
    response = await client.get("/api/v1/users", headers=headers)
    assert response.status_code == 200, response.text
    return next(u["id"] for u in response.json()["items"] if u["email"] == email)


async def _create_lead(client, headers, phone: str, owner_id: str | None = None) -> str:
    body = {"title": "Assignment lead", "contact_name": "Asha Roy", "contact_phone": phone}
    if owner_id:
        body["assigned_to_id"] = owner_id
    response = await client.post("/api/v1/leads", headers=headers, json=body)
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _assignments(client, headers, lead_id: str) -> list[dict]:
    response = await client.get(f"/api/v1/leads/{lead_id}/assignments", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _changes(events: list[dict]) -> set[tuple[str, str | None, str | None]]:
    return {(e["source"], e["from_user_id"], e["to_user_id"]) for e in events}


async def _stage_history_count(client, headers, lead_id: str) -> int:
    response = await client.get(f"/api/v1/leads/{lead_id}/transitions", headers=headers)
    assert response.status_code == 200, response.text
    return len(response.json())


async def _reassign(client, headers, lead_id: str, owner_id: str | None) -> None:
    response = await client.put(f"/api/v1/leads/{lead_id}", headers=headers, json={"assigned_to_id": owner_id})
    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_create_with_owner_logs_the_initial_assignment(client, auth_headers, sales_headers):
    admin_id = await _user_id(client, auth_headers, "admin@example.com")
    counselor_id = await _user_id(client, auth_headers, "sales@example.com")

    lead_id = await _create_lead(client, auth_headers, "+919900300001", owner_id=counselor_id)

    events = await _assignments(client, auth_headers, lead_id)
    assert _changes(events) == {("created", None, counselor_id)}
    assert events[0]["performed_by_id"] == admin_id
    assert events[0]["to_user"]["first_name"] == "Sammy"  # names come back for display
    assert events[0]["from_user"] is None


@pytest.mark.asyncio
async def test_create_without_owner_logs_nothing(client, auth_headers):
    lead_id = await _create_lead(client, auth_headers, "+919900300002")
    assert await _assignments(client, auth_headers, lead_id) == []


@pytest.mark.asyncio
async def test_single_reassign_logs_real_changes_only_and_leaves_stage_history_alone(
    client, auth_headers, sales_headers
):
    admin_id = await _user_id(client, auth_headers, "admin@example.com")
    counselor_id = await _user_id(client, auth_headers, "sales@example.com")
    lead_id = await _create_lead(client, auth_headers, "+919900300003")

    await _reassign(client, auth_headers, lead_id, counselor_id)  # unassigned → counselor
    await _reassign(client, auth_headers, lead_id, counselor_id)  # same owner → nothing
    await _reassign(client, auth_headers, lead_id, admin_id)      # counselor → admin
    await _reassign(client, auth_headers, lead_id, None)          # admin → unassigned

    events = await _assignments(client, auth_headers, lead_id)
    assert len(events) == 3
    assert _changes(events) == {
        ("reassign", None, counselor_id),
        ("reassign", counselor_id, admin_id),
        ("reassign", admin_id, None),
    }
    assert {e["performed_by_id"] for e in events} == {admin_id}
    # Owner changes never go into stage_transitions (commission + HR scorecard read that table).
    assert await _stage_history_count(client, auth_headers, lead_id) == 1


@pytest.mark.asyncio
async def test_concurrent_reassign_records_the_owner_it_actually_replaced(
    client, auth_headers, sales_headers, monkeypatch
):
    """Two managers change the owner at once: M1's PUT (A → B) has already loaded the lead when M2's bulk
    reassign (A → C) commits. M1's history row must read C → B — the owner it really replaced — not a
    stale A → B that would break the chain."""
    from app.services.leads import LeadService

    admin_id = await _user_id(client, auth_headers, "admin@example.com")
    counselor_id = await _user_id(client, auth_headers, "sales@example.com")
    third = await client.post(
        "/api/v1/users",
        headers=auth_headers,
        json={"first_name": "Tara", "last_name": "Third", "email": "third@example.com",
              "password": "StrongPass123", "phone": "+1555000003", "role": "counselor", "status": "active"},
    )
    assert third.status_code == 201, third.text
    third_id = await _user_id(client, auth_headers, "third@example.com")
    lead_id = await _create_lead(client, auth_headers, "+919900300051", owner_id=admin_id)

    original = LeadService._ensure_references
    raced = False

    async def racing(self, customer_id, assigned_to_id):
        nonlocal raced
        if not raced and assigned_to_id is not None and str(assigned_to_id) == counselor_id:
            raced = True  # M2's bulk reassign lands while M1's request is in flight
            bulk = await client.post(
                "/api/v1/leads/bulk-reassign",
                headers=auth_headers,
                json={"lead_ids": [lead_id], "assigned_to_id": third_id},
            )
            assert bulk.status_code == 200, bulk.text
        return await original(self, customer_id, assigned_to_id)

    monkeypatch.setattr(LeadService, "_ensure_references", racing)
    await _reassign(client, auth_headers, lead_id, counselor_id)

    assert raced
    assert _changes(await _assignments(client, auth_headers, lead_id)) == {
        ("created", None, admin_id),
        ("bulk_reassign", admin_id, third_id),
        ("reassign", third_id, counselor_id),
    }


@pytest.mark.asyncio
async def test_bulk_reassign_logs_each_leads_previous_owner(client, auth_headers, sales_headers):
    admin_id = await _user_id(client, auth_headers, "admin@example.com")
    counselor_id = await _user_id(client, auth_headers, "sales@example.com")
    from_counselor = await _create_lead(client, auth_headers, "+919900300011", owner_id=counselor_id)
    unassigned = await _create_lead(client, auth_headers, "+919900300012")
    already_admin = await _create_lead(client, auth_headers, "+919900300013", owner_id=admin_id)

    response = await client.post(
        "/api/v1/leads/bulk-reassign",
        headers=auth_headers,
        json={"lead_ids": [from_counselor, unassigned, already_admin], "assigned_to_id": admin_id},
    )
    assert response.status_code == 200, response.text

    assert _changes(await _assignments(client, auth_headers, from_counselor)) == {
        ("created", None, counselor_id),
        ("bulk_reassign", counselor_id, admin_id),
    }
    assert _changes(await _assignments(client, auth_headers, unassigned)) == {("bulk_reassign", None, admin_id)}
    # Already owned by the target → no bulk event.
    assert _changes(await _assignments(client, auth_headers, already_admin)) == {("created", None, admin_id)}
    for lead_id in (from_counselor, unassigned, already_admin):
        assert await _stage_history_count(client, auth_headers, lead_id) == 1


@pytest.mark.asyncio
async def test_csv_upload_with_owner_logs_an_import_assignment(client, auth_headers, sales_headers):
    counselor_id = await _user_id(client, auth_headers, "sales@example.com")
    csv = b"contact_name,contact_phone,title,owner_email\nNeha Das,+919900300021,Uploaded lead,sales@example.com\n"

    response = await client.post(
        "/api/v1/leads/import",
        headers=auth_headers,
        files={"file": ("leads.csv", io.BytesIO(csv), "text/csv")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["created"] == 1

    listing = (await client.get("/api/v1/leads", headers=auth_headers)).json()["items"]
    lead_id = next(item["id"] for item in listing if item["title"] == "Uploaded lead")
    assert _changes(await _assignments(client, auth_headers, lead_id)) == {("import", None, counselor_id)}


# ---- Real-estate org: Booked / Token salesperson pick + rep access ------------------------------

async def _real_estate_org(client) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "Rita",
            "last_name": "Owner",
            "email": "owner@realty.example.com",
            "password": "StrongPass123",
            "role": "owner",
            "business_type": "real_estate",
            "organization_name": "Assign Realty",
        },
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _add_sales_executive(client, owner_headers, email: str) -> dict[str, str]:
    created = await client.post(
        "/api/v1/users",
        headers=owner_headers,
        json={
            "first_name": "Rinku",
            "last_name": "Kayal",
            "email": email,
            "password": "StrongPass123",
            "phone": "+919900399999",
            "role": "sales_executive",
            "status": "active",
        },
    )
    assert created.status_code == 201, created.text
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": "StrongPass123"})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _available_unit_id(client, owner_headers) -> str:
    created = await client.post(
        "/api/v1/inventory/projects/full",
        headers=owner_headers,
        json={
            "name": "Vriddhica Heritage",
            "builder_name": "Vriddhica",
            "location": "Kolkata",
            "city": "Kolkata",
            "towers": [
                {
                    "name": "A",
                    "total_floors": 1,
                    "unit_specs": [{"floors": [{"floor": 1, "count": 1}], "area": 1000, "base_price": 3500000}],
                }
            ],
        },
    )
    assert created.status_code == 201, created.text
    projects = (await client.get("/api/v1/inventory/projects", headers=owner_headers)).json()
    return next(
        unit["id"]
        for project in projects
        for tower in project["towers"]
        for unit in tower["units"]
        if unit["status"] == "available"
    )


@pytest.mark.asyncio
async def test_booking_salesperson_pick_is_logged(client):
    owner_headers = await _real_estate_org(client)
    await _add_sales_executive(client, owner_headers, "rinku@realty.example.com")
    owner_id = await _user_id(client, owner_headers, "owner@realty.example.com")
    rep_id = await _user_id(client, owner_headers, "rinku@realty.example.com")
    unit_id = await _available_unit_id(client, owner_headers)
    lead_id = await _create_lead(client, owner_headers, "+919900300031", owner_id=owner_id)

    response = await client.post(
        f"/api/v1/leads/{lead_id}/transitions",
        headers=owner_headers,
        json={
            "to_stage_code": "booked",
            "comment": "Token received for unit A-101.",
            "assigned_to_id": rep_id,
            "booking": {
                "unit_id": unit_id,
                "token_amount": 11000,
                "token_mode": "neft",
                "token_received_on": "2026-09-27",
            },
        },
    )
    assert response.status_code == 201, response.text

    assert _changes(await _assignments(client, owner_headers, lead_id)) == {
        ("created", None, owner_id),
        ("booking", owner_id, rep_id),
    }


@pytest.mark.asyncio
async def test_rep_cannot_read_another_owners_assignment_history(client):
    owner_headers = await _real_estate_org(client)
    rep_headers = await _add_sales_executive(client, owner_headers, "rep@realty.example.com")
    owner_id = await _user_id(client, owner_headers, "owner@realty.example.com")
    lead_id = await _create_lead(client, owner_headers, "+919900300041", owner_id=owner_id)

    response = await client.get(f"/api/v1/leads/{lead_id}/assignments", headers=rep_headers)

    assert response.status_code == 404  # same anti-poaching rule as the stage history
