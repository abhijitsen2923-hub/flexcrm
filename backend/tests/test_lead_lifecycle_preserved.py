"""A lead's lifecycle must survive reassignment and bulk actions.

Reassigning a lead (single owner change or bulk "Change owner") must keep its stage and history, and a bulk
"Move to stage" is forward-only — it can't silently send a batch back to New Enquiry, and it never changes a
closed (Sold or lost) lead, except the routine Did Not Pick ↔ Follow Up toggle. Single-lead backward moves
(managers) and single-lead reopens stay available.

Runs against the Education test org (`auth_headers` = owner, a manager role; `sales_headers` = a counselor).
"""
from __future__ import annotations

import pytest


async def _create_lead(client, headers, phone: str) -> str:
    response = await client.post(
        "/api/v1/leads",
        headers=headers,
        json={"title": "Lifecycle lead", "contact_name": "Asha Roy", "contact_phone": phone},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _move(client, headers, lead_id: str, stage: str) -> None:
    response = await client.post(
        f"/api/v1/leads/{lead_id}/transitions",
        headers=headers,
        json={"to_stage_code": stage, "comment": f"Moving this lead to {stage} for the test."},
    )
    assert response.status_code == 201, response.text


async def _bulk_move(client, headers, lead_ids: list[str], stage: str) -> dict:
    response = await client.post(
        "/api/v1/leads/bulk-transition",
        headers=headers,
        json={"lead_ids": lead_ids, "to_stage_code": stage, "comment": "Bulk move for the lifecycle test."},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _stage_and_history(client, headers, lead_id: str) -> tuple[str, int]:
    # No single-lead GET route — read it from the list, as the UI does.
    listing = await client.get("/api/v1/leads", headers=headers)
    assert listing.status_code == 200, listing.text
    lead = next(item for item in listing.json()["items"] if item["id"] == lead_id)
    history = await client.get(f"/api/v1/leads/{lead_id}/transitions", headers=headers)
    assert history.status_code == 200, history.text
    return lead["stage_code"], len(history.json())


async def _user_id(client, headers, email: str) -> str:
    response = await client.get("/api/v1/users", headers=headers)
    assert response.status_code == 200, response.text
    return next(u["id"] for u in response.json()["items"] if u["email"] == email)


@pytest.mark.asyncio
async def test_single_reassign_keeps_stage_and_history(client, auth_headers, sales_headers):
    lead_id = await _create_lead(client, auth_headers, "+919900200001")
    await _move(client, auth_headers, lead_id, "qualified")
    before = await _stage_and_history(client, auth_headers, lead_id)
    counselor_id = await _user_id(client, auth_headers, "sales@example.com")

    response = await client.put(
        f"/api/v1/leads/{lead_id}", headers=auth_headers, json={"assigned_to_id": counselor_id}
    )
    assert response.status_code == 200, response.text
    assert response.json()["assigned_to_id"] == counselor_id
    assert await _stage_and_history(client, auth_headers, lead_id) == before == ("qualified", 2)


@pytest.mark.asyncio
async def test_bulk_reassign_keeps_stage_and_history(client, auth_headers, sales_headers):
    lead_ids = [await _create_lead(client, auth_headers, f"+91990020001{i}") for i in range(2)]
    await _move(client, auth_headers, lead_ids[0], "follow_up")
    await _move(client, auth_headers, lead_ids[1], "qualified")
    before = [await _stage_and_history(client, auth_headers, lid) for lid in lead_ids]
    counselor_id = await _user_id(client, auth_headers, "sales@example.com")

    response = await client.post(
        "/api/v1/leads/bulk-reassign",
        headers=auth_headers,
        json={"lead_ids": lead_ids, "assigned_to_id": counselor_id},
    )
    assert response.status_code == 200, response.text
    after = [await _stage_and_history(client, auth_headers, lid) for lid in lead_ids]
    assert after == before == [("follow_up", 2), ("qualified", 2)]


@pytest.mark.asyncio
async def test_bulk_move_skips_leads_already_past_target(client, auth_headers):
    ahead = await _create_lead(client, auth_headers, "+919900200021")
    behind = await _create_lead(client, auth_headers, "+919900200022")
    await _move(client, auth_headers, ahead, "qualified")

    result = await _bulk_move(client, auth_headers, [ahead, behind], "prospect")

    assert (result["updated"], result["failed"]) == (1, 1)
    assert "Already past" in result["errors"][0]
    assert await _stage_and_history(client, auth_headers, ahead) == ("qualified", 2)  # untouched, no new row
    assert (await _stage_and_history(client, auth_headers, behind))[0] == "prospect"


@pytest.mark.asyncio
async def test_bulk_move_back_to_new_enquiry_moves_nothing(client, auth_headers):
    lead_id = await _create_lead(client, auth_headers, "+919900200031")
    await _move(client, auth_headers, lead_id, "follow_up")

    result = await _bulk_move(client, auth_headers, [lead_id], "new_enquiry")

    assert (result["updated"], result["failed"]) == (0, 1)
    assert await _stage_and_history(client, auth_headers, lead_id) == ("follow_up", 2)


@pytest.mark.asyncio
async def test_single_backward_move_still_allowed_for_manager(client, auth_headers):
    lead_id = await _create_lead(client, auth_headers, "+919900200041")
    await _move(client, auth_headers, lead_id, "qualified")

    await _move(client, auth_headers, lead_id, "prospect")  # owner = manager role; one lead, with a comment

    assert await _stage_and_history(client, auth_headers, lead_id) == ("prospect", 3)


@pytest.mark.asyncio
async def test_bulk_move_does_not_reopen_lost_leads(client, auth_headers):
    lead_id = await _create_lead(client, auth_headers, "+919900200051")
    await _move(client, auth_headers, lead_id, "not_interested")

    reopen = await _bulk_move(client, auth_headers, [lead_id], "prospect")
    lateral = await _bulk_move(client, auth_headers, [lead_id], "disqualified")  # lost → lost

    assert (reopen["updated"], reopen["failed"]) == (0, 1)
    assert "Closed lead" in reopen["errors"][0]
    assert (lateral["updated"], lateral["failed"]) == (0, 1)
    assert await _stage_and_history(client, auth_headers, lead_id) == ("not_interested", 2)


@pytest.mark.asyncio
async def test_bulk_move_leaves_sold_leads_alone(client, auth_headers):
    # Moving Sold leads to a lost stage in bulk would reverse won deals (and their brokerage).
    lead_id = await _create_lead(client, auth_headers, "+919900200081")
    await _move(client, auth_headers, lead_id, "sold")

    result = await _bulk_move(client, auth_headers, [lead_id], "not_interested")

    assert (result["updated"], result["failed"]) == (0, 1)
    assert "Closed lead" in result["errors"][0]
    assert await _stage_and_history(client, auth_headers, lead_id) == ("sold", 2)


@pytest.mark.asyncio
async def test_bulk_did_not_pick_to_follow_up_toggle_still_allowed(client, auth_headers):
    # Education "Did Not Pick" is closed-lost, but toggling it with Follow Up is a routine daily action.
    lead_id = await _create_lead(client, auth_headers, "+919900200091")
    await _move(client, auth_headers, lead_id, "did_not_pick")

    result = await _bulk_move(client, auth_headers, [lead_id], "follow_up")

    assert (result["updated"], result["failed"]) == (1, 0)
    assert (await _stage_and_history(client, auth_headers, lead_id))[0] == "follow_up"


@pytest.mark.asyncio
async def test_bulk_move_does_not_reset_did_not_pick_lead(client, auth_headers):
    # Education "Did Not Pick" is closed-lost, so a bulk move to New Enquiry would count as a reopen.
    lead_id = await _create_lead(client, auth_headers, "+919900200061")
    await _move(client, auth_headers, lead_id, "demo_done")
    await _move(client, auth_headers, lead_id, "did_not_pick")

    result = await _bulk_move(client, auth_headers, [lead_id], "new_enquiry")

    assert (result["updated"], result["failed"]) == (0, 1)
    assert await _stage_and_history(client, auth_headers, lead_id) == ("did_not_pick", 3)


@pytest.mark.asyncio
async def test_single_reopen_still_allowed(client, auth_headers):
    lead_id = await _create_lead(client, auth_headers, "+919900200071")
    await _move(client, auth_headers, lead_id, "not_interested")

    await _move(client, auth_headers, lead_id, "prospect")  # deliberate, one lead, with a comment

    assert await _stage_and_history(client, auth_headers, lead_id) == ("prospect", 3)
