// How a unit is named on screen: its flat type ("Type A · 2 BHK"), picker labels and the text a unit search
// matches. Pure, no React, no runtime imports (unit-tested in tests/unitLabel.test.ts).
//
// Units made before flat types existed have no flatType / configuration: every label here falls back to the
// unit's category (or to nothing) so those units read exactly as before.
import type { UnitType } from "../types/realestate";

export const UNIT_CATEGORY_LABEL: Record<UnitType, string> = {
  residential: "Residential",
  parking: "Parking",
  shop: "Shop",
  godown: "Godown",
};

interface FlatFields {
  flatType?: string | null;
  configuration?: string | null;
}

interface KindFields extends FlatFields {
  unitType?: UnitType | string | null;
}

interface AreaFields {
  area?: number | null;
  areaUnit?: string | null;
}

/** A unit as the pickers know it: the unit plus the names of its tower and project. */
export interface PickerUnit extends KindFields, AreaFields {
  unitNumber: string;
  floor?: number | null;
  towerName: string;
  projectName: string;
}

/** "Type A · 2 BHK" / "Type A" / "2 BHK" / "" (a unit set up before flat types). */
export function flatTypeLabel(unit: FlatFields): string {
  const type = unit.flatType?.trim();
  const config = unit.configuration?.trim();
  return [type ? `Type ${type}` : "", config ?? ""].filter(Boolean).join(" · ");
}

/** The flat type when there is one, else the category ("Shop", "Residential" …). */
export function unitKindLabel(unit: KindFields): string {
  const flat = flatTypeLabel(unit);
  if (flat) return flat;
  if (!unit.unitType) return "";
  return UNIT_CATEGORY_LABEL[unit.unitType as UnitType] ?? String(unit.unitType);
}

/** "1,250 sq ft" ("" for a unit with no area, e.g. a parking spot). */
export function areaLabel(unit: AreaFields): string {
  const area = Number(unit.area);
  if (!Number.isFinite(area) || area <= 0) return "";
  const amount = area.toLocaleString("en-IN", { maximumFractionDigits: 2 });
  return `${amount} ${unit.areaUnit === "sqmt" ? "sq m" : "sq ft"}`;
}

/**
 * Everything a picker shows after the unit number: "Type A · 2 BHK · 1,250 sq ft · Tower A · Project".
 * A flat with no type shows no kind (as before); a shop / godown / parking spot shows its category.
 */
export function unitOptionParts(unit: PickerUnit): string[] {
  const flat = flatTypeLabel(unit);
  const kind = flat || (unit.unitType && unit.unitType !== "residential" ? unitKindLabel(unit) : "");
  return [kind, areaLabel(unit), unit.towerName, unit.projectName].filter((part) => part && part.trim());
}

/** One-line picker label: "A-101 · Type A · 2 BHK · 1,250 sq ft · Tower A · Project". */
export function unitOptionLabel(unit: PickerUnit): string {
  return [unit.unitNumber, ...unitOptionParts(unit)].join(" · ");
}

/** The text a unit search looks through — number, project, tower, floor, type and configuration. */
export function unitSearchText(unit: PickerUnit): string {
  return unitSearchFields(unit).join(" ").toLowerCase();
}

function unitSearchFields(unit: PickerUnit): string[] {
  const fields = [unit.unitNumber, unit.projectName, unit.towerName];
  if (unit.floor != null) fields.push(`floor ${unit.floor}`);
  if (unit.flatType?.trim()) fields.push(`type ${unit.flatType.trim()}`);
  if (unit.configuration?.trim()) fields.push(unit.configuration.trim());
  if (unit.unitType) fields.push(UNIT_CATEGORY_LABEL[unit.unitType as UnitType] ?? String(unit.unitType));
  return fields.filter(Boolean);
}

// Spaces, hyphens, dots and slashes dropped, so "2bhk" finds "2 BHK" and "a101" finds "A-101".
function compact(value: string): string {
  return value.toLowerCase().replace(/[\s\-_./]+/g, "");
}

/** Does the unit match what was typed in a picker's search box? An empty search matches everything. */
export function matchesUnitSearch(unit: PickerUnit, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  if (unitSearchText(unit).includes(q)) return true;
  const cq = compact(q);
  // Compared field by field, so a squashed query can't match across two fields ("a2" ≠ "Type A" + "2 BHK").
  return cq.length > 0 && unitSearchFields(unit).some((field) => compact(field).includes(cq));
}

// One collator for every comparison — the board sorts thousands of units.
const UNIT_NUMBER_ORDER = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });

/** Natural order for unit numbers on a floor: A-101, A-102 … A-110 (not A-101, A-110, A-102). */
export function compareUnitNumbers(a: string, b: string): number {
  return UNIT_NUMBER_ORDER.compare(a, b);
}

// "Studio" first, then by the leading number (1 BHK, 1.5 BHK, 2 BHK …), then names without one (Penthouse …).
function configRank(config: string): number {
  const lead = /^\s*(\d+(?:\.\d+)?)/.exec(config);
  if (lead) return Number(lead[1]);
  if (/^\s*studio/i.test(config)) return 0;
  return Number.POSITIVE_INFINITY;
}

/** The distinct configurations among these units, in a sensible order ("" / missing ones left out). */
export function configurationOptions(units: FlatFields[]): string[] {
  const seen = new Map<string, string>();
  for (const unit of units) {
    const config = unit.configuration?.trim();
    if (config && !seen.has(config.toLowerCase())) seen.set(config.toLowerCase(), config);
  }
  return [...seen.values()].sort((a, b) => {
    const ra = configRank(a);
    const rb = configRank(b);
    if (ra !== rb) return ra < rb ? -1 : 1;
    return a.localeCompare(b, undefined, { sensitivity: "base" });
  });
}

/** Does this unit have the configuration chosen in a filter (case-insensitive)? */
export function hasConfiguration(unit: FlatFields, config: string): boolean {
  return (unit.configuration?.trim().toLowerCase() ?? "") === config.trim().toLowerCase();
}
