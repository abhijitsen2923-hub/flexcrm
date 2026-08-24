"""Regression tests for the cross-org batch jobs.

These guard the bug class that made `archive`, `customer_health` and
`scorecard_compute` inoperable: they iterated organizations but called only
`set_scope`, which is a no-op compat stub (app/core/tenancy.py). Query routing
comes from `set_tenant_schema`, so every per-tenant read/write targeted the
literal "tenant" schema.

⚠️  Harness limits (see the schema-collapse note in conftest.py): this suite runs
on a single collapsed schema, so it cannot assert that org A's *rows* are
invisible to org B. What it CAN assert — and what actually regressed — is:

  * every org gets `set_tenant_schema` called for it, with its own schema name;
  * routing is cleared when the loop ends, so the session isn't left pinned to
    whichever org happened to be last;
  * `list_active_sales_users` filters by organization_id. That one is a genuine
    isolation test even here, because `users` lives in the PUBLIC schema and is
    shared by every tenant — no schema boundary protects it.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.tenancy import get_schema
from app.database.session import db_manager
from app.hr.services import list_active_sales_users
from app.jobs import archive as archive_job
from app.jobs import customer_health as customer_health_job
from app.jobs import scorecard_compute as scorecard_job
from app.models.organization import Organization
from app.models.user import User


async def _register_org(client, *, email: str, org_name: str, business_type: str = "real_estate") -> dict:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "Job",
            "last_name": "Owner",
            "email": email,
            "password": "StrongPass123",
            "role": "owner",
            "business_type": business_type,
            "organization_name": org_name,
        },
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _spy_on_routing(monkeypatch, job_module) -> list[str]:
    """Record every schema `job_module` routes to, preserving current behaviour."""
    seen: list[str] = []
    original = job_module.set_tenant_schema

    async def _recording(session, schema_name):
        seen.append(schema_name)
        return await original(session, schema_name)

    monkeypatch.setattr(job_module, "set_tenant_schema", _recording)
    return seen


async def _org_schema_names() -> list[str]:
    async with db_manager.session_factory() as session:
        return [
            name
            for name in (await session.execute(select(Organization.schema_name))).scalars().all()
            if name
        ]


@pytest.mark.parametrize(
    "job_module, dispatch_name",
    [
        ("archive", "dispatch_archival"),
        ("customer_health", "dispatch_customer_health"),
        ("scorecard_compute", "dispatch_scorecard_compute"),
    ],
)
@pytest.mark.asyncio
async def test_job_routes_every_org_and_clears_routing_after(
    client, monkeypatch, job_module, dispatch_name
):
    """Each job must call set_tenant_schema once per org, then unpin the session."""
    modules = {
        "archive": archive_job,
        "customer_health": customer_health_job,
        "scorecard_compute": scorecard_job,
    }
    module = modules[job_module]

    await _register_org(client, email="one@jobs.example.com", org_name="Jobs Org One")
    await _register_org(client, email="two@jobs.example.com", org_name="Jobs Org Two")
    expected = await _org_schema_names()
    assert len(expected) == 2

    routed = _spy_on_routing(monkeypatch, module)

    async with db_manager.session_factory() as session:
        await getattr(module, dispatch_name)(session)
        # The loop must not leave the session pinned to the last org — anything
        # run afterwards (e.g. archival's public `users` purge) would silently
        # resolve inside that tenant.
        assert get_schema(session) is None

    assert sorted(routed) == sorted(expected), (
        f"{dispatch_name} routed to {routed}, expected one call per org: {expected}"
    )


@pytest.mark.asyncio
async def test_archival_reports_every_org_and_purges_public_users_once(client):
    await _register_org(client, email="one@arch.example.com", org_name="Arch Org One")
    await _register_org(client, email="two@arch.example.com", org_name="Arch Org Two")

    async with db_manager.session_factory() as session:
        report = await archive_job.dispatch_archival(session, retention_days=90)

    assert report.orgs == 2
    # `users` is public and shared — the purge runs once for the platform, after
    # the org loop, so the key is present exactly once regardless of org count.
    assert "users" in report.deleted


@pytest.mark.asyncio
async def test_list_active_sales_users_is_scoped_to_one_org(client):
    """`users` is PUBLIC and shared across tenants, so this needs an explicit
    organization_id filter — schema routing cannot provide one.

    Without it the nightly scorecard job scores every tenant's users and writes
    a PerformanceSnapshot for each of them into every org's schema.
    """
    await _register_org(client, email="owner@alpha.example.com", org_name="Alpha Realty")
    await _register_org(client, email="owner@beta.example.com", org_name="Beta Realty")

    async with db_manager.session_factory() as session:
        orgs = {
            org.name: org.id
            for org in (await session.execute(select(Organization))).scalars().all()
        }
        alpha_users = await list_active_sales_users(session, orgs["Alpha Realty"])
        beta_users = await list_active_sales_users(session, orgs["Beta Realty"])

        emails_by_org = {
            org_id: {
                u.email
                for u in (
                    await session.execute(select(User).where(User.organization_id == org_id))
                ).scalars().all()
            }
            for org_id in orgs.values()
        }

    alpha_emails = {u.email for u in alpha_users}
    beta_emails = {u.email for u in beta_users}

    assert alpha_emails == {"owner@alpha.example.com"}
    assert beta_emails == {"owner@beta.example.com"}
    assert alpha_emails.isdisjoint(beta_emails)
    # And each result really is a subset of that org's users, not a coincidence.
    assert alpha_emails <= emails_by_org[orgs["Alpha Realty"]]
    assert beta_emails <= emails_by_org[orgs["Beta Realty"]]


@pytest.mark.asyncio
async def test_scorecard_roles_exclude_unassignable_legacy_roles():
    """SCORECARD_ROLES must contain no LEGACY_ROLES member.

    The job previously queried {sales, manager, admin} — all three unassignable
    since the Phase 8 remap (migration 20260522_0010) — so it matched no user and
    silently wrote zero snapshots.
    """
    from app.core.permissions import LEGACY_ROLES, SCORECARD_ROLES

    assert SCORECARD_ROLES
    assert SCORECARD_ROLES.isdisjoint(LEGACY_ROLES)
