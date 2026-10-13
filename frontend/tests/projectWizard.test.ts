// Unit tests for the Add / Edit Project wizard helpers (src/utils/projectWizard.ts): flat-type letters, prefixes,
// flats per floor, the price check, parking, the payment plan, older-tower conversion, the requests Save sends
// and each step's checks.
import assert from "node:assert/strict";
import { test } from "node:test";

import type { Project, Tower, Unit, UnitType } from "../src/types/realestate.ts";
import { PARKING_TYPES } from "../src/utils/projectInventory.ts";
import {
  NO_EXISTING_PARKING,
  STEP_INFO,
  STEP_PLAN,
  STEP_TOWERS,
  WIZARD_PARKING_TYPES,
  addFlatType,
  areaOrderWarning,
  blankFlatType,
  blankOtherUnit,
  buildCreatePayload,
  buildEditPayloads,
  buildPreviewRequest,
  codeForPosition,
  convertLegacyTower,
  coverFileError,
  dueOnText,
  estimateAdds,
  fieldKey,
  firstInvalidStep,
  flatsFooterText,
  flatsSummary,
  floorRiseAt,
  guessPrefix,
  initialParkingForm,
  initialWizardState,
  isStepOk,
  layoutOf,
  legacyPlanWarning,
  legacySummaryText,
  listPrice,
  newMilestoneKey,
  newTowerForm,
  nextFreeCode,
  nextTowerName,
  parkingAdds,
  planRowsFromProject,
  planTotal,
  positionOfCode,
  priceCheckRows,
  pricingNumbers,
  removedTypesWithUnits,
  renameTower,
  revertLegacyTower,
  samplePlan,
  towerFormFromTower,
  validateInfo,
  validateParking,
  validatePlan,
  validatePricing,
  validateTowers,
  type FlatTypeForm,
  type PricingForm,
  type TowerForm,
  type WizardState,
} from "../src/utils/projectWizard.ts";

// --- fixtures ---------------------------------------------------------------------------------------------------

let seq = 0;
function unit(unitNumber: string, floor: number, unitType: UnitType = "residential", extra: Partial<Unit> = {}): Unit {
  seq += 1;
  return {
    id: `u${seq}`,
    projectId: "p1",
    towerId: "t1",
    floor,
    unitNumber,
    unitType,
    area: 1200,
    carpetArea: null,
    builtUpArea: null,
    areaUnit: "sqft",
    facing: null,
    view: null,
    basePrice: 6_000_000,
    status: "available",
    flatType: null,
    configuration: null,
    hasPlc: false,
    updatedAt: "2026-10-13T00:00:00Z",
    ...extra,
  };
}

function legacyTower(id: string, name: string, floors: number, perFloor: number, prefix = "R"): Tower {
  const units: Unit[] = [];
  for (let f = 1; f <= floors; f += 1) {
    for (let n = 1; n <= perFloor; n += 1) units.push(unit(`${prefix}${f}${String(n).padStart(2, "0")}`, f));
  }
  return { id, projectId: "p1", name, totalFloors: floors, layout: null, units };
}

function project(extra: Partial<Project> = {}): Project {
  return {
    id: "p1",
    name: "Lakeside",
    builderName: "Prestige",
    location: "Whitefield",
    city: "Bengaluru",
    reraNumber: null,
    pinCode: null,
    landmark: null,
    totalTowers: null,
    totalFloors: null,
    flatsPerFloor: null,
    totalGarages: null,
    garageOptions: null,
    rateA: 5000,
    rateB: null,
    rateC: null,
    parkingCost: 250000,
    legalFees: null,
    overheadCost: null,
    otherCharges: null,
    sinkingFund: null,
    amenitiesCharges: 100000,
    demandSchedule: null,
    projectType: "residential",
    pricingBasis: null,
    floorRiseRate: null,
    floorRiseBasis: null,
    floorRiseFrom: null,
    plcRate: null,
    amenitiesRate: null,
    parkingPrices: null,
    paymentPlan: null,
    milestonesReached: null,
    towers: [],
    media: [],
    totalUnits: 0,
    availableUnits: 0,
    totalParking: 0,
    availableParking: 0,
    createdAt: "2026-10-01T00:00:00Z",
    updatedAt: "2026-10-01T00:00:00Z",
    ...extra,
  };
}

function type(code: string, superBuiltUp: string, extra: Partial<FlatTypeForm> = {}): FlatTypeForm {
  return { ...blankFlatType(code), superBuiltUp, ...extra };
}

function typedTower(name: string, floors: number, types: FlatTypeForm[]): TowerForm {
  const t = renameTower(newTowerForm(undefined, []), name);
  return { ...t, floors: String(floors), flatTypes: types };
}

const PRICING: PricingForm = {
  basis: "super_built_up",
  rateFlats: "5000",
  rateShops: "",
  rateGodowns: "",
  floorRise: "",
  floorRiseBasis: "per_sqft",
  floorRiseFrom: "2",
  plcRate: "",
  amenitiesRate: "",
  legal: "",
  other: "",
  sinking: "",
  overhead: "",
};

function validState(): WizardState {
  const state = initialWizardState(null, NO_EXISTING_PARKING);
  return {
    ...state,
    info: { ...state.info, name: "Lakeside", builder: "Prestige", projectType: "residential", location: "Whitefield", city: "Bengaluru" },
    towers: [typedTower("Tower A", 10, [type("A", "1250"), type("B", "1100"), type("C", "1100"), type("D", "1250")])],
    pricing: PRICING,
  };
}

const CTX = { editing: false, existingParking: NO_EXISTING_PARKING };

// --- letters, names, prefixes -----------------------------------------------------------------------------------

test("flat-type letters are positions: A=1 … Z=26, AA=27 (Excel style), up to 99", () => {
  assert.deepEqual([1, 2, 4, 26, 27, 28, 52, 53, 99].map(codeForPosition), ["A", "B", "D", "Z", "AA", "AB", "AZ", "BA", "CU"]);
  for (let p = 1; p <= 99; p += 1) assert.equal(positionOfCode(codeForPosition(p)), p);
  assert.equal(positionOfCode("a"), null);
  assert.equal(positionOfCode("ABC"), null);
});

test("a new flat type takes the lowest free letter — deleting B leaves C as it is", () => {
  assert.equal(nextFreeCode(["A", "C", "D"]), "B");
  assert.equal(nextFreeCode([]), "A");
  const tower = typedTower("Tower A", 10, [type("A", "1"), type("C", "1")]);
  assert.deepEqual(addFlatType(tower)!.flatTypes.map((t) => t.code), ["A", "B", "C"]);
  const full = typedTower("Tower A", 1, Array.from({ length: 99 }, (_, i) => type(codeForPosition(i + 1), "1")));
  assert.equal(addFlatType(full), null);
});

test("prefix guess from the tower name", () => {
  assert.equal(guessPrefix("A"), "A-");
  assert.equal(guessPrefix("t1"), "T1-");
  assert.equal(guessPrefix("Tower A"), "A-");
  assert.equal(guessPrefix("Block 12"), "12-");
  assert.equal(guessPrefix("Orchid Heights"), "OH-");
  assert.equal(guessPrefix("Prestige Sky Garden"), "PSG-");
  assert.equal(guessPrefix("Sky Garden Phase Two"), "TWO-"); // a short last word wins
  assert.equal(guessPrefix("  "), "");
  // Follows the name until the user types one.
  const t = renameTower(newTowerForm(undefined, []), "Wing C");
  assert.equal(t.prefix, "C-");
  assert.equal(renameTower({ ...t, prefix: "WC/", prefixTouched: true }, "Wing D").prefix, "WC/");
});

test("a new tower copies the previous tower's types with the next name", () => {
  assert.equal(nextTowerName([]), "Tower A");
  assert.equal(nextTowerName(["Tower A"]), "Tower B");
  assert.equal(nextTowerName(["Tower A", "tower b"]), "tower c");
  assert.equal(nextTowerName(["Tower Z"]), "Tower 2");
  assert.equal(nextTowerName(["Block 3"]), "Block 4");
  assert.equal(nextTowerName(["Orchid"]), "Tower 2");
  const a = typedTower("Tower A", 12, [type("A", "1250", { configuration: "2 BHK" }), type("B", "1600", { plc: true })]);
  const b = newTowerForm(a, ["Tower A"]);
  assert.equal(b.name, "Tower B");
  assert.equal(b.prefix, "B-");
  assert.equal(b.floors, "12");
  assert.deepEqual(b.flatTypes.map((t) => [t.code, t.configuration, t.superBuiltUp, t.plc]), [["A", "2 BHK", "1250", false], ["B", "", "1600", true]]);
  assert.notEqual(b.flatTypes[0], a.flatTypes[0]); // a copy — editing B never edits A
  assert.equal(b.towerId, null);
});

// --- flats per floor --------------------------------------------------------------------------------------------

test("flats per floor = number of types; total from the floor ranges", () => {
  const t = typedTower("Tower A", 10, [type("A", "1"), type("B", "1"), type("C", "1"), type("D", "1")]);
  assert.deepEqual(flatsSummary(t), { floors: 10, perFloorMin: 4, perFloorMax: 4, flats: 40, shops: 0, godowns: 0 });
  assert.equal(flatsFooterText(t), "Flats per floor: 4 (one of each type) · Flats in tower: 40 (10 floors × 4)");

  // A penthouse type on the top floor only.
  const ph = { ...t, flatTypes: [...t.flatTypes, type("E", "3000", { limitFloors: true, floorFrom: "10", floorTo: "10" })] };
  assert.equal(flatsSummary(ph).flats, 41);
  assert.equal(flatsFooterText(ph), "Flats per floor: 4–5 · Flats in tower: 41");

  // Ground-floor shops.
  const shops = { ...t, others: [{ ...blankOtherUnit("shop"), perFloor: "3", area: "400" }] };
  assert.equal(flatsFooterText(shops), "Flats per floor: 4 (one of each type) · Flats in tower: 40 (10 floors × 4) · Shops: 3");
  assert.equal(flatsFooterText(typedTower("Tower A", 1, [type("A", "1")])), "Flats per floor: 1 · Flats in tower: 1 (1 floor × 1)");
});

test("area order warning (never an error)", () => {
  assert.equal(areaOrderWarning({ carpet: "800", builtUp: "1000", superBuiltUp: "1250" }), null);
  assert.equal(areaOrderWarning({ carpet: "", builtUp: "", superBuiltUp: "1250" }), null);
  assert.match(areaOrderWarning({ carpet: "1100", builtUp: "1000", superBuiltUp: "1250" }) ?? "", /carpet ≤ built-up ≤ super built-up/);
  assert.match(areaOrderWarning({ carpet: "", builtUp: "1300", superBuiltUp: "1250" }) ?? "", /check these sizes/);
});

// --- pricing ----------------------------------------------------------------------------------------------------

test("price check: basic = basis area × rate, for each basis", () => {
  const t = typedTower("Tower A", 10, [type("A", "1250", { carpet: "850", builtUp: "1050" })]);
  const at = (basis: PricingForm["basis"]) => priceCheckRows([t], { ...PRICING, basis })[0];
  assert.equal(at("super_built_up").basic, 1250 * 5000);
  assert.equal(at("built_up").basic, 1050 * 5000);
  assert.equal(at("carpet").basic, 850 * 5000);
  // Missing basis area → no price, a plain reason.
  const noCarpet = priceCheckRows([typedTower("Tower A", 10, [type("A", "1250")])], { ...PRICING, basis: "carpet" })[0];
  assert.equal(noCarpet.basic, null);
  assert.equal(noCarpet.problem, "No carpet area");
  assert.equal(priceCheckRows([t], { ...PRICING, rateFlats: "" })[0].problem, "Enter the base rate for flats");
});

test("floor rise: per sq ft per floor or per floor, starting at the 'from' floor", () => {
  const perSqft = pricingNumbers({ ...PRICING, floorRise: "20", floorRiseBasis: "per_sqft", floorRiseFrom: "2" });
  assert.equal(floorRiseAt(1, 1000, perSqft), 0);
  assert.equal(floorRiseAt(2, 1000, perSqft), 20 * 1000);
  assert.equal(floorRiseAt(10, 1000, perSqft), 20 * 1000 * 9);
  const perFloor = pricingNumbers({ ...PRICING, floorRise: "50000", floorRiseBasis: "per_floor", floorRiseFrom: "5" });
  assert.equal(floorRiseAt(4, 1000, perFloor), 0);
  assert.equal(floorRiseAt(5, 1000, perFloor), 50000);
  assert.equal(floorRiseAt(10, 1000, perFloor), 50000 * 6);
  // Blank "from" = floor 2 (floor 1 pays nothing, as the booking calculator always did).
  assert.equal(pricingNumbers({ ...PRICING, floorRiseFrom: "" }).floorRiseFrom, 2);
});

test("list price: basic + floor rise + PLC (only when ticked) + amenities + fixed charges", () => {
  const form: PricingForm = {
    ...PRICING,
    floorRise: "20",
    plcRate: "100",
    amenitiesRate: "150",
    legal: "25000",
    other: "10000",
    sinking: "5000",
    overhead: "1000",
  };
  const p = pricingNumbers(form);
  const fixed = 25000 + 10000 + 5000 + 1000;
  assert.equal(listPrice(1000, 5000, 1, false, p), 1000 * 5000 + 1000 * 150 + fixed);
  assert.equal(listPrice(1000, 5000, 1, true, p), 1000 * 5000 + 1000 * 150 + 1000 * 100 + fixed);
  assert.equal(listPrice(1000, 5000, 3, true, p), 1000 * (5000 + 150 + 100) + 20 * 1000 * 2 + fixed);

  const t = typedTower("Tower A", 10, [type("A", "1000"), type("B", "1000", { plc: true })]);
  const [a, b] = priceCheckRows([t], form);
  assert.deepEqual([a.lowFloor, a.topFloor], [1, 10]);
  assert.equal(a.lowPrice, listPrice(1000, 5000, 1, false, p));
  assert.equal(a.topPrice, listPrice(1000, 5000, 10, false, p));
  assert.equal(b.lowPrice! - a.lowPrice!, 100 * 1000); // PLC only on the ticked type
});

test("shops use the shop rate; godowns their own rate, else the shop rate", () => {
  const t = {
    ...typedTower("Tower A", 5, []),
    others: [
      { ...blankOtherUnit("shop"), area: "400" },
      { ...blankOtherUnit("godown"), area: "1000" },
    ],
  };
  const rows = priceCheckRows([t], { ...PRICING, rateShops: "9000" });
  assert.deepEqual(rows.map((r) => [r.label, r.basic]), [["Shops", 3_600_000], ["Godowns", 9_000_000]]);
  const own = priceCheckRows([t], { ...PRICING, rateShops: "9000", rateGodowns: "3000" });
  assert.equal(own[1].basic, 3_000_000);
});

// --- parking ----------------------------------------------------------------------------------------------------

test("parking: same types as the inventory helpers; DP never goes into garage_options", () => {
  assert.deepEqual(WIZARD_PARKING_TYPES, PARKING_TYPES);
  const state = validState();
  state.parking.CP = { on: true, count: "80", price: "400000" };
  state.parking.DP = { on: true, count: "20", price: "350000" };
  state.parking.OP = { on: false, count: "50", price: "100000" }; // not ticked → not sent
  const payload = buildCreatePayload(state);
  assert.deepEqual(payload.garage_options, ["CP"]);
  assert.deepEqual(payload.parking, { CP: 80, DP: 20 });
  assert.deepEqual(payload.parking_prices, { CP: 400000, DP: 350000 });
  assert.equal(payload.total_garages, 100);
  assert.deepEqual(parkingAdds(state.parking, { byType: { MLP: 0, CP: 70, IP: 0, OP: 0, DP: 0 }, untyped: 0 }), { CP: 10, DP: 20 });
});

test("parking on Edit: existing spots tick their type; the count can't go below them", () => {
  const existing = { byType: { MLP: 0, CP: 12, IP: 0, OP: 0, DP: 0 }, untyped: 3 };
  const form = initialParkingForm(project({ garageOptions: ["OP"], parkingPrices: { DP: 300000 } }), existing);
  assert.deepEqual(
    WIZARD_PARKING_TYPES.filter((t) => form[t].on),
    ["CP", "OP", "DP"]
  );
  assert.equal(form.CP.count, "12");
  assert.equal(form.DP.price, "300000");
  const lowered = { ...form, CP: { ...form.CP, count: "10" } };
  assert.equal(validateParking(lowered, existing).fields[fieldKey.parking("CP", "count")], "12 already exist — the number can't go below that.");
  assert.ok(isStepOk(validateParking(form, existing)));
  // An older project with one type and only a declared total starts from that total.
  const declared = initialParkingForm(project({ garageOptions: ["CP"], totalGarages: 112 }), NO_EXISTING_PARKING);
  assert.equal(declared.CP.count, "112");
});

// --- payment plan -----------------------------------------------------------------------------------------------

test("payment plan: total must be exactly 100 %, empty is fine, rows are checked", () => {
  const sample = samplePlan();
  assert.deepEqual(sample.map((r) => [r.label, r.percent, r.dueOn, r.days]), [
    ["Booking", "10", "on_booking", ""],
    ["Agreement", "20", "days_after_booking", "30"],
    ["Foundation complete", "15", "on_stage", ""],
    ["Structure complete", "20", "on_stage", ""],
    ["Possession", "25", "on_possession", ""],
    ["Registration", "10", "on_registration", ""],
  ]);
  assert.equal(new Set(sample.map((r) => r.key)).size, 6);
  assert.equal(planTotal(sample), 100);
  const opts = { dirty: true, legacy: false };
  assert.ok(isStepOk(validatePlan(sample, opts)));
  assert.ok(isStepOk(validatePlan([], opts)));

  const short = sample.slice(0, 5);
  assert.deepEqual(validatePlan(short, opts).general, ["The milestones add up to 90% — they must add up to exactly 100%."]);
  const bad = [
    { ...sample[0], label: " " },
    { ...sample[1], days: "" },
    { ...sample[2], percent: "0" },
    { ...sample[3], dueOn: "on_date" as const, dueDate: "" },
  ];
  const fields = validatePlan(bad, opts).fields;
  assert.equal(fields[fieldKey.milestone(bad[0].key, "label")], "Name this milestone.");
  assert.equal(fields[fieldKey.milestone(bad[1].key, "days")], "Days: 1 to 3650.");
  assert.equal(fields[fieldKey.milestone(bad[2].key, "percent")], "Above 0, up to 100.");
  assert.equal(fields[fieldKey.milestone(bad[3].key, "date")], "Pick the date.");
  assert.equal(planTotal([{ ...sample[0], percent: "33.33" }, { ...sample[1], percent: "33.33" }, { ...sample[2], percent: "33.34" }]), 100);
});

test("milestone keys are stable and unique; older dated schedules open as 'On a date'", () => {
  const key = newMilestoneKey([]);
  assert.match(key, /^m[a-z0-9]+$/);
  assert.ok(key.length <= 40);
  const kept = planRowsFromProject(
    project({ paymentPlan: [{ key: "m1", label: "Booking", percent: 100, due_on: "on_booking", days: null, due_date: null }] })
  );
  assert.deepEqual([kept.legacy, kept.rows[0].key], [false, "m1"]);

  const legacy = planRowsFromProject(project({ demandSchedule: [{ label: "Plinth", percent: 30, due_date: "2027-01-15" }] }));
  assert.equal(legacy.legacy, true);
  assert.deepEqual([legacy.rows[0].dueOn, legacy.rows[0].dueDate, legacy.rows[0].percent], ["on_date", "2027-01-15", "30"]);
  // Untouched, an older 30 % schedule is kept as it is (a warning, not an error).
  assert.ok(isStepOk(validatePlan(legacy.rows, { dirty: false, legacy: true })));
  assert.match(legacyPlanWarning(legacy.rows, { dirty: false, legacy: true }) ?? "", /adds up to 30%/);
  assert.equal(isStepOk(validatePlan(legacy.rows, { dirty: true, legacy: true })), false);
  assert.equal(dueOnText({ dueOn: "days_after_booking", days: "30", dueDate: "" }), "Within 30 days of booking");
  assert.equal(dueOnText({ dueOn: "on_stage", days: "", dueDate: "" }), "When this stage is complete");
});

// --- older towers -----------------------------------------------------------------------------------------------

test("an older tower opens read-only and converts to N types with its most common sizes", () => {
  const tower = legacyTower("t1", "Tower A", 10, 4);
  tower.units[0] = { ...tower.units[0], area: 1500 }; // one odd flat doesn't change the most common size
  tower.units.push(unit("S001", 0, "shop", { area: 400 }), unit("S002", 0, "shop", { area: 400 }));
  const form = towerFormFromTower(tower);
  assert.equal(form.legacy, true);
  assert.equal(form.converted, false);
  assert.equal(form.prefix, "R");
  assert.equal(legacySummaryText(form), "Set up before flat types — 40 flats, 4 per floor, floors 1–10 · 2 shops. Its flats keep their details.");

  const converted = convertLegacyTower(form);
  assert.equal(converted.converted, true);
  assert.deepEqual(converted.flatTypes.map((t) => [t.code, t.superBuiltUp, t.limitFloors]), [
    ["A", "1200", false],
    ["B", "1200", false],
    ["C", "1200", false],
    ["D", "1200", false],
  ]);
  assert.deepEqual(converted.others.map((o) => [o.unitType, o.perFloor, o.floorFrom, o.floorTo, o.area, o.prefix]), [["shop", "2", "0", "0", "400", "S"]]);
  // Nothing new on the floors it already fills.
  assert.deepEqual(estimateAdds(converted), { flats: 0, shops: 0, godowns: 0 });
  assert.equal(revertLegacyTower(converted).converted, false);
});

test("an older tower whose flats don't reach the top keeps its floor range when converted", () => {
  const tower = { ...legacyTower("t1", "Tower B", 8, 2), totalFloors: 10 };
  const converted = convertLegacyTower(towerFormFromTower(tower));
  assert.deepEqual(converted.flatTypes.map((t) => [t.limitFloors, t.floorFrom, t.floorTo]), [[true, "1", "8"], [true, "1", "8"]]);
  assert.deepEqual(estimateAdds(converted), { flats: 0, shops: 0, godowns: 0 });
});

test("a tower with flat types opens from its layout; removed types and lowered floors keep their flats", () => {
  const units: Unit[] = [];
  for (let f = 1; f <= 3; f += 1) for (const [i, code] of ["A", "B", "C"].entries()) units.push(unit(`A-${f}0${i + 1}`, f, "residential", { flatType: code }));
  const tower: Tower = {
    id: "t9",
    projectId: "p1",
    name: "Tower A",
    totalFloors: 3,
    layout: {
      unit_prefix: "A-",
      flat_types: [
        { code: "C", configuration: null, carpet_area: null, built_up_area: null, super_built_up_area: 900, has_plc: false, floor_from: null, floor_to: null },
        { code: "A", configuration: "2 BHK", carpet_area: 850, built_up_area: null, super_built_up_area: 1250, has_plc: true, floor_from: null, floor_to: null },
        { code: "B", configuration: null, carpet_area: null, built_up_area: null, super_built_up_area: 1100, has_plc: false, floor_from: 1, floor_to: 2 },
      ],
      others: [],
    },
    units,
  };
  const form = towerFormFromTower(tower);
  assert.equal(form.legacy, false);
  assert.deepEqual(form.flatTypes.map((t) => [t.code, t.configuration, t.carpet, t.plc, t.limitFloors]), [
    ["A", "2 BHK", "850", true, false],
    ["B", "", "", false, true],
    ["C", "", "", false, false],
  ]);
  assert.deepEqual(estimateAdds(form), { flats: 0, shops: 0, godowns: 0 }); // B's floor-3 slot never existed
  const twoMore = { ...form, floors: "5" };
  assert.deepEqual(estimateAdds(twoMore), { flats: 4, shops: 0, godowns: 0 }); // A + C on floors 4–5
  const withoutC = { ...form, flatTypes: form.flatTypes.filter((t) => t.code !== "C") };
  assert.deepEqual(removedTypesWithUnits(withoutC), [{ code: "C", units: 3 }]);
});

// --- requests ---------------------------------------------------------------------------------------------------

test("create payload: one call with layouts, pricing, parking and the plan", () => {
  const state = validState();
  state.plan = samplePlan();
  state.towers[0].flatTypes[0] = { ...state.towers[0].flatTypes[0], configuration: " 2 BHK ", carpet: "850", plc: true };
  state.towers[0].flatTypes[3] = { ...state.towers[0].flatTypes[3], limitFloors: true, floorFrom: "10", floorTo: "10" };
  const payload = buildCreatePayload(state);
  assert.equal(payload.name, "Lakeside");
  assert.equal(payload.project_type, "residential");
  assert.equal(payload.towers.length, 1);
  const tower = payload.towers[0];
  assert.equal("tower_id" in tower, false);
  assert.deepEqual([tower.name, tower.total_floors, tower.layout!.unit_prefix], ["Tower A", 10, "A-"]);
  assert.deepEqual(tower.layout!.flat_types[0], {
    code: "A",
    configuration: "2 BHK",
    carpet_area: 850,
    built_up_area: null,
    super_built_up_area: 1250,
    has_plc: true,
    floor_from: null,
    floor_to: null,
  });
  assert.deepEqual([tower.layout!.flat_types[3].floor_from, tower.layout!.flat_types[3].floor_to], [10, 10]);
  assert.deepEqual([payload.total_towers, payload.total_floors, payload.flats_per_floor], [1, 10, 4]);
  assert.equal(payload.rate_a, 5000);
  assert.equal(payload.pricing_basis, "super_built_up");
  assert.equal(payload.floor_rise_rate, null);
  assert.equal(payload.floor_rise_basis, null);
  assert.equal(payload.payment_plan!.length, 6);
  assert.deepEqual(payload.payment_plan![1], { key: state.plan[1].key, label: "Agreement", percent: 20, due_on: "days_after_booking", days: 30, due_date: null });
  assert.equal("parking_cost" in payload, false);
  assert.equal("amenities_charges" in payload, false);
  // The preview sends the same towers, without the plan.
  const preview = buildPreviewRequest(state, null);
  assert.equal(preview.kind, "create");
  assert.deepEqual((preview.payload as typeof payload).towers, payload.towers);
  assert.equal("payment_plan" in preview.payload, false);
});

test("edit payloads: older towers aren't sent, existing typed towers carry their id, plan only when changed", () => {
  const legacy = legacyTower("t1", "Tower A", 10, 4);
  const p = project({ towers: [legacy], demandSchedule: [{ label: "Plinth", percent: 100, due_date: "2027-01-15" }] });
  const state = initialWizardState(p, NO_EXISTING_PARKING);
  state.info.projectType = "residential";
  state.towers = [...state.towers, newTowerForm(state.towers[0], state.towers.map((t) => t.name))];
  state.towers[1] = { ...state.towers[1], floors: "12", flatTypes: [type("A", "1250"), type("B", "1250")] };
  let { update, sync } = buildEditPayloads(state, p);
  assert.deepEqual(sync.towers.map((t) => [t.name, "tower_id" in t]), [["Tower B", false]]);
  assert.equal("payment_plan" in update, false); // the older schedule wasn't touched — left as it is
  assert.equal("demand_schedule" in update, false);
  assert.equal("parking_cost" in update, false);
  assert.equal(update.total_towers, 2);

  // Converting the older tower sends it (with its id); emptying the plan clears both plan columns.
  state.towers[0] = convertLegacyTower(state.towers[0]);
  ({ update, sync } = buildEditPayloads({ ...state, plan: [], planDirty: true }, p));
  assert.deepEqual(sync.towers.map((t) => [t.name, (t as { tower_id?: string }).tower_id ?? null]), [["Tower A", "t1"], ["Tower B", null]]);
  assert.equal(update.payment_plan, null);
  assert.equal(update.demand_schedule, null);
  ({ update } = buildEditPayloads({ ...state, plan: samplePlan(), planDirty: true }, p));
  assert.equal(update.payment_plan!.length, 6);
  assert.equal("demand_schedule" in update, false); // the server clears it when a plan is written

  const preview = buildPreviewRequest(state, p);
  assert.equal(preview.kind, "edit");
  assert.equal(preview.payload.rate_a, 5000);
  assert.equal(preview.payload.towers.length, 2);
});

// --- step checks ------------------------------------------------------------------------------------------------

test("step 1 checks the required fields", () => {
  const empty = initialWizardState(null, NO_EXISTING_PARKING).info;
  assert.deepEqual(Object.keys(validateInfo(empty).fields).sort(), ["builder", "city", "location", "name", "projectType"]);
  assert.equal(validateInfo({ ...validState().info, pinCode: "56O066" }).fields.pinCode, "Use digits only, e.g. 560066.");
  assert.equal(coverFileError({ type: "image/gif", size: 10 }), "Pick a JPG or PNG image.");
  assert.match(coverFileError({ type: "image/png", size: 6 * 1024 * 1024 }) ?? "", /larger than 5 MB/);
  assert.equal(coverFileError({ type: "image/jpeg", size: 1024 }), null);
});

test("step 2 checks names, floors, prefixes, sizes and floor ranges", () => {
  const a = typedTower("Tower A", 10, [type("A", ""), type("B", "1100", { limitFloors: true, floorFrom: "8", floorTo: "12" })]);
  const b = { ...typedTower("tower a", 0, []), prefix: "A-" };
  const check = validateTowers([a, b], false);
  assert.equal(check.fields[fieldKey.tower(a.key, "name")], "Another tower has this name.");
  assert.equal(check.fields[fieldKey.tower(b.key, "floors")], "Enter the number of floors (1 to 200).");
  assert.equal(check.fields[fieldKey.tower(b.key, "prefix")], "Another tower uses this prefix — its flats would get the same numbers.");
  assert.equal(check.fields[fieldKey.tower(b.key, "units")], "Add at least one flat type (or shops / godowns).");
  assert.equal(check.fields[fieldKey.flatType(a.key, "A", "super")], "Enter the super built-up area.");
  assert.equal(check.fields[fieldKey.flatType(a.key, "B", "floors")], "The tower has 10 floors.");
  assert.equal(validateTowers([{ ...a, name: "Parking" }], false).fields[fieldKey.tower(a.key, "name")], "“Parking” is kept for the project's parking — pick another name.");

  // Older towers that already share a prefix (every tower numbered R101 …) aren't blocked.
  const t1 = convertLegacyTower(towerFormFromTower(legacyTower("t1", "Tower 1", 2, 2)));
  const t2 = convertLegacyTower(towerFormFromTower(legacyTower("t2", "Tower 2", 2, 2)));
  assert.ok(isStepOk(validateTowers([t1, t2], true)));
  assert.ok(validateTowers([t1, { ...t2, prefix: "r" }], true).fields[fieldKey.tower(t2.key, "prefix")]);

  // Shops are numbered with the prefix + S, which must still fit 8 characters.
  const longPrefix = { ...a, name: "Tower Z", prefix: "TOWERZ1-", others: [{ ...blankOtherUnit("shop"), area: "400" }] };
  assert.match(validateTowers([longPrefix], false).fields[fieldKey.tower(a.key, "prefix")] ?? "", /keep it to 7 characters/);

  // More than 5,000 new units in one create.
  const huge = typedTower("Tower A", 200, Array.from({ length: 30 }, (_, i) => type(codeForPosition(i + 1), "1000")));
  assert.match(validateTowers([huge], false).general[0], /6,000 units — more than 5,000 in one save/);
});

test("step 3 needs the rates in use and the basis area of every type", () => {
  const towers = [typedTower("Tower A", 10, [type("A", "1250")])];
  assert.equal(validatePricing({ ...PRICING, rateFlats: "" }, towers).fields.rateFlats, "Enter the base rate for flats — flat prices are worked out from it.");
  assert.ok(isStepOk(validatePricing(PRICING, towers)));
  assert.match(validatePricing({ ...PRICING, basis: "carpet" }, towers).general[0], /carpet area, but Tower A · Type A has none/);
  const withGodowns = [{ ...towers[0], others: [{ ...blankOtherUnit("godown"), area: "900" }] }];
  assert.equal(validatePricing(PRICING, withGodowns).fields.rateShops, "Enter a godown rate, or a shop rate for godowns to use.");
  assert.ok(isStepOk(validatePricing({ ...PRICING, rateGodowns: "2000" }, withGodowns)));
  assert.equal(validatePricing({ ...PRICING, floorRise: "-5" }, towers).fields.floorRise, "Enter an amount of 0 or more.");
});

test("the stepper's forward jump stops at the first step with problems", () => {
  const state = validState();
  assert.equal(firstInvalidStep(state, CTX), null);
  assert.equal(firstInvalidStep({ ...state, info: { ...state.info, city: "" } }, CTX), STEP_INFO);
  const noRate = { ...state, pricing: { ...state.pricing, rateFlats: "" } };
  assert.equal(firstInvalidStep(noRate, CTX), 2);
  assert.equal(firstInvalidStep(noRate, CTX, 2), null); // steps before Pricing are fine
  const badPlan = { ...state, plan: samplePlan().slice(0, 2) };
  assert.equal(firstInvalidStep(badPlan, CTX), STEP_PLAN);
  assert.equal(firstInvalidStep({ ...state, towers: [] }, CTX), null); // a project can start without towers
  assert.equal(STEP_TOWERS, 1);
  assert.deepEqual(layoutOf(state.towers[0]).flat_types.map((t) => t.code), ["A", "B", "C", "D"]);
});
