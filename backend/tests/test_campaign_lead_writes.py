"""Every manual lead write maps its campaign onto the tenant's list: the New Lead form / API, edits, and CSV
imports. Reps pick from the list (unknown or deactivated names → 422 with a reason the UI shows); campaign
managers — by role or by a per-user grant — may add names; uploads never lose a row over its campaign."""
from __future__ import annotations

import csv
import io
from uuid import UUID

import pytest
from sqlalchemy import select

from app.database.session import db_manager
from app.models.campaign import Campaign
from app.models.lead import Lead

_phone_seq = iter(range(1, 10_000))


def _phone() -> str:
    return f"+9199008{next(_phone_seq):05d}"


async def _post_lead(client, headers, campaign: str | None):
    body = {"title": "Enquiry", "contact_name": "Asha Roy", "contact_phone": _phone()}
    if campaign is not None:
        body["campaign"] = campaign
    return await client.post("/api/v1/leads", headers=headers, json=body)


async def _campaign_rows() -> dict[str, Campaign]:
    async with db_manager.session_factory() as session:
        return {c.name: c for c in (await session.execute(select(Campaign))).scalars()}


async def _lead_campaign(lead_id: str) -> str | None:
    async with db_manager.session_factory() as session:
        return (await session.execute(select(Lead.campaign).where(Lead.id == UUID(lead_id)))).scalar_one()


async def _lead_count() -> int:
    async with db_manager.session_factory() as session:
        return len((await session.execute(select(Lead.id))).all())


async def _add_campaign(client, headers, name: str) -> dict:
    response = await client.post("/api/v1/campaigns", headers=headers, json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()


def _error(response) -> tuple[str, dict]:
    """(message, extra). The detail is FastAPI's field-error list so older clients also show the message."""
    body = response.json()["error"]
    assert body["detail"][0]["loc"] == ["body", "campaign"]
    return body["detail"][0]["msg"], body["extra"]


# ---- New Lead form / API --------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rep_cannot_invent_a_campaign_and_gets_a_did_you_mean(client, auth_headers, sales_headers):
    await _add_campaign(client, auth_headers, "Monsoon Offer")
    leads_before = await _lead_count()

    response = await _post_lead(client, sales_headers, "Monsoon Ofer")
    assert response.status_code == 422, response.text
    detail, extra = _error(response)
    assert extra == {"field": "campaign", "reason": "unknown_campaign", "suggestions": ["Monsoon Offer"]}
    assert "Monsoon Offer" in detail
    # Nothing was written: no lead, no new campaign.
    assert await _lead_count() == leads_before
    assert set(await _campaign_rows()) == {"Monsoon Offer"}


@pytest.mark.asyncio
async def test_rep_spelling_variant_is_stored_as_the_campaign_name(client, auth_headers, sales_headers):
    await _add_campaign(client, auth_headers, "Monsoon Offer")
    response = await _post_lead(client, sales_headers, "  monsoon   OFFER ")
    assert response.status_code == 201, response.text
    assert response.json()["campaign"] == "Monsoon Offer"


@pytest.mark.asyncio
async def test_blank_campaign_is_stored_as_none(client, sales_headers):
    response = await _post_lead(client, sales_headers, "   ")
    assert response.status_code == 201, response.text
    assert response.json()["campaign"] is None
    assert await _campaign_rows() == {}


@pytest.mark.asyncio
async def test_manager_may_add_a_new_name_from_the_form(client, auth_headers):
    response = await _post_lead(client, auth_headers, "  Brand   Day ")
    assert response.status_code == 201, response.text
    assert response.json()["campaign"] == "Brand Day"
    row = (await _campaign_rows())["Brand Day"]
    assert (row.source, row.needs_review, row.is_active) == ("manual", False, True)


@pytest.mark.asyncio
async def test_a_per_user_grant_lets_a_rep_add_names(client, auth_headers, sales_headers):
    assert (await _post_lead(client, sales_headers, "Rep Special")).status_code == 422
    users = (await client.get("/api/v1/users?page=1&page_size=20", headers=auth_headers)).json()["items"]
    rep = next(u for u in users if u["email"] == "sales@example.com")
    grant = await client.post(
        f"/api/v1/users/{rep['id']}/permissions", headers=auth_headers, json={"permission_code": "CAMPAIGN_MANAGE"}
    )
    assert grant.status_code == 201, grant.text
    response = await _post_lead(client, sales_headers, "Rep Special")
    assert response.status_code == 201, response.text
    assert "Rep Special" in await _campaign_rows()


@pytest.mark.asyncio
async def test_deactivated_campaign_is_for_managers_only(client, auth_headers, sales_headers):
    campaign = await _add_campaign(client, auth_headers, "Old Promo")
    await client.patch(f"/api/v1/campaigns/{campaign['id']}", headers=auth_headers, json={"is_active": False})

    refused = await _post_lead(client, sales_headers, "old promo")
    assert refused.status_code == 422
    assert _error(refused)[1]["reason"] == "inactive_campaign"
    allowed = await _post_lead(client, auth_headers, "old promo")
    assert allowed.status_code == 201 and allowed.json()["campaign"] == "Old Promo"


# ---- edits ------------------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_editing_a_lead_never_trips_over_its_existing_campaign(client, auth_headers, sales_headers):
    campaign = await _add_campaign(client, auth_headers, "Old Promo")
    lead_id = (await _post_lead(client, auth_headers, "Old Promo")).json()["id"]
    await client.patch(f"/api/v1/campaigns/{campaign['id']}", headers=auth_headers, json={"is_active": False})

    # The form re-sends the (now inactive) campaign with an unrelated change — any spelling — and it's fine.
    same = await client.put(
        f"/api/v1/leads/{lead_id}", headers=sales_headers, json={"title": "Updated", "campaign": "OLD PROMO"}
    )
    assert same.status_code == 200, same.text
    assert same.json()["title"] == "Updated"
    assert await _lead_campaign(lead_id) == "Old Promo"

    # Changing it to a name that isn't in the list is refused for a rep ...
    unknown = await client.put(f"/api/v1/leads/{lead_id}", headers=sales_headers, json={"campaign": "Fresh Thing"})
    assert unknown.status_code == 422 and _error(unknown)[1]["reason"] == "unknown_campaign"
    # ... clearing it is always allowed ...
    cleared = await client.put(f"/api/v1/leads/{lead_id}", headers=sales_headers, json={"campaign": ""})
    assert cleared.status_code == 200 and cleared.json()["campaign"] is None
    # ... and a known name is stored canonically.
    await _add_campaign(client, auth_headers, "Expo Fair")
    moved = await client.put(f"/api/v1/leads/{lead_id}", headers=sales_headers, json={"campaign": " expo FAIR"})
    assert moved.status_code == 200 and moved.json()["campaign"] == "Expo Fair"


# ---- CSV import -------------------------------------------------------------------------------------------

def _csv(rows: list[tuple[str, str, str]]) -> bytes:
    lines = ["contact_name,contact_phone,title,campaign", *(",".join(r) for r in rows)]
    return ("\n".join(lines) + "\n").encode("utf-8")


async def _import(client, headers, payload: bytes) -> dict:
    response = await client.post(
        "/api/v1/leads/import", headers=headers, files={"file": ("leads.csv", io.BytesIO(payload), "text/csv")}
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_rep_upload_keeps_every_row_and_flags_new_names(client, auth_headers, sales_headers):
    await _add_campaign(client, auth_headers, "Monsoon Offer")
    summary = await _import(client, sales_headers, _csv([
        ("Sneha Iyer", _phone(), "Lead A", " monsoon  offer"),
        ("Rohan T", _phone(), "Lead B", "Expo Fair"),
        ("Mira K", _phone(), "Lead C", "expo fair"),
    ]))
    assert summary["created"] == 3 and summary["errors"] == []
    rows = await _campaign_rows()
    assert set(rows) == {"Monsoon Offer", "Expo Fair"}
    assert (rows["Expo Fair"].source, rows["Expo Fair"].needs_review) == ("import", True)
    assert rows["Monsoon Offer"].needs_review is False
    listed = (await client.get("/api/v1/leads", headers=auth_headers, params={"page_size": 50})).json()["items"]
    assert sorted(item["campaign"] for item in listed) == ["Expo Fair", "Expo Fair", "Monsoon Offer"]


@pytest.mark.asyncio
async def test_manager_upload_adds_names_without_review(client, auth_headers):
    summary = await _import(client, auth_headers, _csv([("Sneha Iyer", _phone(), "Lead A", "Owner Expo")]))
    assert summary["created"] == 1
    row = (await _campaign_rows())["Owner Expo"]
    assert (row.source, row.needs_review) == ("import", False)


@pytest.mark.asyncio
async def test_import_template_has_no_built_in_campaign_names(client, auth_headers):
    response = await client.get("/api/v1/leads/import/template.csv", headers=auth_headers)
    assert response.status_code == 200
    rows = list(csv.DictReader(io.StringIO(response.text.lstrip("﻿"))))
    assert rows and "Campaign" in rows[0]
    assert {row["Campaign"] for row in rows} == {""}


# ---- list filter -----------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_filter_matches_any_spelling_of_the_campaign(client, auth_headers):
    await _add_campaign(client, auth_headers, "Monsoon Offer")
    lead_id = (await _post_lead(client, auth_headers, "Monsoon Offer")).json()["id"]
    other = (await _post_lead(client, auth_headers, "Expo Fair")).json()["id"]
    for spelling in ("Monsoon Offer", "monsoon offer", "  MONSOON   offer "):
        listed = await client.get("/api/v1/leads", headers=auth_headers, params={"campaign": spelling})
        ids = {item["id"] for item in listed.json()["items"]}
        assert ids == {lead_id}, spelling
    assert other not in ids
