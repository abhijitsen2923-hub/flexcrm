import pytest


@pytest.mark.asyncio
async def test_register_login_refresh_and_profile(client):
    register_response = await client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "First",
            "last_name": "Admin",
            "email": "first.admin@example.com",
            "password": "StrongPass123",
            "phone": "+1555000100",
            "role": "travel_agent",  # Ignored — first user of an org is always `owner`.
            "business_type": "travel",
        },
    )
    assert register_response.status_code == 201
    registered_payload = register_response.json()
    assert registered_payload["user"]["role"] == "owner"
    assert registered_payload["user"]["business_type"] == "travel"
    # Owner gets the full effective-permission set in the login response.
    assert len(registered_payload["user"]["permissions"]) > 0

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": "first.admin@example.com", "password": "StrongPass123"},
    )
    assert login_response.status_code == 200
    login_payload = login_response.json()
    assert login_payload["access_token"]
    assert login_payload["refresh_token"]

    profile_response = await client.get(
        "/api/v1/auth/profile",
        headers={"Authorization": f"Bearer {login_payload['access_token']}"},
    )
    assert profile_response.status_code == 200
    assert profile_response.json()["email"] == "first.admin@example.com"

    refresh_response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": login_payload["refresh_token"]},
    )
    assert refresh_response.status_code == 200
    refreshed_payload = refresh_response.json()
    assert refreshed_payload["access_token"] != login_payload["access_token"]

    logout_response = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refreshed_payload["refresh_token"]},
    )
    assert logout_response.status_code == 204
