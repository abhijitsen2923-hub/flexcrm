"""Turn the project page's layout (tower cards + parking counts) into the units to create.

Additive and idempotent: every existing unit — archived ones too, so a unit someone deliberately removed is
never re-created — counts toward the layout, and a new unit takes the lowest number not already used. Saving
the same layout twice therefore creates nothing the second time, and existing units (with any booking on them)
are never changed or removed. Pure (no DB): the router loads the existing units and writes the plan.

Flat types (the project wizard, t048): a tower is laid out as types A, B, C … with ONE flat of each type per
floor, and a type's position on the floor is fixed by its letter (A-101 = Type A, A-102 = Type B …).
`layout_specs` turns such a layout into unit batches priced from the project; the planner matches typed units by
their type, and falls back to untyped units so a tower set up before flat types is never duplicated.
"""
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from app.database.enums import UnitType
from app.real_estate.schemas import FloorUnits, OtherUnitSpec, TowerLayout, UnitBatchCreate

# Default unit-number prefix per type when the caller doesn't supply one.
TYPE_PREFIX = {
    UnitType.residential: "R",
    UnitType.parking: "P",
    UnitType.shop: "S",
    UnitType.godown: "G",
}

# Parking types, in the order they're numbered/listed (Multi-Level, Covered, Independent, Open, Dependent). A
# spot's type is its number prefix (CP01 …): no column needed, and it reads the same on the board and in a
# booking. New types go at the END so the existing ones keep their order.
PARKING_TYPES = ("MLP", "CP", "IP", "OP", "DP")
# The project-level block that holds parking spots, whatever tower they serve.
PARKING_BLOCK_NAME = "Parking"
# One Save may not create more than this (a typo like 1200 flats per floor shouldn't lock a tenant up).
MAX_NEW_UNITS_PER_SAVE = 5000
# A flat's position on its floor is the last two digits of its number (A-101 → 01), so a floor holds at most
# 99 flat types: A … Z, AA … CU.
MAX_FLAT_POSITION = 99

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
    flat_type: str | None = None  # None for units set up before flat types (and for shops, parking …)


@dataclass(frozen=True)
class NewUnit:
    floor: int
    unit_number: str
    spec: UnitBatchCreate


@dataclass
class TowerPlan:
    new: list[NewUnit] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def flat_type_position(code: str) -> int:
    """A → 1 … Z → 26, AA → 27 … (like spreadsheet columns): the type's fixed position on every floor."""
    position = 0
    for letter in code.strip().upper():
        position = position * 26 + (ord(letter) - ord("A") + 1)
    return position


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

    def claim(self, stem: str, position: int) -> str | None:
        """`{stem}{position:02d}` if no unit has that number yet (it's then taken), else None."""
        number = f"{stem}{position:02d}"
        if number.upper() in self._used:
            return None
        self._used.add(number.upper())
        return number


def is_parking_block(name: str) -> bool:
    return name.strip().casefold() == PARKING_BLOCK_NAME.casefold()


def _prefix(spec: UnitBatchCreate) -> str:
    return (spec.unit_prefix or TYPE_PREFIX.get(spec.unit_type, "U")).strip()


def _number(slots: list[tuple[UnitBatchCreate, int, int]], numberer: _Numberer) -> list[NewUnit]:
    """Number `slots` — (spec, floor, how many) in the order the units are listed.

    A typed unit first claims its own position (Type C on floor 4 → A-403) wherever that number is free; this runs
    before anything else is numbered so no other unit can take a type's number. Everything else — and a typed unit
    whose number is already used — gets the lowest free number, exactly as before flat types."""
    numbers: list[list[str | None]] = [[None] * count for _, _, count in slots]
    for k, (spec, floor, count) in enumerate(slots):
        if spec.flat_type and count:
            numbers[k][0] = numberer.claim(f"{_prefix(spec)}{floor}", flat_type_position(spec.flat_type))
    new: list[NewUnit] = []
    for k, (spec, floor, count) in enumerate(slots):
        for m in range(count):
            number = numbers[k][m] or numberer.take(f"{_prefix(spec)}{floor}")
            new.append(NewUnit(floor=floor, unit_number=number, spec=spec))
    return new


def number_units(spec: UnitBatchCreate, used: set[str]) -> list[NewUnit]:
    """Every unit `spec` describes, numbered after the ones in `used` (the batch endpoint: it always adds)."""
    return _number([(spec, fu.floor, fu.count) for fu in spec.floors], _Numberer(used))


_ANY = object()  # match a unit whatever its flat type


class _Pool:
    """The tower's existing units not yet matched to the layout, per (unit type, floor) and flat type."""

    def __init__(self, existing: list[ExistingUnit]):
        # archived? → (unit type, floor) → {flat type (None = untyped): how many}
        self._left: dict[bool, defaultdict[tuple[str, int], Counter]] = {
            False: defaultdict(Counter),
            True: defaultdict(Counter),
        }
        for u in existing:
            self._left[u.archived][(u.unit_type, u.floor)][u.flat_type or None] += 1

    def take(self, unit_type: str, floor: int, need: int, flat_type=_ANY) -> tuple[int, int]:
        """Match up to `need` units of `flat_type` (None = untyped ones, _ANY = any) — active ones first, then
        archived. Returns (matched, of which archived)."""
        matched = from_archived = 0
        for archived in (False, True):
            counts = self._left[archived][(unit_type, floor)]
            kinds = sorted(counts, key=lambda k: (k is not None, k or "")) if flat_type is _ANY else [flat_type]
            for kind in kinds:
                n = min(counts[kind], need - matched)
                if n <= 0:
                    continue
                counts[kind] -= n
                matched += n
                if archived:
                    from_archived += n
        return matched, from_archived

    def active_left(self) -> Counter:
        """Unmatched live units per unit type."""
        left: Counter[str] = Counter()
        for (unit_type, _floor), counts in self._left[False].items():
            left[unit_type] += sum(counts.values())
        return left


def plan_tower_units(tower_name: str, specs: list[UnitBatchCreate], existing: list[ExistingUnit]) -> TowerPlan:
    """The units to add so the tower holds what `specs` describe.

    Existing units are matched per (unit type, floor) — not by number or size, so renaming a unit or changing a
    tower's flat size never makes Save duplicate a floor — and only the shortfall is created. Untyped specs match
    any unit on the floor, so two of the same type on a floor (2BHK + 3BHK) share one count.

    Typed specs (flat type A, B …) match in two passes per floor: first existing units of their own flat type,
    then, for what is still missing, existing UNTYPED units. A tower set up before flat types (4 untyped flats a
    floor) reopened with 4 types therefore gets nothing new on those floors.
    """
    pool = _Pool(existing)
    numberer = _Numberer({u.unit_number for u in existing})
    plan = TowerPlan()
    target_by_type: Counter[str] = Counter()
    archived_counted: Counter[str] = Counter()
    missing: dict[tuple[int, int], int] = {}
    for i, spec in enumerate(specs):
        for j, fu in enumerate(spec.floors):
            target_by_type[spec.unit_type.value] += fu.count
            missing[(i, j)] = fu.count

    def match(i: int, spec: UnitBatchCreate, flat_type) -> None:
        for j, fu in enumerate(spec.floors):
            matched, from_archived = pool.take(spec.unit_type.value, fu.floor, missing[(i, j)], flat_type)
            missing[(i, j)] -= matched
            archived_counted[spec.unit_type.value] += from_archived

    typed = [(i, spec) for i, spec in enumerate(specs) if spec.flat_type]
    for i, spec in typed:  # pass 1: units of the same flat type
        match(i, spec, spec.flat_type)
    for i, spec in typed:  # pass 2: untyped units (set up before flat types) fill what's still missing
        match(i, spec, None)
    for i, spec in enumerate(specs):  # untyped specs: any unit left on the floor, as always
        if not spec.flat_type:
            match(i, spec, _ANY)

    plan.new = _number(
        [(spec, fu.floor, missing[(i, j)]) for i, spec in enumerate(specs) for j, fu in enumerate(spec.floors)],
        numberer,
    )

    noun = _TYPE_NOUN.get
    for unit_type, count in sorted(archived_counted.items()):
        if count:
            plan.notes.append(
                f"{tower_name}: {count} archived {noun(unit_type, 'units')} count toward the layout and were not re-created."
            )
    for unit_type, extra in sorted(pool.active_left().items()):
        # Only for types this page lays out: a tower's other units (its older parking, say) aren't "extra".
        if extra and unit_type in target_by_type:
            plan.notes.append(
                f"{tower_name}: kept {extra} existing {noun(unit_type, 'units')} beyond this layout "
                f"(Save never removes units — archive them from the project's unit list if they shouldn't exist)."
            )
    return plan


# --- a tower's layout (flat types + shops / godowns) → priced unit batches ---------------------------------------

_AREA_LABEL = {"super_built_up": "super built-up area", "built_up": "built-up area", "carpet": "carpet area"}
_RATE_MISSING = {
    UnitType.residential: "Set the base rate for flats in the Pricing step — flat prices are worked out from it.",
    UnitType.shop: (
        "Set the base rate for shops / commercial in the Pricing step — shop prices are worked out from it."
    ),
    UnitType.godown: (
        "Set the godown rate (or the shops / commercial rate) in the Pricing step — godown prices are worked out "
        "from it."
    ),
}


@dataclass(frozen=True)
class LayoutPricing:
    """What a layout's units are priced from: the project's pricing basis and base rates (₹ per sq ft)."""
    basis: str | None = None              # super_built_up (default) / built_up / carpet
    flat_rate: Decimal | None = None      # rate_a
    shop_rate: Decimal | None = None      # rate_b
    godown_rate: Decimal | None = None    # rate_c — godowns fall back to the shop rate when it isn't set

    def rate_for(self, unit_type: UnitType) -> Decimal | None:
        if unit_type == UnitType.residential:
            return self.flat_rate
        if unit_type == UnitType.godown and self.godown_rate is not None:
            return self.godown_rate
        return self.shop_rate


class LayoutError(ValueError):
    """The layout can't be built as sent; the message says why, in plain words."""


@dataclass
class LayoutSpecs:
    specs: list[UnitBatchCreate] = field(default_factory=list)
    # Specs whose price couldn't be worked out (no rate / no basis area) → why. Save refuses them; the preview
    # still lists their units, unpriced. Such a spec carries base_price 0 only as a placeholder.
    unpriced: dict[int, str] = field(default_factory=dict)  # id(spec) → reason

    def price_problem(self, spec: UnitBatchCreate) -> str | None:
        return self.unpriced.get(id(spec))


def _floors(label: str, floor_from: int, floor_to: int | None, total_floors: int) -> list[int]:
    """The floors a layout row covers: from `floor_from` to `floor_to` (default the top floor), never above the
    tower's top floor."""
    if floor_to is not None and floor_from > floor_to:
        raise LayoutError(
            f"{label}: its floors run from {floor_from} to {floor_to} — the first floor can't be above the last."
        )
    top = total_floors if floor_to is None else min(floor_to, total_floors)
    if floor_from > top:
        raise LayoutError(f"{label} starts on floor {floor_from}, but the tower has only {total_floors} floors.")
    return list(range(floor_from, top + 1))


def _price(
    label: str,
    unit_type: UnitType,
    pricing: LayoutPricing,
    super_built_up: Decimal,
    built_up: Decimal | None,
    carpet: Decimal | None,
) -> tuple[Decimal, str | None]:
    """basis area × base rate, to the paisa — or (0, why not)."""
    rate = pricing.rate_for(unit_type)
    if rate is None:
        return Decimal("0"), _RATE_MISSING[unit_type]
    basis = pricing.basis if pricing.basis in _AREA_LABEL else "super_built_up"
    area = {"super_built_up": super_built_up, "built_up": built_up, "carpet": carpet}[basis]
    if area is None:
        what = _AREA_LABEL[basis]
        return Decimal("0"), f"{label} has no {what} — prices are worked out on the {what} (Pricing step)."
    return (area * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), None


def _other_label(tower_name: str, other: OtherUnitSpec) -> str:
    noun = "Shops" if other.unit_type == UnitType.shop.value else "Godowns"
    if other.floor_from == other.floor_to:
        floors = f"floor {other.floor_from}"
    else:
        floors = f"floors {other.floor_from}–{other.floor_to}"
    return f"{tower_name} · {noun} ({floors})"


def layout_specs(tower_name: str, total_floors: int, layout: TowerLayout, pricing: LayoutPricing) -> LayoutSpecs:
    """The unit batches a tower's layout describes (the server's single source of truth for a wizard tower).

    Each flat type → one flat on every floor of its range (default floor 1 to the top), numbered at the type's
    position; each shops / godowns row → `per_floor` of them on each floor of its range. Prices are worked out
    here — basis area × base rate — never taken from the browser. Raises LayoutError for a layout that can't be
    built (floor range, numbering); a price that can't be worked out is reported in `unpriced` instead, so the
    preview can still show the units."""
    out = LayoutSpecs()

    def add(spec: UnitBatchCreate, problem: str | None) -> None:
        out.specs.append(spec)
        if problem:
            out.unpriced[id(spec)] = problem

    for flat in sorted(layout.flat_types, key=lambda t: flat_type_position(t.code)):
        label = f"{tower_name} · Type {flat.code}"
        if flat_type_position(flat.code) > MAX_FLAT_POSITION:
            raise LayoutError(f"{label}: a floor can number at most {MAX_FLAT_POSITION} flat types (A to CU).")
        floors = _floors(label, 1 if flat.floor_from is None else flat.floor_from, flat.floor_to, total_floors)
        price, problem = _price(
            label, UnitType.residential, pricing, flat.super_built_up_area, flat.built_up_area, flat.carpet_area
        )
        add(
            UnitBatchCreate(
                unit_type=UnitType.residential,
                floors=[FloorUnits(floor=f, count=1) for f in floors],
                area=flat.super_built_up_area,
                carpet_area=flat.carpet_area,
                built_up_area=flat.built_up_area,
                base_price=price,
                unit_prefix=layout.unit_prefix or None,
                flat_type=flat.code,
                configuration=flat.configuration,
                has_plc=flat.has_plc,
            ),
            problem,
        )

    for other in layout.others:
        label = _other_label(tower_name, other)
        unit_type = UnitType(other.unit_type)
        prefix = (other.unit_prefix or "").strip() or f"{layout.unit_prefix}{TYPE_PREFIX[unit_type]}"
        if len(prefix) > 8:
            raise LayoutError(
                f"{label}: their numbers would start “{prefix}”, which is longer than 8 characters — shorten the "
                "tower's unit number prefix."
            )
        floors = _floors(label, other.floor_from, other.floor_to, total_floors)
        price, problem = _price(label, unit_type, pricing, other.area, other.built_up_area, other.carpet_area)
        add(
            UnitBatchCreate(
                unit_type=unit_type,
                floors=[FloorUnits(floor=f, count=other.per_floor) for f in floors],
                area=other.area,
                carpet_area=other.carpet_area,
                built_up_area=other.built_up_area,
                base_price=price,
                unit_prefix=prefix,
            ),
            problem,
        )
    return out


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
