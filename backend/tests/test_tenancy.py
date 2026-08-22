"""Multi-tenancy tests (Phase 7).

⚠️  Most of this module cannot run on the SQLite harness — see the schema-collapse
note in `conftest.py`.

These tests were written against the ORIGINAL tenancy design, where a global
`organization_id` row filter made another org's rows invisible (hence the
"the global filter makes the row invisible" wording that used to be here).
That model is gone: `set_scope()` is now a no-op compat stub
(`app/core/tenancy.py`) and isolation comes purely from schema-per-tenant
routing via `schema_translate_map`.

That routing has no SQLite equivalent, so the harness collapses every schema
into one — which means both orgs' rows genuinely DO share a table here. The
three isolation tests below are therefore skipped rather than rewritten:
asserting what this harness actually does would enshrine the opposite of the
production guarantee. They need a real Postgres to be meaningful.

`test_two_orgs_register_independently` touches only public-schema tables
(organizations/users), so it runs normally.
"""
import pytest


# Isolation here is a property of the Postgres schema boundary, not of any
# application-level predicate, so there is nothing left to assert once the
# schemas are collapsed. Run these against Postgres to get real coverage.
requires_real_schemas = pytest.mark.skip(
    reason="Needs Postgres: schema-per-tenant isolation cannot be modelled on the collapsed SQLite harness."
)


async def _register_org(client, *, email: str, org_name: str, business_type: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "Org",
            "last_name": "Admin",
            "email": email,
            "password": "StrongPass123",
            "phone": None,
            "role": "admin",
            "business_type": business_type,
            "organization_name": org_name,
        },
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    return {"Authorization": f"Bearer {payload['access_token']}"}


@pytest.mark.asyncio
async def test_two_orgs_register_independently(client):
    org_a = await _register_org(client, email="a@example.com", org_name="Org Alpha", business_type="education")
    org_b = await _register_org(client, email="b@example.com", org_name="Org Beta", business_type="travel")

    me_a = (await client.get("/api/v1/organizations/me", headers=org_a)).json()
    me_b = (await client.get("/api/v1/organizations/me", headers=org_b)).json()

    assert me_a["name"] == "Org Alpha"
    assert me_a["business_type"] == "education"
    assert me_b["name"] == "Org Beta"
    assert me_b["business_type"] == "travel"
    assert me_a["id"] != me_b["id"]


@requires_real_schemas
@pytest.mark.asyncio
async def test_leads_are_isolated_between_orgs(client):
    org_a = await _register_org(client, email="a@example.com", org_name="Org Alpha", business_type="education")
    org_b = await _register_org(client, email="b@example.com", org_name="Org Beta", business_type="travel")

    # Org A creates an education lead.
    lead_a = (await client.post(
        "/api/v1/leads",
        headers=org_a,
        json={"title": "Alpha applicant", "contact_name": "Alice"},
    )).json()
    assert lead_a["industry"] == "education"

    # Org B creates a travel lead.
    lead_b = (await client.post(
        "/api/v1/leads",
        headers=org_b,
        json={"title": "Beta traveler", "contact_name": "Bob"},
    )).json()
    assert lead_b["industry"] == "travel"

    # A list query in each org sees only its own lead.
    listed_a = (await client.get("/api/v1/leads?page=1&page_size=20", headers=org_a)).json()
    listed_b = (await client.get("/api/v1/leads?page=1&page_size=20", headers=org_b)).json()

    a_ids = {item["id"] for item in listed_a["items"]}
    b_ids = {item["id"] for item in listed_b["items"]}
    assert lead_a["id"] in a_ids
    assert lead_b["id"] not in a_ids
    assert lead_b["id"] in b_ids
    assert lead_a["id"] not in b_ids


@requires_real_schemas
@pytest.mark.asyncio
async def test_cross_org_transition_returns_404(client):
    org_a = await _register_org(client, email="a@example.com", org_name="Org Alpha", business_type="education")
    org_b = await _register_org(client, email="b@example.com", org_name="Org Beta", business_type="travel")

    lead_a = (await client.post(
        "/api/v1/leads",
        headers=org_a,
        json={"title": "Alpha applicant", "contact_name": "Alice"},
    )).json()

    # Org B tries to transition Org A's lead. The global filter makes the
    # lead invisible, so the service raises NotFoundError → 404.
    response = await client.post(
        f"/api/v1/leads/{lead_a['id']}/transitions",
        headers=org_b,
        json={"to_stage_code": "qualified", "comment": "Trying to poach from another org."},
    )
    assert response.status_code == 404


@requires_real_schemas
@pytest.mark.asyncio
async def test_auto_promotion_lands_in_originating_org(client):
    org_a = await _register_org(client, email="a@example.com", org_name="Org Alpha", business_type="education")
    org_b = await _register_org(client, email="b@example.com", org_name="Org Beta", business_type="travel")

    # Org A creates and closes a lead.
    lead = (await client.post(
        "/api/v1/leads",
        headers=org_a,
        json={"title": "MBA applicant", "contact_name": "Alice", "value": "50000"},
    )).json()
    stages = [
        ("prospect", "Initial contact and prospect details confirmed."),
        ("qualified", "Budget, interest, decision authority verified."),
        ("counseling_session_booked", "Counseling session scheduled."),
        ("counseling_session_done", "Counselor met with student."),
        ("follow_up", "Awaiting decision; following up periodically."),
        ("demo_booked", "Demo class scheduled."),
        ("demo_done", "Demo completed; positive feedback."),
        ("course_suggested", "Suggested the MBA Marketing track."),
        ("admission_process_started", "Application form initiated."),
        ("fee_pending", "Admission approved, awaiting fee payment."),
        ("sold", "Fee paid. Closed-won."),
    ]
    for code, comment in stages:
        r = await client.post(
            f"/api/v1/leads/{lead['id']}/transitions",
            headers=org_a,
            json={"to_stage_code": code, "comment": comment},
        )
        assert r.status_code == 201, r.text

    # Customer auto-created in Org A.
    customers_in_a = (await client.get("/api/v1/customers?page=1&page_size=20", headers=org_a)).json()
    assert customers_in_a["pagination"]["total"] >= 1

    # Org B sees zero customers — auto-promote correctly scoped to A.
    customers_in_b = (await client.get("/api/v1/customers?page=1&page_size=20", headers=org_b)).json()
    assert customers_in_b["pagination"]["total"] == 0
