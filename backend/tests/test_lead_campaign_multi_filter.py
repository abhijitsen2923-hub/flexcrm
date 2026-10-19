"""The Leads list can be filtered by several campaigns at once (?campaigns=A&campaigns=B → leads of ANY of them), with
the same spelling rules as one campaign (case / spaces / a merged campaign's old name all match). The single
`campaign` parameter keeps working, and a user whose role covers only some campaigns still sees only those."""
from __future__ import annotations

import pytest

_seq = iter(range(1, 100_000))


async def _campaign(client, headers, name: str) -> str:
    response = await client.post("/api/v1/campaigns", headers=headers, json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _lead(client, headers, title: str, campaign: str | None) -> None:
    body = {"title": title, "contact_name": "Asha Roy", "contact_phone": f"+9198120{next(_seq):05d}"}
    if campaign is not None:
        body["campaign"] = campaign
    response = await client.post("/api/v1/leads", headers=headers, json=body)
    assert response.status_code == 201, response.text


async def _titles(client, headers, params) -> set[str]:
    pairs = list(params.items()) if isinstance(params, dict) else list(params)
    response = await client.get("/api/v1/leads", headers=headers, params=[("page_size", 100), *pairs])
    assert response.status_code == 200, response.text
    return {item["title"] for item in response.json()["items"]}


async def _seed(client, headers) -> dict[str, str]:
    ids = {name: await _campaign(client, headers, name) for name in ("Alpha Towers", "Beta Homes", "Gamma Park")}
    for title, campaign in [("alpha", "Alpha Towers"), ("beta", "Beta Homes"), ("gamma", "Gamma Park"), ("none", None)]:
        await _lead(client, headers, title, campaign)
    return ids


@pytest.mark.asyncio
async def test_several_campaigns_match_any_of_them(client, auth_headers):
    await _seed(client, auth_headers)
    assert await _titles(client, auth_headers, [("campaigns", "Alpha Towers"), ("campaigns", "Beta Homes")]) == {
        "alpha",
        "beta",
    }
    # Any spelling; blanks and repeats are ignored.
    assert await _titles(
        client, auth_headers, [("campaigns", " alpha   TOWERS "), ("campaigns", ""), ("campaigns", "Alpha Towers")]
    ) == {"alpha"}
    # One campaign the old way still works; nothing chosen = every lead.
    assert await _titles(client, auth_headers, {"campaign": "Gamma Park"}) == {"gamma"}
    assert await _titles(client, auth_headers, {}) == {"alpha", "beta", "gamma", "none"}
    # Combined with another filter (search) — still AND.
    assert await _titles(
        client, auth_headers, [("campaigns", "Alpha Towers"), ("campaigns", "Beta Homes"), ("search", "beta")]
    ) == {"beta"}


@pytest.mark.asyncio
async def test_a_merged_campaigns_old_name_still_finds_its_leads(client, auth_headers):
    ids = await _seed(client, auth_headers)
    merged = await client.post(
        "/api/v1/campaigns/merge", headers=auth_headers, json={"source_ids": [ids["Beta Homes"]], "target_id": ids["Alpha Towers"]}
    )
    assert merged.status_code == 200, merged.text
    assert await _titles(client, auth_headers, [("campaigns", "Beta Homes"), ("campaigns", "Gamma Park")]) == {
        "alpha",
        "beta",
        "gamma",
    }


@pytest.mark.asyncio
async def test_too_many_campaigns_is_refused(client, auth_headers):
    params = [("campaigns", f"Campaign {i}") for i in range(51)]
    response = await client.get("/api/v1/leads", headers=auth_headers, params=params)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_a_limited_user_still_sees_only_their_campaigns(client, auth_headers):
    ids = await _seed(client, auth_headers)
    role = await client.post(
        "/api/v1/custom-roles",
        headers=auth_headers,
        json={"name": "Alpha only", "permissions": ["LEAD_VIEW"], "lead_access": {"campaign_ids": [ids["Alpha Towers"]]}},
    )
    assert role.status_code == 201, role.text
    created = await client.post(
        "/api/v1/users",
        headers=auth_headers,
        json={
            "first_name": "Al", "last_name": "Pha", "email": "alpha.only@example.com", "password": "StrongPass123",
            "role": "custom", "custom_role_id": role.json()["id"], "status": "active",
        },
    )
    assert created.status_code == 201, created.text
    login = await client.post("/api/v1/auth/login", json={"email": "alpha.only@example.com", "password": "StrongPass123"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert await _titles(client, headers, [("campaigns", "Alpha Towers"), ("campaigns", "Beta Homes")]) == {"alpha"}
