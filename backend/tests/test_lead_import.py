"""CSV import smoke tests.

Covers: happy path (multiple rows), bad-stage row that fails alongside good
rows, Sold-stage row triggering the auto-promotion to Customer, and
cross-org isolation (org A's import doesn't surface in org B's lead list).
"""
import io

import pytest


def _csv_bytes(rows: list[str], header: str | None = None) -> bytes:
    # `contact_phone` is mandatory on capture for every vertical (see LeadCreate
    # in app/schemas/lead.py and the phone check in LeadImportService._import_row).
    # A row without it fails before any other column is validated.
    header_line = header or "contact_name,contact_phone,title,stage,value,currency"
    return ("\n".join([header_line, *rows]) + "\n").encode("utf-8")


@pytest.mark.asyncio
async def test_csv_import_creates_leads(client, auth_headers):
    payload = _csv_bytes(
        [
            "Sneha Iyer,+919900500001,MBA applicant,Qualified,70000,INR",
            "Rohan T,+919900500002,CA student,Prospect,15000,INR",
        ]
    )
    response = await client.post(
        "/api/v1/leads/import",
        headers=auth_headers,
        files={"file": ("leads.csv", io.BytesIO(payload), "text/csv")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created"] == 2
    assert body["promoted"] == 0
    assert body["errors"] == []

    listed = (await client.get("/api/v1/leads?page=1&page_size=20", headers=auth_headers)).json()
    titles = {item["title"] for item in listed["items"]}
    assert "MBA applicant" in titles
    assert "CA student" in titles


@pytest.mark.asyncio
async def test_csv_import_sold_row_promotes_to_customer(client, auth_headers):
    payload = _csv_bytes(
        ["Karan Mehta,+919900500003,MBBS,Sold,85000,INR"]
    )
    response = await client.post(
        "/api/v1/leads/import",
        headers=auth_headers,
        files={"file": ("leads.csv", io.BytesIO(payload), "text/csv")},
    )
    body = response.json()
    assert response.status_code == 200, body
    assert body["created"] == 1
    assert body["promoted"] == 1
    assert body["errors"] == []

    customers = (await client.get("/api/v1/customers?page=1&page_size=20", headers=auth_headers)).json()
    # Auto-promotion materializes a customer record from the lead's contact info.
    assert any(c["contact_name"] == "Karan Mehta" for c in customers["items"])


@pytest.mark.asyncio
async def test_csv_import_per_row_errors_dont_abort(client, auth_headers):
    payload = _csv_bytes(
        [
            "Good Row,+919900500004,OK,Qualified,5000,INR",
            "Bad Row,+919900500005,Borked,NotAStage,5000,INR",
            "Another Good,+919900500006,OK,Prospect,5000,INR",
        ]
    )
    response = await client.post(
        "/api/v1/leads/import",
        headers=auth_headers,
        files={"file": ("leads.csv", io.BytesIO(payload), "text/csv")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["created"] == 2
    assert len(body["errors"]) == 1
    assert body["errors"][0]["row"] == 3  # row 3 is the bad one (header is row 1)
    assert "NotAStage" in body["errors"][0]["error"]


@pytest.mark.asyncio
async def test_csv_import_rejects_unknown_currency(client, auth_headers):
    # Education org allow-list is [INR, USD]; EUR should fail per row.
    payload = _csv_bytes(
        [
            "Good Row,+919900500007,Test,Qualified,5000,USD",
            "Bad Row,+919900500008,Test,Qualified,5000,EUR",
        ]
    )
    response = await client.post(
        "/api/v1/leads/import",
        headers=auth_headers,
        files={"file": ("leads.csv", io.BytesIO(payload), "text/csv")},
    )
    body = response.json()
    assert body["created"] == 1
    assert len(body["errors"]) == 1
    assert "EUR" in body["errors"][0]["error"]


@pytest.mark.skip(
    reason="Needs Postgres: cross-org invisibility is the schema-per-tenant boundary, "
           "which the collapsed SQLite harness cannot model (see conftest.py)."
)
@pytest.mark.asyncio
async def test_csv_import_scoped_to_org(client):
    """Import in Org A is invisible to Org B."""
    org_a_resp = await client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "A", "last_name": "Admin", "email": "a-imp@example.com",
            "password": "StrongPass123", "role": "admin", "business_type": "education",
            "organization_name": "ImportOrgA",
        },
    )
    org_b_resp = await client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "B", "last_name": "Admin", "email": "b-imp@example.com",
            "password": "StrongPass123", "role": "admin", "business_type": "travel",
            "organization_name": "ImportOrgB",
        },
    )
    h_a = {"Authorization": f"Bearer {org_a_resp.json()['access_token']}"}
    h_b = {"Authorization": f"Bearer {org_b_resp.json()['access_token']}"}

    payload = _csv_bytes(["Alice Lead,+919900500009,From Org A,Qualified,1000,INR"])
    resp = await client.post(
        "/api/v1/leads/import",
        headers=h_a,
        files={"file": ("leads.csv", io.BytesIO(payload), "text/csv")},
    )
    assert resp.json()["created"] == 1

    # Org B sees zero leads.
    b_listed = (await client.get("/api/v1/leads?page=1&page_size=20", headers=h_b)).json()
    assert b_listed["pagination"]["total"] == 0


@pytest.mark.asyncio
async def test_csv_import_requires_contact_name_column(client, auth_headers):
    # Missing the required `contact_name` column entirely → 422.
    payload = b"title,stage\nFoo,Qualified\n"
    response = await client.post(
        "/api/v1/leads/import",
        headers=auth_headers,
        files={"file": ("leads.csv", io.BytesIO(payload), "text/csv")},
    )
    assert response.status_code == 422
    assert "contact_name" in response.json()["error"]["detail"]


@pytest.mark.asyncio
async def test_csv_import_template_download_education(client, auth_headers):
    """auth_headers registers an Education org → Education template (Course column, MBA samples)."""
    response = await client.get(
        "/api/v1/leads/import/template.csv", headers=auth_headers
    )
    assert response.status_code == 200
    body = response.text
    assert "Title" in body
    assert "Course" in body
    assert "Probability (%)" in body
    # build_template_csv emits 1 header + 1 "column sample" row + the vertical's
    # _EXTRA_SAMPLE_ROWS (one per vertical today) — 3 lines, not the 10 sample
    # rows this once asserted. See app/core/lead_csv.py:build_template_csv.
    assert body.count("\n") == 3
    assert "education" in response.headers["content-disposition"].lower()


@pytest.mark.asyncio
async def test_csv_import_template_download_travel(client):
    """A Travel org receives the Destination-flavoured template with travel samples."""
    register = await client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "T",
            "last_name": "Owner",
            "email": "travel-template@example.com",
            "password": "StrongPass123",
            "role": "owner",
            "business_type": "travel",
            "organization_name": "TplTravelCo",
        },
    )
    assert register.status_code == 201, register.text
    headers = {"Authorization": f"Bearer {register.json()['access_token']}"}
    response = await client.get("/api/v1/leads/import/template.csv", headers=headers)
    assert response.status_code == 200
    body = response.text
    assert "Destination" in body
    assert "Bali" in body
    # 1 header + 1 column-sample row + 1 travel example row.
    assert body.count("\n") == 3
    assert "travel" in response.headers["content-disposition"].lower()
