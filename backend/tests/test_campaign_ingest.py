"""Sheet / Meta ingest against the tenant's campaign list: new rows land on the campaign a manager merged
their name into, unknown names are added "needs review", the #46 self-heal lands on the canonical name
(and still recognises legacy leads whose spelling was unified), a manager's merge of the legacy name
sticks, and a lead is never lost over its campaign. Sheet reader stubbed; neutral names only."""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import OperationalError

from app.core.google_sheets import SHEET_TAB_KEY
from app.core.tenancy import set_scope
from app.database.enums import LeadIndustry
from app.database.session import db_manager
from app.models.campaign import Campaign
from app.models.lead import Lead
from app.models.organization import Organization
from app.models.user import User
from app.services import google_sheet_service as gss
from app.services.campaigns import CampaignService
from app.services.lead_ingest import LeadIngestService

_COMBINED = "Acme two and three lakh plots campaign"


def _row(lead_id: str, tab: str, name: str, phone: str) -> dict:
    return {
        "id": lead_id,
        "created_time": "2026-09-18T03:03:50-05:00",
        "campaign_name": _COMBINED,
        "adset_name": "AdSet",
        "platform": "fb",
        "full_name": name,
        "phone": phone,
        SHEET_TAB_KEY: tab,
    }


_ROWS = [
    _row("l:1", "Plot Two", "Asha Roy", "p:+919800100001"),
    _row("l:2", "Plot Three", "Bina Das", "p:+919800100002"),
    _row("l:3", "Nationwide", "Chitra Sen", "p:+919800100003"),
]
_CONN = SimpleNamespace(
    id=uuid4(),
    external_account_id="sheet-1",
    default_industry=None,
    integration_user_id=None,
    field_map={"format": "anttech_positional"},
)


@pytest.fixture
def sheet(monkeypatch) -> list[dict]:
    """Stub the sheet reader (returns the current `rows`) and record realtime events."""
    rows = [dict(r) for r in _ROWS]
    monkeypatch.setattr(gss, "read_rows_positional", lambda _sheet_id: [dict(r) for r in rows])
    events: list[dict] = []

    async def _record(payload, org_id=None):
        events.append(payload)

    monkeypatch.setattr(gss.realtime_manager, "broadcast", _record)
    return SimpleNamespace(rows=rows, events=events)


async def _owner(client) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/register",
        json={"first_name": "Sheet", "last_name": "Owner", "email": "owner@ingest.example.com",
              "password": "StrongPass123", "role": "owner", "business_type": "real_estate",
              "organization_name": "Ingest Realty"},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _sync(session) -> dict[str, int]:
    org_id = (await session.execute(select(Organization.id))).scalar_one()
    set_scope(session, org_id)
    return await gss.GoogleSheetService(session).sync_connection(_CONN, organization_id=org_id)


async def _campaigns_of_leads(session) -> dict[str, str | None]:
    result = await session.execute(select(Lead).execution_options(populate_existing=True))
    return {lead.external_id: lead.campaign for lead in result.scalars()}


async def _campaign_rows(session) -> dict[str, Campaign]:
    result = await session.execute(select(Campaign).execution_options(populate_existing=True))
    return {c.name: c for c in result.scalars()}


async def _merge(client, headers, source: str, target: str) -> None:
    items = (await client.get("/api/v1/campaigns/manage", headers=headers)).json()["items"]
    ids = {item["name"]: item["id"] for item in items}
    if target not in ids:
        created = await client.post("/api/v1/campaigns", headers=headers, json={"name": target})
        assert created.status_code == 201, created.text
        ids[target] = created.json()["id"]
    response = await client.post(
        "/api/v1/campaigns/merge", headers=headers, json={"source_ids": [ids[source]], "target_id": ids[target]}
    )
    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_new_rows_land_on_the_merged_campaign_and_unknown_tabs_wait_for_review(client, sheet):
    headers = await _owner(client)
    created = await client.post("/api/v1/campaigns", headers=headers, json={"name": "Plot Two"})
    assert created.status_code == 201
    await _merge(client, headers, "Plot Two", "Two Lakh Plot")
    sheet.events.clear()

    async with db_manager.session_factory() as session:
        stats = await _sync(session)
        assert stats["created"] == 3
        assert await _campaigns_of_leads(session) == {
            "l:1": "Two Lakh Plot",  # the tab name is a remembered old spelling → canonical name
            "l:2": "Plot Three",
            "l:3": "Nationwide",
        }
        rows = await _campaign_rows(session)
        assert set(rows) == {"Two Lakh Plot", "Plot Three", "Nationwide"}
        assert {(rows[n].source, rows[n].needs_review) for n in ("Plot Three", "Nationwide")} == {("sheet", True)}
        assert rows["Two Lakh Plot"].needs_review is False
    # Adding campaigns during ingest broadcasts nothing extra.
    assert {e["event"] for e in sheet.events} == {"lead.created"}


@pytest.mark.asyncio
async def test_old_imports_heal_onto_the_canonical_campaign(client, sheet):
    headers = await _owner(client)
    async with db_manager.session_factory() as session:
        await _sync(session)
        # Imports from before #46 hold Meta's combined campaign — one of them in another case (the campaign
        # list unifies spellings, so the stored text can differ from the raw sheet value) — and a rep
        # hand-edited l:3.
        await session.execute(update(Lead).where(Lead.external_id == "l:1").values(campaign=_COMBINED))
        await session.execute(update(Lead).where(Lead.external_id == "l:2").values(campaign=_COMBINED.upper()))
        await session.execute(update(Lead).where(Lead.external_id == "l:3").values(campaign="Walk-in Event"))
        await session.commit()

    # Meanwhile a manager decided the "Plot Two" tab belongs to "Two Lakh Plot".
    await _merge(client, headers, "Plot Two", "Two Lakh Plot")
    sheet.events.clear()

    async with db_manager.session_factory() as session:
        stats = await _sync(session)
        assert (stats["created"], stats["relabelled"]) == (0, 2)
        assert await _campaigns_of_leads(session) == {
            "l:1": "Two Lakh Plot",
            "l:2": "Plot Three",
            "l:3": "Walk-in Event",  # hand edit untouched
        }
        assert sheet.events == [{"event": "lead.updated", "payload": {"count": 2, "reason": "sheet_relabel"}}]
        assert (await _sync(session))["relabelled"] == 0  # converged


@pytest.mark.asyncio
async def test_a_managers_merge_of_the_legacy_name_sticks(client, sheet):
    headers = await _owner(client)
    async with db_manager.session_factory() as session:
        await _sync(session)
        await session.execute(update(Lead).where(Lead.external_id == "l:1").values(campaign=_COMBINED))
        await session.commit()
    await client.get("/api/v1/campaigns", headers=headers)  # the legacy name joins the list
    await _merge(client, headers, _COMBINED, "Plot Bundle")

    async with db_manager.session_factory() as session:
        assert (await _campaigns_of_leads(session))["l:1"] == "Plot Bundle"
        assert (await _sync(session))["relabelled"] == 0
        assert (await _campaigns_of_leads(session))["l:1"] == "Plot Bundle"


@pytest.mark.asyncio
async def test_a_cleared_tab_campaign_is_not_re_added_by_rows_that_change_nothing(client, sheet):
    headers = await _owner(client)
    async with db_manager.session_factory() as session:
        await _sync(session)
    items = (await client.get("/api/v1/campaigns/manage", headers=headers)).json()["items"]
    nationwide = next(item for item in items if item["name"] == "Nationwide")
    cleared = await client.post(f"/api/v1/campaigns/{nationwide['id']}/clear", headers=headers)
    assert cleared.status_code == 200, cleared.text

    async with db_manager.session_factory() as session:
        stats = await _sync(session)
        assert (stats["created"], stats["relabelled"]) == (0, 0)
        assert "Nationwide" not in await _campaign_rows(session)
        # A NEW row in that tab brings the name back, flagged for review.
        sheet.rows.append(_row("l:4", "Nationwide", "Dev Pal", "p:+919800100004"))
        assert (await _sync(session))["created"] == 1
        assert (await _campaign_rows(session))["Nationwide"].needs_review is True


async def _ingest_meta(session, external_id: str, campaign: str) -> Lead:
    org_id = (await session.execute(select(Organization.id))).scalar_one()
    actor_id = (await session.execute(select(User.id))).scalars().first()
    set_scope(session, org_id)
    lead, created = await LeadIngestService(session).ingest_lead(
        organization_id=org_id,
        actor_id=actor_id,
        industry=LeadIndustry.real_estate,
        source_provider="facebook",
        external_id=external_id,
        fields={"contact_name": "Meta Person", "contact_phone": "+919800200001", "campaign": campaign},
    )
    assert created
    return lead


@pytest.mark.asyncio
async def test_meta_ingest_uses_the_campaign_list(client, monkeypatch):
    monkeypatch.setattr(gss.realtime_manager, "broadcast", lambda *a, **k: _noop())
    headers = await _owner(client)
    created = await client.post("/api/v1/campaigns", headers=headers, json={"name": "Spring Leadgen"})
    assert created.status_code == 201
    await _merge(client, headers, "Spring Leadgen", "Spring Offer")

    async with db_manager.session_factory() as session:
        assert (await _ingest_meta(session, "m:1", "  spring   LEADGEN")).campaign == "Spring Offer"
        assert (await _ingest_meta(session, "m:2", "Autumn Leadgen")).campaign == "Autumn Leadgen"
        row = (await _campaign_rows(session))["Autumn Leadgen"]
        assert (row.source, row.needs_review) == ("meta", True)


@pytest.mark.asyncio
async def test_a_lead_is_never_lost_over_its_campaign(client, monkeypatch):
    monkeypatch.setattr(gss.realtime_manager, "broadcast", lambda *a, **k: _noop())
    await _owner(client)

    async def _broken(self, raw, policy):
        raise OperationalError("SELECT 1", {}, Exception("database hiccup"))

    monkeypatch.setattr(CampaignService, "resolve", _broken)
    async with db_manager.session_factory() as session:
        lead = await _ingest_meta(session, "m:9", "  Winter   Leadgen ")
        assert lead.campaign == "Winter Leadgen"


async def _noop() -> None:
    return None
