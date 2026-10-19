"""A custom role's "Data access": its users see only the leads of the chosen campaigns and/or sources (or only the
leads assigned to them) — and only what is built from those leads. Adding or editing a lead stays inside the limits;
a CSV row outside them is reported, not imported. A limited user never manages users, roles, the workspace or the
campaign list, and nobody hands out a role with more than they hold."""
from __future__ import annotations

import csv
import io
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.database.session import db_manager
from app.models.custom_role import CustomRole
from app.models.notification import Notification
from app.services.lead_scope import LeadScope

_seq = iter(range(1, 100_000))

LIMITED_PERMISSIONS = ["DASHBOARD_VIEW", "LEAD_VIEW", "LEAD_MANAGE", "LEAD_IMPORT", "CUSTOMER_VIEW", "ANALYTICS_VIEW"]


def _phone() -> str:
    return f"+9198110{next(_seq):05d}"


def _detail(response) -> str:
    body = response.json()
    error = body.get("error", body)
    detail = error.get("detail")
    if isinstance(detail, list):
        return " ".join(str(d.get("msg", d)) for d in detail)
    return str(detail)


async def _campaign(client, owner, name: str) -> str:
    response = await client.post("/api/v1/campaigns", headers=owner, json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _lead(client, headers, *, campaign=None, source=None, assigned_to_id=None, title="Enquiry"):
    body = {"title": title, "contact_name": "Asha Roy", "contact_phone": _phone()}
    if campaign is not None:
        body["campaign"] = campaign
    if source is not None:
        body["source"] = source
    if assigned_to_id is not None:
        body["assigned_to_id"] = str(assigned_to_id)
    return await client.post("/api/v1/leads", headers=headers, json=body)


async def _role(client, owner, name: str, *, lead_access: dict, permissions=None):
    return await client.post(
        "/api/v1/custom-roles",
        headers=owner,
        json={"name": name, "permissions": permissions or LIMITED_PERMISSIONS, "lead_access": lead_access},
    )


async def _user(client, owner, role_id: str, email: str) -> tuple[dict[str, str], str, dict]:
    created = await client.post(
        "/api/v1/users",
        headers=owner,
        json={
            "first_name": "Lim",
            "last_name": "Ited",
            "email": email,
            "password": "StrongPass123",
            "role": "custom",
            "custom_role_id": role_id,
            "status": "active",
        },
    )
    assert created.status_code == 201, created.text
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": "StrongPass123"})
    assert login.status_code == 200, login.text
    body = login.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, created.json()["id"], body["user"]


async def _seed(client, owner):
    """Campaigns A and B; leads: A/Website, A/Walk-in, B/Website, no campaign/Website, A/no source."""
    a = await _campaign(client, owner, "Alpha Towers")
    b = await _campaign(client, owner, "Beta Homes")
    leads = {}
    for key, campaign, source in [
        ("a_web", "Alpha Towers", "Website"),
        ("a_walk", "Alpha Towers", "Walk-in"),
        ("b_web", "Beta Homes", "Website"),
        ("none_web", None, "Website"),
        ("a_none", "Alpha Towers", None),
    ]:
        response = await _lead(client, owner, campaign=campaign, source=source, title=key)
        assert response.status_code == 201, response.text
        leads[key] = response.json()["id"]
    return a, b, leads


async def _visible_titles(client, headers) -> set[str]:
    response = await client.get("/api/v1/leads", headers=headers, params={"page_size": 100})
    assert response.status_code == 200, response.text
    return {item["title"] for item in response.json()["items"]}


# ---- the role's settings ------------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_role_saves_and_reads_back_its_data_access(client, auth_headers):
    a, b, _ = await _seed(client, auth_headers)
    created = await _role(
        client, auth_headers, "Alpha web", lead_access={"campaign_ids": [a], "sources": [" website ", "Website"]}
    )
    assert created.status_code == 201, created.text
    access = created.json()["lead_access"]
    assert access == {
        "own_leads_only": False,
        "campaigns": [{"id": a, "name": "Alpha Towers"}],
        "sources": ["website"],
    }

    # Unrestricted by default; list shows the same.
    plain = await _role(client, auth_headers, "Everyone", lead_access={})
    assert plain.json()["lead_access"] == {"own_leads_only": False, "campaigns": None, "sources": None}
    listed = {r["name"]: r["lead_access"] for r in (await client.get("/api/v1/custom-roles", headers=auth_headers)).json()}
    assert listed["Alpha web"]["campaigns"] == [{"id": a, "name": "Alpha Towers"}]

    # Edit: switch to campaign B only, sources back to all.
    role_id = created.json()["id"]
    updated = await client.put(
        f"/api/v1/custom-roles/{role_id}", headers=auth_headers, json={"lead_access": {"campaign_ids": [b]}}
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["lead_access"]["campaigns"] == [{"id": b, "name": "Beta Homes"}]
    assert updated.json()["lead_access"]["sources"] is None

    # Editing only the name leaves the access alone.
    renamed = await client.put(f"/api/v1/custom-roles/{role_id}", headers=auth_headers, json={"name": "Beta only"})
    assert renamed.json()["lead_access"]["campaigns"] == [{"id": b, "name": "Beta Homes"}]


@pytest.mark.asyncio
async def test_role_data_access_is_validated(client, auth_headers):
    a, _, _ = await _seed(client, auth_headers)
    empty = await _role(client, auth_headers, "Empty", lead_access={"campaign_ids": []})
    assert empty.status_code == 422
    assert "at least one campaign" in _detail(empty)

    unknown = await _role(client, auth_headers, "Unknown", lead_access={"campaign_ids": [str(uuid4())]})
    assert unknown.status_code == 422
    assert "no longer exist" in _detail(unknown)

    blank_sources = await _role(client, auth_headers, "Blank", lead_access={"sources": ["  "]})
    assert blank_sources.status_code == 422

    managing = await _role(
        client, auth_headers, "Limited admin", lead_access={"campaign_ids": [a]},
        permissions=[*LIMITED_PERMISSIONS, "USER_MANAGE"],
    )
    assert managing.status_code == 422
    assert "Manage users" in _detail(managing)

    # An unlimited role may hold it; limiting it later is refused while it does.
    admin = await _role(client, auth_headers, "Admin-ish", lead_access={}, permissions=["LEAD_VIEW", "USER_MANAGE"])
    assert admin.status_code == 201, admin.text
    limit = await client.put(
        f"/api/v1/custom-roles/{admin.json()['id']}", headers=auth_headers, json={"lead_access": {"own_leads_only": True}}
    )
    assert limit.status_code == 422


@pytest.mark.asyncio
async def test_lead_access_options_lists_campaigns_and_sources(client, auth_headers):
    await _seed(client, auth_headers)
    await _lead(client, auth_headers, source="Expo 2026")
    response = await client.get("/api/v1/custom-roles/lead-access-options", headers=auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert [c["name"] for c in body["campaigns"]] == ["Alpha Towers", "Beta Homes"]
    assert {"Website", "Walk-in", "Expo 2026"} <= set(body["sources"])


# ---- what a limited user sees -------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_campaign_and_source_limits_must_both_match(client, auth_headers):
    a, _, leads = await _seed(client, auth_headers)
    role = await _role(client, auth_headers, "Alpha web", lead_access={"campaign_ids": [a], "sources": ["website"]})
    headers, _, user = await _user(client, auth_headers, role.json()["id"], "alpha.web@example.com")

    assert await _visible_titles(client, headers) == {"a_web"}
    assert user["lead_access"] == {"own_leads_only": False, "campaigns": ["Alpha Towers"], "sources": ["website"]}

    # By id: hidden leads are "not found", also their history and calls.
    assert (await client.get(f"/api/v1/leads/{leads['b_web']}/transitions", headers=headers)).status_code == 404
    assert (await client.get(f"/api/v1/leads/{leads['b_web']}/assignments", headers=headers)).status_code == 404
    assert (await client.get(f"/api/v1/leads/{leads['b_web']}/intent-changes", headers=headers)).status_code == 404
    assert (await client.get(f"/api/v1/leads/{leads['b_web']}/calls", headers=headers)).status_code == 404
    assert (await client.get(f"/api/v1/leads/{leads['a_web']}/transitions", headers=headers)).status_code == 200
    hidden_edit = await client.put(f"/api/v1/leads/{leads['b_web']}", headers=headers, json={"notes": "x"})
    assert hidden_edit.status_code == 404
    hidden_delete = await client.delete(f"/api/v1/leads/{leads['a_walk']}", headers=headers)
    assert hidden_delete.status_code == 404

    # Filters / pickers offer only what's inside the limits.
    assert (await client.get("/api/v1/leads/campaigns", headers=headers)).json() == ["Alpha Towers"]
    assert [c["name"] for c in (await client.get("/api/v1/campaigns", headers=headers)).json()] == ["Alpha Towers"]

    # The owner still sees everything.
    assert await _visible_titles(client, auth_headers) == {"a_web", "a_walk", "b_web", "none_web", "a_none"}


@pytest.mark.asyncio
async def test_blank_campaign_or_source_is_outside_a_limit(client, auth_headers):
    a, _, _ = await _seed(client, auth_headers)
    by_campaign = await _role(client, auth_headers, "Alpha", lead_access={"campaign_ids": [a]})
    headers, _, _ = await _user(client, auth_headers, by_campaign.json()["id"], "alpha@example.com")
    assert await _visible_titles(client, headers) == {"a_web", "a_walk", "a_none"}

    by_source = await _role(client, auth_headers, "Web", lead_access={"sources": ["Website"]})
    headers, _, _ = await _user(client, auth_headers, by_source.json()["id"], "web@example.com")
    assert await _visible_titles(client, headers) == {"a_web", "b_web", "none_web"}


@pytest.mark.asyncio
async def test_duplicate_check_does_not_reveal_hidden_leads(client, auth_headers):
    a, _, _ = await _seed(client, auth_headers)
    hidden = await _lead(client, auth_headers, campaign="Beta Homes", source="Website", title="hidden")
    phone = hidden.json()["contact_phone"]
    role = await _role(client, auth_headers, "Alpha", lead_access={"campaign_ids": [a]})
    headers, _, _ = await _user(client, auth_headers, role.json()["id"], "dup@example.com")
    response = await client.get("/api/v1/leads/duplicates", headers=headers, params={"phone": phone})
    assert response.status_code == 200
    assert response.json() == []
    owner_view = await client.get("/api/v1/leads/duplicates", headers=auth_headers, params={"phone": phone})
    assert len(owner_view.json()) == 1


@pytest.mark.asyncio
async def test_own_leads_only(client, auth_headers):
    role = await _role(client, auth_headers, "Mine", lead_access={"own_leads_only": True})
    headers, user_id, _ = await _user(client, auth_headers, role.json()["id"], "mine@example.com")
    await _lead(client, auth_headers, title="someone else's")
    await _lead(client, auth_headers, title="theirs", assigned_to_id=user_id)

    assert await _visible_titles(client, headers) == {"theirs"}

    # A new lead with no owner becomes theirs (else it would vanish from their list).
    created = await _lead(client, headers, title="new")
    assert created.status_code == 201, created.text
    assert created.json()["assigned_to"]["id"] == user_id
    assert await _visible_titles(client, headers) == {"theirs", "new"}

    # Handing one to someone else works and answers with the saved lead, which then leaves their view.
    owner_id = (await client.get("/api/v1/auth/profile", headers=auth_headers)).json()["id"]
    handed = await client.put(
        f"/api/v1/leads/{created.json()['id']}", headers=headers, json={"assigned_to_id": owner_id}
    )
    assert handed.status_code == 200, handed.text
    assert handed.json()["assigned_to"]["id"] == owner_id
    assert await _visible_titles(client, headers) == {"theirs"}


# ---- adding and editing -------------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_adding_and_editing_stay_inside_the_limits(client, auth_headers):
    a, _, _ = await _seed(client, auth_headers)
    role = await _role(client, auth_headers, "Alpha web", lead_access={"campaign_ids": [a], "sources": ["Website"]})
    headers, _, _ = await _user(client, auth_headers, role.json()["id"], "writer@example.com")

    wrong_campaign = await _lead(client, headers, campaign="Beta Homes", source="Website")
    assert wrong_campaign.status_code == 422
    assert "Not your campaign" in _detail(wrong_campaign)
    no_campaign = await _lead(client, headers, source="Website")
    assert no_campaign.status_code == 422
    assert "Choose a campaign" in _detail(no_campaign)
    wrong_source = await _lead(client, headers, campaign="Alpha Towers", source="Walk-in")
    assert wrong_source.status_code == 422
    assert "Not your source" in _detail(wrong_source)

    ok = await _lead(client, headers, campaign=" alpha towers ", source="website", title="mine")
    assert ok.status_code == 201, ok.text
    assert ok.json()["campaign"] == "Alpha Towers"
    lead_id = ok.json()["id"]

    moved = await client.put(f"/api/v1/leads/{lead_id}", headers=headers, json={"campaign": "Beta Homes"})
    assert moved.status_code == 422
    resourced = await client.put(f"/api/v1/leads/{lead_id}", headers=headers, json={"source": "Walk-in"})
    assert resourced.status_code == 422
    other_edit = await client.put(f"/api/v1/leads/{lead_id}", headers=headers, json={"notes": "called"})
    assert other_edit.status_code == 200, other_edit.text


@pytest.mark.asyncio
async def test_csv_rows_outside_the_limits_are_reported_not_imported(client, auth_headers):
    a, _, _ = await _seed(client, auth_headers)
    role = await _role(client, auth_headers, "Alpha", lead_access={"campaign_ids": [a]})
    headers, _, _ = await _user(client, auth_headers, role.json()["id"], "csv@example.com")

    rows = [
        {"Contact name": "In", "Phone": _phone(), "Campaign": "Alpha Towers"},
        {"Contact name": "Out", "Phone": _phone(), "Campaign": "Beta Homes"},
        {"Contact name": "Blank", "Phone": _phone(), "Campaign": ""},
    ]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=["Contact name", "Phone", "Campaign"])
    writer.writeheader()
    writer.writerows(rows)
    response = await client.post(
        "/api/v1/leads/import",
        headers=headers,
        files={"file": ("leads.csv", buffer.getvalue().encode(), "text/csv")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created"] == 1
    errors = {e["row"]: e["error"] for e in body["errors"]}
    assert "Not your campaign" in errors[3]
    assert "Choose a campaign" in errors[4]


# ---- permissions ----------------------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_limited_user_never_manages_users_even_with_a_grant(client, auth_headers):
    a, _, _ = await _seed(client, auth_headers)
    role = await _role(client, auth_headers, "Alpha", lead_access={"campaign_ids": [a]})
    headers, user_id, _ = await _user(client, auth_headers, role.json()["id"], "nogrant@example.com")
    granted = await client.post(
        f"/api/v1/users/{user_id}/permissions", headers=auth_headers, json={"permission_code": "USER_MANAGE"}
    )
    assert granted.status_code == 201, granted.text

    profile = (await client.get("/api/v1/auth/profile", headers=headers)).json()
    assert "USER_MANAGE" not in profile["permissions"]
    assert (await client.get("/api/v1/custom-roles", headers=headers)).status_code == 403
    assert (await client.get("/api/v1/campaigns/manage", headers=headers)).status_code == 403


@pytest.mark.asyncio
async def test_switched_off_role_grants_nothing(client, auth_headers):
    role = await _role(client, auth_headers, "Plain", lead_access={})
    headers, _, _ = await _user(client, auth_headers, role.json()["id"], "off@example.com")
    assert (await client.get("/api/v1/leads", headers=headers)).status_code == 200
    off = await client.put(f"/api/v1/custom-roles/{role.json()['id']}", headers=auth_headers, json={"is_active": False})
    assert off.status_code == 200
    assert (await client.get("/api/v1/leads", headers=headers)).status_code == 403
    assert (await client.get("/api/v1/auth/profile", headers=headers)).json()["permissions"] == []


@pytest.mark.asyncio
async def test_nobody_hands_out_more_than_they_hold_or_changes_their_own_role(client, auth_headers):
    # A (non-owner) user manager: may manage users, but holds no finance permissions.
    manager_role = await _role(
        client, auth_headers, "User manager", lead_access={}, permissions=["LEAD_VIEW", "USER_VIEW", "USER_MANAGE"]
    )
    headers, manager_id, _ = await _user(client, auth_headers, manager_role.json()["id"], "um@example.com")

    bigger = await _role(client, headers, "Finance", lead_access={}, permissions=["LEAD_VIEW", "FINANCE_REFUND"])
    assert bigger.status_code == 403
    assert "FINANCE_REFUND" in _detail(bigger)
    fine = await _role(client, headers, "Viewer", lead_access={}, permissions=["LEAD_VIEW"])
    assert fine.status_code == 201, fine.text

    # Can't give themselves another role, nor reset someone to owner.
    own = await client.post(
        f"/api/v1/users/{manager_id}/custom-role", headers=headers, json={"custom_role_id": fine.json()["id"]}
    )
    assert own.status_code == 403
    finance_role = await _role(client, auth_headers, "Finance team", lead_access={}, permissions=["FINANCE_REFUND"])
    _, other_id, _ = await _user(client, auth_headers, fine.json()["id"], "other@example.com")
    assign_bigger = await client.post(
        f"/api/v1/users/{other_id}/custom-role", headers=headers, json={"custom_role_id": finance_role.json()["id"]}
    )
    assert assign_bigger.status_code == 403
    to_owner = await client.request(
        "DELETE", f"/api/v1/users/{other_id}/custom-role", headers=headers, json={"new_role": "owner"}
    )
    assert to_owner.status_code in (403, 422)
    create_bigger = await client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "first_name": "F", "last_name": "T", "email": "ft@example.com", "password": "StrongPass123",
            "role": "custom", "custom_role_id": finance_role.json()["id"], "status": "active",
        },
    )
    assert create_bigger.status_code == 403


# ---- campaign list changes follow into roles ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_merge_and_clear_follow_into_roles(client, auth_headers):
    a, b, _ = await _seed(client, auth_headers)
    role = await _role(client, auth_headers, "Beta", lead_access={"campaign_ids": [b]})
    headers, _, _ = await _user(client, auth_headers, role.json()["id"], "merge@example.com")
    assert await _visible_titles(client, headers) == {"b_web"}

    merged = await client.post(
        "/api/v1/campaigns/merge", headers=auth_headers, json={"source_ids": [b], "target_id": a}
    )
    assert merged.status_code == 200, merged.text
    async with db_manager.session_factory() as session:
        stored = (await session.execute(select(CustomRole.lead_campaign_ids).where(CustomRole.name == "Beta"))).scalar_one()
    assert stored == [a]
    assert await _visible_titles(client, headers) == {"a_web", "a_walk", "a_none", "b_web"}

    cleared = await client.post(f"/api/v1/campaigns/{a}/clear", headers=auth_headers)
    assert cleared.status_code == 200, cleared.text
    assert await _visible_titles(client, headers) == set()


# ---- messages about a lead ------------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mention_on_a_hidden_lead_is_not_sent(client, auth_headers):
    a, _, leads = await _seed(client, auth_headers)
    role = await _role(client, auth_headers, "Alpha", lead_access={"campaign_ids": [a]})
    _, user_id, _ = await _user(client, auth_headers, role.json()["id"], "mention@example.com")

    for lead_key in ("b_web", "a_web"):
        response = await client.post(
            f"/api/v1/leads/{leads[lead_key]}/transitions",
            headers=auth_headers,
            json={"to_stage_code": "prospect", "comment": f"please see {lead_key}", "mentions": [user_id]},
        )
        assert response.status_code == 201, response.text
    async with db_manager.session_factory() as session:
        messages = (
            await session.execute(select(Notification.message).where(Notification.user_id == UUID(user_id)))
        ).scalars().all()
    assert any("a_web" in m for m in messages)
    assert not any("b_web" in m for m in messages)


# ---- pure rules -----------------------------------------------------------------------------------------------------

def test_scope_rules_and_cache_fingerprint():
    scope = LeadScope(campaign_keys=frozenset({"alpha towers"}), source_keys=None, campaign_names=("Alpha Towers",))
    assert scope.allows(campaign="  ALPHA   towers ", source=None)
    assert not scope.allows(campaign=None, source="Website")
    assert scope.refusal(campaign="Beta", source=None).startswith("Not your campaign (Beta)")
    other = LeadScope(campaign_keys=frozenset({"beta"}))
    assert scope.fingerprint() != other.fingerprint()
    assert scope.fingerprint() == LeadScope(campaign_keys=frozenset({"alpha towers"})).fingerprint()
    assert LeadScope(source_keys=frozenset()).allows(campaign="x", source="y") is False

    from app.services.dashboard import DashboardService

    service = DashboardService.__new__(DashboardService)
    service.session = SimpleNamespace(info={"schema_name": "org_x"})
    plain_key = service._cache_key("summary")
    service.session.info["lead_scope"] = scope
    assert service._cache_key("summary") == f"{plain_key}:{scope.fingerprint()}"
    assert service._cache_key("summary").startswith("dashboard:")  # still cleared by the reporting-cache wipe

