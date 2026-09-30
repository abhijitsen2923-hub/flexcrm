// Pure helpers for the one-page project form (towers, flats, parking) and the inventory counts — no React, no
// network (unit-tested in tests/projectInventory.test.ts). The "what will Save add" rules mirror the backend
// (backend/app/real_estate/inventory_layout.py): existing units are matched by unit type + floor, only the
// shortfall is created, nothing is ever removed, and parking is counted per type across the whole project.
import type { GarageOption, Tower, Unit, UnitType } from "../types/realestate";

export const PARKING_TYPES: GarageOption[] = ["MLP", "CP", "IP", "OP"];
export const PARKING_TYPE_LABEL: Record<GarageOption, string> = {
  MLP: "Multi-Level Parking",
  CP: "Covered Parking",
  IP: "Independent Parking",
  OP: "Open Parking",
};
// The project-level block that holds the parking spots (the backend creates it on demand).
export const PARKING_BLOCK_NAME = "Parking";
// Same limit as the backend: one Save may not create more units than this.
export const MAX_NEW_UNITS_PER_SAVE = 5000;
export const MAX_FLOORS = 200;
export const MAX_UNITS_PER_FLOOR = 200;

// Unit types a tower card can lay out (parking is project-level, counted per type).
export type TowerUnitType = Exclude<UnitType, "parking">;
export const TOWER_UNIT_TYPES: TowerUnitType[] = ["residential", "shop", "godown"];
const DEFAULT_PREFIX: Record<UnitType, string> = { residential: "R", parking: "P", shop: "S", godown: "G" };
const TYPE_NOUN: Record<UnitType, [string, string]> = {
  residential: ["flat", "flats"],
  shop: ["shop", "shops"],
  godown: ["godown", "godowns"],
  parking: ["parking spot", "parking spots"],
};

export function plural(count: number, type: UnitType): string {
  const [one, many] = TYPE_NOUN[type];
  return `${count.toLocaleString("en-IN")} ${count === 1 ? one : many}`;
}

export function isParkingBlock(name: string): boolean {
  return name.trim().toLowerCase() === PARKING_BLOCK_NAME.toLowerCase();
}

/** CP07 → "CP"; a spot not numbered by type (an older "P101") → null. */
export function parkingTypeOf(unitNumber: string): GarageOption | null {
  const value = unitNumber.trim().toUpperCase();
  return PARKING_TYPES.find((type) => new RegExp(`^${type}\\d+$`).test(value)) ?? null;
}

// ---------------------------------------------------------------------------------------------------------------
// Inventory counts (Projects list, Inventory board header)
// ---------------------------------------------------------------------------------------------------------------

export interface InventoryCounts {
  units: number; // everything except parking (flats, shops, godowns)
  unitsAvailable: number;
  parking: number;
  parkingAvailable: number;
}

export function inventoryCounts(towers: Pick<Tower, "units">[]): InventoryCounts {
  const counts: InventoryCounts = { units: 0, unitsAvailable: 0, parking: 0, parkingAvailable: 0 };
  for (const unit of towers.flatMap((t) => t.units)) {
    const available = unit.status === "available" ? 1 : 0;
    if (unit.unitType === "parking") {
      counts.parking += 1;
      counts.parkingAvailable += available;
    } else {
      counts.units += 1;
      counts.unitsAvailable += available;
    }
  }
  return counts;
}

/** Parking spots per type across the whole project (+ older spots not numbered by type). */
export function parkingCountsByType(towers: Pick<Tower, "units">[]): {
  byType: Record<GarageOption, number>;
  untyped: number;
} {
  const byType = { MLP: 0, CP: 0, IP: 0, OP: 0 } as Record<GarageOption, number>;
  let untyped = 0;
  for (const unit of towers.flatMap((t) => t.units)) {
    if (unit.unitType !== "parking") continue;
    const type = parkingTypeOf(unit.unitNumber);
    if (type) byType[type] += 1;
    else untyped += 1;
  }
  return { byType, untyped };
}

/** Board rows for the parking block: one row per type (in PARKING_TYPES order), then any older spots. */
export function groupParkingByType<T extends Pick<Unit, "unitNumber">>(units: T[]): { label: string; units: T[] }[] {
  const groups = new Map<string, T[]>();
  for (const unit of units) {
    const label = parkingTypeOf(unit.unitNumber) ?? "Other";
    groups.set(label, [...(groups.get(label) ?? []), unit]);
  }
  const order = [...PARKING_TYPES, "Other"];
  return order
    .filter((label) => groups.has(label))
    .map((label) => ({
      label,
      units: [...groups.get(label)!].sort((a, b) =>
        a.unitNumber.localeCompare(b.unitNumber, undefined, { numeric: true })
      ),
    }));
}

// ---------------------------------------------------------------------------------------------------------------
// Tower cards (the form state — strings, as typed into the inputs)
// ---------------------------------------------------------------------------------------------------------------

export interface UnitSpecForm {
  unit_type: TowerUnitType;
  units_per_floor: string;
  floor_from: string;
  floor_to: string;
  area: string; // super built-up (saleable) sqft — drives the suggested price
  carpet_area: string;
  built_up_area: string;
  base_price: string;
  unit_prefix: string;
  priceTouched: boolean; // the user typed a price (or it came from existing units) — don't auto-suggest over it
  followsTop: boolean; // runs to the tower's top floor — moves with it when the floor count changes
}

export interface TowerCard {
  key: string;
  towerId: string | null; // an existing tower, or null for one Save will create
  name: string;
  total_floors: string;
  unitSpecs: UnitSpecForm[];
  // Still following the Project details (total floors / flats per floor)? Cleared once the user edits the card.
  auto: boolean;
}

export interface ProjectRates {
  rateA: number | null; // ₹/sqft residential
  rateB: number | null; // ₹/sqft shop
  rateC: number | null; // ₹/sqft godown
}

export interface LayoutDetails {
  towers: number | null;
  floors: number | null;
  flatsPerFloor: number | null;
}

let cardSeq = 0;
function nextKey(): string {
  cardSeq += 1;
  return `card-${cardSeq}`;
}

function toInt(value: string): number | null {
  const trimmed = value.trim();
  if (trimmed === "") return null;
  const n = Number(trimmed);
  return Number.isFinite(n) ? Math.trunc(n) : null;
}

function toNum(value: string): number | null {
  const trimmed = value.trim();
  if (trimmed === "") return null;
  const n = Number(trimmed);
  return Number.isFinite(n) ? n : null;
}

export function rateFor(type: UnitType, rates: ProjectRates): number | null {
  const rate = type === "residential" ? rates.rateA : type === "shop" ? rates.rateB : type === "godown" ? rates.rateC : null;
  return rate != null && rate > 0 ? rate : null;
}

/** Suggested price = size × the project's rate for that type ("" when either is missing). */
export function suggestedPrice(spec: Pick<UnitSpecForm, "unit_type" | "area">, rates: ProjectRates): string {
  const area = toNum(spec.area);
  const rate = rateFor(spec.unit_type, rates);
  return area != null && area > 0 && rate != null ? String(Math.round(area * rate)) : "";
}

export function newUnitSpec(
  type: TowerUnitType,
  floors: number,
  perFloor: number | null,
  rates: ProjectRates
): UnitSpecForm {
  // Flats fill floors 1..top; shops / godowns default to the ground floor.
  const residential = type === "residential";
  return {
    unit_type: type,
    units_per_floor: perFloor != null && perFloor > 0 ? String(perFloor) : "",
    floor_from: residential ? "1" : "0",
    floor_to: residential ? String(Math.max(1, floors)) : "0",
    area: "",
    carpet_area: "",
    built_up_area: "",
    base_price: suggestedPrice({ unit_type: type, area: "" }, rates),
    unit_prefix: "",
    priceTouched: false,
    followsTop: residential,
  };
}

export function defaultTowerName(index: number): string {
  return `Tower ${index + 1}`;
}

/** A card for a tower Save will create, laid out from the Project details. */
export function newTowerCard(index: number, details: LayoutDetails, rates: ProjectRates, takenNames: string[] = []): TowerCard {
  const floors = details.floors != null && details.floors > 0 ? Math.min(details.floors, MAX_FLOORS) : 1;
  const taken = new Set(takenNames.map((n) => n.trim().toLowerCase()));
  let n = index;
  while (taken.has(defaultTowerName(n).toLowerCase())) n += 1;
  return {
    key: nextKey(),
    towerId: null,
    name: defaultTowerName(n),
    total_floors: String(floors),
    unitSpecs: [newUnitSpec("residential", floors, details.flatsPerFloor, rates)],
    auto: true,
  };
}

function mode<T>(values: T[]): T | undefined {
  const counts = new Map<T, number>();
  let best: T | undefined;
  let bestCount = 0;
  for (const value of values) {
    const count = (counts.get(value) ?? 0) + 1;
    counts.set(value, count);
    if (count > bestCount) {
      best = value;
      bestCount = count;
    }
  }
  return best;
}

/** "R101" on floor 1 → "R"; "A-1203" on floor 12 → "A-"; anything else → "" (use the default). */
function numberPrefix(unitNumber: string, floor: number): string | null {
  const match = new RegExp(`^(.*?)${floor}\\d{2,}$`).exec(unitNumber);
  return match ? match[1] : null;
}

/** A card for an existing tower, laid out from the units it has (so an unchanged Save adds nothing). */
export function cardFromTower(tower: Tower, details: LayoutDetails, rates: ProjectRates): TowerCard {
  const specs: UnitSpecForm[] = [];
  for (const type of TOWER_UNIT_TYPES) {
    const units = tower.units.filter((u) => u.unitType === type);
    if (units.length === 0) continue;
    const perFloor = new Map<number, number>();
    for (const u of units) perFloor.set(u.floor, (perFloor.get(u.floor) ?? 0) + 1);
    const floors = [...perFloor.keys()];
    const prefix = mode(units.map((u) => numberPrefix(u.unitNumber, u.floor)).filter((p): p is string => p !== null)) ?? "";
    const areaMode = mode(units.map((u) => u.area));
    specs.push({
      unit_type: type,
      units_per_floor: String(mode([...perFloor.values()]) ?? 1),
      floor_from: String(Math.min(...floors)),
      floor_to: String(Math.max(...floors)),
      area: areaMode != null ? String(areaMode) : "",
      carpet_area: String(mode(units.map((u) => u.carpetArea).filter((v): v is number => v != null)) ?? ""),
      built_up_area: String(mode(units.map((u) => u.builtUpArea).filter((v): v is number => v != null)) ?? ""),
      base_price: String(mode(units.map((u) => u.basePrice)) ?? ""),
      unit_prefix: prefix === DEFAULT_PREFIX[type] ? "" : prefix,
      priceTouched: true,
      followsTop: Math.max(...floors) === tower.totalFloors,
    });
  }
  const hasOnlyParking = tower.units.length > 0 && specs.length === 0;
  if (!hasOnlyParking && specs.length === 0) {
    // A tower with no units yet: lay it out from the details, like a new one.
    specs.push(newUnitSpec("residential", tower.totalFloors, details.flatsPerFloor, rates));
  }
  return {
    key: nextKey(),
    towerId: tower.id,
    name: tower.name,
    total_floors: String(tower.totalFloors),
    unitSpecs: specs,
    auto: false,
  };
}

/** The cards the form opens with: every existing tower (not the parking block), else N new ones from the details. */
export function initialCards(towers: Tower[], details: LayoutDetails, rates: ProjectRates): TowerCard[] {
  const existing = towers.filter((t) => !isParkingBlock(t.name)).map((t) => cardFromTower(t, details, rates));
  return syncCardsWithDetails(existing, details, rates);
}

/**
 * Follow the Project details: add new cards up to "Total towers", drop trailing new cards nobody edited when it
 * goes down, and re-lay-out cards still on `auto` (floors + flats per floor). Existing towers are never dropped.
 */
export function syncCardsWithDetails(cards: TowerCard[], details: LayoutDetails, rates: ProjectRates): TowerCard[] {
  const target = details.towers != null && details.towers > 0 ? Math.min(details.towers, 100) : null;
  let next = cards.map((card) => (card.auto ? relayout(card, details) : card));
  if (target != null) {
    while (next.length < target) next = [...next, newTowerCard(next.length, details, rates, next.map((c) => c.name))];
    while (next.length > target) {
      const last = next[next.length - 1];
      if (last.towerId || !last.auto) break;
      next = next.slice(0, -1);
    }
  }
  return next;
}

function relayout(card: TowerCard, details: LayoutDetails): TowerCard {
  const floors = details.floors != null && details.floors > 0 ? Math.min(details.floors, MAX_FLOORS) : null;
  let next = floors != null ? setCardFloors(card, String(floors)) : card;
  if (details.flatsPerFloor != null && details.flatsPerFloor > 0) {
    next = {
      ...next,
      unitSpecs: next.unitSpecs.map((s, i) =>
        i === 0 && s.unit_type === "residential" ? { ...s, units_per_floor: String(details.flatsPerFloor) } : s
      ),
    };
  }
  return next;
}

/** Change a tower's floor count; a spec that runs to the top floor keeps running to the new top. */
export function setCardFloors(card: TowerCard, floors: string): TowerCard {
  const top = toInt(floors);
  return {
    ...card,
    total_floors: floors,
    unitSpecs: card.unitSpecs.map((s) =>
      s.followsTop && top != null && top >= 1 ? { ...s, floor_to: String(Math.min(top, MAX_FLOORS)) } : s
    ),
  };
}

/** Edit one spec; a changed size re-suggests the price unless the user typed one. */
export function updateSpec(spec: UnitSpecForm, patch: Partial<UnitSpecForm>, rates: ProjectRates): UnitSpecForm {
  const next = { ...spec, ...patch };
  if ("base_price" in patch) return { ...next, priceTouched: true };
  if (("area" in patch || "unit_type" in patch) && !next.priceTouched) {
    return { ...next, base_price: suggestedPrice(next, rates) };
  }
  return next;
}

/** Edit spec `index` of a card (the user's edit — the card stops following the Project details). */
export function updateCardSpec(card: TowerCard, index: number, patch: Partial<UnitSpecForm>, rates: ProjectRates): TowerCard {
  return {
    ...card,
    auto: false,
    unitSpecs: card.unitSpecs.map((s, i) => {
      if (i !== index) return s;
      const next = updateSpec(s, patch, rates);
      // Typing the top floor by hand: it follows the tower only when it's set to the tower's top.
      return "floor_to" in patch
        ? { ...next, followsTop: toInt(next.floor_to) != null && toInt(next.floor_to) === toInt(card.total_floors) }
        : next;
    }),
  };
}

/** The project's rates changed: re-suggest every price the user hasn't typed. */
export function applyRates(cards: TowerCard[], rates: ProjectRates): TowerCard[] {
  return cards.map((card) => ({
    ...card,
    unitSpecs: card.unitSpecs.map((s) => (s.priceTouched ? s : { ...s, base_price: suggestedPrice(s, rates) })),
  }));
}

export interface FloorCount {
  floor: number;
  count: number;
}

/** A spec's floors → [{floor, count}] (empty when the count or range isn't usable). */
export function specFloors(spec: UnitSpecForm): FloorCount[] {
  const count = toInt(spec.units_per_floor);
  const from = toInt(spec.floor_from);
  const to = toInt(spec.floor_to);
  if (count == null || count < 1 || from == null || to == null || from < 0 || to < from) return [];
  return Array.from({ length: Math.min(to - from + 1, MAX_FLOORS + 1) }, (_, i) => ({
    floor: from + i,
    count: Math.min(count, MAX_UNITS_PER_FLOOR),
  }));
}

export interface UnitSpecPayload {
  unit_type: TowerUnitType;
  floors: FloorCount[];
  area: number;
  carpet_area: number | null;
  built_up_area: number | null;
  base_price: number;
  unit_prefix?: string;
}

export interface TowerCardPayload {
  tower_id?: string;
  name: string;
  total_floors: number;
  unit_specs: UnitSpecPayload[];
}

export function cardPayload(card: TowerCard): TowerCardPayload {
  const specs = card.unitSpecs
    .map((s) => ({ spec: s, floors: specFloors(s) }))
    .filter(({ floors }) => floors.length > 0)
    .map(({ spec, floors }) => ({
      unit_type: spec.unit_type,
      floors,
      area: toNum(spec.area) ?? 0,
      carpet_area: toNum(spec.carpet_area) || null,
      built_up_area: toNum(spec.built_up_area) || null,
      base_price: toNum(spec.base_price) ?? 0,
      ...(spec.unit_prefix.trim() ? { unit_prefix: spec.unit_prefix.trim() } : {}),
    }));
  return {
    ...(card.towerId ? { tower_id: card.towerId } : {}),
    name: card.name.trim(),
    total_floors: Math.min(Math.max(toInt(card.total_floors) ?? 1, 1), MAX_FLOORS),
    unit_specs: specs,
  };
}

// ---------------------------------------------------------------------------------------------------------------
// What Save will add (preview — the server's reply is the final word, e.g. archived units it counts too)
// ---------------------------------------------------------------------------------------------------------------

/** Units Save will add to this tower, per type — existing units matched by type + floor, only the shortfall. */
export function plannedAdds(card: TowerCard, existing: Pick<Unit, "unitType" | "floor">[]): Partial<Record<UnitType, number>> {
  const have = new Map<string, number>();
  for (const u of existing) have.set(`${u.unitType}|${u.floor}`, (have.get(`${u.unitType}|${u.floor}`) ?? 0) + 1);
  const adds: Partial<Record<UnitType, number>> = {};
  for (const spec of card.unitSpecs) {
    for (const { floor, count } of specFloors(spec)) {
      const key = `${spec.unit_type}|${floor}`;
      const reuse = Math.min(have.get(key) ?? 0, count);
      have.set(key, (have.get(key) ?? 0) - reuse);
      if (count > reuse) adds[spec.unit_type] = (adds[spec.unit_type] ?? 0) + count - reuse;
    }
  }
  return adds;
}

export function totalOf(adds: Partial<Record<string, number>>): number {
  return Object.values(adds).reduce<number>((sum, n) => sum + (n ?? 0), 0);
}

export function describeAdds(adds: Partial<Record<UnitType, number>>): string {
  return (Object.entries(adds) as [UnitType, number][])
    .filter(([, n]) => n > 0)
    .map(([type, n]) => plural(n, type))
    .join(", ");
}

export type ParkingCountsForm = Record<GarageOption, string>;

export const EMPTY_PARKING_COUNTS: ParkingCountsForm = { MLP: "", CP: "", IP: "", OP: "" };

/** Parking counts to send: only the types that are ticked (a blank count is 0). */
export function parkingPayload(selected: GarageOption[], counts: ParkingCountsForm): Partial<Record<GarageOption, number>> {
  const out: Partial<Record<GarageOption, number>> = {};
  for (const type of PARKING_TYPES) {
    if (!selected.includes(type)) continue;
    out[type] = Math.max(0, toInt(counts[type]) ?? 0);
  }
  return out;
}

export function parkingTotal(selected: GarageOption[], counts: ParkingCountsForm): number {
  return Object.values(parkingPayload(selected, counts)).reduce((sum, n) => sum + (n ?? 0), 0);
}

/** Parking spots Save will add per type (existing = active typed spots on the project). */
export function plannedParkingAdds(
  selected: GarageOption[],
  counts: ParkingCountsForm,
  existingByType: Record<GarageOption, number>
): Partial<Record<GarageOption, number>> {
  const adds: Partial<Record<GarageOption, number>> = {};
  for (const [type, target] of Object.entries(parkingPayload(selected, counts)) as [GarageOption, number][]) {
    const missing = target - (existingByType[type] ?? 0);
    if (missing > 0) adds[type] = missing;
  }
  return adds;
}

/** Edit form prefill: counts from the spots that exist; for a project with none, its declared total when it
 * offers exactly one parking type (several types can't be split for the user). */
export function initialParkingCounts(
  existingByType: Record<GarageOption, number>,
  garageOptions: GarageOption[],
  totalGarages: number | null
): { selected: GarageOption[]; counts: ParkingCountsForm } {
  const counts = { ...EMPTY_PARKING_COUNTS };
  const selected = PARKING_TYPES.filter((t) => garageOptions.includes(t) || existingByType[t] > 0);
  const anyBuilt = PARKING_TYPES.some((t) => existingByType[t] > 0);
  for (const type of selected) {
    if (existingByType[type] > 0) counts[type] = String(existingByType[type]);
  }
  if (!anyBuilt && selected.length === 1 && totalGarages != null && totalGarages > 0) {
    counts[selected[0]] = String(totalGarages);
  }
  return { selected, counts };
}

/** Problems that would make Save fail or build the wrong thing — shown before anything is sent. */
export function validateLayout(cards: TowerCard[], newUnitsTotal: number): string | null {
  const seen = new Set<string>();
  for (const [i, card] of cards.entries()) {
    const name = card.name.trim();
    const label = name || `Tower ${i + 1}`;
    if (!name) return `Tower ${i + 1}: enter a tower name.`;
    if (isParkingBlock(name)) return `“${PARKING_BLOCK_NAME}” is kept for the project's parking — rename ${label}.`;
    if (seen.has(name.toLowerCase())) return `Two towers are named “${name}” — give each tower its own name.`;
    seen.add(name.toLowerCase());
    const floors = toInt(card.total_floors);
    if (floors == null || floors < 1 || floors > MAX_FLOORS) return `${label}: floors must be between 1 and ${MAX_FLOORS}.`;
    for (const spec of card.unitSpecs) {
      const count = toInt(spec.units_per_floor);
      if (count == null || count < 1) continue; // an empty spec adds nothing
      const noun = TYPE_NOUN[spec.unit_type][1];
      if (count > MAX_UNITS_PER_FLOOR) return `${label}: at most ${MAX_UNITS_PER_FLOOR} ${noun} per floor.`;
      if (specFloors(spec).length === 0) return `${label}: check the floor range for ${noun}.`;
      if (toInt(spec.floor_to)! > floors) {
        return `${label}: ${noun} go up to floor ${spec.floor_to}, above the tower's ${floors} floors.`;
      }
      if (!((toNum(spec.area) ?? 0) > 0)) return `${label}: enter the size (sq ft) of the ${noun}.`;
      if (toNum(spec.base_price) == null || toNum(spec.base_price)! < 0) return `${label}: enter the price of the ${noun}.`;
    }
  }
  if (newUnitsTotal > MAX_NEW_UNITS_PER_SAVE) {
    return `This would create ${newUnitsTotal.toLocaleString("en-IN")} units — more than ${MAX_NEW_UNITS_PER_SAVE.toLocaleString("en-IN")} in one save. Check the floors, flats per floor and parking counts.`;
  }
  return null;
}

/** "2 towers, 288 units and 112 parking spots added" (or "No new towers or units were needed"). */
export function describeCreated(created: { towers: number; units: number; parking: number }): string {
  const parts: string[] = [];
  if (created.towers) parts.push(`${created.towers} tower${created.towers === 1 ? "" : "s"}`);
  if (created.units) parts.push(`${created.units.toLocaleString("en-IN")} unit${created.units === 1 ? "" : "s"}`);
  if (created.parking) parts.push(plural(created.parking, "parking"));
  if (parts.length === 0) return "No new towers or units were needed.";
  const list = parts.length > 1 ? `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}` : parts[0];
  return `${list} added.`;
}
