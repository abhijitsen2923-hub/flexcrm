"""FlexCRM runs real estate only: a new workspace can't be created for Education or Travel (existing ones keep
working), and a real-estate workspace's staff get the real-estate CSV template.
"""
from __future__ import annotations

import pytest

from app.core.config import get_settings


def _register_body(email: str, business_type: str | None) -> dict:
    body = {"first_name": "Nia", "last_name": "Owner", "email": email, "password": "StrongPass123",
            "role": "owner", "organization_name": f"{email.split('@')[0]} Org"}
    if business_type is not None:
        body["business_type"] = business_type
    return body


@pytest.fixture
def default_signup_types(monkeypatch):
    """The deployment default (the test fixtures allow all three for the older tests)."""
    monkeypatch.delenv("SIGNUP_BUSINESS_TYPES", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
@pytest.mark.parametrize("business_type", ["education", "travel"])
async def test_education_and_travel_signups_are_refused(client, default_signup_types, business_type):
    response = await client.post("/api/v1/auth/register", json=_register_body(f"{business_type}@v.example.com", business_type))

    assert response.status_code == 422, response.text
    assert "only be created for real estate" in response.json()["error"]["detail"]
    # Nothing was created: the email is still free for a real-estate signup.
    again = await client.post("/api/v1/auth/register", json=_register_body(f"{business_type}@v.example.com", "real_estate"))
    assert again.status_code == 201, again.text


@pytest.mark.asyncio
async def test_signup_defaults_to_real_estate(client, default_signup_types):
    response = await client.post("/api/v1/auth/register", json=_register_body("plain@v.example.com", None))

    assert response.status_code == 201, response.text
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    org = await client.get("/api/v1/organizations/me", headers=headers)
    assert org.status_code == 200, org.text
    assert org.json()["business_type"] == "real_estate"


@pytest.mark.asyncio
async def test_staff_of_a_real_estate_workspace_get_the_real_estate_template(client, default_signup_types):
    owner = await client.post("/api/v1/auth/register", json=_register_body("boss@v.example.com", "real_estate"))
    owner_headers = {"Authorization": f"Bearer {owner.json()['access_token']}"}
    created = await client.post(
        "/api/v1/users", headers=owner_headers,
        json={"first_name": "Mira", "last_name": "Manager", "email": "mira@v.example.com", "password": "StrongPass123",
              "phone": "+919900411111", "role": "sales_manager", "status": "active"},
    )
    assert created.status_code == 201, created.text
    login = await client.post("/api/v1/auth/login", json={"email": "mira@v.example.com", "password": "StrongPass123"})
    staff_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    template = await client.get("/api/v1/leads/import/template.csv", headers=staff_headers)

    assert template.status_code == 200, template.text
    header = template.text.splitlines()[0]
    assert "Property type" in header and "Budget min" in header
    assert "Course" not in header and "Value" not in header
    assert "real_estate" in template.headers["content-disposition"]
