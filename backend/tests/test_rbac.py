from datetime import UTC, datetime, timedelta

import pytest


@pytest.mark.asyncio
async def test_sales_cannot_list_or_create_users(client, sales_headers):
    list_response = await client.get("/api/v1/users", headers=sales_headers)
    assert list_response.status_code == 403

    create_response = await client.post(
        "/api/v1/users",
        headers=sales_headers,
        json={
            "first_name": "Should",
            "last_name": "Fail",
            "email": "should.fail@example.com",
            "password": "StrongPass123",
            "role": "counselor",
            "status": "active",
        },
    )
    assert create_response.status_code == 403


async def _make_support_headers(client, auth_headers) -> dict[str, str]:
    """A `support` user: has LEAD_VIEW but NOT LEAD_MANAGE (see
    ROLE_PERMISSION_DEFAULTS in app/core/permissions.py). `support` is
    cross-vertical, so it is assignable inside the Education org."""
    create = await client.post(
        "/api/v1/users",
        headers=auth_headers,
        json={
            "first_name": "Sam",
            "last_name": "Support",
            "email": "support@example.com",
            "password": "StrongPass123",
            "phone": "+1555000003",
            "role": "support",
            "status": "active",
        },
    )
    assert create.status_code == 201, create.text
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "support@example.com", "password": "StrongPass123"},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.mark.asyncio
async def test_lead_manage_role_can_create_and_delete(client, auth_headers, sales_headers):
    """LEAD_MANAGE is a single lead-lifecycle permission — there is no separate
    delete permission, so a `counselor` (which holds LEAD_MANAGE) can delete.

    This previously asserted 403 on delete, which was correct pre-Phase 8 when
    the fixture user was the legacy `sales` role — that role's defaults are now
    empty and it is unassignable. The negative case moved to
    test_view_only_role_cannot_create_or_delete_lead below.
    """
    customer_response = await client.post(
        "/api/v1/customers",
        headers=auth_headers,
        json={
            "company_name": "RBAC Co",
            "contact_name": "Role Test",
            "email": "rbac@example.com",
            "phone": "+15551231234",
            "address": "1 Test Way",
            "source": "referral",
            "status": "prospect",
        },
    )
    customer_id = customer_response.json()["id"]

    create_response = await client.post(
        "/api/v1/leads",
        headers=sales_headers,
        json={
            "customer_id": customer_id,
            "industry": "education",
            "title": "Sales-created lead",
            "contact_name": "RBAC Test Contact",
            "contact_phone": "+919900200001",
            "value": "1000",
            "probability": 10,
            "expected_close_date": (datetime.now(UTC) + timedelta(days=5)).date().isoformat(),
        },
    )
    assert create_response.status_code == 201
    lead_id = create_response.json()["id"]

    delete_response = await client.delete(f"/api/v1/leads/{lead_id}", headers=sales_headers)
    assert delete_response.status_code == 200

    # Already gone — a second delete is a 404.
    cleanup = await client.delete(f"/api/v1/leads/{lead_id}", headers=auth_headers)
    assert cleanup.status_code == 404


@pytest.mark.asyncio
async def test_view_only_role_cannot_create_or_delete_lead(client, auth_headers, sales_headers):
    """A role without LEAD_MANAGE is blocked from both create and delete."""
    support_headers = await _make_support_headers(client, auth_headers)

    blocked_create = await client.post(
        "/api/v1/leads",
        headers=support_headers,
        json={
            "industry": "education",
            "title": "Support should not create this",
            "contact_name": "Support Test Contact",
            "contact_phone": "+919900200002",
        },
    )
    assert blocked_create.status_code == 403

    # A lead that does exist (created by a LEAD_MANAGE role) still can't be deleted.
    created = await client.post(
        "/api/v1/leads",
        headers=sales_headers,
        json={
            "industry": "education",
            "title": "Deletable by counselor only",
            "contact_name": "RBAC Delete Target",
            "contact_phone": "+919900200003",
        },
    )
    assert created.status_code == 201, created.text
    blocked_delete = await client.delete(
        f"/api/v1/leads/{created.json()['id']}", headers=support_headers
    )
    assert blocked_delete.status_code == 403


@pytest.mark.asyncio
async def test_sales_cannot_access_analytics(client, sales_headers):
    response = await client.get("/api/v1/analytics/revenue", headers=sales_headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_missing_token_returns_401(client):
    response = await client.get("/api/v1/customers")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_invalid_token_returns_401(client):
    response = await client.get(
        "/api/v1/customers",
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_user_can_view_own_but_not_other_profile(client, auth_headers, sales_headers):
    # `sales_headers` belongs to the second registered user; fetch their id by
    # listing users as admin first.
    listing = await client.get("/api/v1/users?page=1&page_size=10", headers=auth_headers)
    assert listing.status_code == 200
    items = listing.json()["items"]
    sales_user = next(item for item in items if item["email"] == "sales@example.com")
    admin_user = next(item for item in items if item["email"] == "admin@example.com")

    own_response = await client.get(f"/api/v1/users/{sales_user['id']}", headers=sales_headers)
    assert own_response.status_code == 200

    other_response = await client.get(f"/api/v1/users/{admin_user['id']}", headers=sales_headers)
    assert other_response.status_code == 403
