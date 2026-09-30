"""Projects page → inventory: Create and Edit build the towers, flats and parking the page describes.

Saving is additive and idempotent — only missing units are created, numbers never repeat, and existing units
(booked or archived ones included) are never changed, removed or re-created. Parking is counted per type across
the whole project (CP01 …, OP01 …) in one "Parking" block.
"""
from __future__ import annotations

from collections import Counter
from decimal import Decimal

import pytest
import pytest_asyncio

from app.real_estate.inventory_layout import ExistingUnit, number_units, plan_parking, plan_tower_units
from app.real_estate.schemas import UnitBatchCreate

API = "/api/v1/inventory"


@pytest_asyncio.fixture
async def owner_headers(client) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "Riya",
            "last_name": "Builder",
            "email": "owner@realty.example.com",
            "password": "StrongPass123",
            "phone": "+1555000101",
            "role": "owner",
            "business_type": "real_estate",
            "organization_name": "Realty Org",
        },
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _flats(floors: int, per_floor: int, area: int = 1200, price: int = 6_000_000, **extra) -> dict:
    return {
        "unit_type": "residential",
        "floors": [{"floor": f, "count": per_floor} for f in range(1, floors + 1)],
        "area": area,
        "base_price": price,
        **extra,
    }


def _tower(name: str, floors: int, per_floor: int, tower_id: str | None = None, **spec) -> dict:
    card = {"name": name, "total_floors": floors, "unit_specs": [_flats(floors, per_floor, **spec)]}
    if tower_id:
        card["tower_id"] = tower_id
    return card


_PROJECT = {"name": "Skyline", "builder_name": "Acme", "location": "Salt Lake", "city": "Kolkata"}


async def _create_full(client, headers, towers: list[dict], parking: dict | None = None, **details) -> dict:
    body = {**_PROJECT, **details, "towers": towers, "parking": parking or {}}
    response = await client.post(f"{API}/projects/full", headers=headers, json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def _sync(client, headers, project_id: str, towers: list[dict], parking: dict | None = None, expect=200):
    response = await client.post(
        f"{API}/projects/{project_id}/inventory", headers=headers, json={"towers": towers, "parking": parking or {}}
    )
    assert response.status_code == expect, response.text
    return response.json()


async def _project(client, headers, project_id: str) -> dict:
    response = await client.get(f"{API}/projects/{project_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _units(project: dict, tower_name: str | None = None) -> list[dict]:
    return [u for t in project["towers"] if tower_name in (None, t["name"]) for u in t["units"]]


def _numbers(project: dict, tower_name: str | None = None) -> list[str]:
    return sorted(u["unit_number"] for u in _units(project, tower_name))


def _tower_id(project: dict, name: str) -> str:
    return next(t["id"] for t in project["towers"] if t["name"] == name)


def _assert_no_duplicate_numbers(project: dict) -> None:
    for tower in project["towers"]:
        counts = Counter(u["unit_number"] for u in tower["units"])
        assert not [n for n, c in counts.items() if c > 1], f"duplicates in {tower['name']}"


@pytest.mark.asyncio
async def test_full_create_builds_towers_flats_and_parking_by_type(client, owner_headers):
    project = await _create_full(
        client,
        owner_headers,
        [_tower("Tower A", 3, 4), _tower("Tower B", 2, 2, area=1500, price=8_000_000)],
        parking={"CP": 3, "OP": 2},
        parking_cost=300000,
        total_towers=9,  # stale brochure numbers are replaced by what was built
        total_garages=1,
    )

    assert sorted(t["name"] for t in project["towers"]) == ["Parking", "Tower A", "Tower B"]
    assert _numbers(project, "Tower A") == sorted(f"R{f}{n:02d}" for f in (1, 2, 3) for n in (1, 2, 3, 4))
    assert _numbers(project, "Tower B") == ["R101", "R102", "R201", "R202"]
    tower_b = _units(project, "Tower B")
    assert {Decimal(u["area"]) for u in tower_b} == {Decimal(1500)}
    assert {Decimal(u["base_price"]) for u in tower_b} == {Decimal(8_000_000)}

    parking = _units(project, "Parking")
    assert sorted(u["unit_number"] for u in parking) == ["CP01", "CP02", "CP03", "OP01", "OP02"]
    assert {(u["unit_type"], u["floor"], u["status"]) for u in parking} == {("parking", 0, "available")}
    assert {Decimal(u["base_price"]) for u in parking} == {Decimal(300000)}
    assert (project["total_towers"], project["total_floors"], project["total_garages"]) == (2, 3, 5)


@pytest.mark.asyncio
async def test_edit_builds_the_inventory_of_a_project_that_only_has_details(client, owner_headers):
    # The reported bug: details filled (2 towers × 12 floors × 12 flats, 112 garages) but 0 units anywhere.
    created = await client.post(
        f"{API}/projects",
        headers=owner_headers,
        json={**_PROJECT, "total_towers": 2, "total_floors": 12, "flats_per_floor": 12, "total_garages": 112,
              "garage_options": ["CP", "OP"]},
    )
    assert created.status_code == 201, created.text
    project_id = created.json()["id"]
    assert _units(await _project(client, owner_headers, project_id)) == []

    result = await _sync(
        client, owner_headers, project_id,
        [_tower("Tower 1", 12, 12), _tower("Tower 2", 12, 12)],
        parking={"CP": 100, "OP": 12},
    )

    assert result["created"] == {"towers": 2, "units": 288, "parking": 112}
    project = result["project"]
    assert len(_units(project, "Tower 1")) == len(_units(project, "Tower 2")) == 144
    assert len(_units(project, "Parking")) == 112
    assert (project["total_towers"], project["total_floors"], project["total_garages"]) == (2, 12, 112)
    listed = (await client.get(f"{API}/projects", headers=owner_headers)).json()
    assert sum(len(t["units"]) for t in listed[0]["towers"]) == 400


@pytest.mark.asyncio
async def test_saving_the_same_page_twice_creates_nothing_new(client, owner_headers):
    project = await _create_full(client, owner_headers, [_tower("Tower A", 3, 4)], parking={"CP": 3})
    project_id, tower_a = project["id"], _tower_id(project, "Tower A")
    before = _numbers(project)

    # By id, and — a stale tab or a double click — by name without the id.
    for card in (_tower("Tower A", 3, 4, tower_id=tower_a), _tower("Tower A", 3, 4)):
        result = await _sync(client, owner_headers, project_id, [card], parking={"CP": 3})
        assert result["created"] == {"towers": 0, "units": 0, "parking": 0}
        assert _numbers(result["project"]) == before
    assert [t["name"] for t in (await _project(client, owner_headers, project_id))["towers"]].count("Tower A") == 1


@pytest.mark.asyncio
async def test_raising_adds_only_the_missing_units_and_lowering_keeps_existing(client, owner_headers):
    project = await _create_full(client, owner_headers, [_tower("Tower A", 3, 4)])
    project_id, tower_a = project["id"], _tower_id(project, "Tower A")

    raised = await _sync(client, owner_headers, project_id, [_tower("Tower A", 4, 5, tower_id=tower_a)])
    assert raised["created"]["units"] == 3 * 1 + 5  # one more on floors 1-3, a full new floor 4
    numbers = _numbers(raised["project"], "Tower A")
    assert numbers == sorted(f"R{f}{n:02d}" for f in (1, 2, 3, 4) for n in (1, 2, 3, 4, 5))
    _assert_no_duplicate_numbers(raised["project"])

    lowered = await _sync(client, owner_headers, project_id, [_tower("Tower A", 2, 2, tower_id=tower_a)])
    assert lowered["created"] == {"towers": 0, "units": 0, "parking": 0}
    assert _numbers(lowered["project"], "Tower A") == numbers
    tower = next(t for t in lowered["project"]["towers"] if t["name"] == "Tower A")
    assert tower["total_floors"] == 4  # units exist up to floor 4
    assert any("kept 4 floors" in note for note in lowered["notes"])
    assert any("kept 16 existing flats" in note for note in lowered["notes"])


@pytest.mark.asyncio
async def test_existing_units_and_bookings_are_never_changed(client, owner_headers):
    project = await _create_full(client, owner_headers, [_tower("Tower A", 1, 2)])
    project_id, tower_a = project["id"], _tower_id(project, "Tower A")
    booked = _units(project, "Tower A")[0]
    response = await client.patch(
        f"{API}/units/{booked['id']}/status", headers=owner_headers, json={"status": "booked"}
    )
    assert response.status_code == 200, response.text

    # New size + price on the page apply to NEW units only.
    result = await _sync(
        client, owner_headers, project_id, [_tower("Tower A", 1, 3, tower_id=tower_a, area=999, price=1)]
    )
    units = {u["unit_number"]: u for u in _units(result["project"], "Tower A")}
    assert units[booked["unit_number"]]["status"] == "booked"
    assert Decimal(units[booked["unit_number"]]["area"]) == Decimal(1200)
    assert Decimal(units["R102"]["base_price"]) == Decimal(6_000_000)
    assert (Decimal(units["R103"]["area"]), Decimal(units["R103"]["base_price"])) == (Decimal(999), Decimal(1))


@pytest.mark.asyncio
async def test_an_archived_unit_is_not_brought_back(client, owner_headers):
    project = await _create_full(client, owner_headers, [_tower("Tower A", 1, 3)])
    project_id, tower_a = project["id"], _tower_id(project, "Tower A")
    removed = next(u for u in _units(project) if u["unit_number"] == "R102")
    assert (await client.delete(f"{API}/units/{removed['id']}", headers=owner_headers)).status_code == 204

    result = await _sync(client, owner_headers, project_id, [_tower("Tower A", 1, 3, tower_id=tower_a)])
    assert result["created"]["units"] == 0
    assert _numbers(result["project"]) == ["R101", "R103"]
    assert any("archived flats count toward the layout" in note for note in result["notes"])

    # Asking for more adds after every number ever used — R102 is not handed out again.
    more = await _sync(client, owner_headers, project_id, [_tower("Tower A", 1, 4, tower_id=tower_a)])
    assert _numbers(more["project"]) == ["R101", "R103", "R104"]


@pytest.mark.asyncio
async def test_parking_is_numbered_per_type_across_the_project(client, owner_headers):
    project = await _create_full(client, owner_headers, [_tower("Tower A", 1, 2)], parking={"CP": 3})
    project_id, tower_a = project["id"], _tower_id(project, "Tower A")
    # A flat someone renamed "CP04" — the next covered spot must not repeat it.
    flat = _units(project, "Tower A")[0]
    renamed = await client.patch(f"{API}/units/{flat['id']}", headers=owner_headers, json={"unit_number": "CP04"})
    assert renamed.status_code == 200, renamed.text

    result = await _sync(
        client, owner_headers, project_id, [_tower("Tower A", 1, 2, tower_id=tower_a)], parking={"CP": 5, "IP": 2}
    )

    assert result["created"]["parking"] == 4
    parking = sorted(u["unit_number"] for u in _units(result["project"], "Parking"))
    assert parking == ["CP01", "CP02", "CP03", "CP05", "CP06", "IP01", "IP02"]
    assert [t["name"] for t in result["project"]["towers"]].count("Parking") == 1
    assert result["project"]["total_garages"] == 7

    lowered = await _sync(client, owner_headers, project_id, [], parking={"CP": 1})
    assert lowered["created"]["parking"] == 0
    assert any("Parking CP: kept all 5" in note for note in lowered["notes"])


@pytest.mark.asyncio
async def test_units_batch_continues_numbering_instead_of_duplicating(client, owner_headers):
    project = await _create_full(client, owner_headers, [_tower("Tower A", 2, 2)])
    tower_a = _tower_id(project, "Tower A")

    for _ in range(2):
        response = await client.post(f"{API}/towers/{tower_a}/units/batch", headers=owner_headers, json=_flats(2, 2))
        assert response.status_code == 201, response.text
    numbers = sorted(u["unit_number"] for u in response.json())
    assert numbers == sorted(f"R{f}{n:02d}" for f in (1, 2) for n in (1, 2, 3, 4, 5, 6))


@pytest.mark.asyncio
async def test_archived_projects_and_towers_are_refused(client, owner_headers):
    project = await _create_full(client, owner_headers, [_tower("Tower A", 1, 1), _tower("Tower B", 1, 1)])
    project_id, tower_a, tower_b = project["id"], _tower_id(project, "Tower A"), _tower_id(project, "Tower B")

    assert (await client.delete(f"{API}/towers/{tower_b}", headers=owner_headers)).status_code == 204
    await _sync(client, owner_headers, project_id, [_tower("Tower B", 1, 1, tower_id=tower_b)], expect=404)
    response = await client.post(f"{API}/towers/{tower_b}/units/batch", headers=owner_headers, json=_flats(1, 1))
    assert response.status_code == 404

    assert (await client.delete(f"{API}/projects/{project_id}", headers=owner_headers)).status_code == 204
    await _sync(client, owner_headers, project_id, [_tower("Tower A", 1, 1, tower_id=tower_a)], expect=404)
    response = await client.post(
        f"{API}/projects/{project_id}/towers", headers=owner_headers, json={"name": "Tower C", "total_floors": 1}
    )
    assert response.status_code == 404
    response = await client.post(f"{API}/towers/{tower_a}/units/batch", headers=owner_headers, json=_flats(1, 1))
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_bad_tower_names_and_oversized_saves_are_rejected_before_anything_is_written(client, owner_headers):
    project = await _create_full(client, owner_headers, [_tower("Tower A", 1, 1)])
    project_id = project["id"]

    for towers, message in (
        ([_tower("Tower X", 1, 1), _tower(" tower x ", 1, 1)], "Two towers are named"),
        ([_tower("parking", 1, 1)], "kept for the project's parking"),
        ([_tower("   ", 1, 1)], "Every tower needs a name"),
        ([_tower("Huge", 200, 200)], "more than 5,000 in one save"),
    ):
        body = await _sync(client, owner_headers, project_id, towers, expect=422)
        assert message in body["error"]["detail"]
    body = await _sync(client, owner_headers, project_id, [], parking={"CP": 5000, "OP": 1}, expect=422)
    assert "more than 5,000" in body["error"]["detail"]

    after = await _project(client, owner_headers, project_id)
    assert [t["name"] for t in after["towers"]] == ["Tower A"]
    assert _numbers(after) == ["R101"]


@pytest.mark.asyncio
async def test_roles_without_lead_manage_cannot_build_inventory(client, owner_headers):
    project = await _create_full(client, owner_headers, [_tower("Tower A", 1, 1)])
    create = await client.post(
        "/api/v1/users",
        headers=owner_headers,
        json={"first_name": "Ana", "last_name": "Counts", "email": "accounts@realty.example.com",
              "password": "StrongPass123", "phone": "+1555000102", "role": "accounts", "status": "active"},
    )
    assert create.status_code == 201, create.text
    login = await client.post(
        "/api/v1/auth/login", json={"email": "accounts@realty.example.com", "password": "StrongPass123"}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    await _sync(client, headers, project["id"], [_tower("Tower B", 1, 1)], expect=403)
    assert _numbers(await _project(client, owner_headers, project["id"])) == ["R101"]


# --- the planner on its own ------------------------------------------------------------------------------------


def _spec(floors: dict[int, int], unit_type: str = "residential", prefix: str | None = None) -> UnitBatchCreate:
    return UnitBatchCreate(
        unit_type=unit_type,
        floors=[{"floor": f, "count": c} for f, c in floors.items()],
        area=Decimal(100),
        base_price=Decimal(1),
        unit_prefix=prefix,
    )


def test_two_specs_of_one_type_share_a_floor_count_and_a_number_sequence():
    two_bhk, three_bhk = _spec({1: 2}), _spec({1: 1})
    fresh = plan_tower_units("T", [two_bhk, three_bhk], [])
    assert [(n.unit_number, n.spec is three_bhk) for n in fresh.new] == [
        ("R101", False), ("R102", False), ("R103", True)
    ]
    # Two flats exist on floor 1 — they fill the first spec; only the 3BHK is missing.
    existing = [ExistingUnit("R101", "residential", 1, False), ExistingUnit("R102", "residential", 1, False)]
    again = plan_tower_units("T", [two_bhk, three_bhk], existing)
    assert [(n.unit_number, n.spec is three_bhk) for n in again.new] == [("R103", True)]


def test_existing_units_match_by_type_and_floor_not_by_number():
    renamed = [ExistingUnit("A-1", "residential", 1, False), ExistingUnit("r102", "residential", 1, False)]
    assert plan_tower_units("T", [_spec({1: 2})], renamed).new == []
    # A shop on floor 1 doesn't count as a flat; numbers compare case-insensitively.
    plan = plan_tower_units("T", [_spec({1: 3})], renamed + [ExistingUnit("R101", "shop", 1, False)])
    assert [n.unit_number for n in plan.new] == ["R103"]


def test_number_units_always_adds_after_used_numbers():
    assert [n.unit_number for n in number_units(_spec({0: 2}, "shop"), {"S001", "s002"})] == ["S003", "S004"]


def test_parking_plan_counts_only_typed_spots_and_keeps_extra():
    existing = [
        ExistingUnit("CP01", "parking", 0, False),
        ExistingUnit("cp02", "parking", 0, True),   # archived: counted, number not reused
        ExistingUnit("P101", "parking", 1, False),  # older untyped spot: not a CP
        ExistingUnit("MLP01", "parking", 0, False),
    ]
    plan = plan_parking({"CP": 3, "MLP": 0}, existing, {"CP01", "CP02", "P101", "MLP01"})
    assert plan.new == [("CP", "CP03")]
    assert any("Parking MLP: kept all 1" in note for note in plan.notes)
    assert any("1 archived spots count toward the 3" in note for note in plan.notes)
