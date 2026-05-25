"""Phase 8 — vertical-locked role validation.

`UserService._validate_role_for_current_org` rejects:
- Legacy roles (admin/manager/sales) entirely.
- Vertical-locked roles assigned in the wrong industry.

It accepts the three cross-vertical roles (`owner`, `support`, `analyst`) in
either an Education or a Travel org.
"""
import pytest


@pytest.mark.asyncio
async def test_education_org_accepts_education_role(client, auth_headers):
    """Counselor is valid in an Education org (the auth_headers fixture's org)."""
    response = await client.post(
        "/api/v1/users",
        headers=auth_headers,
        json={
            "first_name": "Aman",
            "last_name": "Counselor",
            "email": "aman.counselor@example.com",
            "password": "StrongPass123",
            "role": "counselor",
            "status": "active",
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["role"] == "counselor"


@pytest.mark.asyncio
async def test_education_org_rejects_travel_role(client, auth_headers):
    """visa_coordinator is travel-only — assigning to an Education org's user fails."""
    response = await client.post(
        "/api/v1/users",
        headers=auth_headers,
        json={
            "first_name": "Wrong",
            "last_name": "Vertical",
            "email": "wrong.vertical@example.com",
            "password": "StrongPass123",
            "role": "visa_coordinator",
            "status": "active",
        },
    )
    assert response.status_code == 422, response.text
    assert "visa_coordinator" in response.json()["error"]["detail"]
    assert "education" in response.json()["error"]["detail"]


@pytest.mark.asyncio
async def test_education_org_rejects_other_travel_roles(client, auth_headers):
    """`ops_manager` and `travel_agent` also rejected in an Education org."""
    for role in ("ops_manager", "travel_agent"):
        response = await client.post(
            "/api/v1/users",
            headers=auth_headers,
            json={
                "first_name": "Wrong",
                "last_name": role.title(),
                "email": f"wrong-{role}@example.com",
                "password": "StrongPass123",
                "role": role,
                "status": "active",
            },
        )
        assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_travel_org_accepts_visa_coordinator(client):
    """visa_coordinator works in a Travel org."""
    register = await client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "Travel",
            "last_name": "Owner",
            "email": "travel-owner@example.com",
            "password": "StrongPass123",
            "role": "owner",
            "business_type": "travel",
            "organization_name": "Travel Co",
        },
    )
    travel_headers = {"Authorization": f"Bearer {register.json()['access_token']}"}

    response = await client.post(
        "/api/v1/users",
        headers=travel_headers,
        json={
            "first_name": "Visa",
            "last_name": "Person",
            "email": "visa.person@example.com",
            "password": "StrongPass123",
            "role": "visa_coordinator",
            "status": "active",
        },
    )
    assert response.status_code == 201, response.text


@pytest.mark.asyncio
async def test_travel_org_rejects_counselor(client):
    """counselor is education-only — rejected in a Travel org."""
    register = await client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "T",
            "last_name": "Owner",
            "email": "t-owner@example.com",
            "password": "StrongPass123",
            "role": "owner",
            "business_type": "travel",
            "organization_name": "Travel Co 2",
        },
    )
    headers = {"Authorization": f"Bearer {register.json()['access_token']}"}

    response = await client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "first_name": "Wrong",
            "last_name": "Vertical",
            "email": "wrong-edu-in-travel@example.com",
            "password": "StrongPass123",
            "role": "counselor",
            "status": "active",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_first_user_always_owner(client):
    """Phase 8: regardless of the request's `role`, first user of a new org is `owner`."""
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "Should",
            "last_name": "Be",
            "email": "should-be-owner@example.com",
            "password": "StrongPass123",
            "role": "support",  # Even though we asked for support, registration overrides.
            "business_type": "education",
            "organization_name": "Forced Owner Org",
        },
    )
    assert response.status_code == 201
    assert response.json()["user"]["role"] == "owner"


@pytest.mark.asyncio
async def test_legacy_role_assignment_rejected(client, auth_headers):
    """Legacy `sales` role is no longer assignable post-Phase 8."""
    response = await client.post(
        "/api/v1/users",
        headers=auth_headers,
        json={
            "first_name": "Legacy",
            "last_name": "Sales",
            "email": "legacy-sales@example.com",
            "password": "StrongPass123",
            "role": "sales",
            "status": "active",
        },
    )
    assert response.status_code == 422
    assert "legacy" in response.json()["error"]["detail"].lower()


@pytest.mark.asyncio
async def test_cross_vertical_roles_accepted_in_both(client, auth_headers):
    """`support` and `analyst` work in either vertical."""
    for role in ("support", "analyst"):
        response = await client.post(
            "/api/v1/users",
            headers=auth_headers,
            json={
                "first_name": "X",
                "last_name": role.title(),
                "email": f"x-{role}@example.com",
                "password": "StrongPass123",
                "role": role,
                "status": "active",
            },
        )
        assert response.status_code == 201, f"role={role} failed: {response.text}"
