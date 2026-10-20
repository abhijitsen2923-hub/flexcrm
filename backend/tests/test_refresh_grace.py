"""Refresh-token rotation with a short reuse grace period: the same renewal arriving twice (its reply lost in a deploy
or on a bad network, two tabs renewing at once) must not sign the user out. A token ended on purpose — signed out,
user removed — never renews again, and past the grace period a replaced token is refused as before."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update

from app.database.session import db_manager
from app.models.refresh_token import RefreshToken


async def _login(client) -> dict:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "Rita", "last_name": "Renew", "email": "rita@example.com", "password": "StrongPass123",
            "phone": "+1555000101", "role": "owner", "business_type": "education", "organization_name": "Renew Org",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _refresh(client, token: str):
    return await client.post("/api/v1/auth/refresh", json={"refresh_token": token})


async def _age_rotations(seconds: int) -> None:
    """Pretend every rotation happened `seconds` ago."""
    async with db_manager.session_factory() as session:
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.revoked_at.is_not(None))
            .values(revoked_at=datetime.now(UTC) - timedelta(seconds=seconds))
        )
        await session.commit()


@pytest.mark.asyncio
async def test_the_same_renewal_twice_inside_the_grace_period_keeps_the_user_signed_in(client):
    first = await _login(client)
    renewed = await _refresh(client, first["refresh_token"])
    assert renewed.status_code == 200, renewed.text
    # Its reply was lost — the browser retries with the token it still has.
    again = await _refresh(client, first["refresh_token"])
    assert again.status_code == 200, again.text
    # Both new tokens work; each renews in turn.
    for body in (renewed.json(), again.json()):
        profile = await client.get("/api/v1/auth/profile", headers={"Authorization": f"Bearer {body['access_token']}"})
        assert profile.status_code == 200
        assert (await _refresh(client, body["refresh_token"])).status_code == 200


@pytest.mark.asyncio
async def test_two_tabs_renewing_at_the_same_moment_both_succeed(client):
    first = await _login(client)
    a, b = await asyncio.gather(_refresh(client, first["refresh_token"]), _refresh(client, first["refresh_token"]))
    assert (a.status_code, b.status_code) == (200, 200), (a.text, b.text)


@pytest.mark.asyncio
async def test_a_replaced_token_is_refused_after_the_grace_period(client):
    first = await _login(client)
    renewed = await _refresh(client, first["refresh_token"])
    assert renewed.status_code == 200
    await _age_rotations(31)
    late = await _refresh(client, first["refresh_token"])
    assert late.status_code == 401
    # The current token is unaffected.
    assert (await _refresh(client, renewed.json()["refresh_token"])).status_code == 200


@pytest.mark.asyncio
async def test_signed_out_tokens_never_renew_not_even_the_one_renewed_just_before(client):
    first = await _login(client)
    renewed = (await _refresh(client, first["refresh_token"])).json()
    out = await client.post("/api/v1/auth/logout", json={"refresh_token": renewed["refresh_token"]})
    assert out.status_code == 204
    assert (await _refresh(client, renewed["refresh_token"])).status_code == 401
    # The token replaced seconds before signing out is inside the grace period — still refused.
    assert (await _refresh(client, first["refresh_token"])).status_code == 401
    # Signing out twice is harmless.
    assert (await client.post("/api/v1/auth/logout", json={"refresh_token": renewed["refresh_token"]})).status_code == 204


@pytest.mark.asyncio
async def test_a_removed_users_tokens_end_at_once(client, auth_headers):
    created = await client.post(
        "/api/v1/users",
        headers=auth_headers,
        json={
            "first_name": "Gone", "last_name": "Soon", "email": "gone@example.com", "password": "StrongPass123",
            "role": "counselor", "status": "active",
        },
    )
    assert created.status_code == 201, created.text
    login = (await client.post("/api/v1/auth/login", json={"email": "gone@example.com", "password": "StrongPass123"})).json()
    renewed = (await _refresh(client, login["refresh_token"])).json()
    removed = await client.delete(f"/api/v1/users/{created.json()['id']}", headers=auth_headers)
    assert removed.status_code == 200, removed.text
    assert (await _refresh(client, renewed["refresh_token"])).status_code == 401
    assert (await _refresh(client, login["refresh_token"])).status_code == 401
