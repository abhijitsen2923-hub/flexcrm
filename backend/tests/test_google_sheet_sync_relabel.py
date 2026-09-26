"""DB-backed test of the Google Sheet sync for agency (AntTech) sheets (#46): leads are filed under their
sheet tab, and leads imported before the fix (Meta's combined campaign) self-heal on the next poll while
hand edits are left alone. The sheet reader is stubbed — no Google API."""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select, update

from app.core.google_sheets import SHEET_TAB_KEY
from app.core.tenancy import set_scope
from app.database.session import db_manager
from app.models.lead import Lead
from app.models.organization import Organization
from app.services import google_sheet_service as gss

_COMBINED = "Vriddhica 3.5 lakh and 4.5 lakh Leads campaign"


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
    _row("l:1", "3.5 Lakh Plot", "Asha Roy", "p:+919800000001"),
    _row("l:2", "4.5 Lakh Plot Lead", "Bina Das", "p:+919800000002"),
    _row("l:3", "Pan India", "Chitra Sen", "p:+919800000003"),
]


async def _register_org(client) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "Sheet",
            "last_name": "Owner",
            "email": "owner@sheets.example.com",
            "password": "StrongPass123",
            "role": "owner",
            "business_type": "real_estate",
            "organization_name": "Sheets Realty",
        },
    )
    assert response.status_code == 201, response.text


async def _leads(session) -> dict[str, tuple[str | None, str]]:
    result = await session.execute(select(Lead).execution_options(populate_existing=True))
    return {lead.external_id: (lead.campaign, lead.title) for lead in result.scalars()}


@pytest.mark.asyncio
async def test_agency_sync_files_leads_by_tab_and_heals_old_imports(client, monkeypatch):
    await _register_org(client)
    monkeypatch.setattr(gss, "read_rows_positional", lambda _sheet_id: [dict(r) for r in _ROWS])
    events: list[dict] = []

    async def _record(payload, org_id=None):
        events.append(payload)

    monkeypatch.setattr(gss.realtime_manager, "broadcast", _record)
    # `_set_status` finds no row for this id and returns — the connection needn't be persisted.
    conn = SimpleNamespace(
        id=uuid4(),
        external_account_id="sheet-1",
        default_industry=None,
        integration_user_id=None,
        field_map={"format": "anttech_positional", "source": "AntTech"},
    )

    async with db_manager.session_factory() as session:
        org_id = (await session.execute(select(Organization.id))).scalar_one()
        set_scope(session, org_id)
        service = gss.GoogleSheetService(session)

        stats = await service.sync_connection(conn, organization_id=org_id)
        assert (stats["created"], stats["relabelled"]) == (3, 0)
        leads = await _leads(session)
        assert {k: v[0] for k, v in leads.items()} == {
            "l:1": "3.5 Lakh Plot",
            "l:2": "4.5 Lakh Plot Lead",
            "l:3": "Pan India",
        }

        # Simulate imports from BEFORE #46 (Meta's combined campaign), plus a rep's hand edit on l:3.
        await session.execute(
            update(Lead).where(Lead.external_id == "l:1").values(campaign=_COMBINED, title=f"{_COMBINED} — Asha Roy")
        )
        await session.execute(update(Lead).where(Lead.external_id == "l:2").values(campaign=_COMBINED))
        await session.execute(update(Lead).where(Lead.external_id == "l:3").values(campaign="Walk-in"))
        await session.commit()
        events.clear()

        stats = await service.sync_connection(conn, organization_id=org_id)
        assert (stats["created"], stats["duplicate"], stats["relabelled"]) == (0, 3, 2)
        leads = await _leads(session)
        assert leads["l:1"] == ("3.5 Lakh Plot", "3.5 Lakh Plot — Asha Roy")
        assert leads["l:2"] == ("4.5 Lakh Plot Lead", "4.5 Lakh Plot Lead — Bina Das")
        assert leads["l:3"][0] == "Walk-in"  # hand edit untouched
        assert [e for e in events if e["event"] == "lead.updated"] == [
            {"event": "lead.updated", "payload": {"count": 2, "reason": "sheet_relabel"}}
        ]

        stats = await service.sync_connection(conn, organization_id=org_id)
        assert stats["relabelled"] == 0  # converged — later polls write nothing
