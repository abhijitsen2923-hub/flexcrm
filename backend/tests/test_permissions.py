"""Phase 8 — fine-grained permissions tests.

Covers the role-defaults / explicit-grants / alias-expansion mechanics and the
endpoint enforcement around them. Tests run against the same in-memory SQLite
schema as the rest of the suite (see conftest.py); the `auth_headers` fixture
registers an Education org whose first user is `owner`.
"""
import pytest


@pytest.mark.asyncio
async def test_owner_has_full_permission_set(client, auth_headers):
    """Owner role grants every permission in the catalog."""
    me = await client.get("/api/v1/me/permissions", headers=auth_headers)
    assert me.status_code == 200, me.text
    body = me.json()
    # Owner gets every PermissionCode. The sentinel here checks for a few of
    # the cross-cutting ones — if defaults change, this list might shrink, but
    # at minimum the owner should have full management codes.
    for code in ("USER_MANAGE", "FINANCE_REFUND", "ORG_MANAGE", "LEAD_DOCS_MANAGE"):
        assert code in body["effective"], f"{code} missing from owner's effective perms"


@pytest.mark.asyncio
async def test_counselor_default_permissions_only(client, sales_headers):
    """A counselor (sales_headers fixture) gets the operational slice — not USER_MANAGE."""
    me = await client.get("/api/v1/me/permissions", headers=sales_headers)
    assert me.status_code == 200
    body = me.json()
    effective = set(body["effective"])
    # Operational perms a counselor should have.
    assert "LEAD_MANAGE" in effective
    assert "CUSTOMER_MANAGE" in effective
    assert "FINANCE_VIEW" in effective
    # Admin-only perms a counselor should NOT have.
    assert "USER_MANAGE" not in effective
    assert "ORG_MANAGE" not in effective
    assert "FINANCE_REFUND" not in effective
    # No explicit grants yet — `granted` is empty.
    assert body["granted"] == []


@pytest.mark.asyncio
async def test_alias_expansion_lead_manage_implies_lead_view(client, sales_headers):
    """LEAD_MANAGE implies LEAD_VIEW via PERMISSION_ALIASES."""
    me = await client.get("/api/v1/me/permissions", headers=sales_headers)
    effective = set(me.json()["effective"])
    assert "LEAD_MANAGE" in effective
    assert "LEAD_VIEW" in effective, "LEAD_MANAGE should alias-expand to include LEAD_VIEW"


@pytest.mark.asyncio
async def test_403_carries_missing_codes(client, sales_headers):
    """Endpoint 403 surfaces the missing permission code in the error detail."""
    response = await client.post(
        "/api/v1/users",
        headers=sales_headers,
        json={
            "first_name": "Should",
            "last_name": "Fail",
            "email": "should-fail@example.com",
            "password": "StrongPass123",
            "role": "counselor",
            "status": "active",
        },
    )
    assert response.status_code == 403, response.text
    assert "USER_MANAGE" in response.json()["error"]["detail"]


@pytest.mark.asyncio
async def test_explicit_grant_unlocks_endpoint(client, auth_headers, sales_headers):
    """Owner grants FINANCE_REFUND to counselor; counselor's /me/permissions reflects it."""
    # Find the counselor user id via the user list (auth_headers is the owner).
    listing = await client.get("/api/v1/users?page=1&page_size=20", headers=auth_headers)
    sales_user = next(u for u in listing.json()["items"] if u["email"] == "sales@example.com")

    grant = await client.post(
        f"/api/v1/users/{sales_user['id']}/permissions",
        headers=auth_headers,
        json={"permission_code": "FINANCE_REFUND"},
    )
    assert grant.status_code == 201, grant.text

    # Refetch the counselor's effective set — should now include FINANCE_REFUND
    # and its aliases (FINANCE_VIEW, FINANCE_RECORD_PAYMENT — counselor already
    # had these, so the assertion is on FINANCE_REFUND specifically).
    me = await client.get("/api/v1/me/permissions", headers=sales_headers)
    assert "FINANCE_REFUND" in me.json()["effective"]


@pytest.mark.asyncio
async def test_revoke_explicit_grant(client, auth_headers, sales_headers):
    """After revoking, the permission disappears from /me/permissions."""
    listing = await client.get("/api/v1/users?page=1&page_size=20", headers=auth_headers)
    sales_user = next(u for u in listing.json()["items"] if u["email"] == "sales@example.com")

    await client.post(
        f"/api/v1/users/{sales_user['id']}/permissions",
        headers=auth_headers,
        json={"permission_code": "ORG_MANAGE"},
    )
    me = await client.get("/api/v1/me/permissions", headers=sales_headers)
    assert "ORG_MANAGE" in me.json()["effective"]

    revoke = await client.delete(
        f"/api/v1/users/{sales_user['id']}/permissions/ORG_MANAGE",
        headers=auth_headers,
    )
    assert revoke.status_code == 200, revoke.text

    me = await client.get("/api/v1/me/permissions", headers=sales_headers)
    assert "ORG_MANAGE" not in me.json()["effective"]


@pytest.mark.asyncio
async def test_cannot_revoke_role_default(client, auth_headers):
    """Role-default permissions are NOT in `user_permission_grants`, so DELETE 404s."""
    listing = await client.get("/api/v1/users?page=1&page_size=20", headers=auth_headers)
    owner_user = next(u for u in listing.json()["items"] if u["email"] == "admin@example.com")
    revoke = await client.delete(
        f"/api/v1/users/{owner_user['id']}/permissions/USER_MANAGE",
        headers=auth_headers,
    )
    assert revoke.status_code == 404
    assert "Role defaults are not revocable" in revoke.json()["error"]["detail"]


@pytest.mark.asyncio
async def test_login_response_carries_permissions(client, auth_headers):
    """POST /auth/login returns user.permissions populated."""
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "StrongPass123"},
    )
    assert login.status_code == 200
    perms = login.json()["user"]["permissions"]
    assert isinstance(perms, list) and len(perms) > 0
    assert "USER_MANAGE" in perms


@pytest.mark.asyncio
async def test_grant_to_user_in_other_org_returns_404(client, auth_headers):
    """Org A admin cannot grant against Org B users — tenancy hides them as 404."""
    # Create a second org.
    other_org = await client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "B",
            "last_name": "Owner",
            "email": "b-owner@example.com",
            "password": "StrongPass123",
            "role": "owner",
            "business_type": "travel",
            "organization_name": "Other Org",
        },
    )
    other_user_id = other_org.json()["user"]["id"]

    grant = await client.post(
        f"/api/v1/users/{other_user_id}/permissions",
        headers=auth_headers,  # Org A admin
        json={"permission_code": "LEAD_VIEW"},
    )
    assert grant.status_code == 404


@pytest.mark.asyncio
async def test_duplicate_grant_409(client, auth_headers):
    """Granting the same permission twice returns 409 instead of breaking the unique constraint."""
    listing = await client.get("/api/v1/users?page=1&page_size=20", headers=auth_headers)
    sales_user = next((u for u in listing.json()["items"] if u["email"] == "sales@example.com"), None)
    if sales_user is None:
        # No counselor yet — create one inline so this test stands alone.
        create = await client.post(
            "/api/v1/users",
            headers=auth_headers,
            json={
                "first_name": "Dup",
                "last_name": "Test",
                "email": "dup-test@example.com",
                "password": "StrongPass123",
                "role": "counselor",
                "status": "active",
            },
        )
        assert create.status_code == 201
        sales_user = create.json()

    first = await client.post(
        f"/api/v1/users/{sales_user['id']}/permissions",
        headers=auth_headers,
        json={"permission_code": "ANALYTICS_VIEW"},
    )
    assert first.status_code == 201

    second = await client.post(
        f"/api/v1/users/{sales_user['id']}/permissions",
        headers=auth_headers,
        json={"permission_code": "ANALYTICS_VIEW"},
    )
    assert second.status_code == 409
