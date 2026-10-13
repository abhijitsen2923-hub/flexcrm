// Pure helpers for the Add / Edit Project wizard (pages/inventory/components/ProjectWizard*.tsx) — no React, no
// network, unit-tested in tests/projectWizard.test.ts. Only TYPE imports here: the test runner loads this file
// directly, so it can't pull in other modules at runtime.
//
// The server is the final word on what Save creates (it builds and prices the units from each tower's layout,
// and its preview runs the same code). These helpers keep the form state (strings, as typed), check each step
// before the user moves on, show the builder the sums (flats per floor, list prices) and build the requests.
import type {
  FlatTypeLayout,
  FloorRiseBasis,
  GarageOption,
  OtherUnitLayout,
  ParkingType,
  PlanDueOn,
  PlanMilestone,
  PricingBasis,
  Project,
  ProjectType,
  Tower,
  TowerLayout,
  Unit,
} from "../types/realestate";
import type {
  ParkingCountsPayload,
  ProjectFullPayload,
  ProjectInventoryPayload,
  ProjectInventoryPreviewPayload,
  ProjectTowerPayload,
  ProjectTowerSyncPayload,
  ProjectUpdatePayload,
} from "../services/inventory";

export const WIZARD_STEPS = [
  "Project info",
  "Towers & flat types",
  "Pricing",
  "Parking",
  "Payment plan",
  "Preview",
  "Review & save",
] as const;
export const STEP_INFO = 0;
export const STEP_TOWERS = 1;
export const STEP_PRICING = 2;
export const STEP_PARKING = 3;
export const STEP_PLAN = 4;
export const STEP_PREVIEW = 5;
export const STEP_REVIEW = 6;

// Same limits as the server.
export const MAX_FLOORS = 200;
export const MAX_FLAT_TYPES = 99; // positions 01..99 on a floor
export const MAX_PER_FLOOR = 200;
export const MAX_OTHER_ROWS = 20;
export const MAX_PREFIX_LENGTH = 8;
export const MAX_NEW_UNITS_PER_SAVE = 5000;
export const MAX_PARKING_PER_TYPE = 5000;
export const MAX_PLAN_MILESTONES = 40;
export const MAX_COVER_BYTES = 5 * 1024 * 1024;
export const COVER_TYPES = ["image/jpeg", "image/png"];
// The project-level block that holds the parking spots (never a tower card).
const PARKING_BLOCK_NAME = "parking";

// Same order as PARKING_TYPES in utils/projectInventory.ts (a test keeps them equal). DP is last so the older
// types keep their place everywhere.
export const WIZARD_PARKING_TYPES: ParkingType[] = ["MLP", "CP", "IP", "OP", "DP"];
// The four types older builds understand — the only ones ever written into garage_options.
const GARAGE_OPTION_TYPES: GarageOption[] = ["MLP", "CP", "IP", "OP"];

export const CONFIGURATION_SUGGESTIONS = [
  "Studio",
  "1 BHK",
  "1.5 BHK",
  "2 BHK",
  "2.5 BHK",
  "3 BHK",
  "3.5 BHK",
  "4 BHK",
  "5 BHK",
  "Penthouse",
  "Duplex",
];

// ---------------------------------------------------------------------------------------------------------------
// Small parsing helpers (inputs hold strings)
// ---------------------------------------------------------------------------------------------------------------

export function toNum(value: string): number | null {
  const trimmed = value.trim();
  if (trimmed === "") return null;
  const n = Number(trimmed);
  return Number.isFinite(n) ? n : null;
}

export function toInt(value: string): number | null {
  const n = toNum(value);
  return n != null && Number.isInteger(n) ? n : null;
}

function str(value: number | null | undefined): string {
  return value != null && Number.isFinite(value) ? String(value) : "";
}

function positive(value: string): number | null {
  const n = toNum(value);
  return n != null && n > 0 ? n : null;
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

let keySeq = 0;
function nextKey(prefix: string): string {
  keySeq += 1;
  return `${prefix}${keySeq}`;
}

export function isParkingBlockName(name: string): boolean {
  return name.trim().toLowerCase() === PARKING_BLOCK_NAME;
}

// ---------------------------------------------------------------------------------------------------------------
// Flat-type letters: the letter IS the position on the floor (A → x01, B → x02 … Z → x26, AA → x27 …)
// ---------------------------------------------------------------------------------------------------------------

export function codeForPosition(position: number): string {
  let n = Math.trunc(position);
  let code = "";
  while (n > 0) {
    const r = (n - 1) % 26;
    code = String.fromCharCode(65 + r) + code;
    n = Math.floor((n - 1) / 26);
  }
  return code;
}

export function positionOfCode(code: string): number | null {
  if (!/^[A-Z]{1,2}$/.test(code)) return null;
  let n = 0;
  for (const ch of code) n = n * 26 + (ch.charCodeAt(0) - 64);
  return n;
}

/** The lowest letter no type in the tower uses yet (deleting B leaves a gap that the next type fills). */
export function nextFreeCode(codes: string[]): string | null {
  const used = new Set(codes);
  for (let p = 1; p <= MAX_FLAT_TYPES; p += 1) {
    const code = codeForPosition(p);
    if (!used.has(code)) return code;
  }
  return null;
}

function byPosition<T extends { code: string }>(types: T[]): T[] {
  return [...types].sort((a, b) => (positionOfCode(a.code) ?? 999) - (positionOfCode(b.code) ?? 999));
}

// ---------------------------------------------------------------------------------------------------------------
// Step 1 — project info
// ---------------------------------------------------------------------------------------------------------------

export interface InfoForm {
  name: string;
  builder: string;
  projectType: ProjectType | "";
  location: string;
  city: string;
  pinCode: string;
  landmark: string;
  rera: string;
}

export const PROJECT_TYPE_OPTIONS: { value: ProjectType; label: string }[] = [
  { value: "residential", label: "Residential" },
  { value: "commercial", label: "Commercial" },
  { value: "mixed", label: "Mixed use" },
];

/** Why a picked cover image can't be used (null = fine). Checked in the browser before anything uploads. */
export function coverFileError(file: { type: string; size: number }): string | null {
  if (!COVER_TYPES.includes(file.type)) return "Pick a JPG or PNG image.";
  if (file.size > MAX_COVER_BYTES) return "The image is larger than 5 MB — pick a smaller one.";
  return null;
}

// ---------------------------------------------------------------------------------------------------------------
// Step 2 — towers & flat types
// ---------------------------------------------------------------------------------------------------------------

export interface FlatTypeForm {
  code: string; // "A" — read-only, stable
  configuration: string;
  carpet: string;
  builtUp: string;
  superBuiltUp: string;
  plc: boolean;
  limitFloors: boolean; // off = floor 1 to the tower's top floor
  floorFrom: string;
  floorTo: string;
}

export type OtherUnitKind = "shop" | "godown";

export interface OtherUnitForm {
  key: string;
  unitType: OtherUnitKind;
  perFloor: string;
  floorFrom: string;
  floorTo: string;
  area: string; // super built-up
  carpet: string;
  builtUp: string;
  prefix: string; // carried from the saved layout / older units — "" = the server's default ({tower prefix}S / G)
}

export type ExistingUnitInfo = Pick<
  Unit,
  "floor" | "unitType" | "unitNumber" | "flatType" | "area" | "carpetArea" | "builtUpArea" | "configuration"
>;

export interface TowerForm {
  key: string;
  towerId: string | null; // an existing tower, or null for one Save will create
  name: string;
  floors: string;
  prefix: string;
  prefixTouched: boolean; // the user typed a prefix — stop following the name
  originalPrefix: string | null; // an existing tower's prefix as it is today (null = new tower)
  flatTypes: FlatTypeForm[];
  others: OtherUnitForm[];
  existingUnits: ExistingUnitInfo[]; // live units of an existing tower
  // Set up before flat types (no saved layout). Until the user converts it, it's shown read-only and NOT sent.
  legacy: boolean;
  converted: boolean;
}

/** A tower Save sends (new towers, towers with flat types, older towers the user converted). */
export function isEditableTower(tower: TowerForm): boolean {
  return !tower.legacy || tower.converted;
}

export function blankFlatType(code: string): FlatTypeForm {
  return {
    code,
    configuration: "",
    carpet: "",
    builtUp: "",
    superBuiltUp: "",
    plc: false,
    limitFloors: false,
    floorFrom: "",
    floorTo: "",
  };
}

export function blankOtherUnit(unitType: OtherUnitKind): OtherUnitForm {
  return {
    key: nextKey("o"),
    unitType,
    perFloor: "1",
    floorFrom: "0",
    floorTo: "0",
    area: "",
    carpet: "",
    builtUp: "",
    prefix: "",
  };
}

/**
 * The unit-number prefix a tower name suggests: "A" / "T1" → "A-" / "T1-"; else the last word when it is 1–3
 * letters or digits ("Tower A" → "A-", "Block 12" → "12-"); else the initials of up to 3 words ("Orchid
 * Heights" → "OH-").
 */
export function guessPrefix(name: string): string {
  const trimmed = name.trim();
  if (!trimmed) return "";
  const short = /^[A-Za-z0-9]{1,3}$/;
  let stem: string;
  if (short.test(trimmed)) {
    stem = trimmed;
  } else {
    const words = trimmed.split(/[^A-Za-z0-9]+/).filter(Boolean);
    const last = words[words.length - 1] ?? "";
    stem = short.test(last) ? last : words.slice(0, 3).map((w) => w[0]).join("");
  }
  return `${stem.toUpperCase()}-`.slice(0, MAX_PREFIX_LENGTH);
}

/** The next tower's name: "Tower A" → "Tower B", "Block 3" → "Block 4"; otherwise "Tower N". Never a taken one. */
export function nextTowerName(names: string[]): string {
  const taken = new Set(names.map((n) => n.trim().toLowerCase()));
  const free = (candidate: string) => !taken.has(candidate.toLowerCase());
  const last = names.length ? names[names.length - 1].trim() : "";
  const letter = /^(.*?)([A-Y])$/i.exec(last);
  if (letter && (letter[1] === "" || /\s$/.test(letter[1]))) {
    const lower = letter[2] === letter[2].toLowerCase();
    for (let c = letter[2].toUpperCase().charCodeAt(0) + 1; c <= 90; c += 1) {
      const next = String.fromCharCode(c);
      const candidate = `${letter[1]}${lower ? next.toLowerCase() : next}`;
      if (free(candidate)) return candidate;
    }
  }
  const number = /^(.*?)(\d+)$/.exec(last);
  if (number) {
    for (let n = Number(number[2]) + 1; n < Number(number[2]) + 500; n += 1) {
      const candidate = `${number[1]}${n}`;
      if (free(candidate)) return candidate;
    }
  }
  if (!last && free("Tower A")) return "Tower A";
  for (let n = names.length + 1; ; n += 1) {
    if (free(`Tower ${n}`)) return `Tower ${n}`;
  }
}

/** A new tower: copies the previous tower's floors and flat types (the common case), with the next name. */
export function newTowerForm(previous: TowerForm | undefined, takenNames: string[]): TowerForm {
  const name = nextTowerName(takenNames);
  const copyTypes = previous && previous.flatTypes.length > 0;
  return {
    key: nextKey("t"),
    towerId: null,
    name,
    floors: previous?.floors ?? "",
    prefix: guessPrefix(name),
    prefixTouched: false,
    originalPrefix: null,
    flatTypes: copyTypes ? previous!.flatTypes.map((t) => ({ ...t })) : [blankFlatType("A")],
    others: [],
    existingUnits: [],
    legacy: false,
    converted: false,
  };
}

/** "R101" on floor 1 → "R"; "A-1203" on floor 12 → "A-"; anything else → null. */
function numberPrefix(unitNumber: string, floor: number): string | null {
  const match = new RegExp(`^(.*?)${floor}\\d{2,}$`).exec(unitNumber);
  return match ? match[1] : null;
}

function existingInfo(units: Unit[]): ExistingUnitInfo[] {
  return units
    .filter((u) => u.unitType !== "parking")
    .map((u) => ({
      floor: u.floor,
      unitType: u.unitType,
      unitNumber: u.unitNumber,
      flatType: u.flatType,
      area: u.area,
      carpetArea: u.carpetArea,
      builtUpArea: u.builtUpArea,
      configuration: u.configuration,
    }));
}

function numOrBlank(value: unknown): string {
  return typeof value === "number" && Number.isFinite(value) ? String(value) : typeof value === "string" ? value : "";
}

/** A saved layout read defensively (it's stored as plain JSON) — null when it isn't usable. */
export function readLayout(raw: unknown): TowerLayout | null {
  if (!raw || typeof raw !== "object") return null;
  const layout = raw as Partial<TowerLayout>;
  if (!Array.isArray(layout.flat_types) && !Array.isArray(layout.others)) return null;
  return {
    unit_prefix: typeof layout.unit_prefix === "string" ? layout.unit_prefix : "",
    flat_types: (Array.isArray(layout.flat_types) ? layout.flat_types : []).filter(
      (t): t is FlatTypeLayout => !!t && typeof t === "object" && typeof (t as FlatTypeLayout).code === "string"
    ),
    others: (Array.isArray(layout.others) ? layout.others : []).filter(
      (o): o is OtherUnitLayout => !!o && typeof o === "object" && (o.unit_type === "shop" || o.unit_type === "godown")
    ),
  };
}

/** An existing tower as the wizard opens it: from its saved layout, or read-only when it predates flat types. */
export function towerFormFromTower(tower: Tower): TowerForm {
  const layout = readLayout(tower.layout);
  const existingUnits = existingInfo(tower.units);
  const base = {
    key: nextKey("t"),
    towerId: tower.id,
    name: tower.name,
    floors: String(tower.totalFloors),
    prefixTouched: true,
    existingUnits,
  };
  if (!layout) {
    const prefix = guessExistingPrefix(existingUnits) ?? guessPrefix(tower.name);
    return { ...base, prefix, originalPrefix: prefix, flatTypes: [], others: [], legacy: true, converted: false };
  }
  return {
    ...base,
    prefix: layout.unit_prefix,
    originalPrefix: layout.unit_prefix,
    flatTypes: byPosition(layout.flat_types).map((t) => ({
      code: t.code,
      configuration: t.configuration ?? "",
      carpet: numOrBlank(t.carpet_area),
      builtUp: numOrBlank(t.built_up_area),
      superBuiltUp: numOrBlank(t.super_built_up_area),
      plc: Boolean(t.has_plc),
      limitFloors: t.floor_from != null || t.floor_to != null,
      floorFrom: t.floor_from != null ? String(t.floor_from) : "1",
      floorTo: t.floor_to != null ? String(t.floor_to) : String(tower.totalFloors),
    })),
    others: layout.others.map((o) => ({
      key: nextKey("o"),
      unitType: o.unit_type,
      perFloor: numOrBlank(o.per_floor),
      floorFrom: numOrBlank(o.floor_from),
      floorTo: numOrBlank(o.floor_to),
      area: numOrBlank(o.area),
      carpet: numOrBlank(o.carpet_area),
      builtUp: numOrBlank(o.built_up_area),
      prefix: o.unit_prefix ?? "",
    })),
    legacy: false,
    converted: false,
  };
}

function guessExistingPrefix(units: ExistingUnitInfo[]): string | null {
  const flats = units.filter((u) => u.unitType === "residential");
  const pool = flats.length ? flats : units;
  return mode(pool.map((u) => numberPrefix(u.unitNumber, u.floor)).filter((p): p is string => p !== null)) ?? null;
}

function perFloorCounts(units: ExistingUnitInfo[]): Map<number, number> {
  const perFloor = new Map<number, number>();
  for (const u of units) perFloor.set(u.floor, (perFloor.get(u.floor) ?? 0) + 1);
  return perFloor;
}

export interface LegacySummary {
  flats: number;
  perFloor: number; // the most common flats-per-floor count
  floorFrom: number | null;
  floorTo: number | null;
  shops: number;
  godowns: number;
}

export function legacySummary(tower: TowerForm): LegacySummary {
  const flats = tower.existingUnits.filter((u) => u.unitType === "residential");
  const perFloor = perFloorCounts(flats);
  const floors = [...perFloor.keys()];
  return {
    flats: flats.length,
    perFloor: mode([...perFloor.values()]) ?? 0,
    floorFrom: floors.length ? Math.min(...floors) : null,
    floorTo: floors.length ? Math.max(...floors) : null,
    shops: tower.existingUnits.filter((u) => u.unitType === "shop").length,
    godowns: tower.existingUnits.filter((u) => u.unitType === "godown").length,
  };
}

function countNoun(n: number, one: string, many: string): string {
  return `${n.toLocaleString("en-IN")} ${n === 1 ? one : many}`;
}

/** "Set up before flat types — 40 flats, 4 per floor, floors 1–10. Its flats keep their details." */
export function legacySummaryText(tower: TowerForm): string {
  const s = legacySummary(tower);
  const parts: string[] = [];
  if (s.flats > 0) {
    const range = s.floorFrom === s.floorTo ? `floor ${s.floorFrom}` : `floors ${s.floorFrom}–${s.floorTo}`;
    parts.push(`${countNoun(s.flats, "flat", "flats")}, ${s.perFloor} per floor, ${range}`);
  }
  if (s.shops > 0) parts.push(countNoun(s.shops, "shop", "shops"));
  if (s.godowns > 0) parts.push(countNoun(s.godowns, "godown", "godowns"));
  if (parts.length === 0) return "Set up before flat types — no units yet.";
  return `Set up before flat types — ${parts.join(" · ")}. Its ${s.flats > 0 ? "flats" : "units"} keep their details.`;
}

/**
 * "Set up flat types" on an older tower: N types (N = its most common flats-per-floor count), each pre-filled with
 * the tower's most common sizes, over the floors its flats are on; shops / godowns grouped per kind. The server
 * matches the existing flats first, so an unchanged conversion adds nothing on floors that are already full.
 */
export function convertLegacyTower(tower: TowerForm): TowerForm {
  const units = tower.existingUnits;
  const flats = units.filter((u) => u.unitType === "residential");
  const top = toInt(tower.floors) ?? 1;
  let flatTypes: FlatTypeForm[] = [];
  if (flats.length > 0) {
    const s = legacySummary(tower);
    const fullRange = s.floorFrom === 1 && s.floorTo === top;
    const size = {
      configuration: mode(flats.map((u) => u.configuration).filter((c): c is string => !!c)) ?? "",
      carpet: str(mode(flats.map((u) => u.carpetArea).filter((v): v is number => v != null))),
      builtUp: str(mode(flats.map((u) => u.builtUpArea).filter((v): v is number => v != null))),
      superBuiltUp: str(mode(flats.map((u) => u.area))),
    };
    flatTypes = Array.from({ length: Math.min(Math.max(s.perFloor, 1), MAX_FLAT_TYPES) }, (_, i) => ({
      ...blankFlatType(codeForPosition(i + 1)),
      ...size,
      limitFloors: !fullRange,
      floorFrom: String(s.floorFrom ?? 1),
      floorTo: String(s.floorTo ?? top),
    }));
  } else if (units.length === 0) {
    flatTypes = [blankFlatType("A")];
  }
  const others: OtherUnitForm[] = [];
  for (const kind of ["shop", "godown"] as const) {
    const ofKind = units.filter((u) => u.unitType === kind);
    if (ofKind.length === 0) continue;
    const perFloor = perFloorCounts(ofKind);
    const floors = [...perFloor.keys()];
    others.push({
      key: nextKey("o"),
      unitType: kind,
      perFloor: String(mode([...perFloor.values()]) ?? 1),
      floorFrom: String(Math.min(...floors)),
      floorTo: String(Math.max(...floors)),
      area: str(mode(ofKind.map((u) => u.area))),
      carpet: str(mode(ofKind.map((u) => u.carpetArea).filter((v): v is number => v != null))),
      builtUp: str(mode(ofKind.map((u) => u.builtUpArea).filter((v): v is number => v != null))),
      prefix: mode(ofKind.map((u) => numberPrefix(u.unitNumber, u.floor)).filter((p): p is string => p !== null)) ?? "",
    });
  }
  return { ...tower, flatTypes, others, converted: true };
}

/** Undo "Set up flat types" before saving: back to the read-only summary (nothing is sent for it). */
export function revertLegacyTower(tower: TowerForm): TowerForm {
  return { ...tower, flatTypes: [], others: [], prefix: tower.originalPrefix ?? tower.prefix, converted: false };
}

/** Rename a tower; its prefix keeps following the name until the user types one. */
export function renameTower(tower: TowerForm, name: string): TowerForm {
  return { ...tower, name, prefix: tower.prefixTouched ? tower.prefix : guessPrefix(name) };
}

/** Add a flat type with the lowest free letter (null when the tower already has the most a floor can hold). A letter
 * whose flats still exist (a type removed from the page) is not free: reusing it would hand those flats a blank type. */
export function addFlatType(tower: TowerForm): TowerForm | null {
  const code = nextFreeCode([
    ...tower.flatTypes.map((t) => t.code),
    ...removedTypesWithUnits(tower).map((t) => t.code),
  ]);
  if (!code) return null;
  return { ...tower, flatTypes: byPosition([...tower.flatTypes, blankFlatType(code)]) };
}

/** The floors a flat type is on: floor 1 to the top unless it's limited (null when the range isn't usable). */
export function flatTypeRange(type: FlatTypeForm, top: number): [number, number] | null {
  if (!type.limitFloors) return top >= 1 ? [1, top] : null;
  const from = toInt(type.floorFrom);
  const to = toInt(type.floorTo);
  if (from == null || to == null || from < 0 || to < from || to > top) return null;
  return [from, to];
}

function otherRange(other: OtherUnitForm, top: number): [number, number] | null {
  const from = toInt(other.floorFrom);
  const to = toInt(other.floorTo);
  if (from == null || to == null || from < 0 || to < from || to > top) return null;
  return [from, to];
}

export interface FlatsSummary {
  floors: number; // floors that have flats
  perFloorMin: number;
  perFloorMax: number;
  flats: number;
  shops: number;
  godowns: number;
}

/** Flats per floor and in the tower, from the types' floor ranges (each type = one flat per floor). */
export function flatsSummary(tower: TowerForm): FlatsSummary {
  const top = toInt(tower.floors);
  const empty: FlatsSummary = { floors: 0, perFloorMin: 0, perFloorMax: 0, flats: 0, shops: 0, godowns: 0 };
  if (top == null || top < 1 || top > MAX_FLOORS) return empty;
  const perFloor = new Map<number, number>();
  for (const type of tower.flatTypes) {
    const range = flatTypeRange(type, top);
    if (!range) continue;
    for (let f = range[0]; f <= range[1]; f += 1) perFloor.set(f, (perFloor.get(f) ?? 0) + 1);
  }
  const counts = [...perFloor.values()];
  const summary: FlatsSummary = {
    floors: counts.length,
    perFloorMin: counts.length ? Math.min(...counts) : 0,
    perFloorMax: counts.length ? Math.max(...counts) : 0,
    flats: counts.reduce((sum, n) => sum + n, 0),
    shops: 0,
    godowns: 0,
  };
  for (const other of tower.others) {
    const range = otherRange(other, top);
    const per = toInt(other.perFloor);
    if (!range || per == null || per < 1) continue;
    const n = per * (range[1] - range[0] + 1);
    if (other.unitType === "shop") summary.shops += n;
    else summary.godowns += n;
  }
  return summary;
}

/** "Flats per floor: 4 (one of each type) · Flats in tower: 40 (10 floors × 4)" (a range when floors differ). */
export function flatsFooterText(tower: TowerForm): string {
  const s = flatsSummary(tower);
  const parts: string[] = [];
  if (s.flats === 0) {
    parts.push(tower.flatTypes.length ? "Enter the number of floors to see the flat count" : "No flats");
  } else if (s.perFloorMin === s.perFloorMax) {
    const each = tower.flatTypes.length > 1 && s.perFloorMax === tower.flatTypes.length ? " (one of each type)" : "";
    parts.push(`Flats per floor: ${s.perFloorMax}${each}`);
    parts.push(`Flats in tower: ${s.flats.toLocaleString("en-IN")} (${s.floors} floor${s.floors === 1 ? "" : "s"} × ${s.perFloorMax})`);
  } else {
    parts.push(`Flats per floor: ${s.perFloorMin}–${s.perFloorMax}`);
    parts.push(`Flats in tower: ${s.flats.toLocaleString("en-IN")}`);
  }
  if (s.shops) parts.push(`Shops: ${s.shops.toLocaleString("en-IN")}`);
  if (s.godowns) parts.push(`Godowns: ${s.godowns.toLocaleString("en-IN")}`);
  return parts.join(" · ");
}

/** Sizes usually run carpet ≤ built-up ≤ super built-up — a gentle warning (never blocks) when they don't. */
export function areaOrderWarning(sizes: { carpet: string; builtUp: string; superBuiltUp: string }): string | null {
  const carpet = positive(sizes.carpet);
  const builtUp = positive(sizes.builtUp);
  const superBuiltUp = positive(sizes.superBuiltUp);
  const broken =
    (carpet != null && builtUp != null && carpet > builtUp) ||
    (builtUp != null && superBuiltUp != null && builtUp > superBuiltUp) ||
    (carpet != null && superBuiltUp != null && carpet > superBuiltUp);
  return broken ? "Usually carpet ≤ built-up ≤ super built-up — check these sizes." : null;
}

export interface EstimatedAdds {
  flats: number;
  shops: number;
  godowns: number;
}

/**
 * Roughly what Save adds to a tower (the Preview step asks the server for the exact list — it also counts archived
 * units, which the browser never sees). Mirrors the server: on each floor, a type matches an existing flat of that
 * type first, then any flat without a type; shops / godowns match any of their kind on the floor.
 */
export function estimateAdds(tower: TowerForm): EstimatedAdds {
  const adds: EstimatedAdds = { flats: 0, shops: 0, godowns: 0 };
  if (!isEditableTower(tower)) return adds;
  const top = toInt(tower.floors);
  if (top == null || top < 1) return adds;
  const typed = new Map<string, number>();
  const untyped = new Map<number, number>();
  const others = new Map<string, number>();
  for (const u of tower.existingUnits) {
    if (u.unitType === "residential") {
      if (u.flatType) typed.set(`${u.floor}|${u.flatType}`, (typed.get(`${u.floor}|${u.flatType}`) ?? 0) + 1);
      else untyped.set(u.floor, (untyped.get(u.floor) ?? 0) + 1);
    } else {
      others.set(`${u.unitType}|${u.floor}`, (others.get(`${u.unitType}|${u.floor}`) ?? 0) + 1);
    }
  }
  const missing = new Map<number, number>();
  for (const type of tower.flatTypes) {
    const range = flatTypeRange(type, top);
    if (!range) continue;
    for (let f = range[0]; f <= range[1]; f += 1) {
      const key = `${f}|${type.code}`;
      if ((typed.get(key) ?? 0) > 0) typed.set(key, typed.get(key)! - 1);
      else missing.set(f, (missing.get(f) ?? 0) + 1);
    }
  }
  for (const [floor, need] of missing) {
    const reuse = Math.min(untyped.get(floor) ?? 0, need);
    untyped.set(floor, (untyped.get(floor) ?? 0) - reuse);
    adds.flats += need - reuse;
  }
  for (const other of tower.others) {
    const range = otherRange(other, top);
    const per = toInt(other.perFloor);
    if (!range || per == null || per < 1) continue;
    for (let f = range[0]; f <= range[1]; f += 1) {
      const key = `${other.unitType}|${f}`;
      const reuse = Math.min(others.get(key) ?? 0, per);
      others.set(key, (others.get(key) ?? 0) - reuse);
      if (other.unitType === "shop") adds.shops += per - reuse;
      else adds.godowns += per - reuse;
    }
  }
  return adds;
}

/** Flat types an existing tower has units of that the page no longer lists (their flats stay). */
export function removedTypesWithUnits(tower: TowerForm): { code: string; units: number }[] {
  const listed = new Set(tower.flatTypes.map((t) => t.code));
  const counts = new Map<string, number>();
  for (const u of tower.existingUnits) {
    if (u.unitType === "residential" && u.flatType && !listed.has(u.flatType)) {
      counts.set(u.flatType, (counts.get(u.flatType) ?? 0) + 1);
    }
  }
  return byPosition([...counts.entries()].map(([code, units]) => ({ code, units })));
}

/** The highest floor an existing tower has units on (0 when none). */
export function existingTopFloor(tower: TowerForm): number {
  return tower.existingUnits.reduce((top, u) => Math.max(top, u.floor), 0);
}

export function layoutOf(tower: TowerForm): TowerLayout {
  const top = toInt(tower.floors) ?? 1;
  return {
    unit_prefix: tower.prefix.trim(),
    flat_types: byPosition(tower.flatTypes).map((t) => ({
      code: t.code,
      configuration: t.configuration.trim() || null,
      carpet_area: positive(t.carpet),
      built_up_area: positive(t.builtUp),
      super_built_up_area: positive(t.superBuiltUp) ?? 0,
      has_plc: t.plc,
      // Unlimited types follow the tower's floors (null = 1 … top), so adding floors later extends them.
      floor_from: t.limitFloors ? toInt(t.floorFrom) ?? 1 : null,
      floor_to: t.limitFloors ? toInt(t.floorTo) ?? top : null,
    })),
    others: tower.others.map((o) => ({
      unit_type: o.unitType,
      per_floor: toInt(o.perFloor) ?? 1,
      floor_from: toInt(o.floorFrom) ?? 0,
      floor_to: toInt(o.floorTo) ?? 0,
      area: positive(o.area) ?? 0,
      carpet_area: positive(o.carpet),
      built_up_area: positive(o.builtUp),
      unit_prefix: o.prefix.trim() || null,
    })),
  };
}

// ---------------------------------------------------------------------------------------------------------------
// Step 3 — pricing
// ---------------------------------------------------------------------------------------------------------------

export interface PricingForm {
  basis: PricingBasis;
  rateFlats: string; // rate_a
  rateShops: string; // rate_b
  rateGodowns: string; // rate_c
  floorRise: string;
  floorRiseBasis: FloorRiseBasis;
  floorRiseFrom: string;
  plcRate: string;
  amenitiesRate: string;
  legal: string;
  other: string;
  sinking: string;
  overhead: string;
}

export const PRICING_BASIS_OPTIONS: { value: PricingBasis; label: string }[] = [
  { value: "super_built_up", label: "Super built-up" },
  { value: "built_up", label: "Built-up" },
  { value: "carpet", label: "Carpet" },
];

export const FLOOR_RISE_BASIS_OPTIONS: { value: FloorRiseBasis; label: string }[] = [
  { value: "per_sqft", label: "₹ per sq ft per floor" },
  { value: "per_floor", label: "₹ per floor" },
];

const BASIS_NOUN: Record<PricingBasis, string> = {
  super_built_up: "super built-up area",
  built_up: "built-up area",
  carpet: "carpet area",
};

export const DEFAULT_FLOOR_RISE_FROM = 2;

export interface PricingNumbers {
  basis: PricingBasis;
  rateFlats: number | null;
  rateShops: number | null;
  rateGodowns: number | null;
  floorRise: number | null;
  floorRiseBasis: FloorRiseBasis;
  floorRiseFrom: number;
  plcRate: number | null;
  amenitiesRate: number | null;
  legal: number | null;
  other: number | null;
  sinking: number | null;
  overhead: number | null;
}

export function pricingNumbers(form: PricingForm): PricingNumbers {
  return {
    basis: form.basis,
    rateFlats: toNum(form.rateFlats),
    rateShops: toNum(form.rateShops),
    rateGodowns: toNum(form.rateGodowns),
    floorRise: toNum(form.floorRise),
    floorRiseBasis: form.floorRiseBasis,
    floorRiseFrom: toInt(form.floorRiseFrom) ?? DEFAULT_FLOOR_RISE_FROM,
    plcRate: toNum(form.plcRate),
    amenitiesRate: toNum(form.amenitiesRate),
    legal: toNum(form.legal),
    other: toNum(form.other),
    sinking: toNum(form.sinking),
    overhead: toNum(form.overhead),
  };
}

/** The area a unit is priced on (null when that area isn't entered). */
export function basisArea(
  sizes: { superBuiltUp: string; builtUp: string; carpet: string },
  basis: PricingBasis
): number | null {
  if (basis === "carpet") return positive(sizes.carpet);
  if (basis === "built_up") return positive(sizes.builtUp);
  return positive(sizes.superBuiltUp);
}

/** Floor rise for a unit on `floor`: nothing below the "from" floor, then one step per floor from there. */
export function floorRiseAt(floor: number, area: number, p: PricingNumbers): number {
  if (!p.floorRise) return 0;
  const steps = Math.max(0, floor - p.floorRiseFrom + 1);
  return p.floorRiseBasis === "per_sqft" ? p.floorRise * area * steps : p.floorRise * steps;
}

/**
 * The list price before GST (what the booking calculator starts from): basic (area × rate) + floor rise + PLC
 * (only for a type ticked PLC) + amenities (per sq ft) + the fixed charges.
 */
export function listPrice(area: number, rate: number, floor: number, hasPlc: boolean, p: PricingNumbers): number {
  const perSqft = (rate + (hasPlc ? p.plcRate ?? 0 : 0) + (p.amenitiesRate ?? 0)) * area;
  const fixed = (p.legal ?? 0) + (p.other ?? 0) + (p.sinking ?? 0) + (p.overhead ?? 0);
  return Math.round(perSqft + floorRiseAt(floor, area, p) + fixed);
}

export interface PriceCheckRow {
  key: string;
  tower: string;
  label: string; // "Type A" / "Shops" / "Godowns"
  configuration: string;
  area: number | null; // the basis area
  basic: number | null;
  lowFloor: number;
  topFloor: number;
  lowPrice: number | null;
  topPrice: number | null;
  problem: string | null; // why a price can't be worked out yet
}

/** One row per tower × flat type (and shops / godowns): basic and the all-in list price on its lowest and top floor. */
export function priceCheckRows(towers: TowerForm[], form: PricingForm): PriceCheckRow[] {
  const p = pricingNumbers(form);
  const rows: PriceCheckRow[] = [];
  const row = (
    key: string,
    tower: string,
    label: string,
    configuration: string,
    sizes: { superBuiltUp: string; builtUp: string; carpet: string },
    rate: number | null,
    range: [number, number],
    hasPlc: boolean,
    rateName: string
  ) => {
    const area = basisArea(sizes, p.basis);
    const problem = area == null ? `No ${BASIS_NOUN[p.basis]}` : rate == null ? `Enter the ${rateName}` : null;
    const priced = area != null && rate != null;
    rows.push({
      key,
      tower,
      label,
      configuration,
      area,
      basic: priced ? Math.round(area * rate) : null,
      lowFloor: range[0],
      topFloor: range[1],
      lowPrice: priced ? listPrice(area, rate, range[0], hasPlc, p) : null,
      topPrice: priced ? listPrice(area, rate, range[1], hasPlc, p) : null,
      problem,
    });
  };
  for (const tower of towers.filter(isEditableTower)) {
    const top = toInt(tower.floors);
    if (top == null || top < 1) continue;
    for (const type of byPosition(tower.flatTypes)) {
      const range = flatTypeRange(type, top);
      if (!range) continue;
      row(`${tower.key}:${type.code}`, tower.name.trim(), `Type ${type.code}`, type.configuration.trim(), type, p.rateFlats, range, type.plc, "base rate for flats");
    }
    for (const other of tower.others) {
      const range = otherRange(other, top);
      if (!range) continue;
      const godown = other.unitType === "godown";
      row(
        `${tower.key}:${other.key}`,
        tower.name.trim(),
        godown ? "Godowns" : "Shops",
        "",
        { superBuiltUp: other.area, builtUp: other.builtUp, carpet: other.carpet },
        godown ? p.rateGodowns ?? p.rateShops : p.rateShops,
        range,
        false,
        godown ? "godown or shop rate" : "base rate for shops"
      );
    }
  }
  return rows;
}

// ---------------------------------------------------------------------------------------------------------------
// Step 4 — parking
// ---------------------------------------------------------------------------------------------------------------

export interface ParkingRowForm {
  on: boolean;
  count: string;
  price: string;
}
export type ParkingForm = Record<ParkingType, ParkingRowForm>;

export interface ExistingParking {
  byType: Record<ParkingType, number>;
  untyped: number; // older spots not numbered by type — kept as they are
}

export const NO_EXISTING_PARKING: ExistingParking = { byType: { MLP: 0, CP: 0, IP: 0, OP: 0, DP: 0 }, untyped: 0 };

export const WIZARD_PARKING_LABEL: Record<ParkingType, string> = {
  MLP: "Multi-level",
  CP: "Covered",
  IP: "Independent",
  OP: "Open",
  DP: "Dependent",
};

export function initialParkingForm(project: Project | null, existing: ExistingParking): ParkingForm {
  const offered = project?.garageOptions ?? [];
  const prices = project?.parkingPrices ?? {};
  const form = {} as ParkingForm;
  for (const type of WIZARD_PARKING_TYPES) {
    const built = existing.byType[type] ?? 0;
    const price = prices[type];
    form[type] = {
      on: built > 0 || (offered as ParkingType[]).includes(type) || price != null,
      count: built > 0 ? String(built) : "",
      price: price != null ? String(price) : "",
    };
  }
  // An older project that only declared a total for its one parking type (and has built no spots, typed or not):
  // start from that total. Older untyped spots count — the server only counts typed ones, so prefilling the total
  // on top of them would build a second set.
  const anyBuilt = existing.untyped > 0 || WIZARD_PARKING_TYPES.some((t) => (existing.byType[t] ?? 0) > 0);
  const on = WIZARD_PARKING_TYPES.filter((t) => form[t].on);
  const declared = project?.totalGarages ?? null;
  if (!anyBuilt && on.length === 1 && declared != null && declared > 0) form[on[0]].count = String(declared);
  return form;
}

/** Target spots per ticked type (blank = 0). Targets only add — the server never removes a spot. */
export function parkingCountsPayload(form: ParkingForm): ParkingCountsPayload {
  const out: ParkingCountsPayload = {};
  for (const type of WIZARD_PARKING_TYPES) {
    if (form[type].on) out[type] = Math.max(0, toInt(form[type].count) ?? 0);
  }
  return out;
}

export function parkingTotal(form: ParkingForm): number {
  return Object.values(parkingCountsPayload(form)).reduce<number>((sum, n) => sum + (n ?? 0), 0);
}

/** Price per spot for each ticked type that has one (null = none set — new spots fall back to the older price). */
export function parkingPricesPayload(form: ParkingForm): Partial<Record<ParkingType, number>> | null {
  const out: Partial<Record<ParkingType, number>> = {};
  for (const type of WIZARD_PARKING_TYPES) {
    const price = toNum(form[type].price);
    if (form[type].on && price != null && price >= 0) out[type] = price;
  }
  return Object.keys(out).length ? out : null;
}

/** The types written into garage_options: never DP (older builds reject it). */
export function garageOptionsPayload(form: ParkingForm): GarageOption[] | null {
  const out = GARAGE_OPTION_TYPES.filter((t) => form[t].on);
  return out.length ? out : null;
}

/** New spots per type Save would add. */
export function parkingAdds(form: ParkingForm, existing: ExistingParking): Partial<Record<ParkingType, number>> {
  const adds: Partial<Record<ParkingType, number>> = {};
  for (const [type, target] of Object.entries(parkingCountsPayload(form)) as [ParkingType, number][]) {
    const missing = target - (existing.byType[type] ?? 0);
    if (missing > 0) adds[type] = missing;
  }
  return adds;
}

// ---------------------------------------------------------------------------------------------------------------
// Step 5 — payment plan
// ---------------------------------------------------------------------------------------------------------------

export interface PlanRowForm {
  key: string;
  label: string;
  percent: string;
  dueOn: PlanDueOn;
  days: string;
  dueDate: string;
}

export const DUE_ON_OPTIONS: { value: PlanDueOn; label: string }[] = [
  { value: "on_booking", label: "On booking" },
  { value: "days_after_booking", label: "Within N days of booking" },
  { value: "on_stage", label: "When this stage is complete" },
  { value: "on_possession", label: "On possession" },
  { value: "on_registration", label: "On registration" },
  { value: "on_date", label: "On a date" },
];

/** A stable milestone key ("m" + random base36), unique within the plan — kept for the milestone forever. */
export function newMilestoneKey(taken: string[]): string {
  const used = new Set(taken);
  for (;;) {
    const key = `m${Math.random().toString(36).slice(2, 8)}`;
    if (key.length > 1 && !used.has(key)) return key;
  }
}

export function blankMilestone(taken: string[]): PlanRowForm {
  return { key: newMilestoneKey(taken), label: "", percent: "", dueOn: "on_booking", days: "", dueDate: "" };
}

const SAMPLE_PLAN: [string, number, PlanDueOn, number | null][] = [
  ["Booking", 10, "on_booking", null],
  ["Agreement", 20, "days_after_booking", 30],
  ["Foundation complete", 15, "on_stage", null],
  ["Structure complete", 20, "on_stage", null],
  ["Possession", 25, "on_possession", null],
  ["Registration", 10, "on_registration", null],
];

/** A common construction-linked plan the builder edits (names are theirs to change). */
export function samplePlan(): PlanRowForm[] {
  const rows: PlanRowForm[] = [];
  for (const [label, percent, dueOn, days] of SAMPLE_PLAN) {
    rows.push({ ...blankMilestone(rows.map((r) => r.key)), label, percent: String(percent), dueOn, days: str(days) });
  }
  return rows;
}

/** The plan's total %, to 2 decimals — the sum of each row as it is SENT (rounded to 2 decimals), so a plan of
 * 33.333 + 33.333 + 33.334 reads 99.99 here, as the server will see it. */
export function planTotal(rows: PlanRowForm[]): number {
  return rows.reduce((sum, r) => sum + Math.round((toNum(r.percent) ?? 0) * 100), 0) / 100;
}

/** The plan the wizard opens with: the project's plan, else its older dated schedule as "On a date" rows. */
export function planRowsFromProject(project: Project | null): { rows: PlanRowForm[]; legacy: boolean } {
  if (project?.paymentPlan?.length) {
    return {
      rows: project.paymentPlan.map((m) => ({
        key: m.key,
        label: m.label,
        percent: String(m.percent),
        dueOn: m.due_on,
        days: str(m.days),
        dueDate: m.due_date ?? "",
      })),
      legacy: false,
    };
  }
  const rows: PlanRowForm[] = [];
  for (const m of project?.demandSchedule ?? []) {
    rows.push({
      key: newMilestoneKey(rows.map((r) => r.key)),
      label: m.label,
      percent: String(m.percent),
      dueOn: "on_date",
      days: "",
      dueDate: m.due_date,
    });
  }
  return { rows, legacy: rows.length > 0 };
}

export function planPayload(rows: PlanRowForm[]): PlanMilestone[] {
  return rows.map((r) => ({
    key: r.key,
    label: r.label.trim(),
    percent: Math.round((toNum(r.percent) ?? 0) * 100) / 100,
    due_on: r.dueOn,
    days: r.dueOn === "days_after_booking" ? toInt(r.days) : null,
    due_date: r.dueOn === "on_date" ? r.dueDate || null : null,
  }));
}

/** "Within 30 days of booking" / "On 15 Jan 2027" / "When this stage is complete" … */
export function dueOnText(
  row: Pick<PlanRowForm, "dueOn" | "days" | "dueDate">,
  formatDate: (iso: string) => string = (iso) => iso
): string {
  if (row.dueOn === "days_after_booking") {
    const days = toInt(row.days);
    return days != null ? `Within ${days} day${days === 1 ? "" : "s"} of booking` : "Within N days of booking";
  }
  if (row.dueOn === "on_date") return row.dueDate ? `On ${formatDate(row.dueDate)}` : "On a date";
  return DUE_ON_OPTIONS.find((o) => o.value === row.dueOn)?.label ?? row.dueOn;
}

// ---------------------------------------------------------------------------------------------------------------
// The whole wizard
// ---------------------------------------------------------------------------------------------------------------

export interface WizardState {
  info: InfoForm;
  towers: TowerForm[];
  pricing: PricingForm;
  parking: ParkingForm;
  plan: PlanRowForm[];
  planLegacy: boolean; // opened from an older dated schedule
  planDirty: boolean; // changed in this session — only then is it sent on Edit
}

export function initialWizardState(project: Project | null, existingParking: ExistingParking): WizardState {
  const plan = planRowsFromProject(project);
  const towers = project
    ? project.towers.filter((t) => !isParkingBlockName(t.name)).map(towerFormFromTower)
    : [newTowerForm(undefined, [])];
  return {
    info: {
      name: project?.name ?? "",
      builder: project?.builderName ?? "",
      projectType: project?.projectType ?? "",
      location: project?.location ?? "",
      city: project?.city ?? "",
      pinCode: project?.pinCode ?? "",
      landmark: project?.landmark ?? "",
      rera: project?.reraNumber ?? "",
    },
    towers,
    pricing: {
      basis: project?.pricingBasis ?? "super_built_up",
      rateFlats: str(project?.rateA),
      rateShops: str(project?.rateB),
      rateGodowns: str(project?.rateC),
      floorRise: str(project?.floorRiseRate),
      floorRiseBasis: project?.floorRiseBasis ?? "per_sqft",
      floorRiseFrom: str(project?.floorRiseFrom ?? DEFAULT_FLOOR_RISE_FROM),
      plcRate: str(project?.plcRate),
      amenitiesRate: str(project?.amenitiesRate),
      legal: str(project?.legalFees),
      other: str(project?.otherCharges),
      sinking: str(project?.sinkingFund),
      overhead: str(project?.overheadCost),
    },
    parking: initialParkingForm(project, existingParking),
    plan: plan.rows,
    planLegacy: plan.legacy,
    planDirty: false,
  };
}

export function hasFlatTypes(towers: TowerForm[]): boolean {
  return towers.some((t) => isEditableTower(t) && t.flatTypes.length > 0);
}

export function hasOthers(towers: TowerForm[], kind: OtherUnitKind): boolean {
  return towers.some((t) => isEditableTower(t) && t.others.some((o) => o.unitType === kind));
}

/** Units Save creates on a new project (exact — nothing exists yet). */
export function newProjectUnitCount(state: WizardState): number {
  return state.towers.reduce((sum, t) => {
    const a = estimateAdds(t);
    return sum + a.flats + a.shops + a.godowns;
  }, 0);
}

// ---------------------------------------------------------------------------------------------------------------
// Validation, one step at a time. Field keys are stable so the step can show each message next to its input.
// ---------------------------------------------------------------------------------------------------------------

export interface StepCheck {
  fields: Record<string, string>;
  general: string[];
}

export function isStepOk(check: StepCheck): boolean {
  return Object.keys(check.fields).length === 0 && check.general.length === 0;
}

export const fieldKey = {
  tower: (t: string, field: "name" | "floors" | "prefix" | "units") => `t:${t}:${field}`,
  flatType: (t: string, code: string, field: "super" | "carpet" | "builtUp" | "floors" | "configuration") =>
    `t:${t}:ft:${code}:${field}`,
  other: (t: string, o: string, field: "perFloor" | "floors" | "area" | "carpet" | "builtUp") => `t:${t}:o:${o}:${field}`,
  parking: (type: ParkingType, field: "count" | "price") => `p:${type}:${field}`,
  milestone: (key: string, field: "label" | "percent" | "days" | "date") => `m:${key}:${field}`,
};

function checkOptionalArea(fields: Record<string, string>, key: string, value: string): void {
  if (value.trim() !== "" && positive(value) == null) fields[key] = "Enter a size above 0, or leave it blank.";
}

function checkMoney(fields: Record<string, string>, key: string, value: string): void {
  const n = toNum(value);
  if (value.trim() !== "" && (n == null || n < 0)) fields[key] = "Enter an amount of 0 or more.";
}

export function validateInfo(info: InfoForm): StepCheck {
  const fields: Record<string, string> = {};
  if (!info.name.trim()) fields.name = "Enter the project name.";
  if (!info.builder.trim()) fields.builder = "Enter the builder / developer.";
  if (!info.projectType) fields.projectType = "Pick the project type.";
  if (!info.location.trim()) fields.location = "Enter the location / area.";
  if (!info.city.trim()) fields.city = "Enter the city.";
  if (info.pinCode.trim() && !/^[0-9 ]{1,12}$/.test(info.pinCode.trim())) fields.pinCode = "Use digits only, e.g. 560066.";
  return { fields, general: [] };
}

export function validateTowers(towers: TowerForm[], editing: boolean): StepCheck {
  const fields: Record<string, string> = {};
  const general: string[] = [];
  const names = new Map<string, number>();
  for (const t of towers) {
    const n = t.name.trim().toLowerCase();
    if (n) names.set(n, (names.get(n) ?? 0) + 1);
  }
  // Prefixes: two towers sharing one would give their flats the same numbers. Existing towers that already share
  // one (older projects numbered every tower R101 …) are left as they are.
  const prefixes = new Map<string, TowerForm[]>();
  for (const t of towers) {
    const p = t.prefix.trim().toLowerCase();
    if (p) prefixes.set(p, [...(prefixes.get(p) ?? []), t]);
  }
  const unchangedPrefix = (t: TowerForm) => t.originalPrefix != null && t.prefix.trim() === t.originalPrefix.trim();

  for (const t of towers) {
    if (!isEditableTower(t)) continue;
    const name = t.name.trim();
    if (!name) fields[fieldKey.tower(t.key, "name")] = "Enter the tower name.";
    else if (isParkingBlockName(name)) fields[fieldKey.tower(t.key, "name")] = "“Parking” is kept for the project's parking — pick another name.";
    else if ((names.get(name.toLowerCase()) ?? 0) > 1) fields[fieldKey.tower(t.key, "name")] = "Another tower has this name.";

    const top = toInt(t.floors);
    const topOk = top != null && top >= 1 && top <= MAX_FLOORS;
    if (!topOk) fields[fieldKey.tower(t.key, "floors")] = `Enter the number of floors (1 to ${MAX_FLOORS}).`;

    const prefix = t.prefix.trim();
    if (!prefix) fields[fieldKey.tower(t.key, "prefix")] = "Enter a unit number prefix, e.g. A-.";
    else if (prefix.length > MAX_PREFIX_LENGTH) fields[fieldKey.tower(t.key, "prefix")] = `Use at most ${MAX_PREFIX_LENGTH} characters.`;
    else if (/\s/.test(prefix)) fields[fieldKey.tower(t.key, "prefix")] = "Leave out spaces, e.g. A-.";
    else if (prefix.length >= MAX_PREFIX_LENGTH && t.others.some((o) => !o.prefix.trim())) {
      // Shops / godowns are numbered with the tower's prefix + S / G (A-S001), which must fit 8 characters too.
      fields[fieldKey.tower(t.key, "prefix")] = `With shops / godowns, keep it to ${MAX_PREFIX_LENGTH - 1} characters (their numbers add an S or G).`;
    } else {
      const sharing = prefixes.get(prefix.toLowerCase()) ?? [];
      if (sharing.length > 1 && !sharing.every(unchangedPrefix)) {
        fields[fieldKey.tower(t.key, "prefix")] = "Another tower uses this prefix — its flats would get the same numbers.";
      }
    }

    if (t.flatTypes.length === 0 && t.others.length === 0) {
      fields[fieldKey.tower(t.key, "units")] = "Add at least one flat type (or shops / godowns).";
    }
    if (t.flatTypes.length > MAX_FLAT_TYPES) {
      fields[fieldKey.tower(t.key, "units")] = `A floor can hold at most ${MAX_FLAT_TYPES} flat types.`;
    }
    for (const type of t.flatTypes) {
      if (positive(type.superBuiltUp) == null) fields[fieldKey.flatType(t.key, type.code, "super")] = "Enter the super built-up area.";
      checkOptionalArea(fields, fieldKey.flatType(t.key, type.code, "carpet"), type.carpet);
      checkOptionalArea(fields, fieldKey.flatType(t.key, type.code, "builtUp"), type.builtUp);
      if (type.configuration.trim().length > 32) fields[fieldKey.flatType(t.key, type.code, "configuration")] = "Keep it under 32 characters.";
      if (type.limitFloors && topOk) {
        const from = toInt(type.floorFrom);
        const to = toInt(type.floorTo);
        const key = fieldKey.flatType(t.key, type.code, "floors");
        if (from == null || to == null || from < 0 || to < 0) fields[key] = "Enter whole floor numbers.";
        else if (from > to) fields[key] = "The first floor must not be above the last.";
        else if (to > top!) fields[key] = `The tower has ${top} floors.`;
      }
    }
    if (t.others.length > MAX_OTHER_ROWS) fields[fieldKey.tower(t.key, "units")] = `Use at most ${MAX_OTHER_ROWS} shop / godown rows.`;
    for (const o of t.others) {
      const per = toInt(o.perFloor);
      if (per == null || per < 1 || per > MAX_PER_FLOOR) fields[fieldKey.other(t.key, o.key, "perFloor")] = `1 to ${MAX_PER_FLOOR}.`;
      if (positive(o.area) == null) fields[fieldKey.other(t.key, o.key, "area")] = "Enter the super built-up area.";
      checkOptionalArea(fields, fieldKey.other(t.key, o.key, "carpet"), o.carpet);
      checkOptionalArea(fields, fieldKey.other(t.key, o.key, "builtUp"), o.builtUp);
      const from = toInt(o.floorFrom);
      const to = toInt(o.floorTo);
      const key = fieldKey.other(t.key, o.key, "floors");
      if (from == null || to == null || from < 0 || to < 0) fields[key] = "Enter whole floor numbers (0 = ground).";
      else if (from > to) fields[key] = "The first floor must not be above the last.";
      else if (topOk && to > top!) fields[key] = `The tower has ${top} floors.`;
    }
  }
  if (!editing) {
    const total = towers.reduce((sum, t) => {
      const a = estimateAdds(t);
      return sum + a.flats + a.shops + a.godowns;
    }, 0);
    if (total > MAX_NEW_UNITS_PER_SAVE) {
      general.push(
        `This would create ${total.toLocaleString("en-IN")} units — more than ${MAX_NEW_UNITS_PER_SAVE.toLocaleString("en-IN")} in one save. Check the floors and flat types.`
      );
    }
  }
  return { fields, general };
}

export function validatePricing(pricing: PricingForm, towers: TowerForm[]): StepCheck {
  const fields: Record<string, string> = {};
  const general: string[] = [];
  const p = pricingNumbers(pricing);
  const anyFlats = hasFlatTypes(towers);
  const anyShops = hasOthers(towers, "shop");
  const anyGodowns = hasOthers(towers, "godown");
  for (const key of ["rateFlats", "rateShops", "rateGodowns", "floorRise", "plcRate", "amenitiesRate", "legal", "other", "sinking", "overhead"] as const) {
    checkMoney(fields, key, pricing[key]);
  }
  if (anyFlats && !fields.rateFlats && !(p.rateFlats != null && p.rateFlats > 0)) {
    fields.rateFlats = "Enter the base rate for flats — flat prices are worked out from it.";
  }
  const shopRateNeeded = anyShops || (anyGodowns && !(p.rateGodowns != null && p.rateGodowns > 0));
  if (shopRateNeeded && !fields.rateShops && !(p.rateShops != null && p.rateShops > 0)) {
    fields.rateShops = anyShops
      ? "Enter the base rate for shops."
      : "Enter a godown rate, or a shop rate for godowns to use.";
  }
  if (pricing.floorRise.trim() !== "") {
    const from = toInt(pricing.floorRiseFrom);
    if (from == null || from < 1 || from > MAX_FLOORS) fields.floorRiseFrom = `A floor from 1 to ${MAX_FLOORS}.`;
  }
  // Every unit needs the area its price is worked out on.
  const missing: string[] = [];
  for (const t of towers.filter(isEditableTower)) {
    for (const type of byPosition(t.flatTypes)) {
      if (basisArea(type, pricing.basis) == null) missing.push(`${t.name.trim() || "A tower"} · Type ${type.code}`);
    }
    for (const o of t.others) {
      if (basisArea({ superBuiltUp: o.area, builtUp: o.builtUp, carpet: o.carpet }, pricing.basis) == null) {
        missing.push(`${t.name.trim() || "A tower"} · ${o.unitType === "godown" ? "Godowns" : "Shops"}`);
      }
    }
  }
  if (missing.length) {
    const list = missing.length > 3 ? `${missing.slice(0, 3).join(", ")} and ${missing.length - 3} more` : missing.join(", ");
    general.push(
      `Prices are worked out on the ${BASIS_NOUN[pricing.basis]}, but ${list} ${missing.length === 1 ? "has" : "have"} none. Enter it in Towers & flat types, or pick another pricing basis.`
    );
  }
  return { fields, general };
}

export function validateParking(parking: ParkingForm, existing: ExistingParking): StepCheck {
  const fields: Record<string, string> = {};
  for (const type of WIZARD_PARKING_TYPES) {
    const row = parking[type];
    if (!row.on) continue;
    const count = toInt(row.count);
    const built = existing.byType[type] ?? 0;
    if (row.count.trim() !== "" && (count == null || count < 0 || count > MAX_PARKING_PER_TYPE)) {
      fields[fieldKey.parking(type, "count")] = `A whole number from 0 to ${MAX_PARKING_PER_TYPE.toLocaleString("en-IN")}.`;
    } else if ((count ?? 0) < built) {
      fields[fieldKey.parking(type, "count")] = `${built} already exist — the number can't go below that.`;
    }
    checkMoney(fields, fieldKey.parking(type, "price"), row.price);
  }
  return { fields, general: [] };
}

/** A plan must add up to exactly 100 % (an empty plan is fine). An older schedule nobody touched is kept as it is. */
export function validatePlan(rows: PlanRowForm[], opts: { dirty: boolean; legacy: boolean }): StepCheck {
  const fields: Record<string, string> = {};
  const general: string[] = [];
  if (!opts.dirty && opts.legacy) return { fields, general };
  if (rows.length > MAX_PLAN_MILESTONES) general.push(`A payment plan can have at most ${MAX_PLAN_MILESTONES} milestones.`);
  for (const r of rows) {
    if (!r.label.trim()) fields[fieldKey.milestone(r.key, "label")] = "Name this milestone.";
    else if (r.label.trim().length > 120) fields[fieldKey.milestone(r.key, "label")] = "Keep the name under 120 characters.";
    const pct = toNum(r.percent);
    if (pct == null || pct <= 0 || pct > 100) fields[fieldKey.milestone(r.key, "percent")] = "Above 0, up to 100.";
    if (r.dueOn === "days_after_booking") {
      const days = toInt(r.days);
      if (days == null || days < 1 || days > 3650) fields[fieldKey.milestone(r.key, "days")] = "Days: 1 to 3650.";
    }
    if (r.dueOn === "on_date" && !/^\d{4}-\d{2}-\d{2}$/.test(r.dueDate)) fields[fieldKey.milestone(r.key, "date")] = "Pick the date.";
  }
  const total = planTotal(rows);
  if (rows.length > 0 && Math.round(total * 100) !== 10000) {
    general.push(`The milestones add up to ${total}% — they must add up to exactly 100%.`);
  }
  return { fields, general };
}

/** An older dated schedule that doesn't add up to 100%, kept untouched: say so (it isn't re-saved). */
export function legacyPlanWarning(rows: PlanRowForm[], opts: { dirty: boolean; legacy: boolean }): string | null {
  if (opts.dirty || !opts.legacy) return null;
  const total = planTotal(rows);
  return Math.abs(total - 100) > 0.01
    ? `This older schedule adds up to ${total}%. It's kept as it is — change it to save it as a payment plan (it must add up to 100%).`
    : null;
}

export function validateStep(step: number, state: WizardState, ctx: { editing: boolean; existingParking: ExistingParking }): StepCheck {
  switch (step) {
    case STEP_INFO:
      return validateInfo(state.info);
    case STEP_TOWERS:
      return validateTowers(state.towers, ctx.editing);
    case STEP_PRICING:
      return validatePricing(state.pricing, state.towers);
    case STEP_PARKING:
      return validateParking(state.parking, ctx.existingParking);
    case STEP_PLAN:
      return validatePlan(state.plan, { dirty: state.planDirty, legacy: state.planLegacy });
    default:
      return { fields: {}, general: [] };
  }
}

/** The first step (before `before`) that still has problems, or null. */
export function firstInvalidStep(
  state: WizardState,
  ctx: { editing: boolean; existingParking: ExistingParking },
  before: number = WIZARD_STEPS.length
): number | null {
  for (let step = 0; step < Math.min(before, WIZARD_STEPS.length); step += 1) {
    if (!isStepOk(validateStep(step, state, ctx))) return step;
  }
  return null;
}

// ---------------------------------------------------------------------------------------------------------------
// Requests
// ---------------------------------------------------------------------------------------------------------------

function textOrNull(value: string): string | null {
  return value.trim() || null;
}

/** The project's own fields, as the wizard manages them (never parking_cost / amenities_charges — not on the page). */
export function projectFields(state: WizardState, project: Project | null): ProjectUpdatePayload {
  const { info, pricing, towers } = state;
  const p = pricingNumbers(pricing);
  // Declared totals, worked out from the towers (older towers count with what they have).
  const floors = towers.map((t) => toInt(t.floors) ?? 0);
  const perFloor = towers.map((t) => (isEditableTower(t) ? flatsSummary(t).perFloorMax : legacySummary(t).perFloor));
  const total = parkingTotal(state.parking);
  return {
    name: info.name.trim(),
    builder_name: info.builder.trim(),
    location: info.location.trim(),
    city: info.city.trim(),
    rera_number: textOrNull(info.rera),
    pin_code: textOrNull(info.pinCode),
    landmark: textOrNull(info.landmark),
    project_type: info.projectType || null,
    total_towers: towers.length || null,
    total_floors: floors.length ? Math.max(...floors) || null : null,
    flats_per_floor: perFloor.length ? Math.max(...perFloor) || null : null,
    total_garages: total || (project?.totalGarages ?? null),
    garage_options: garageOptionsPayload(state.parking),
    pricing_basis: pricing.basis,
    rate_a: p.rateFlats,
    rate_b: p.rateShops,
    rate_c: p.rateGodowns,
    floor_rise_rate: p.floorRise,
    floor_rise_basis: p.floorRise != null ? p.floorRiseBasis : null,
    floor_rise_from: p.floorRise != null ? p.floorRiseFrom : null,
    plc_rate: p.plcRate,
    amenities_rate: p.amenitiesRate,
    legal_fees: p.legal,
    other_charges: p.other,
    sinking_fund: p.sinking,
    overhead_cost: p.overhead,
    parking_prices: parkingPricesPayload(state.parking),
  };
}

function towerPayload(t: TowerForm): ProjectTowerPayload {
  return {
    name: t.name.trim(),
    total_floors: Math.min(Math.max(toInt(t.floors) ?? 1, 1), MAX_FLOORS),
    layout: layoutOf(t),
  };
}

function towerSyncPayload(t: TowerForm): ProjectTowerSyncPayload {
  return { ...(t.towerId ? { tower_id: t.towerId } : {}), ...towerPayload(t) };
}

/** Create: one call — the project, its towers (as layouts), parking counts + prices, and the payment plan. */
export function buildCreatePayload(state: WizardState): ProjectFullPayload {
  const plan = state.plan.length ? planPayload(state.plan) : null;
  return {
    ...(projectFields(state, null) as ProjectFullPayload),
    towers: state.towers.filter(isEditableTower).map(towerPayload),
    parking: parkingCountsPayload(state.parking),
    ...(plan ? { payment_plan: plan } : {}),
  };
}

/**
 * Edit: the project's fields first (the server prices new units and spots from them), then the inventory —
 * towers with flat types only (an older tower nobody converted is left out, so it stays exactly as it is).
 * The payment plan is sent only when it was changed here.
 */
export function buildEditPayloads(state: WizardState, project: Project): { update: ProjectUpdatePayload; sync: ProjectInventoryPayload } {
  const update = projectFields(state, project);
  if (state.planDirty) {
    if (state.plan.length) {
      update.payment_plan = planPayload(state.plan);
    } else {
      update.payment_plan = null;
      // The older dated schedule was emptied here too.
      if (project.demandSchedule?.length) update.demand_schedule = null;
    }
  }
  return {
    update,
    sync: { towers: state.towers.filter(isEditableTower).map(towerSyncPayload), parking: parkingCountsPayload(state.parking) },
  };
}

/** The Preview step's request: exactly what Save sends (Edit: plus the page's unsaved pricing). */
export function buildPreviewRequest(
  state: WizardState,
  project: Project | null
): { kind: "create"; payload: ProjectFullPayload } | { kind: "edit"; payload: ProjectInventoryPreviewPayload } {
  if (!project) {
    // The plan isn't needed to plan the units (and is checked on its own step).
    const { payment_plan: _plan, ...payload } = buildCreatePayload(state);
    return { kind: "create", payload };
  }
  const { update, sync } = buildEditPayloads(state, project);
  return {
    kind: "edit",
    payload: {
      ...sync,
      pricing_basis: update.pricing_basis ?? null,
      rate_a: update.rate_a ?? null,
      rate_b: update.rate_b ?? null,
      rate_c: update.rate_c ?? null,
      parking_prices: update.parking_prices ?? null,
    },
  };
}
