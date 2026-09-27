"""Leads list — "Lead date" filter (created_from / created_to on the lead's Created / enquiry date).

Reported: picking a date and then a campaign or source listed that campaign's leads from OTHER days —
the only date filters were "next action due" and "stage changed", neither of which is the date shown
on the lead. The lead-date range must AND with every other filter, for managers and for reps.

The client sends the selected LOCAL days as UTC instants, half-open: created_from <= created_at <
created_to. Timestamps are stored in UTC here (the SQLite harness keeps wall-clock values).
"""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy import update

from app.database.session import db_manager
from app.models.lead import Lead

# 20 Sep 2026 in IST (UTC+05:30) as the client sends it: [2026-09-19T18:30Z, 2026-09-20T18:30Z).
IST_SEP_20 = {"created_from": "2026-09-19T18:30:00Z", "created_to": "2026-09-20T18:30:00Z"}


async def _create_lead(client, headers, phone: str, *, campaign: str, source: str, owner_id: str | None = None) -> str:
    body = {"title": f"{campaign} lead", "contact_name": "Asha Roy", "contact_phone": phone,
            "campaign": campaign, "source": source}
    if owner_id:
        body["assigned_to_id"] = owner_id
    response = await client.post("/api/v1/leads", headers=headers, json=body)
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _set_created_at(lead_id: str, when: datetime) -> None:
    async with db_manager.session_factory() as session:
        await session.execute(update(Lead).where(Lead.id == UUID(lead_id)).values(created_at=when))
        await session.commit()


async def _ids(client, headers, **params) -> set[str]:
    response = await client.get("/api/v1/leads", headers=headers, params={"page_size": 100, **params})
    assert response.status_code == 200, response.text
    return {item["id"] for item in response.json()["items"]}


@pytest_asyncio.fixture
async def dated_leads(client, auth_headers) -> dict[str, str]:
    leads = {
        # 20 Sep IST 10:00 = 04:30Z
        "diwali_20": await _create_lead(client, auth_headers, "+919900400001", campaign="Diwali", source="Website"),
        # 22 Sep IST
        "diwali_22": await _create_lead(client, auth_headers, "+919900400002", campaign="Diwali", source="Website"),
        # 20 Sep IST 23:59 = 18:29Z — still the 20th locally
        "summer_20": await _create_lead(client, auth_headers, "+919900400003", campaign="Summer", source="Referral"),
        # 21 Sep IST 00:00 = 20 Sep 18:30Z — the (exclusive) upper bound of the 20th
        "summer_21": await _create_lead(client, auth_headers, "+919900400004", campaign="Summer", source="Website"),
    }
    await _set_created_at(leads["diwali_20"], datetime(2026, 9, 20, 4, 30, tzinfo=UTC))
    await _set_created_at(leads["diwali_22"], datetime(2026, 9, 22, 4, 30, tzinfo=UTC))
    await _set_created_at(leads["summer_20"], datetime(2026, 9, 20, 18, 29, tzinfo=UTC))
    await _set_created_at(leads["summer_21"], datetime(2026, 9, 20, 18, 30, tzinfo=UTC))
    return leads


@pytest.mark.asyncio
async def test_lead_date_alone_returns_only_that_days_leads(client, auth_headers, dated_leads):
    assert await _ids(client, auth_headers, **IST_SEP_20) == {dated_leads["diwali_20"], dated_leads["summer_20"]}


@pytest.mark.asyncio
async def test_lead_date_and_campaign_are_combined(client, auth_headers, dated_leads):
    # The reported bug: the 22 Sep Diwali lead must NOT appear when the 20th is selected.
    assert await _ids(client, auth_headers, campaign="Diwali", **IST_SEP_20) == {dated_leads["diwali_20"]}
    assert await _ids(client, auth_headers, campaign="Diwali") == {dated_leads["diwali_20"], dated_leads["diwali_22"]}


@pytest.mark.asyncio
async def test_lead_date_and_source_are_combined(client, auth_headers, dated_leads):
    assert await _ids(client, auth_headers, source="Website", **IST_SEP_20) == {dated_leads["diwali_20"]}


@pytest.mark.asyncio
async def test_open_ended_lead_date_ranges(client, auth_headers, dated_leads):
    assert await _ids(client, auth_headers, created_from="2026-09-21T18:30:00Z") == {dated_leads["diwali_22"]}
    assert await _ids(client, auth_headers, created_to="2026-09-20T18:30:00Z") == {
        dated_leads["diwali_20"], dated_leads["summer_20"]
    }


# ---- Executive (assigned-only rep) side ------------------------------------------------------------

async def _real_estate_owner_and_rep(client) -> tuple[dict[str, str], dict[str, str], str]:
    owner = await client.post(
        "/api/v1/auth/register",
        json={"first_name": "Rita", "last_name": "Owner", "email": "owner@dates.example.com",
              "password": "StrongPass123", "role": "owner", "business_type": "real_estate",
              "organization_name": "Dates Realty"},
    )
    assert owner.status_code == 201, owner.text
    owner_headers = {"Authorization": f"Bearer {owner.json()['access_token']}"}
    created = await client.post(
        "/api/v1/users",
        headers=owner_headers,
        json={"first_name": "Rinku", "last_name": "Kayal", "email": "rep@dates.example.com",
              "password": "StrongPass123", "phone": "+919900499999", "role": "sales_executive", "status": "active"},
    )
    assert created.status_code == 201, created.text
    login = await client.post("/api/v1/auth/login", json={"email": "rep@dates.example.com", "password": "StrongPass123"})
    assert login.status_code == 200, login.text
    return owner_headers, {"Authorization": f"Bearer {login.json()['access_token']}"}, created.json()["id"]


@pytest.mark.asyncio
async def test_executive_lead_date_filter_is_scoped_and_combined(client):
    owner_headers, rep_headers, rep_id = await _real_estate_owner_and_rep(client)
    mine_20 = await _create_lead(client, owner_headers, "+919900400011", campaign="Diwali", source="Website", owner_id=rep_id)
    mine_22 = await _create_lead(client, owner_headers, "+919900400012", campaign="Diwali", source="Website", owner_id=rep_id)
    not_mine_20 = await _create_lead(client, owner_headers, "+919900400013", campaign="Diwali", source="Website")
    await _set_created_at(mine_20, datetime(2026, 9, 20, 4, 30, tzinfo=UTC))
    await _set_created_at(mine_22, datetime(2026, 9, 22, 4, 30, tzinfo=UTC))
    await _set_created_at(not_mine_20, datetime(2026, 9, 20, 4, 30, tzinfo=UTC))

    assert await _ids(client, rep_headers, **IST_SEP_20) == {mine_20}
    assert await _ids(client, rep_headers, campaign="Diwali", **IST_SEP_20) == {mine_20}
