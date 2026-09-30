"""Turn the project page's layout (tower cards + parking counts) into the units to create.

Additive and idempotent: every existing unit — archived ones too, so a unit someone deliberately removed is
never re-created — counts toward the layout, and a new unit takes the lowest number not already used. Saving
the same layout twice therefore creates nothing the second time, and existing units (with any booking on them)
are never changed or removed. Pure (no DB): the router loads the existing units and writes the plan.
"""
import re
from collections import Counter
from dataclasses import dataclass, field

from app.database.enums import UnitType
from app.real_estate.schemas import UnitBatchCreate

# Default unit-number prefix per type when the caller doesn't supply one.
TYPE_PREFIX = {
    UnitType.residential: "R",
    UnitType.parking: "P",
    UnitType.shop: "S",
    UnitType.godown: "G",
}

# Parking types, in the order they're numbered/listed (Multi-Level, Covered, Independent, Open). A spot's type
# is its number prefix (CP01 …): no column needed, and it reads the same on the board and in a booking.
PARKING_TYPES = ("MLP", "CP", "IP", "OP")
# The project-level block that holds parking spots, whatever tower they serve.
PARKING_BLOCK_NAME = "Parking"
# One Save may not create more than this (a typo like 1200 flats per floor shouldn't lock a tenant up).
MAX_NEW_UNITS_PER_SAVE = 5000

_TYPE_NOUN = {
    UnitType.residential.value: "flats",
    UnitType.shop.value: "shops",
    UnitType.godown.value: "godowns",
    UnitType.parking.value: "parking spots",
}


@dataclass(frozen=True)
class ExistingUnit:
    unit_number: str
    unit_type: str
    floor: int
    archived: bool


@dataclass(frozen=True)
class NewUnit:
    floor: int
    unit_number: str
    spec: UnitBatchCreate


@dataclass
class TowerPlan:
    new: list[NewUnit] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class _Numberer:
    """Hands out the lowest free `{prefix}{floor}{nn}` per (prefix, floor), never one in `used` (compared
    case-insensitively — "r101" and "R101" would read as the same unit)."""

    def __init__(self, used: set[str]):
        self._used = {n.upper() for n in used}
        self._cursor: dict[str, int] = {}

    def take(self, stem: str) -> str:
        n = self._cursor.get(stem, 0) + 1
        while f"{stem}{n:02d}".upper() in self._used:
            n += 1
        self._cursor[stem] = n
        number = f"{stem}{n:02d}"
        self._used.add(number.upper())
        return number


def is_parking_block(name: str) -> bool:
    return name.strip().casefold() == PARKING_BLOCK_NAME.casefold()


def _prefix(spec: UnitBatchCreate) -> str:
    return (spec.unit_prefix or TYPE_PREFIX.get(spec.unit_type, "U")).strip()


def number_units(spec: UnitBatchCreate, used: set[str]) -> list[NewUnit]:
    """Every unit `spec` describes, numbered after the ones in `used` (the batch endpoint: it always adds)."""
    numberer = _Numberer(used)
    return [
        NewUnit(floor=fu.floor, unit_number=numberer.take(f"{_prefix(spec)}{fu.floor}"), spec=spec)
        for fu in spec.floors
        for _ in range(fu.count)
    ]


def plan_tower_units(tower_name: str, specs: list[UnitBatchCreate], existing: list[ExistingUnit]) -> TowerPlan:
    """The units to add so the tower holds what `specs` describe.

    Existing units are matched by (unit type, floor) — not by number or size, so renaming a unit or changing a
    tower's flat size never makes Save duplicate a floor. They fill the specs in order; only the shortfall is
    created. Two specs of the same type on a floor (2BHK + 3BHK) share one count.
    """
    active = Counter((u.unit_type, u.floor) for u in existing if not u.archived)
    archived = Counter((u.unit_type, u.floor) for u in existing if u.archived)
    numberer = _Numberer({u.unit_number for u in existing})
    plan = TowerPlan()
    target_by_type: Counter[str] = Counter()
    archived_counted: Counter[str] = Counter()

    for spec in specs:
        unit_type = spec.unit_type.value
        prefix = _prefix(spec)
        for fu in spec.floors:
            key = (unit_type, fu.floor)
            target_by_type[unit_type] += fu.count
            from_active = min(active[key], fu.count)
            active[key] -= from_active
            from_archived = min(archived[key], fu.count - from_active)
            archived[key] -= from_archived
            archived_counted[unit_type] += from_archived
            for _ in range(fu.count - from_active - from_archived):
                plan.new.append(NewUnit(floor=fu.floor, unit_number=numberer.take(f"{prefix}{fu.floor}"), spec=spec))

    noun = _TYPE_NOUN.get
    for unit_type, count in sorted(archived_counted.items()):
        if count:
            plan.notes.append(
                f"{tower_name}: {count} archived {noun(unit_type, 'units')} count toward the layout and were not re-created."
            )
    extra_by_type: Counter[str] = Counter()
    for (unit_type, _floor), left in active.items():
        extra_by_type[unit_type] += left
    for unit_type, extra in sorted(extra_by_type.items()):
        # Only for types this page lays out: a tower's other units (its older parking, say) aren't "extra".
        if extra and unit_type in target_by_type:
            plan.notes.append(
                f"{tower_name}: kept {extra} existing {noun(unit_type, 'units')} beyond this layout "
                f"(Save never removes units — archive them from the project's unit list if they shouldn't exist)."
            )
    return plan


def parking_type_of(unit_number: str) -> str | None:
    """CP07 → "CP"; anything not numbered by type (e.g. an older "P101") → None."""
    for parking_type in PARKING_TYPES:
        if re.fullmatch(rf"{parking_type}\d+", unit_number.strip(), flags=re.IGNORECASE):
            return parking_type
    return None


@dataclass
class ParkingPlan:
    new: list[tuple[str, str]] = field(default_factory=list)  # (parking type, unit number)
    notes: list[str] = field(default_factory=list)


def plan_parking(counts: dict[str, int], existing_parking: list[ExistingUnit], project_numbers: set[str]) -> ParkingPlan:
    """The parking spots to add so each type reaches its count, numbered per type across the whole project
    (CP01, CP02 … OP01 …). `existing_parking` = the project's parking units (archived included);
    `project_numbers` = every unit number in the project, so a new spot never repeats one."""
    active = Counter(parking_type_of(u.unit_number) for u in existing_parking if not u.archived)
    archived = Counter(parking_type_of(u.unit_number) for u in existing_parking if u.archived)
    numberer = _Numberer(project_numbers)
    plan = ParkingPlan()
    for parking_type in PARKING_TYPES:
        target = counts.get(parking_type, 0)
        have_active, have_archived = active[parking_type], archived[parking_type]
        missing = max(0, target - have_active - have_archived)
        plan.new.extend((parking_type, numberer.take(parking_type)) for _ in range(missing))
        if target > have_active and have_archived and target - have_active > missing:
            plan.notes.append(
                f"Parking {parking_type}: {target - have_active - missing} archived spots count toward the "
                f"{target} and were not re-created."
            )
        if parking_type in counts and have_active > target:
            plan.notes.append(
                f"Parking {parking_type}: kept all {have_active} existing spots (more than {target}) — Save never "
                f"removes units."
            )
    return plan
