// Pure helpers for project inventory: counts, parking per type and the toast wording — no React, no network
// (unit-tested in tests/projectInventory.test.ts). Parking is counted per type across the whole project; the
// project wizard's own helpers live in utils/projectWizard.ts.
import type { ParkingType, Tower, Unit, UnitType } from "../types/realestate";

// Dependent Parking (DP) is last so the older types keep their order (and numbering) everywhere.
export const PARKING_TYPES: ParkingType[] = ["MLP", "CP", "IP", "OP", "DP"];
export const PARKING_TYPE_LABEL: Record<ParkingType, string> = {
  MLP: "Multi-Level Parking",
  CP: "Covered Parking",
  IP: "Independent Parking",
  OP: "Open Parking",
  DP: "Dependent Parking",
};
// The project-level block that holds the parking spots (the backend creates it on demand).
export const PARKING_BLOCK_NAME = "Parking";

// Unit types a tower can hold (parking is project-level, counted per type).
export type TowerUnitType = Exclude<UnitType, "parking">;
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
export function parkingTypeOf(unitNumber: string): ParkingType | null {
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
  byType: Record<ParkingType, number>;
  untyped: number;
} {
  const byType: Record<ParkingType, number> = { MLP: 0, CP: 0, IP: 0, OP: 0, DP: 0 };
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
// The older one-page form's tower request (unit_specs). Still accepted by the server; the wizard sends layouts.
// ---------------------------------------------------------------------------------------------------------------

export interface FloorCount {
  floor: number;
  count: number;
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
