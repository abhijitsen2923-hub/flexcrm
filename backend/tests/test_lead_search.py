"""Leads search — an exact lead number shows THAT lead.

Reported: searching "92422" listed lead #92422 plus other leads whose phone number happened to contain
"92422" (the search is a "contains" match over title, interest, name, email, phones and lead number).
A search that is just a lead number ("92422", "#92422") now returns only that lead — with the same filters
and rep scoping — and falls back to the normal search when no such lead is visible. Phone numbers, phone
fragments with a leading zero or "+", and text keep the "contains" search.
"""
from __future__ import annotations

import pytest

from app.services.leads import lead_number_from_search

_seq = iter(range(1, 10_000))


def _phone() -> str:
    return f"+9199005{next(_seq):05d}"


async def _create(client, headers, *, phone: str | None = None, title: str = "Enquiry", **extra) -> dict:
    body = {"title": title, "contact_name": "Asha Roy", "contact_phone": phone or _phone(), **extra}
    response = await client.post("/api/v1/leads", headers=headers, json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def _search(client, headers, term: str, **params) -> dict:
    response = await client.get(
        "/api/v1/leads", headers=headers, params={"search": term, "page_size": 50, **params}
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _ids(client, headers, term: str, **params) -> set[str]:
    return {item["id"] for item in (await _search(client, headers, term, **params))["items"]}


async def _three_leads(client, headers) -> tuple[dict, dict, dict]:
    """A = the lead we look up; B's phone and C's title contain A's number."""
    a = await _create(client, headers, source="Website")
    number = a["lead_number"]
    b = await _create(client, headers, phone=f"+91{number}12345", source="Referral")
    c = await _create(client, headers, title=f"Referred by {number}")
    return a, b, c


# ---- the parser ---------------------------------------------------------------------------------------------

def test_lead_number_parser():
    for term in ("92422", "#92422", "# 92422", "  92422  ", "#92422 "):
        assert lead_number_from_search(term) == 92422, term
    assert lead_number_from_search("999999999") == 999999999  # 9 digits: still fits INTEGER
    for term in (
        None, "", "   ", "#", "0", "092422",  # leading zero → a phone fragment
        "9242212345", "919242212345", "2147483648", "9" * 5000,  # phone numbers / too long for INTEGER
        "92 422", "+9192422", "-92422", "92422a", "ravi 92422",
        "٩٢٤٢٢",  # Arabic-Indic digits
        "९२४२२",  # Devanagari digits
    ):
        assert lead_number_from_search(term) is None, repr(term)


# ---- the list ---------------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_exact_lead_number_returns_only_that_lead(client, auth_headers):
    a, b, c = await _three_leads(client, auth_headers)
    number = a["lead_number"]
    for term in (str(number), f"#{number}", f"# {number}", f"  {number} "):
        body = await _search(client, auth_headers, term)
        assert [item["id"] for item in body["items"]] == [a["id"]], term
        assert body["pagination"]["total"] == 1


@pytest.mark.asyncio
async def test_other_searches_still_match_anywhere(client, auth_headers):
    a, b, c = await _three_leads(client, auth_headers)
    number = str(a["lead_number"])
    # A shorter piece of the number matches no lead number → "contains" search across all fields, as before.
    assert await _ids(client, auth_headers, number[:4]) >= {a["id"], b["id"], c["id"]}
    # Phone-style input keeps finding the phone.
    assert await _ids(client, auth_headers, f"+91{number}") == {b["id"]}
    assert await _ids(client, auth_headers, f"{number}12345") == {b["id"]}
    # Looks like a lead number but no such lead → the normal search (here: B's phone).
    assert await _ids(client, auth_headers, f"91{number}") == {b["id"]}
    # A leading zero is a phone fragment, never a lead number.
    assert a["id"] not in await _ids(client, auth_headers, f"0{number}")
    # Text still works.
    assert await _ids(client, auth_headers, "Referred") == {c["id"]}


@pytest.mark.asyncio
async def test_long_numbers_never_error(client, auth_headers):
    await _three_leads(client, auth_headers)
    for term in ("9242212345", "919242212345", "2147483648", "9" * 20, "9" * 5000, "#" + "9" * 12):
        await _search(client, auth_headers, term)  # 200, never a 500


@pytest.mark.asyncio
async def test_exact_hit_respects_other_filters(client, auth_headers):
    a, b, c = await _three_leads(client, auth_headers)
    number = str(a["lead_number"])
    assert await _ids(client, auth_headers, number, source="Website") == {a["id"]}
    # A is filtered out by the source filter → the normal search runs within that filter.
    assert await _ids(client, auth_headers, number, source="Referral") == {b["id"]}


@pytest.mark.asyncio
async def test_page_two_of_an_exact_hit_does_not_fall_back(client, auth_headers):
    a, _b, _c = await _three_leads(client, auth_headers)
    response = await client.get(
        "/api/v1/leads", headers=auth_headers, params={"search": str(a["lead_number"]), "page": 2, "page_size": 1}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == [] and body["pagination"]["total"] == 1


@pytest.mark.asyncio
async def test_deleted_lead_number_falls_back_to_the_normal_search(client, auth_headers):
    a, b, c = await _three_leads(client, auth_headers)
    deleted = await client.delete(f"/api/v1/leads/{a['id']}", headers=auth_headers)
    assert deleted.status_code == 200, deleted.text
    assert await _ids(client, auth_headers, str(a["lead_number"])) == {b["id"], c["id"]}


@pytest.mark.asyncio
async def test_exact_hit_keeps_the_duplicate_marker(client, auth_headers):
    a = await _create(client, auth_headers, phone="+919900777001")
    await _create(client, auth_headers, phone="+919900777001")
    body = await _search(client, auth_headers, str(a["lead_number"]))
    assert [(item["id"], item["is_duplicate"]) for item in body["items"]] == [(a["id"], True)]


async def _real_estate_owner_and_rep(client) -> tuple[dict[str, str], dict[str, str], str]:
    owner = await client.post(
        "/api/v1/auth/register",
        json={"first_name": "Rita", "last_name": "Owner", "email": "owner@search.example.com",
              "password": "StrongPass123", "role": "owner", "business_type": "real_estate",
              "organization_name": "Search Realty"},
    )
    assert owner.status_code == 201, owner.text
    owner_headers = {"Authorization": f"Bearer {owner.json()['access_token']}"}
    created = await client.post(
        "/api/v1/users",
        headers=owner_headers,
        json={"first_name": "Rinku", "last_name": "Kayal", "email": "rep@search.example.com",
              "password": "StrongPass123", "phone": "+919900599999", "role": "sales_executive", "status": "active"},
    )
    assert created.status_code == 201, created.text
    login = await client.post("/api/v1/auth/login", json={"email": "rep@search.example.com", "password": "StrongPass123"})
    assert login.status_code == 200, login.text
    return owner_headers, {"Authorization": f"Bearer {login.json()['access_token']}"}, created.json()["id"]


@pytest.mark.asyncio
async def test_reps_only_ever_find_their_own_leads(client):
    owner_headers, rep_headers, rep_id = await _real_estate_owner_and_rep(client)
    others = await _create(client, owner_headers)  # not the rep's
    number = others["lead_number"]
    mine = await _create(client, owner_headers, phone=f"+91{number}12345", assigned_to_id=rep_id)
    mine_by_number = await _create(client, owner_headers, assigned_to_id=rep_id)

    # Another rep's lead number: no leak — the rep gets the normal search over THEIR leads.
    assert await _ids(client, rep_headers, str(number)) == {mine["id"]}
    # Their own lead number: just that lead.
    assert await _ids(client, rep_headers, str(mine_by_number["lead_number"])) == {mine_by_number["id"]}
    # The owner sees the exact lead.
    assert await _ids(client, owner_headers, str(number)) == {others["id"]}
