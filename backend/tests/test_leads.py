from datetime import UTC, datetime, timedelta

import pytest


# --- Helpers -------------------------------------------------------------

async def _create_customer(client, headers):
    """Only used by the test that exercises the legacy attach-existing-customer
    path. New lead creation no longer requires a pre-existing customer."""
    response = await client.post(
        "/api/v1/customers",
        headers=headers,
        json={
            "company_name": "Initech",
            "contact_name": "Peter Gibbons",
            "email": "peter@initech.example",
            "phone": "+15553334444",
            "address": "1 TPS Lane",
            "source": "referral",
            "status": "prospect",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _advance_lead_through_education_pipeline(client, headers, lead_id: str) -> None:
    """Walk an education lead from new_enquiry → sold via the transitions endpoint."""
    stages_to_visit = [
        ("prospect", "Made initial contact and confirmed prospect details."),
        ("qualified", "Budget, interest & decision authority verified."),
        ("counseling_session_booked", "Counseling appointment scheduled for next week."),
        ("counseling_session_done", "Counselor met with student; positive signal."),
        ("follow_up", "Awaiting decision; following up periodically."),
        ("demo_booked", "Trial class scheduled."),
        ("demo_done", "Demo completed; feedback was positive."),
        ("course_suggested", "Suggested the MBA marketing track."),
        ("admission_process_started", "Application form initiated."),
        ("fee_pending", "Admission approved; awaiting fee payment."),
        ("sold", "Fee paid; admission confirmed. Closed-won."),
    ]
    for code, comment in stages_to_visit:
        response = await client.post(
            f"/api/v1/leads/{lead_id}/transitions",
            headers=headers,
            json={"to_stage_code": code, "comment": comment},
        )
        assert response.status_code == 201, f"Transition to {code} failed: {response.text}"


# --- Tests --------------------------------------------------------------

@pytest.mark.asyncio
async def test_lead_create_inherits_business_type(client, auth_headers):
    """Industry is inherited from the user's business_type — no need to pass it."""
    response = await client.post(
        "/api/v1/leads",
        headers=auth_headers,
        json={
            # NOTE: no `industry` field — should fall back to the user's
            # business_type set at registration (admin@example.com is education).
            "title": "Initial pitch",
            "contact_name": "Ishika Bose",
            "contact_email": "ishika@example.com",
            "contact_phone": "+919999000011",
            "company_name": "Self",
            "value": "12500",
            "probability": 25,
            "expected_close_date": (datetime.now(UTC) + timedelta(days=21)).date().isoformat(),
            "source": "Instagram",
            "interest": "MBA — Marketing",
        },
    )
    assert response.status_code == 201, response.text
    lead = response.json()
    assert lead["industry"] == "education"
    assert lead["stage_code"] == "new_enquiry"
    assert lead["customer_id"] is None
    assert lead["contact_name"] == "Ishika Bose"
    assert lead["contact_email"] == "ishika@example.com"


@pytest.mark.asyncio
async def test_lead_can_still_attach_existing_customer(client, auth_headers):
    """Legacy path: passing customer_id at create time still works."""
    customer_id = await _create_customer(client, auth_headers)
    response = await client.post(
        "/api/v1/leads",
        headers=auth_headers,
        json={
            "industry": "education",
            "title": "Existing-customer lead",
            "contact_name": "Peter Gibbons",
            "customer_id": customer_id,
        },
    )
    assert response.status_code == 201
    assert response.json()["customer_id"] == customer_id


@pytest.mark.asyncio
async def test_lead_sold_creates_customer(client, auth_headers):
    """Reaching the Sold stage materializes a Customer from the lead's contact info."""
    create = await client.post(
        "/api/v1/leads",
        headers=auth_headers,
        json={
            "industry": "education",
            "title": "MBA applicant",
            "contact_name": "Sneha Iyer",
            "contact_email": "sneha.iyer@example.com",
            "contact_phone": "+919900112233",
            "company_name": "Iyer & Co",
            "source": "Walk-in",
        },
    )
    assert create.status_code == 201
    lead_id = create.json()["id"]
    assert create.json()["customer_id"] is None

    await _advance_lead_through_education_pipeline(client, auth_headers, lead_id)

    # Re-fetch the lead — it should now be linked to a customer.
    listed = await client.get("/api/v1/leads?page=1&page_size=10", headers=auth_headers)
    lead = next(item for item in listed.json()["items"] if item["id"] == lead_id)
    assert lead["stage_code"] == "sold"
    assert lead["customer_id"] is not None
    customer_id = lead["customer_id"]

    # The auto-created Customer carries the lead's contact details + source_lead linkage.
    customer = await client.get(f"/api/v1/customers/{customer_id}", headers=auth_headers)
    assert customer.status_code == 200
    body = customer.json()
    assert body["company_name"] == "Iyer & Co"
    assert body["contact_name"] == "Sneha Iyer"
    assert body["email"] == "sneha.iyer@example.com"
    assert body["status"] == "active"
    assert body["source_lead_id"] == lead_id
    assert body["source_lead"]["lead_number"] == lead["lead_number"]


@pytest.mark.asyncio
async def test_lead_sold_does_not_double_promote(client, auth_headers):
    """Re-transitioning to Sold on an already-promoted lead does not duplicate the customer."""
    create = await client.post(
        "/api/v1/leads",
        headers=auth_headers,
        json={
            "industry": "education",
            "title": "Re-sold lead",
            "contact_name": "Rahul Ojha",
        },
    )
    lead_id = create.json()["id"]
    await _advance_lead_through_education_pipeline(client, auth_headers, lead_id)

    initial = await client.get("/api/v1/customers?page=1&page_size=50", headers=auth_headers)
    initial_count = initial.json()["pagination"]["total"]

    # Move the lead backward to a previous active stage (admin can) and back to sold.
    # Backward must be manager+; auth_headers is admin so it's allowed.
    bounce_back = await client.post(
        f"/api/v1/leads/{lead_id}/transitions",
        headers=auth_headers,
        json={"to_stage_code": "fee_pending", "comment": "Backed up to re-verify payment terms."},
    )
    assert bounce_back.status_code == 201, bounce_back.text
    re_sold = await client.post(
        f"/api/v1/leads/{lead_id}/transitions",
        headers=auth_headers,
        json={"to_stage_code": "sold", "comment": "Re-confirmed payment. Closed-won again."},
    )
    assert re_sold.status_code == 201

    after = await client.get("/api/v1/customers?page=1&page_size=50", headers=auth_headers)
    assert after.json()["pagination"]["total"] == initial_count


@pytest.mark.asyncio
async def test_lead_create_seeds_initial_transition(client, auth_headers):
    create = await client.post(
        "/api/v1/leads",
        headers=auth_headers,
        json={"industry": "travel", "title": "Bali honeymoon", "contact_name": "Karan Mehta"},
    )
    assert create.status_code == 201
    lead_id = create.json()["id"]
    transitions = await client.get(f"/api/v1/leads/{lead_id}/transitions", headers=auth_headers)
    rows = transitions.json()
    assert len(rows) == 1
    assert rows[0]["from_stage_code"] is None
    assert rows[0]["to_stage_code"] == "new_enquiry"


@pytest.mark.asyncio
async def test_stage_transition_requires_min_comment(client, auth_headers):
    create = await client.post(
        "/api/v1/leads",
        headers=auth_headers,
        json={"industry": "education", "title": "Demo lead", "contact_name": "Demo Person"},
    )
    lead_id = create.json()["id"]

    too_short = await client.post(
        f"/api/v1/leads/{lead_id}/transitions",
        headers=auth_headers,
        json={"to_stage_code": "qualified", "comment": "ok"},
    )
    assert too_short.status_code == 422

    ok = await client.post(
        f"/api/v1/leads/{lead_id}/transitions",
        headers=auth_headers,
        json={
            "to_stage_code": "qualified",
            "comment": "Spoke with applicant — confirmed budget and intent.",
        },
    )
    assert ok.status_code == 201
    assert ok.json()["to_stage_code"] == "qualified"


@pytest.mark.asyncio
async def test_put_rejects_stage_code(client, auth_headers):
    create = await client.post(
        "/api/v1/leads",
        headers=auth_headers,
        json={"industry": "education", "title": "Direct edit", "contact_name": "Edit Tester"},
    )
    lead_id = create.json()["id"]
    rejected = await client.put(
        f"/api/v1/leads/{lead_id}",
        headers=auth_headers,
        json={"stage_code": "qualified"},
    )
    assert rejected.status_code == 422
    assert "transitions" in rejected.json()["error"]["detail"]


@pytest.mark.asyncio
async def test_invalid_stage_code_for_industry_is_rejected(client, auth_headers):
    create = await client.post(
        "/api/v1/leads",
        headers=auth_headers,
        json={"industry": "education", "title": "Wrong vertical", "contact_name": "Wrong Industry"},
    )
    lead_id = create.json()["id"]
    bad = await client.post(
        f"/api/v1/leads/{lead_id}/transitions",
        headers=auth_headers,
        json={"to_stage_code": "package_shared", "comment": "This should be rejected because wrong industry."},
    )
    assert bad.status_code == 422
    assert "package_shared" in bad.json()["error"]["detail"]


@pytest.mark.asyncio
async def test_lead_probability_constraint(client, auth_headers):
    invalid = await client.post(
        "/api/v1/leads",
        headers=auth_headers,
        json={
            "industry": "education",
            "title": "Invalid probability",
            "contact_name": "Bad Probability",
            "value": "100",
            "probability": 150,
        },
    )
    assert invalid.status_code in {400, 409, 422}
