"""Add Project wizard → inventory: towers laid out as flat types (A, B, C … — one flat of each per floor, Type A
at position 01), priced on the server from the project's pricing, plus a preview that runs the same planner as Save.

Most of these guard production data: Save stays additive and idempotent, a tower set up before flat types is
never duplicated when it is reopened with types, and an old browser tab can't add untyped copies of a typed
tower's flats.
"""
from __future__ import annotations

import csv
import io
from dataclasses import replace
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
import pytest_asyncio

from pydantic import ValidationError

from app.database.enums import UnitType
from app.real_estate.documents import render_booking_document
from app.real_estate.inventory_layout import (
    ExistingUnit,
    LayoutError,
    LayoutPricing,
    TowerPlan,
    flat_type_position,
    layout_specs,
    number_units,
    plan_tower_units,
)
from app.real_estate.models import Booking, Project, Tower, Unit
from app.real_estate.schemas import TowerLayout, UnitBatchCreate

API = "/api/v1/inventory"
_PROJECT = {"name": "Skyline", "builder_name": "Acme", "location": "Salt Lake", "city": "Kolkata"}


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


def _flat(code: str, sbu: int, *, config: str | None = None, carpet: int | None = None, built_up: int | None = None,
          plc: bool = False, floor_from: int | None = None, floor_to: int | None = None) -> dict:
    return {
        "code": code,
        "configuration": config,
        "carpet_area": carpet,
        "built_up_area": built_up,
        "super_built_up_area": sbu,
        "has_plc": plc,
        "floor_from": floor_from,
        "floor_to": floor_to,
    }


FOUR_TYPES = [
    _flat("A", 1250, config="2 BHK", carpet=850, built_up=1050),
    _flat("B", 1200, config="2 BHK", carpet=820, built_up=1010),
    _flat("C", 1600, config="3 BHK", carpet=1100, built_up=1350),
    _flat("D", 1650, config="3 BHK", carpet=1120, built_up=1380, plc=True),
]


def _typed(name: str, floors: int, flat_types: list[dict], prefix: str = "A-", others: list[dict] | None = None,
           tower_id: str | None = None) -> dict:
    card = {
        "name": name,
        "total_floors": floors,
        "layout": {"unit_prefix": prefix, "flat_types": flat_types, "others": others or []},
    }
    if tower_id:
        card["tower_id"] = tower_id
    return card


def _legacy(name: str, floors: int, per_floor: int, tower_id: str | None = None) -> dict:
    """A tower card as the page before flat types sends it (still what an old browser tab sends)."""
    spec = {
        "unit_type": "residential",
        "floors": [{"floor": f, "count": per_floor} for f in range(1, floors + 1)],
        "area": 1200,
        "base_price": 6_000_000,
    }
    card = {"name": name, "total_floors": floors, "unit_specs": [spec]}
    if tower_id:
        card["tower_id"] = tower_id
    return card


async def _create_full(client, headers, towers: list[dict], parking: dict | None = None, expect=201, **details):
    body = {**_PROJECT, **details, "towers": towers, "parking": parking or {}}
    response = await client.post(f"{API}/projects/full", headers=headers, json=body)
    assert response.status_code == expect, response.text
    return response.json()


async def _sync(client, headers, project_id: str, towers: list[dict], parking: dict | None = None, expect=200):
    response = await client.post(
        f"{API}/projects/{project_id}/inventory", headers=headers, json={"towers": towers, "parking": parking or {}}
    )
    assert response.status_code == expect, response.text
    return response.json()


async def _preview(client, headers, project_id: str, towers: list[dict], parking: dict | None = None, expect=200,
                   **pricing):
    response = await client.post(
        f"{API}/projects/{project_id}/inventory/preview",
        headers=headers,
        json={"towers": towers, "parking": parking or {}, **pricing},
    )
    assert response.status_code == expect, response.text
    return response.json()


async def _project(client, headers, project_id: str) -> dict:
    response = await client.get(f"{API}/projects/{project_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _tower(project: dict, name: str) -> dict:
    return next(t for t in project["towers"] if t["name"] == name)


def _units(project: dict, tower_name: str) -> dict[str, dict]:
    return {u["unit_number"]: u for u in _tower(project, tower_name)["units"]}


def _planned(preview: dict, tower_name: str) -> dict[str, dict]:
    return {u["unit_number"]: u for t in preview["towers"] if t["name"] == tower_name for u in t["new_units"]}


# --- Create ---------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_builds_one_flat_of_each_type_per_floor_priced_from_the_project(client, owner_headers):
    penthouse = _flat("E", 3000, config="Penthouse", carpet=2200, built_up=2600, floor_from=10, floor_to=10)
    shops = {"unit_type": "shop", "per_floor": 2, "floor_from": 0, "floor_to": 0, "area": 400, "built_up_area": 350}
    five_types = FOUR_TYPES + [_flat("E", 900, config="1 BHK", carpet=600, built_up=780)]
    project = await _create_full(
        client,
        owner_headers,
        [
            # Types listed out of order on purpose: the letter, not the list order, fixes the position.
            _typed("Tower A", 10, [penthouse, *reversed(FOUR_TYPES)], others=[shops]),
            _typed("Tower B", 2, five_types, prefix="B-"),
        ],
        parking={"CP": 2, "DP": 2},
        pricing_basis="built_up",
        rate_a=6000,
        rate_b=9000,
        parking_cost=300000,
        parking_prices={"CP": 400000, "DP": 350000.5},
        garage_options=["CP"],
    )

    tower_a = _units(project, "Tower A")
    flats = {n: u for n, u in tower_a.items() if u["unit_type"] == "residential"}
    expected = {f"A-{floor}{position:02d}": "ABCD"[position - 1] for floor in range(1, 11) for position in range(1, 5)}
    expected["A-1005"] = "E"  # the penthouse type: top floor only
    assert {n: u["flat_type"] for n, u in flats.items()} == expected
    built_up = {"A": 1050, "B": 1010, "C": 1350, "D": 1380, "E": 2600}
    for unit in flats.values():
        assert Decimal(unit["base_price"]) == Decimal(built_up[unit["flat_type"]] * 6000)  # built-up × flat rate
    a101, a104 = flats["A-101"], flats["A-104"]
    assert (a101["configuration"], Decimal(a101["area"]), Decimal(a101["carpet_area"]), a101["has_plc"]) == (
        "2 BHK", Decimal(1250), Decimal(850), False
    )
    assert (a104["configuration"], a104["has_plc"]) == ("3 BHK", True)
    assert flats["A-1005"]["configuration"] == "Penthouse" and flats["A-1005"]["floor"] == 10

    # Ground-floor shops: their own numbers, priced at the shops rate, no flat type.
    shop_units = {n: u for n, u in tower_a.items() if u["unit_type"] == "shop"}
    assert sorted(shop_units) == ["A-S001", "A-S002"]
    assert {(u["floor"], u["flat_type"], Decimal(u["base_price"])) for u in shop_units.values()} == {
        (0, None, Decimal(350 * 9000))
    }

    tower_b = _units(project, "Tower B")
    assert sorted(tower_b) == sorted(f"B-{f}0{p}" for f in (1, 2) for p in range(1, 6))
    assert (tower_b["B-105"]["flat_type"], tower_b["B-105"]["configuration"]) == ("E", "1 BHK")

    # The layout is stored as sent (numbers stay numbers) so Edit reopens exactly what was set up.
    layout = _tower(project, "Tower A")["layout"]
    assert layout["unit_prefix"] == "A-"
    assert layout["flat_types"] == [penthouse, *reversed(FOUR_TYPES)]
    assert layout["others"][0]["built_up_area"] == 350

    # Dependent parking + a price per parking type (parking_cost is only the fallback).
    parking = _units(project, "Parking")
    assert {n: Decimal(u["base_price"]) for n, u in parking.items()} == {
        "CP01": Decimal(400000), "CP02": Decimal(400000), "DP01": Decimal("350000.5"), "DP02": Decimal("350000.5"),
    }
    assert {k: Decimal(v) for k, v in project["parking_prices"].items()} == {"CP": 400000, "DP": Decimal("350000.5")}
    assert project["garage_options"] == ["CP"]  # DP lives in parking counts / prices only
    assert (project["total_towers"], project["total_floors"], project["total_garages"]) == (2, 10, 4)
    assert (project["pricing_basis"], Decimal(project["rate_a"])) == ("built_up", Decimal(6000))

    # The inventory export carries the type and configuration (appended, so older column positions hold).
    export = await client.get("/api/v1/exports/inventory.csv", headers=owner_headers)
    assert export.status_code == 200, export.text
    rows = list(csv.reader(io.StringIO(export.text)))
    assert rows[0][-2:] == ["flat_type", "configuration"]
    by_number = {r[2]: r for r in rows[1:]}
    assert by_number["A-101"][-2:] == ["A", "2 BHK"]
    assert by_number["A-S001"][-2:] == ["", ""]


@pytest.mark.asyncio
async def test_create_preview_is_exactly_what_create_builds_and_writes_nothing(client, owner_headers):
    shops = {"unit_type": "shop", "per_floor": 3, "floor_from": 0, "floor_to": 1, "area": 300}
    godowns = {"unit_type": "godown", "per_floor": 1, "floor_from": 0, "floor_to": 0, "area": 500}
    body = {
        **_PROJECT,
        "rate_a": 5500.5,
        "rate_b": 8000,
        "parking_cost": 300000,
        "parking_prices": {"DP": 250000},
        "towers": [
            _typed("Tower A", 6, FOUR_TYPES, others=[shops, godowns]),
            _typed("Tower B", 3, FOUR_TYPES[:2], prefix="B-"),
        ],
        "parking": {"CP": 2, "DP": 1},
    }
    response = await client.post(f"{API}/projects/full/preview", headers=owner_headers, json=body)
    assert response.status_code == 200, response.text
    preview = response.json()
    assert (await client.get(f"{API}/projects", headers=owner_headers)).json() == []  # nothing written

    project = await _create_full(client, owner_headers, body["towers"], body["parking"],
                                 **{k: v for k, v in body.items() if k not in ("towers", "parking")})
    for name in ("Tower A", "Tower B"):
        planned, built = _planned(preview, name), _units(project, name)
        assert planned.keys() == built.keys()
        for number, unit in built.items():
            p = planned[number]
            assert (p["floor"], p["unit_type"], p["flat_type"], p["configuration"], p["has_plc"]) == (
                unit["floor"], unit["unit_type"], unit["flat_type"], unit["configuration"], unit["has_plc"]
            )
            assert Decimal(p["base_price"]) == Decimal(unit["base_price"])
            assert Decimal(p["area"]) == Decimal(unit["area"])
    # Godowns fall back to the shops rate when no godown rate is set; flats are priced to the paisa.
    assert Decimal(_units(project, "Tower A")["A-G001"]["base_price"]) == Decimal(500 * 8000)
    assert Decimal(_units(project, "Tower A")["A-101"]["base_price"]) == Decimal("6875625.00")  # 1250 × 5500.5
    assert preview["new_units"] == sum(len(t["units"]) for t in project["towers"] if t["name"] != "Parking")
    assert all(t["existing_units"] == 0 and t["tower_id"] is None for t in preview["towers"])
    parking = {p["parking_type"]: p for p in preview["parking"]}
    assert set(parking) == {"CP", "DP"}
    assert (parking["CP"]["new_numbers"], Decimal(parking["CP"]["price"])) == (["CP01", "CP02"], Decimal(300000))
    assert (parking["DP"]["new_numbers"], Decimal(parking["DP"]["price"])) == (["DP01"], Decimal(250000))
    assert preview["new_parking"] == 3
    assert sorted(_units(project, "Parking")) == ["CP01", "CP02", "DP01"]

    # No flat rate yet: the preview still shows every unit (flats unpriced) — Save refuses with a plain message.
    no_rate = {**body, "name": "Skyline 2", "rate_a": None}
    response = await client.post(f"{API}/projects/full/preview", headers=owner_headers, json=no_rate)
    assert response.status_code == 200, response.text
    units = [u for t in response.json()["towers"] for u in t["new_units"]]
    assert {u["base_price"] for u in units if u["unit_type"] == "residential"} == {None}
    assert all(u["base_price"] is not None for u in units if u["unit_type"] != "residential")
    response = await client.post(f"{API}/projects/full", headers=owner_headers, json=no_rate)
    assert response.status_code == 422
    assert "Set the base rate for flats in the Pricing step" in response.json()["error"]["detail"]
    assert len((await client.get(f"{API}/projects", headers=owner_headers)).json()) == 1


# --- Edit -----------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reopening_a_typed_tower_adds_only_what_is_new(client, owner_headers):
    project = await _create_full(client, owner_headers, [_typed("Tower A", 3, FOUR_TYPES[:3])], rate_a=6000)
    project_id, tower_id = project["id"], _tower(project, "Tower A")["id"]
    before = _units(project, "Tower A")
    assert sorted(before) == sorted(f"A-{f}0{p}" for f in (1, 2, 3) for p in (1, 2, 3))

    # The same layout again — by id, and by name (a double click / a card without its id) — adds nothing.
    for card in (_typed("Tower A", 3, FOUR_TYPES[:3], tower_id=tower_id), _typed("Tower A", 3, FOUR_TYPES[:3])):
        result = await _sync(client, owner_headers, project_id, [card])
        assert result["created"] == {"towers": 0, "units": 0, "parking": 0}
        assert _units(result["project"], "Tower A").keys() == before.keys()

    # An archived flat still counts — it is not brought back.
    removed = before["A-202"]
    assert (await client.delete(f"{API}/units/{removed['id']}", headers=owner_headers)).status_code == 204

    # New rate (the wizard saves the project first), a 4th floor and a 4th type: preview, then Save — same units.
    patched = await client.patch(f"{API}/projects/{project_id}", headers=owner_headers, json={"rate_a": 7000})
    assert patched.status_code == 200, patched.text
    grown = _typed("Tower A", 4, FOUR_TYPES, tower_id=tower_id)
    preview = await _preview(client, owner_headers, project_id, [grown])
    result = await _sync(client, owner_headers, project_id, [grown])

    added = {n: u for n, u in _units(result["project"], "Tower A").items() if n not in before}
    assert sorted(added) == ["A-104", "A-204", "A-304", "A-401", "A-402", "A-403", "A-404"]
    assert {n: u["flat_type"] for n, u in added.items()} == {
        "A-104": "D", "A-204": "D", "A-304": "D", "A-401": "A", "A-402": "B", "A-403": "C", "A-404": "D"
    }
    assert result["created"]["units"] == preview["new_units"] == 7
    planned = _planned(preview, "Tower A")
    assert planned.keys() == added.keys()
    assert all(Decimal(planned[n]["base_price"]) == Decimal(added[n]["base_price"]) for n in added)
    assert Decimal(added["A-401"]["base_price"]) == Decimal(1250 * 7000)  # new units: the new rate
    assert Decimal(_units(result["project"], "Tower A")["A-101"]["base_price"]) == Decimal(1250 * 6000)  # kept
    assert "A-202" not in _units(result["project"], "Tower A")
    assert any("1 archived flats count toward the layout" in note for note in result["notes"])
    assert preview["notes"] == result["notes"]
    assert preview["towers"][0]["tower_id"] == tower_id and preview["towers"][0]["existing_units"] == 8
    tower = _tower(result["project"], "Tower A")
    assert (tower["total_floors"], [t["code"] for t in tower["layout"]["flat_types"]]) == (4, ["A", "B", "C", "D"])

    # Dropping a type keeps its flats (Save never removes) and says so.
    shrunk = await _sync(client, owner_headers, project_id, [_typed("Tower A", 4, FOUR_TYPES[:3], tower_id=tower_id)])
    assert shrunk["created"]["units"] == 0
    assert any("kept 4 existing flats beyond this layout" in note for note in shrunk["notes"])

    # With the flat rate cleared, re-saving a tower that is fully built still works (nothing to price) — only a
    # Save that would create unpriced flats is refused.
    patched = await client.patch(f"{API}/projects/{project_id}", headers=owner_headers, json={"rate_a": None})
    assert patched.status_code == 200, patched.text
    assert (await _sync(client, owner_headers, project_id, [grown]))["created"]["units"] == 0
    body = await _sync(client, owner_headers, project_id, [_typed("Tower A", 5, FOUR_TYPES, tower_id=tower_id)],
                       expect=422)
    assert "Set the base rate for flats" in body["error"]["detail"]
    assert len(_units(await _project(client, owner_headers, project_id), "Tower A")) == 15


@pytest.mark.asyncio
async def test_a_tower_set_up_before_flat_types_is_never_duplicated_and_old_tabs_are_stopped(client, owner_headers):
    project = await _create_full(client, owner_headers, [_legacy("Tower A", 3, 4)], rate_a=6000)
    project_id, tower_id = project["id"], _tower(project, "Tower A")["id"]
    legacy_numbers = sorted(_units(project, "Tower A"))
    assert legacy_numbers == sorted(f"R{f}0{p}" for f in (1, 2, 3) for p in (1, 2, 3, 4))

    # "Set up flat types" on it: 4 types on 3 floors — every slot is filled by its existing untyped flats.
    typed = _typed("Tower A", 3, FOUR_TYPES, prefix="R", tower_id=tower_id)
    preview = await _preview(client, owner_headers, project_id, [typed])
    assert (preview["new_units"], preview["towers"][0]["existing_units"]) == (0, 12)
    result = await _sync(client, owner_headers, project_id, [typed])
    assert result["created"]["units"] == 0
    units = _units(result["project"], "Tower A")
    assert sorted(units) == legacy_numbers
    assert {u["flat_type"] for u in units.values()} == {None}  # existing flats are never re-typed or re-priced
    assert {Decimal(u["base_price"]) for u in units.values()} == {Decimal(6_000_000)}
    assert _tower(result["project"], "Tower A")["layout"]["unit_prefix"] == "R"

    # A new floor gets one flat of each type, at its own position.
    four_floors = _typed("Tower A", 4, FOUR_TYPES, prefix="R", tower_id=tower_id)
    result = await _sync(client, owner_headers, project_id, [four_floors])
    added = {n: u["flat_type"] for n, u in _units(result["project"], "Tower A").items() if n not in legacy_numbers}
    assert added == {"R401": "A", "R402": "B", "R403": "C", "R404": "D"}

    # An old tab still sends the tower without flat types — by id or by name — and is told to reload; nothing added.
    for card in (_legacy("Tower A", 5, 4, tower_id=tower_id), _legacy("Tower A", 5, 4)):
        body = await _sync(client, owner_headers, project_id, [card], expect=409)
        assert body["error"]["detail"] == "This tower was set up with flat types — reload the page to edit it."
    assert len(_units(await _project(client, owner_headers, project_id), "Tower A")) == 16
    # The preview has no such guard (it writes nothing).
    await _preview(client, owner_headers, project_id, [_legacy("Tower A", 5, 4, tower_id=tower_id)])

    # Towers without flat types keep working exactly as before, next to a typed one.
    result = await _sync(
        client, owner_headers, project_id,
        [_typed("Tower A", 4, FOUR_TYPES, prefix="R", tower_id=tower_id), _legacy("Tower B", 2, 2)],
    )
    assert result["created"] == {"towers": 1, "units": 4, "parking": 0}
    assert sorted(_units(result["project"], "Tower B")) == ["R101", "R102", "R201", "R202"]
    assert _tower(result["project"], "Tower B")["layout"] is None


def _with_no_flats_on(card: dict, *floors: int) -> dict:
    card["layout"]["skip_floors"] = list(floors)
    return card


@pytest.mark.asyncio
async def test_floors_with_no_flats_get_none_and_saving_again_adds_nothing(client, owner_headers):
    shops = {"unit_type": "shop", "per_floor": 2, "floor_from": 0, "floor_to": 0, "area": 400}
    card = _with_no_flats_on(_typed("Tower A", 10, FOUR_TYPES, others=[shops]), 5)
    project = await _create_full(client, owner_headers, [card], rate_a=6000, rate_b=9000)
    project_id, tower_id = project["id"], _tower(project, "Tower A")["id"]
    units = _units(project, "Tower A")
    flats = {n: u for n, u in units.items() if u["unit_type"] == "residential"}
    assert len(flats) == 36
    assert {u["floor"] for u in flats.values()} == set(range(1, 11)) - {5}  # a refuge floor: no flats at all
    assert sorted(n for n, u in units.items() if u["unit_type"] == "shop") == ["A-S001", "A-S002"]
    assert _tower(project, "Tower A")["layout"]["skip_floors"] == [5]

    # The same layout again — the preview and Save — adds nothing.
    again = _with_no_flats_on(_typed("Tower A", 10, FOUR_TYPES, others=[shops], tower_id=tower_id), 5)
    assert (await _preview(client, owner_headers, project_id, [again]))["new_units"] == 0
    result = await _sync(client, owner_headers, project_id, [again])
    assert result["created"]["units"] == 0 and result["notes"] == []

    # Taking floor 5 off the list adds just that floor's flats, at their own numbers.
    opened = _typed("Tower A", 10, FOUR_TYPES, others=[shops], tower_id=tower_id)
    result = await _sync(client, owner_headers, project_id, [opened])
    added = {n: u["flat_type"] for n, u in _units(result["project"], "Tower A").items() if n not in units}
    assert added == {"A-501": "A", "A-502": "B", "A-503": "C", "A-504": "D"}
    assert _tower(result["project"], "Tower A")["layout"]["skip_floors"] == []


@pytest.mark.asyncio
async def test_a_tower_with_a_refuge_floor_set_up_before_flat_types_converts_without_new_flats(client, owner_headers):
    # 4 flats a floor on floors 1–10, none on floor 5 (refuge), made before flat types.
    spec = {
        "unit_type": "residential",
        "floors": [{"floor": f, "count": 4} for f in range(1, 11) if f != 5],
        "area": 1200,
        "base_price": 6_000_000,
    }
    project = await _create_full(client, owner_headers, [{"name": "Tower B", "total_floors": 10, "unit_specs": [spec]}],
                                 rate_a=6000)
    project_id, tower_id = project["id"], _tower(project, "Tower B")["id"]
    before = _units(project, "Tower B")
    assert len(before) == 36

    # "Set up flat types": 4 types over floors 1–10 with floor 5 listed as having no flats → nothing new.
    converted = _with_no_flats_on(_typed("Tower B", 10, FOUR_TYPES, prefix="R", tower_id=tower_id), 5)
    preview = await _preview(client, owner_headers, project_id, [converted])
    assert (preview["new_units"], preview["notes"]) == (0, [])
    result = await _sync(client, owner_headers, project_id, [converted])
    assert result["created"]["units"] == 0
    assert _units(result["project"], "Tower B").keys() == before.keys()

    # Without it, the preview shows the 4 flats Save would add on the refuge floor.
    plain = _typed("Tower B", 10, FOUR_TYPES, prefix="R", tower_id=tower_id)
    assert sorted(_planned(await _preview(client, owner_headers, project_id, [plain]), "Tower B")) == [
        "R501", "R502", "R503", "R504"
    ]

    # Floors with no flats are checked like the rest of the layout.
    for floors, message in (([5, 5], "listed twice"), ([201], "less than or equal to 200")):
        bad = _with_no_flats_on(_typed("Tower B", 10, FOUR_TYPES, prefix="R", tower_id=tower_id), *floors)
        body = await _preview(client, owner_headers, project_id, [bad], expect=422)
        assert message in str(body["error"]["detail"]), body
    only_floor_5 = _with_no_flats_on(
        _typed("Tower B", 10, [*FOUR_TYPES, _flat("E", 900, floor_from=5, floor_to=5)], prefix="R", tower_id=tower_id),
        5,
    )
    body = await _sync(client, owner_headers, project_id, [only_floor_5], expect=422)
    assert "Tower B · Type E: every floor it is on is listed as a floor with no flats" in body["error"]["detail"]
    assert len(_units(await _project(client, owner_headers, project_id), "Tower B")) == 36


@pytest.mark.asyncio
async def test_an_older_tower_with_shops_and_two_refuge_floors_converts_then_grows_by_exactly_one_floor(
    client, owner_headers
):
    # Made before flat types: 3 shops on the ground floor, 4 flats a floor on 1–12 except refuge floors 5 and 9.
    flats = {
        "unit_type": "residential",
        "floors": [{"floor": f, "count": 4} for f in range(1, 13) if f not in (5, 9)],
        "area": 1200,
        "base_price": 6_000_000,
    }
    shops = {"unit_type": "shop", "floors": [{"floor": 0, "count": 3}], "area": 400, "base_price": 3_000_000}
    project = await _create_full(
        client, owner_headers, [{"name": "Tower C", "total_floors": 12, "unit_specs": [flats, shops]}],
        rate_a=6000, rate_b=9000,
    )
    project_id, tower_id = project["id"], _tower(project, "Tower C")["id"]
    before = _units(project, "Tower C")
    assert len(before) == 43 and sorted(n for n in before if n.startswith("S")) == ["S001", "S002", "S003"]

    # What the wizard's "Set up flat types" builds from it: 4 types on every floor, floors 5 and 9 with no flats,
    # one shops row for the ground floor — Save adds nothing, and the preview says so.
    def converted(floors: int) -> dict:
        ground_shops = {"unit_type": "shop", "per_floor": 3, "floor_from": 0, "floor_to": 0, "area": 400,
                        "unit_prefix": "S"}
        card = _typed("Tower C", floors, FOUR_TYPES, prefix="R", others=[ground_shops], tower_id=tower_id)
        return _with_no_flats_on(card, 5, 9)

    preview = await _preview(client, owner_headers, project_id, [converted(12)])
    assert (preview["new_units"], preview["notes"]) == (0, [])
    result = await _sync(client, owner_headers, project_id, [converted(12)])
    assert (result["created"]["units"], result["notes"]) == (0, [])
    assert _units(result["project"], "Tower C").keys() == before.keys()

    # One floor added: exactly that floor's 4 flats, at their own numbers — the preview listed the same ones.
    preview = await _preview(client, owner_headers, project_id, [converted(13)])
    result = await _sync(client, owner_headers, project_id, [converted(13)])
    added = {n: u["flat_type"] for n, u in _units(result["project"], "Tower C").items() if n not in before}
    assert added == {"R1301": "A", "R1302": "B", "R1303": "C", "R1304": "D"}
    assert sorted(_planned(preview, "Tower C")) == sorted(added)
    assert (await _sync(client, owner_headers, project_id, [converted(13)]))["created"]["units"] == 0

    # An old tab (no flat types) is still stopped for it.
    body = await _sync(client, owner_headers, project_id, [_legacy("Tower C", 14, 4, tower_id=tower_id)], expect=409)
    assert body["error"]["detail"] == "This tower was set up with flat types — reload the page to edit it."
    assert len(_units(await _project(client, owner_headers, project_id), "Tower C")) == 47


@pytest.mark.asyncio
async def test_a_flat_retyped_from_the_unit_list_never_makes_save_add_a_flat(client, owner_headers):
    project = await _create_full(client, owner_headers, [_typed("Tower A", 3, FOUR_TYPES, prefix="R")], rate_a=6000)
    project_id, tower_id = project["id"], _tower(project, "Tower A")["id"]
    before = _units(project, "Tower A")
    assert len(before) == 12
    card = _typed("Tower A", 3, FOUR_TYPES, prefix="R", tower_id=tower_id)

    # R101 is Type A. Re-typed to B (now two B's, no A on floor 1), then to E (a type the layout doesn't list):
    # floor 1 still has its 4 flats, so the preview and Save add nothing — and say why.
    for new_type in ("B", "E"):
        response = await client.patch(
            f"{API}/units/{before['R101']['id']}", headers=owner_headers, json={"flat_type": new_type}
        )
        assert response.status_code == 200, response.text
        preview = await _preview(client, owner_headers, project_id, [card])
        result = await _sync(client, owner_headers, project_id, [card])
        assert preview["new_units"] == result["created"]["units"] == 0, new_type
        assert _units(result["project"], "Tower A").keys() == before.keys()
        assert preview["notes"] == result["notes"]
        assert len(result["notes"]) == 1 and "1 existing flat on floor 1 has a flat type" in result["notes"][0]

    # Adding Type E to the layout: R101 is now its Type E flat on floor 1, so floor 1 only lacks its Type A
    # (R101's number is taken → the lowest free one), and floors 2–3 get their Type E flats.
    grown = _typed("Tower A", 3, [*FOUR_TYPES, _flat("E", 900)], prefix="R", tower_id=tower_id)
    result = await _sync(client, owner_headers, project_id, [grown])
    added = {n: u["flat_type"] for n, u in _units(result["project"], "Tower A").items() if n not in before}
    assert added == {"R105": "A", "R205": "E", "R305": "E"}


@pytest.mark.asyncio
async def test_layouts_that_cannot_be_built_or_priced_are_refused_before_anything_is_written(client, owner_headers):
    cases = [
        ({"rate_b": 9000}, [_typed("Tower A", 2, FOUR_TYPES)], "Set the base rate for flats in the Pricing step"),
        (
            {"rate_a": 6000, "pricing_basis": "carpet"},
            [_typed("Tower A", 2, [FOUR_TYPES[0], _flat("B", 1200)])],
            "Tower A · Type B has no carpet area — prices are worked out on the carpet area",
        ),
        (
            {"rate_a": 6000},
            [_typed("Tower A", 10, [_flat("A", 1000, floor_from=5, floor_to=3)])],
            "Tower A · Type A: its floors run from 5 to 3",
        ),
        (
            {"rate_a": 6000},
            [_typed("Tower A", 10, [_flat("A", 1000, floor_from=12)])],
            "Tower A · Type A starts on floor 12, but the tower has only 10 floors",
        ),
        (
            {"rate_a": 6000},
            [_typed("Tower A", 1, [_flat("A", 1000), _flat("A", 1100)])],
            "share the same letter",
        ),
        (
            {"rate_a": 6000},
            [_typed("Tower A", 1, [{**_flat("A", 1000), "super_built_up_area": None}])],
            "super_built_up_area",
        ),
        (
            {"rate_a": 6000},
            [_typed("Tower A", 1, FOUR_TYPES, others=[{"unit_type": "shop", "per_floor": 1, "floor_from": 0,
                                                       "floor_to": 0, "area": 300}])],
            "Set the base rate for shops / commercial in the Pricing step",
        ),
    ]
    for details, towers, message in cases:
        body = await _create_full(client, owner_headers, towers, expect=422, **details)
        assert message in str(body["error"]["detail"]), body
    assert (await client.get(f"{API}/projects", headers=owner_headers)).json() == []

    # Edit prices new units from the project's saved pricing: no flat rate saved → refused, nothing added.
    project = await _create_full(client, owner_headers, [_legacy("Tower A", 1, 1)])
    body = await _sync(client, owner_headers, project["id"], [_typed("Tower B", 2, FOUR_TYPES)], expect=422)
    assert "Set the base rate for flats" in body["error"]["detail"]
    # …while the preview, given the page's unsaved rate, prices them.
    preview = await _preview(client, owner_headers, project["id"], [_typed("Tower B", 2, FOUR_TYPES)], rate_a=5000)
    assert {Decimal(u["base_price"]) for u in _planned(preview, "Tower B").values() if u["flat_type"] == "A"} == {
        Decimal(1250 * 5000)
    }
    assert [t["name"] for t in (await _project(client, owner_headers, project["id"]))["towers"]] == ["Tower A"]
    # Archived / unknown projects: 404 for the preview too.
    assert (await client.delete(f"{API}/projects/{project['id']}", headers=owner_headers)).status_code == 204
    await _preview(client, owner_headers, project["id"], [_typed("Tower B", 2, FOUR_TYPES)], expect=404, rate_a=1)
    await _preview(client, owner_headers, str(uuid4()), [], expect=404)


# --- Project fields -------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_payment_plan_replaces_the_demand_schedule_and_new_fields_are_saved(client, owner_headers):
    legacy_schedule = [{"label": "On booking", "percent": 100, "due_date": "2026-11-01"}]
    created = await client.post(
        f"{API}/projects", headers=owner_headers, json={**_PROJECT, "demand_schedule": legacy_schedule}
    )
    assert created.status_code == 201, created.text
    project_id = created.json()["id"]
    assert created.json()["demand_schedule"][0]["label"] == "On booking"

    plan = [
        {"key": "m1", "label": "Booking amount", "percent": 10, "due_on": "on_booking"},
        {"key": "m2", "label": "Agreement", "percent": 20.5, "due_on": "days_after_booking", "days": 30},
        {"key": "m3", "label": "Foundation complete", "percent": 69.5, "due_on": "on_stage"},
    ]
    response = await client.patch(
        f"{API}/projects/{project_id}",
        headers=owner_headers,
        json={
            "payment_plan": plan, "project_type": "mixed", "pricing_basis": "carpet", "floor_rise_rate": 50,
            "floor_rise_basis": "per_sqft", "floor_rise_from": 3, "plc_rate": 150, "amenities_rate": 75.25,
            "parking_prices": {"MLP": 300000, "DP": 275000.75},
        },
    )
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved["demand_schedule"] is None  # one source of truth from now on
    assert [(m["key"], m["label"], Decimal(m["percent"]), m["due_on"], m["days"]) for m in saved["payment_plan"]] == [
        ("m1", "Booking amount", Decimal(10), "on_booking", None),
        ("m2", "Agreement", Decimal("20.5"), "days_after_booking", 30),
        ("m3", "Foundation complete", Decimal("69.5"), "on_stage", None),
    ]
    assert (saved["project_type"], saved["pricing_basis"], saved["floor_rise_basis"], saved["floor_rise_from"]) == (
        "mixed", "carpet", "per_sqft", 3
    )
    assert Decimal(saved["amenities_rate"]) == Decimal("75.25")
    assert {k: Decimal(v) for k, v in saved["parking_prices"].items()} == {"MLP": 300000, "DP": Decimal("275000.75")}
    assert (await _project(client, owner_headers, project_id))["payment_plan"] == saved["payment_plan"]

    # Stored as plain JSON (numbers, ISO dates) — what bookings and older builds read back.
    from app.database.session import db_manager

    async with db_manager.session_factory() as session:
        row = await session.get(Project, UUID(project_id))
        assert row.payment_plan[1] == {
            "key": "m2", "label": "Agreement", "percent": 20.5, "due_on": "days_after_booking", "days": 30,
            "due_date": None,
        }
        assert row.parking_prices == {"MLP": 300000, "DP": 275000.75}

    # An explicit null clears the plan and leaves the demand schedule as sent.
    response = await client.patch(
        f"{API}/projects/{project_id}", headers=owner_headers,
        json={"payment_plan": None, "demand_schedule": legacy_schedule},
    )
    assert response.status_code == 200, response.text
    assert response.json()["payment_plan"] is None
    assert response.json()["demand_schedule"][0]["due_date"] == "2026-11-01"

    # Create with both: the plan wins. A plan must add up to 100 %; DP never goes into garage_options.
    on_date = [{"key": "x1", "label": "Possession", "percent": 100, "due_on": "on_date", "due_date": "2027-03-31"}]
    project = await _create_full(client, owner_headers, [], name="Two", demand_schedule=legacy_schedule,
                                 payment_plan=on_date)
    assert project["demand_schedule"] is None and project["payment_plan"][0]["due_date"] == "2027-03-31"
    body = await _create_full(client, owner_headers, [], expect=422, name="Three",
                              payment_plan=[{**on_date[0], "percent": 90}])
    assert "must add up to 100%" in str(body["error"]["detail"])
    await _create_full(client, owner_headers, [], expect=422, name="Four", garage_options=["CP", "DP"])


@pytest.mark.asyncio
async def test_unit_fix_up_edits_flat_type_configuration_and_plc(client, owner_headers):
    project = await _create_full(client, owner_headers, [_legacy("Tower A", 1, 1)])
    unit = next(iter(_units(project, "Tower A").values()))
    url = f"{API}/units/{unit['id']}"

    fix = {"flat_type": "B", "configuration": " 3 BHK ", "has_plc": True}
    response = await client.patch(url, headers=owner_headers, json=fix)
    assert response.status_code == 200, response.text
    saved = response.json()
    assert (saved["flat_type"], saved["configuration"], saved["has_plc"]) == ("B", "3 BHK", True)
    # An explicit null on the yes/no leaves it as it is; blank configuration clears it.
    response = await client.patch(url, headers=owner_headers, json={"has_plc": None, "configuration": "  "})
    assert response.status_code == 200, response.text
    assert (response.json()["has_plc"], response.json()["configuration"]) == (True, None)
    assert (await client.patch(url, headers=owner_headers, json={"flat_type": "b1"})).status_code == 422


@pytest.mark.asyncio
async def test_project_images_must_be_a_jpg_or_png_of_at_most_5_mb(client, owner_headers, monkeypatch):
    from app.core import storage

    uploaded: list[tuple[str, int, str | None]] = []

    def fake_put(key: str, data: bytes, content_type: str | None = None) -> str:
        uploaded.append((key, len(data), content_type))
        return key

    monkeypatch.setattr(storage, "put_object", fake_put)
    created = await client.post(f"{API}/projects", headers=owner_headers, json=_PROJECT)
    project_id = created.json()["id"]
    url = f"{API}/projects/{project_id}/media"
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64

    async def upload(name: str, data: bytes, content_type: str, media_type: str = "image"):
        return await client.post(
            url, headers=owner_headers, files={"file": (name, data, content_type)},
            data={"media_type": media_type, "label": "Cover"},
        )

    response = await upload("notes.txt", b"hello", "text/plain")
    assert (response.status_code, response.json()["error"]["detail"]) == (415, "Upload a JPG or PNG image.")
    assert (await upload("fake.png", b"GIF89a....", "image/png")).status_code == 415  # renamed, not a PNG
    response = await upload("huge.jpg", b"\xff\xd8\xff" + b"\x00" * (5 * 1024 * 1024), "image/jpeg")
    assert (response.status_code, response.json()["error"]["detail"]) == (413, "The image is larger than 5 MB.")
    assert uploaded == []

    response = await upload("cover.png", png, "image/png")
    assert response.status_code == 201, response.text
    assert (response.json()["type"], response.json()["label"]) == ("image", "Cover")
    assert (await upload("photo.jpg", b"\xff\xd8\xff\xe0" + b"\x00" * 32, "image/jpeg")).status_code == 201
    # Other media types are unchanged (a brochure PDF is fine).
    assert (await upload("brochure.pdf", b"%PDF-1.4", "application/pdf", media_type="brochure")).status_code == 201
    assert [size for _, size, _ in uploaded] == [len(png), 36, 8]

    assert (await client.delete(f"{API}/projects/{project_id}", headers=owner_headers)).status_code == 204
    assert (await upload("cover.png", png, "image/png")).status_code == 404


# --- the planner and layout on their own ---------------------------------------------------------------------


def _layout(flat_types: list[dict], prefix: str = "A-", others: list[dict] | None = None) -> TowerLayout:
    return TowerLayout.model_validate({"unit_prefix": prefix, "flat_types": flat_types, "others": others or []})


def test_a_type_letter_fixes_its_position_on_the_floor():
    codes = ("A", "B", "D", "Z", "AA", "AZ", "BA", "CU")
    assert [flat_type_position(c) for c in codes] == [1, 2, 4, 26, 27, 52, 53, 99]


def test_layout_prices_each_unit_on_the_project_basis():
    layout = _layout(
        [_flat("A", 1250, carpet=850, built_up=1050)],
        others=[
            {"unit_type": "shop", "per_floor": 1, "floor_from": 0, "floor_to": 0, "area": 400, "carpet_area": 300,
             "built_up_area": 350},
            {"unit_type": "godown", "per_floor": 1, "floor_from": 0, "floor_to": 0, "area": 500, "carpet_area": 450,
             "built_up_area": 480},
        ],
    )
    rates = {"flat_rate": Decimal("5000.55"), "shop_rate": Decimal(9000)}
    for basis, areas in (
        (None, (1250, 400, 500)),
        ("super_built_up", (1250, 400, 500)),
        ("built_up", (1050, 350, 480)),
        ("carpet", (850, 300, 450)),
    ):
        built = layout_specs("Tower A", 2, layout, LayoutPricing(basis=basis, **rates))
        assert built.unpriced == {}
        flat, shop, godown = built.specs
        assert flat.base_price == (Decimal(areas[0]) * Decimal("5000.55")).quantize(Decimal("0.01"))
        assert (shop.base_price, godown.base_price) == (Decimal(areas[1] * 9000), Decimal(areas[2] * 9000))
    godown_rate = layout_specs("T", 1, layout, LayoutPricing(godown_rate=Decimal(2000), **rates)).specs[2]
    assert godown_rate.base_price == Decimal(500 * 2000)
    # A godown rate of 0 is a cleared field, not free godowns: they use the shop rate, like a blank one.
    for unset in (None, Decimal(0), Decimal("0.00")):
        pricing = LayoutPricing(godown_rate=unset, **rates)
        assert pricing.rate_for(UnitType.godown) == Decimal(9000)
        assert layout_specs("T", 1, layout, pricing).specs[2].base_price == Decimal(500 * 9000)
    # No shop rate either: the godowns can't be priced (Save refuses; the preview shows them unpriced).
    no_rate = layout_specs("T", 1, layout, LayoutPricing(flat_rate=Decimal(1), godown_rate=Decimal(0)))
    assert "Set the godown rate (or the shops / commercial rate)" in no_rate.price_problem(no_rate.specs[2])
    # Flat batches: one per type, one flat a floor, prefix + type + configuration carried; shops "A-S".
    flat, shop, _ = built.specs
    assert [(f.floor, f.count) for f in flat.floors] == [(1, 1), (2, 1)]
    assert (flat.unit_prefix, flat.flat_type) == ("A-", "A")
    assert (shop.unit_prefix, [(f.floor, f.count) for f in shop.floors]) == ("A-S", [(0, 1)])


def test_a_unit_that_cannot_be_priced_is_reported_not_raised():
    layout = _layout([_flat("A", 1250, carpet=850), _flat("B", 1200)])
    built = layout_specs("Tower A", 1, layout, LayoutPricing(basis="carpet", flat_rate=Decimal(6000)))
    a, b = built.specs
    assert (built.price_problem(a), a.base_price) == (None, Decimal(850 * 6000))
    assert built.price_problem(b) == (
        "Tower A · Type B has no carpet area — prices are worked out on the carpet area (Pricing step)."
    )
    no_rate = layout_specs("Tower A", 1, layout, LayoutPricing())
    assert all("Set the base rate for flats" in no_rate.price_problem(s) for s in no_rate.specs)


def test_layouts_that_cannot_be_built_raise_a_plain_message():
    pricing = LayoutPricing(flat_rate=Decimal(1), shop_rate=Decimal(1))
    for layout, message in (
        (_layout([_flat("A", 100, floor_from=4, floor_to=2)]), "Tower A · Type A: its floors run from 4 to 2"),
        (_layout([_flat("A", 100, floor_from=11)]), "Tower A · Type A starts on floor 11, but the tower has only 10"),
        (_layout([_flat("CV", 100)]), "a floor can number at most 99 flat types"),
        (
            _layout([], prefix="TOWERAB-", others=[{"unit_type": "shop", "per_floor": 1, "floor_from": 0,
                                                    "floor_to": 0, "area": 100}]),
            "longer than 8 characters",
        ),
    ):
        with pytest.raises(LayoutError, match=message):
            layout_specs("Tower A", 10, layout, pricing)
    # A type's range past the top floor is cut at the top floor.
    built = layout_specs("Tower A", 3, _layout([_flat("A", 100, floor_from=2, floor_to=9)]), pricing)
    assert [f.floor for f in built.specs[0].floors] == [2, 3]


def _typed_spec(code: str, floors: list[int], prefix: str = "R") -> UnitBatchCreate:
    return UnitBatchCreate(
        floors=[{"floor": f, "count": 1} for f in floors], area=Decimal(100), base_price=Decimal(1),
        unit_prefix=prefix, flat_type=code,
    )


def test_typed_specs_match_their_own_type_then_untyped_units():
    abcd = [_typed_spec(c, [1, 2]) for c in "ABCD"]
    # Floor 1: two flats from before flat types. Floor 2: empty. Untyped flats fill types A, B on floor 1.
    existing = [ExistingUnit("R101", "residential", 1, False), ExistingUnit("R102", "residential", 1, False)]
    plan = plan_tower_units("T", abcd, existing)
    assert [(n.unit_number, n.spec.flat_type) for n in plan.new] == [
        ("R201", "A"), ("R202", "B"), ("R103", "C"), ("R203", "C"), ("R104", "D"), ("R204", "D"),
    ]

    # An archived Type A flat counts for Type A (not re-created); an untyped flat fills Type B.
    existing = [ExistingUnit("R101", "residential", 1, True, "A"), ExistingUnit("X-9", "residential", 1, False)]
    plan = plan_tower_units("T", [_typed_spec("A", [1]), _typed_spec("B", [1])], existing)
    assert plan.new == []
    assert plan.notes == ["T: 1 archived flats count toward the layout and were not re-created."]

    # Flats of a type no longer in the layout are kept and reported…
    existing = [ExistingUnit("R101", "residential", 1, False, "A"), ExistingUnit("R102", "residential", 1, False, "B")]
    plan = plan_tower_units("T", [_typed_spec("A", [1])], existing)
    assert plan.new == []
    assert any("kept 1 existing flats beyond this layout" in note for note in plan.notes)
    # …and when the layout still wants that many flats on the floor (B swapped for C), the B flat fills C's place:
    # the floor already has its 2 flats, so Save adds none.
    plan = plan_tower_units("T", [_typed_spec("A", [1]), _typed_spec("C", [1])], existing)
    assert plan.new == []
    assert not any("beyond this layout" in note for note in plan.notes)
    # A floor short of flats still gets the missing one.
    plan = plan_tower_units("T", [_typed_spec(c, [1]) for c in "ABC"], existing)
    assert [(n.unit_number, n.spec.flat_type) for n in plan.new] == [("R103", "C")]


def test_a_typed_unit_takes_its_position_number_unless_that_number_is_used():
    # "r101" is used (case-insensitive) by a parking spot: Type A takes the lowest free number instead, and never
    # Type B's own number.
    existing = [ExistingUnit("r101", "parking", 0, False)]
    plan = plan_tower_units("T", [_typed_spec("A", [1]), _typed_spec("B", [1])], existing)
    assert [(n.unit_number, n.spec.flat_type) for n in plan.new] == [("R103", "A"), ("R102", "B")]
    # The batch endpoint numbers typed units the same way.
    assert [n.unit_number for n in number_units(_typed_spec("C", [1, 2], prefix="A-"), {"A-101"})] == ["A-103", "A-203"]


def test_untyped_specs_still_match_any_unit_on_the_floor():
    existing = [
        ExistingUnit("A-101", "residential", 1, False, "A"),
        ExistingUnit("A-102", "residential", 1, False, "B"),
    ]
    spec = UnitBatchCreate(floors=[{"floor": 1, "count": 3}], area=Decimal(100), base_price=Decimal(1))
    assert [n.unit_number for n in plan_tower_units("T", [spec], existing).new] == ["R101"]


def _abcd(floors: int = 3) -> list[ExistingUnit]:
    """A typed tower as Save built it: R101 = Type A … R104 = Type D on every floor."""
    return [
        ExistingUnit(f"R{f}{p:02d}", "residential", f, False, "ABCD"[p - 1])
        for f in range(1, floors + 1)
        for p in range(1, 5)
    ]


def _retyped(units: list[ExistingUnit], changes: dict[str, str]) -> list[ExistingUnit]:
    return [replace(u, flat_type=changes[u.unit_number]) if u.unit_number in changes else u for u in units]


def test_a_flat_retyped_by_hand_never_makes_save_add_a_flat_to_a_full_floor():
    specs = [_typed_spec(c, [1, 2, 3]) for c in "ABCD"]
    assert plan_tower_units("T", specs, _abcd()) == TowerPlan()

    # One flat re-typed: to a type its floor already has (two B's) or to one the layout doesn't list (E).
    for new_type in ("B", "E"):
        plan = plan_tower_units("T", specs, _retyped(_abcd(), {"R101": new_type}))
        assert plan.new == [], new_type
        assert plan.notes == [
            "T: 1 existing flat on floor 1 has a flat type its floor already has (or one the layout doesn't list) — "
            "it counts for the missing type, so nothing was added there. Check its type in the project's unit list."
        ]

    # Several floors, archived flats too (an archived flat is never re-created, whatever its type).
    existing = _retyped(_abcd(), {"R101": "D", "R102": "D", "R301": "Z"})
    existing = [replace(u, archived=True) if u.unit_number == "R301" else u for u in existing]
    plan = plan_tower_units("T", specs, existing)
    assert plan.new == []
    assert plan.notes == [
        "T: 1 archived flats count toward the layout and were not re-created.",
        "T: 3 existing flats on floors 1, 3 have a flat type their floor already has (or one the layout doesn't "
        "list) — they count for the missing types, so nothing was added there. Check their types in the "
        "project's unit list.",
    ]

    # A floor that really is short still gets its flat, at its own number…
    plan = plan_tower_units("T", specs, [u for u in _abcd() if u.unit_number != "R204"])
    assert [(n.unit_number, n.spec.flat_type) for n in plan.new] == [("R204", "D")]
    # …and a type the floor has no flat for (beyond what's there) is still added: 5 types, 4 flats a floor.
    plan = plan_tower_units("T", [*specs, _typed_spec("E", [1, 2, 3])], _retyped(_abcd(), {"R101": "B"}))
    assert [(n.unit_number, n.spec.flat_type) for n in plan.new] == [("R105", "E"), ("R205", "E"), ("R305", "E")]


def _skip_layout(flat_types: list[dict], skip_floors: list[int], others: list[dict] | None = None) -> TowerLayout:
    return TowerLayout.model_validate(
        {"unit_prefix": "A-", "flat_types": flat_types, "others": others or [], "skip_floors": skip_floors}
    )


def test_floors_with_no_flats_are_left_out_of_every_flat_type_but_not_shops():
    pricing = LayoutPricing(flat_rate=Decimal(1), shop_rate=Decimal(1))
    shops = {"unit_type": "shop", "per_floor": 2, "floor_from": 0, "floor_to": 5, "area": 300}
    layout = _skip_layout(
        [_flat("A", 1000), _flat("B", 1000, floor_from=4, floor_to=6), _flat("C", 2000, floor_from=10, floor_to=10)],
        [12, 5],
        others=[shops],
    )
    assert layout.skip_floors == [5, 12]  # stored in order
    a, b, c, shop = layout_specs("Tower A", 10, layout, pricing).specs
    assert [f.floor for f in a.floors] == [1, 2, 3, 4, 6, 7, 8, 9, 10]
    assert [f.floor for f in b.floors] == [4, 6]
    assert [f.floor for f in c.floors] == [10]
    assert [(f.floor, f.count) for f in shop.floors] == [(f, 2) for f in range(0, 6)]  # their own floors

    # Re-saving plans nothing; a converted older tower (untyped flats, none on floor 5) plans nothing either.
    built = layout_specs("Tower A", 10, _skip_layout([_flat(c, 1000) for c in "ABCD"], [5]), pricing).specs
    typed_units = [
        ExistingUnit(f"A-{f}{p:02d}", "residential", f, False, "ABCD"[p - 1]) for f in range(1, 11) if f != 5
        for p in range(1, 5)
    ]
    untyped_units = [
        ExistingUnit(f"R{f}{p:02d}", "residential", f, False) for f in range(1, 11) if f != 5 for p in range(1, 5)
    ]
    assert plan_tower_units("Tower A", built, typed_units) == TowerPlan()
    assert plan_tower_units("Tower A", built, untyped_units) == TowerPlan()

    # Saved before floors with no flats existed: none (every floor of a type's range has its flats).
    assert TowerLayout.model_validate({"unit_prefix": "A-", "flat_types": [_flat("A", 1000)]}).skip_floors == []
    # A type whose every floor has no flats can't be built; bad lists are refused.
    with pytest.raises(LayoutError, match="Type A: every floor it is on is listed as a floor with no flats"):
        layout_specs("Tower A", 10, _skip_layout([_flat("A", 1000, floor_from=5, floor_to=5)], [5]), pricing)
    for bad in ([5, 5], [-1], [201], list(range(201))):
        with pytest.raises(ValidationError):
            _skip_layout([_flat("A", 1000)], bad)


def test_booking_documents_show_the_flat_type_only_when_the_unit_has_one():
    project = Project(name="Skyline", builder_name="Acme", location="Salt Lake", city="Kolkata")
    tower = Tower(name="Tower A", total_floors=10)
    booking = Booking(id=uuid4(), pricing_snapshot={"total": 7_500_000})
    typed = Unit(unit_number="A-101", floor=1, area=Decimal(1250), area_unit="sqft", base_price=Decimal(1),
                 flat_type="A", configuration="2 BHK")
    html, _ = render_booking_document("booking_form", booking, typed, project, tower, None)
    assert "Flat Type" in html and "Type A" in html and "2 BHK" in html
    legacy = Unit(unit_number="R101", floor=1, area=Decimal(1200), area_unit="sqft", base_price=Decimal(1))
    html, _ = render_booking_document("allotment_letter", booking, legacy, project, tower, None)
    assert "Flat Type" not in html and "Configuration" not in html
