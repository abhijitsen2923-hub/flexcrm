"""The tenant's own campaign list (/api/v1/campaigns): seeded only from the tenant's own leads, one stored
spelling per campaign, and the manager tools (add / rename / merge / clear / (de)activate / old spellings).

Harness limit: the SQLite harness collapses every tenant schema into one, so isolation BETWEEN tenants
can't be shown here (the campaign tables live in the tenant schema like leads). Neutral names only."""
from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import select, text, update

from app.core.permissions import PermissionCode, effective_permissions_for_role
from app.database.enums import UserRole
from app.database.session import db_manager
from app.models.campaign import Campaign, CampaignAlias
from app.models.lead import Lead
from app.services.realtime import realtime_manager

_phone_seq = iter(range(1, 10_000))


async def _lead(client, headers, campaign: str | None = None) -> str:
    body = {"title": "Enquiry", "contact_name": "Asha Roy", "contact_phone": f"+9199007{next(_phone_seq):05d}"}
    if campaign is not None:
        body["campaign"] = campaign
    response = await client.post("/api/v1/leads", headers=headers, json=body)
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _store(lead_id: str, value: str | None) -> None:
    """Write a campaign spelling straight to the row, as data from before campaign lists existed."""
    async with db_manager.session_factory() as session:
        await session.execute(update(Lead).where(Lead.id == UUID(lead_id)).values(campaign=value))
        await session.commit()


async def _row(lead_id: str) -> Lead:
    async with db_manager.session_factory() as session:
        return (await session.execute(select(Lead).where(Lead.id == UUID(lead_id)))).scalar_one()


async def _campaign_of(lead_id: str) -> str | None:
    return (await _row(lead_id)).campaign


async def _names(client, headers, **params) -> list[str]:
    response = await client.get("/api/v1/campaigns", headers=headers, params=params)
    assert response.status_code == 200, response.text
    return [c["name"] for c in response.json()]


async def _manage(client, headers) -> dict[str, dict]:
    response = await client.get("/api/v1/campaigns/manage", headers=headers)
    assert response.status_code == 200, response.text
    return {item["name"]: item for item in response.json()["items"]}


async def _create(client, headers, name: str) -> dict:
    response = await client.post("/api/v1/campaigns", headers=headers, json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()


def _reason(response) -> str | None:
    return response.json()["error"]["extra"].get("reason")


# ---- seeding + one spelling per campaign --------------------------------------------------------------

@pytest.mark.asyncio
async def test_new_tenant_starts_with_an_empty_list(client, auth_headers):
    # No built-in / shared campaign names: a tenant's list comes only from its own data.
    assert await _names(client, auth_headers) == []
    response = await client.get("/api/v1/campaigns/manage", headers=auth_headers)
    assert response.json() == {"items": [], "suggestions": []}


@pytest.mark.asyncio
async def test_list_is_seeded_from_the_tenants_leads_and_spellings_are_unified(client, auth_headers):
    ids = [await _lead(client, auth_headers) for _ in range(6)]
    spellings = ["Monsoon Offer", "Monsoon Offer", "monsoon  offer", " MONSOON OFFER ", "Expo Fair", "   "]
    for lead_id, value in zip(ids, spellings):
        await _store(lead_id, value)
    before = {lead_id: (await _row(lead_id)).updated_at for lead_id in ids}

    # The most frequent spelling becomes the campaign's name; case/space variants are the same campaign.
    assert await _names(client, auth_headers) == ["Expo Fair", "Monsoon Offer"]
    assert [await _campaign_of(i) for i in ids] == ["Monsoon Offer"] * 4 + ["Expo Fair", None]
    # Housekeeping, not a user edit: updated_at is untouched.
    assert {i: (await _row(i)).updated_at for i in ids} == before

    # Idempotent.
    assert await _names(client, auth_headers) == ["Expo Fair", "Monsoon Offer"]
    manage = await _manage(client, auth_headers)
    assert {name: item["lead_count"] for name, item in manage.items()} == {"Expo Fair": 1, "Monsoon Offer": 4}
    assert {item["source"] for item in manage.values()} == {"existing"}
    assert not any(item["needs_review"] for item in manage.values())


@pytest.mark.asyncio
async def test_leads_campaign_filter_list_shows_one_name_per_campaign(client, auth_headers):
    ids = [await _lead(client, auth_headers) for _ in range(3)]
    for lead_id, value in zip(ids, ["Monsoon Offer", "monsoon offer", "Expo Fair"]):
        await _store(lead_id, value)
    # Even before the list is synced, variants collapse to one entry per campaign.
    listed = (await client.get("/api/v1/leads/campaigns", headers=auth_headers)).json()
    assert sorted(v.lower() for v in listed) == ["expo fair", "monsoon offer"]

    await _names(client, auth_headers)  # sync
    assert (await client.get("/api/v1/leads/campaigns", headers=auth_headers)).json() == [
        "Expo Fair", "Monsoon Offer"
    ]


# ---- permissions ----------------------------------------------------------------------------------------

def test_campaign_manage_role_defaults():
    for role in (UserRole.owner, UserRole.sales_manager, UserRole.academic_admin, UserRole.ops_manager):
        assert PermissionCode.CAMPAIGN_MANAGE in effective_permissions_for_role(role), role
    for role in (UserRole.counselor, UserRole.sales_executive, UserRole.telecaller):
        assert PermissionCode.CAMPAIGN_MANAGE not in effective_permissions_for_role(role), role


@pytest.mark.asyncio
async def test_reps_read_the_list_but_cannot_change_it(client, auth_headers, sales_headers):
    campaign = await _create(client, auth_headers, "Monsoon Offer")
    other = await _create(client, auth_headers, "Expo Fair")
    assert await _names(client, sales_headers) == ["Expo Fair", "Monsoon Offer"]

    cid = campaign["id"]
    attempts = [
        client.get("/api/v1/campaigns/manage", headers=sales_headers),
        client.post("/api/v1/campaigns", headers=sales_headers, json={"name": "Rep Idea"}),
        client.post("/api/v1/campaigns/merge", headers=sales_headers,
                    json={"source_ids": [other["id"]], "target_id": cid}),
        client.patch(f"/api/v1/campaigns/{cid}", headers=sales_headers, json={"is_active": False}),
        client.post(f"/api/v1/campaigns/{cid}/rename", headers=sales_headers, json={"name": "X"}),
        client.post(f"/api/v1/campaigns/{cid}/clear", headers=sales_headers),
        client.delete(f"/api/v1/campaigns/{cid}/aliases/{cid}", headers=sales_headers),
    ]
    for attempt in attempts:
        response = await attempt
        assert response.status_code == 403, response.text
    assert await _names(client, auth_headers) == ["Expo Fair", "Monsoon Offer"]


# ---- manager tools --------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_add_cleans_the_name_and_refuses_duplicates(client, auth_headers):
    created = await _create(client, auth_headers, "  Monsoon    Offer ")
    assert (created["name"], created["source"], created["needs_review"]) == ("Monsoon Offer", "manual", False)
    duplicate = await client.post("/api/v1/campaigns", headers=auth_headers, json={"name": "monsoon offer"})
    assert duplicate.status_code == 409
    assert _reason(duplicate) == "name_exists"
    assert duplicate.json()["error"]["extra"]["conflict_campaign_id"] == created["id"]


@pytest.mark.asyncio
async def test_rename_rewrites_leads_and_remembers_the_old_spelling(client, auth_headers, sales_headers):
    campaign = await _create(client, auth_headers, "Monsoon Ofer")
    lead_id = await _lead(client, auth_headers, "Monsoon Ofer")

    renamed = await client.post(
        f"/api/v1/campaigns/{campaign['id']}/rename", headers=auth_headers, json={"name": "Monsoon Offer"}
    )
    assert renamed.status_code == 200, renamed.text
    body = renamed.json()
    assert body["leads_updated"] == 1
    assert body["campaign"]["name"] == "Monsoon Offer"
    assert [(a["alias"], a["kind"]) for a in body["campaign"]["aliases"]] == [("Monsoon Ofer", "rename")]
    assert await _campaign_of(lead_id) == "Monsoon Offer"

    # The old spelling still works everywhere and lands on the new name — even for a rep.
    rep_lead = await _lead(client, sales_headers, "monsoon ofer")
    assert await _campaign_of(rep_lead) == "Monsoon Offer"
    assert await _names(client, auth_headers) == ["Monsoon Offer"]

    # Renaming back to its own old spelling is allowed (the alias is dropped, the new one remembered).
    back = await client.post(
        f"/api/v1/campaigns/{campaign['id']}/rename", headers=auth_headers, json={"name": "Monsoon Ofer"}
    )
    assert back.status_code == 200, back.text
    assert [a["alias"] for a in back.json()["campaign"]["aliases"]] == ["Monsoon Offer"]


@pytest.mark.asyncio
async def test_rename_onto_another_campaign_offers_a_merge(client, auth_headers):
    first = await _create(client, auth_headers, "Expo Fair")
    second = await _create(client, auth_headers, "Expo Fair 2")
    response = await client.post(
        f"/api/v1/campaigns/{second['id']}/rename", headers=auth_headers, json={"name": "EXPO fair"}
    )
    assert response.status_code == 409
    assert _reason(response) == "name_exists"
    assert response.json()["error"]["extra"]["conflict_campaign_id"] == first["id"]


@pytest.mark.asyncio
async def test_merge_moves_leads_keeps_aliases_flat_and_filters_by_old_spellings(client, auth_headers, monkeypatch):
    events: list[dict] = []

    async def _record(payload, org_id=None):
        events.append(payload)

    monkeypatch.setattr(realtime_manager, "broadcast", _record)

    a = await _create(client, auth_headers, "Plot 2L")
    b = await _create(client, auth_headers, "Plot 2 Lacs")
    c = await _create(client, auth_headers, "Two Lakh Plot")
    d = await _create(client, auth_headers, "Plots Two Lakh")
    lead_a = await _lead(client, auth_headers, "Plot 2L")
    lead_b = await _lead(client, auth_headers, "Plot 2 Lacs")
    lead_c = await _lead(client, auth_headers, "Two Lakh Plot")
    events.clear()

    merged = await client.post(
        "/api/v1/campaigns/merge", headers=auth_headers, json={"source_ids": [a["id"], b["id"]], "target_id": c["id"]}
    )
    assert merged.status_code == 200, merged.text
    assert merged.json()["leads_updated"] == 2
    assert {x["alias"] for x in merged.json()["campaign"]["aliases"]} == {"Plot 2L", "Plot 2 Lacs"}
    assert [await _campaign_of(i) for i in (lead_a, lead_b, lead_c)] == ["Two Lakh Plot"] * 3
    # ONE combined realtime event for the whole merge.
    assert events == [{"event": "lead.updated", "payload": {"count": 2, "reason": "campaign_merge"}}]

    # Merging the target again keeps aliases flat: every old spelling points straight at the new target.
    again = await client.post(
        "/api/v1/campaigns/merge", headers=auth_headers, json={"source_ids": [c["id"]], "target_id": d["id"]}
    )
    assert again.status_code == 200, again.text
    async with db_manager.session_factory() as session:
        aliases = (await session.execute(select(CampaignAlias))).scalars().all()
        assert {x.alias: x.campaign_id for x in aliases} == {
            "Plot 2L": UUID(d["id"]), "Plot 2 Lacs": UUID(d["id"]), "Two Lakh Plot": UUID(d["id"]),
        }
        assert [x.name for x in (await session.execute(select(Campaign))).scalars()] == ["Plots Two Lakh"]

    # Filtering by any old spelling (any case) finds the merged campaign's leads.
    for spelling in ("plot 2l", "Two Lakh Plot", "PLOTS two lakh"):
        listed = await client.get("/api/v1/leads", headers=auth_headers, params={"campaign": spelling})
        assert {item["id"] for item in listed.json()["items"]} == {lead_a, lead_b, lead_c}, spelling

    # A campaign someone already merged away → 409 stale (not a 500); merging into itself → 422.
    stale = await client.post(
        "/api/v1/campaigns/merge", headers=auth_headers, json={"source_ids": [a["id"]], "target_id": d["id"]}
    )
    assert stale.status_code == 409 and _reason(stale) == "stale"
    self_merge = await client.post(
        "/api/v1/campaigns/merge", headers=auth_headers, json={"source_ids": [d["id"]], "target_id": d["id"]}
    )
    assert self_merge.status_code == 422


@pytest.mark.asyncio
async def test_add_refuses_a_remembered_old_spelling(client, auth_headers):
    a = await _create(client, auth_headers, "Plot 2L")
    c = await _create(client, auth_headers, "Two Lakh Plot")
    await client.post(
        "/api/v1/campaigns/merge", headers=auth_headers, json={"source_ids": [a["id"]], "target_id": c["id"]}
    )
    response = await client.post("/api/v1/campaigns", headers=auth_headers, json={"name": "PLOT 2L"})
    assert response.status_code == 409 and _reason(response) == "alias_of_other"


@pytest.mark.asyncio
async def test_clear_removes_a_junk_campaign_from_its_leads(client, auth_headers):
    junk = await _create(client, auth_headers, "Test Campaign")
    keep = await _create(client, auth_headers, "Expo Fair")
    junk_lead = await _lead(client, auth_headers, "Test Campaign")
    kept_lead = await _lead(client, auth_headers, "Expo Fair")

    cleared = await client.post(f"/api/v1/campaigns/{junk['id']}/clear", headers=auth_headers)
    assert cleared.status_code == 200, cleared.text
    assert cleared.json() == {"campaign": None, "leads_updated": 1}
    assert await _campaign_of(junk_lead) is None
    assert await _campaign_of(kept_lead) == "Expo Fair"
    assert await _names(client, auth_headers) == ["Expo Fair"]
    missing = await client.post(f"/api/v1/campaigns/{junk['id']}/clear", headers=auth_headers)
    assert missing.status_code == 409 and _reason(missing) == "stale"
    assert keep["name"] == "Expo Fair"


@pytest.mark.asyncio
async def test_deactivate_hides_from_the_form_list_and_mark_reviewed(client, auth_headers):
    campaign = await _create(client, auth_headers, "Old Promo")
    await _create(client, auth_headers, "Expo Fair")
    off = await client.patch(f"/api/v1/campaigns/{campaign['id']}", headers=auth_headers, json={"is_active": False})
    assert off.status_code == 200 and off.json()["is_active"] is False
    assert await _names(client, auth_headers) == ["Expo Fair"]
    assert await _names(client, auth_headers, include_inactive=True) == ["Expo Fair", "Old Promo"]

    # needs_review can only be cleared ("looks good"), never set by hand.
    async with db_manager.session_factory() as session:
        await session.execute(update(Campaign).where(Campaign.id == UUID(campaign["id"])).values(needs_review=True))
        await session.commit()
    reviewed = await client.patch(
        f"/api/v1/campaigns/{campaign['id']}", headers=auth_headers, json={"needs_review": False}
    )
    assert reviewed.status_code == 200 and reviewed.json()["needs_review"] is False
    refused = await client.patch(
        f"/api/v1/campaigns/{campaign['id']}", headers=auth_headers, json={"needs_review": True}
    )
    assert refused.status_code == 422


@pytest.mark.asyncio
async def test_removing_an_old_spelling_forgets_it(client, auth_headers):
    a = await _create(client, auth_headers, "Plot 2L")
    c = await _create(client, auth_headers, "Two Lakh Plot")
    merged = await client.post(
        "/api/v1/campaigns/merge", headers=auth_headers, json={"source_ids": [a["id"]], "target_id": c["id"]}
    )
    alias_id = merged.json()["campaign"]["aliases"][0]["id"]
    removed = await client.delete(f"/api/v1/campaigns/{c['id']}/aliases/{alias_id}", headers=auth_headers)
    assert removed.status_code == 200, removed.text
    again = await client.delete(f"/api/v1/campaigns/{c['id']}/aliases/{alias_id}", headers=auth_headers)
    assert again.status_code == 404
    # The spelling is free again: a manager's new lead creates it as its own campaign.
    lead_id = await _lead(client, auth_headers, "Plot 2L")
    assert await _campaign_of(lead_id) == "Plot 2L"
    assert await _names(client, auth_headers) == ["Plot 2L", "Two Lakh Plot"]


@pytest.mark.asyncio
async def test_front_line_reps_only_ever_see_active_campaigns(client):
    owner = await client.post(
        "/api/v1/auth/register",
        json={"first_name": "Rita", "last_name": "Owner", "email": "owner@camp.example.com",
              "password": "StrongPass123", "role": "owner", "business_type": "real_estate",
              "organization_name": "Camp Realty"},
    )
    assert owner.status_code == 201, owner.text
    owner_headers = {"Authorization": f"Bearer {owner.json()['access_token']}"}
    created = await client.post(
        "/api/v1/users", headers=owner_headers,
        json={"first_name": "Rinku", "last_name": "Kayal", "email": "rep@camp.example.com",
              "password": "StrongPass123", "phone": "+919900799999", "role": "sales_executive", "status": "active"},
    )
    assert created.status_code == 201, created.text
    login = await client.post("/api/v1/auth/login", json={"email": "rep@camp.example.com", "password": "StrongPass123"})
    rep_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    old = await _create(client, owner_headers, "Old Promo")
    await _create(client, owner_headers, "Expo Fair")
    await client.patch(f"/api/v1/campaigns/{old['id']}", headers=owner_headers, json={"is_active": False})
    assert await _names(client, rep_headers, include_inactive=True) == ["Expo Fair"]


# ---- deploy window: tables not created yet --------------------------------------------------------------

@pytest.mark.asyncio
async def test_everything_fails_open_before_the_migration_ran(client, auth_headers, sales_headers):
    async with db_manager.engine.begin() as connection:
        await connection.execute(text("DROP TABLE campaign_aliases"))
        await connection.execute(text("DROP TABLE campaigns"))

    response = await client.get("/api/v1/campaigns", headers=auth_headers)
    assert response.status_code == 409 and _reason(response) == "not_ready"
    # Lead writes keep working with the typed (cleaned) value — even a rep's new name.
    lead_id = await _lead(client, sales_headers, "  Fresh   Idea ")
    assert await _campaign_of(lead_id) == "Fresh Idea"
    listed = await client.get("/api/v1/leads", headers=auth_headers, params={"campaign": "Fresh Idea"})
    assert listed.status_code == 200 and [i["id"] for i in listed.json()["items"]] == [lead_id]
    assert (await client.get("/api/v1/leads/campaigns", headers=auth_headers)).json() == ["Fresh Idea"]


@pytest.mark.asyncio
async def test_list_reads_resync_at_most_every_few_minutes(client, auth_headers, monkeypatch):
    from app.services import campaigns as campaigns_module

    first, second = await _lead(client, auth_headers), await _lead(client, auth_headers)
    await _store(first, "Monsoon Offer")
    assert await _names(client, auth_headers) == ["Monsoon Offer"]  # first read seeds the list

    # A spelling written outside the resolver (e.g. while the migration was still running) is unified on a
    # later re-sync — not on every read, which would rescan all leads on each Leads page load.
    await _store(second, "monsoon OFFER")
    await _names(client, auth_headers)
    assert await _campaign_of(second) == "monsoon OFFER"
    monkeypatch.setattr(campaigns_module, "_SYNC_INTERVAL_S", 0.0)
    await _names(client, auth_headers)
    assert await _campaign_of(second) == "Monsoon Offer"


@pytest.mark.asyncio
async def test_a_lock_conflict_is_a_409_not_a_500(client, auth_headers, monkeypatch):
    from sqlalchemy.exc import DBAPIError

    from app.services.campaigns import CampaignService

    a = await _create(client, auth_headers, "Plot 2L")
    c = await _create(client, auth_headers, "Two Lakh Plot")

    class _Deadlock(Exception):
        sqlstate = "40P01"

    async def _deadlocked(self, source_ids, target_id, *, actor_id):
        raise DBAPIError("UPDATE leads ...", {}, _Deadlock("deadlock detected"))

    monkeypatch.setattr(CampaignService, "merge", _deadlocked)
    response = await client.post(
        "/api/v1/campaigns/merge", headers=auth_headers, json={"source_ids": [a["id"]], "target_id": c["id"]}
    )
    assert response.status_code == 409 and _reason(response) == "busy"
