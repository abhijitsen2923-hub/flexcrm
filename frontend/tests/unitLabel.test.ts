// Unit tests for the unit naming helpers (src/utils/unitLabel.ts): flat-type labels, picker labels, the unit search
// and the board's ordering / configuration chips. Units made before flat types must read exactly as before.
// Run: npm test
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  areaLabel,
  compareUnitNumbers,
  configurationOptions,
  flatTypeLabel,
  hasConfiguration,
  matchesUnitSearch,
  unitKindLabel,
  unitOptionLabel,
  unitOptionParts,
  unitSearchText,
  type PickerUnit,
} from "../src/utils/unitLabel.ts";

function pickerUnit(overrides: Partial<PickerUnit> = {}): PickerUnit {
  return {
    unitNumber: "A-101",
    floor: 1,
    unitType: "residential",
    flatType: "A",
    configuration: "2 BHK",
    area: 1250,
    areaUnit: "sqft",
    towerName: "Tower A",
    projectName: "Green Meadows",
    ...overrides,
  };
}

test("flatTypeLabel: type and configuration, either alone, or nothing for an older unit", () => {
  assert.equal(flatTypeLabel({ flatType: "A", configuration: "2 BHK" }), "Type A · 2 BHK");
  assert.equal(flatTypeLabel({ flatType: "A", configuration: null }), "Type A");
  assert.equal(flatTypeLabel({ flatType: null, configuration: "2 BHK" }), "2 BHK");
  assert.equal(flatTypeLabel({ flatType: null, configuration: null }), "");
  assert.equal(flatTypeLabel({}), "");
  assert.equal(flatTypeLabel({ flatType: "  ", configuration: " " }), "");
  assert.equal(flatTypeLabel({ flatType: " B ", configuration: " 3 BHK " }), "Type B · 3 BHK");
});

test("unitKindLabel falls back to the category when there is no flat type", () => {
  assert.equal(unitKindLabel({ flatType: "C", configuration: "3 BHK", unitType: "residential" }), "Type C · 3 BHK");
  assert.equal(unitKindLabel({ unitType: "residential" }), "Residential");
  assert.equal(unitKindLabel({ unitType: "shop" }), "Shop");
  assert.equal(unitKindLabel({ unitType: "godown" }), "Godown");
  assert.equal(unitKindLabel({ unitType: "parking" }), "Parking");
  assert.equal(unitKindLabel({}), "");
});

test("areaLabel: Indian digit grouping, sq m when the unit says so, nothing for a spot with no area", () => {
  assert.equal(areaLabel({ area: 1250, areaUnit: "sqft" }), "1,250 sq ft");
  assert.equal(areaLabel({ area: 125000, areaUnit: "sqft" }), "1,25,000 sq ft");
  assert.equal(areaLabel({ area: 99.5, areaUnit: "sqmt" }), "99.5 sq m");
  assert.equal(areaLabel({ area: 850 }), "850 sq ft");
  assert.equal(areaLabel({ area: 0, areaUnit: "sqft" }), "");
  assert.equal(areaLabel({ area: null }), "");
});

test("unitOptionLabel: number · type · area · tower · project", () => {
  assert.equal(unitOptionLabel(pickerUnit()), "A-101 · Type A · 2 BHK · 1,250 sq ft · Tower A · Green Meadows");
  // A flat set up before flat types: no kind (as before), just its area and where it is.
  assert.equal(
    unitOptionLabel(pickerUnit({ flatType: null, configuration: null, unitNumber: "R101" })),
    "R101 · 1,250 sq ft · Tower A · Green Meadows"
  );
  // Shops / godowns / parking spots name their category; a spot has no area.
  assert.equal(
    unitOptionLabel(pickerUnit({ unitNumber: "A-S001", unitType: "shop", flatType: null, configuration: null, area: 300 })),
    "A-S001 · Shop · 300 sq ft · Tower A · Green Meadows"
  );
  assert.equal(
    unitOptionLabel(pickerUnit({ unitNumber: "CP01", unitType: "parking", flatType: null, configuration: null, area: 0, towerName: "Parking" })),
    "CP01 · Parking · Parking · Green Meadows"
  );
  assert.deepEqual(unitOptionParts(pickerUnit()), ["Type A · 2 BHK", "1,250 sq ft", "Tower A", "Green Meadows"]);
});

test("unit search finds units by configuration, type, number, tower, project and floor", () => {
  const unit = pickerUnit({ floor: 3, unitNumber: "A-302", flatType: "B" });
  assert.match(unitSearchText(unit), /type b/);
  assert.match(unitSearchText(unit), /2 bhk/);
  for (const query of ["2 BHK", "2bhk", "2 bhk", "type b", "A-302", "a302", "tower a", "green", "floor 3", "", "   "]) {
    assert.equal(matchesUnitSearch(unit, query), true, `"${query}" should match`);
  }
  for (const query of ["3 BHK", "type c", "A-101", "floor 4", "Shop"]) {
    assert.equal(matchesUnitSearch(unit, query), false, `"${query}" should not match`);
  }
});

test("unit search on an older unit keeps the old fields and adds the category", () => {
  const unit = pickerUnit({ flatType: null, configuration: null, unitNumber: "R101", floor: 1 });
  assert.equal(unitSearchText(unit), "r101 green meadows tower a floor 1 residential");
  assert.equal(matchesUnitSearch(unit, "R101"), true);
  assert.equal(matchesUnitSearch(unit, "green meadows tower a"), true);
  assert.equal(matchesUnitSearch(unit, "2 BHK"), false);
});

test("a squashed query is matched field by field, not across fields", () => {
  // "Type A" + "2 BHK" squashed together would read "typea2bhk" — "a2" must not match that.
  assert.equal(matchesUnitSearch(pickerUnit({ unitNumber: "B-101" }), "a2"), false);
});

test("compareUnitNumbers sorts naturally: A-101 … A-104, A-110, then A-201", () => {
  const sorted = ["A-110", "A-104", "A-201", "A-101", "A-103", "A-102"].sort(compareUnitNumbers);
  assert.deepEqual(sorted, ["A-101", "A-102", "A-103", "A-104", "A-110", "A-201"]);
  assert.equal(compareUnitNumbers("a-101", "A-101"), 0);
});

test("configurationOptions: distinct, Studio first, by size, names without a number last", () => {
  const options = configurationOptions([
    { configuration: "3 BHK" },
    { configuration: "Penthouse" },
    { configuration: "2 BHK" },
    { configuration: "2 bhk" },
    { configuration: "1.5 BHK" },
    { configuration: "Studio" },
    { configuration: "10 BHK" },
    { configuration: "Duplex" },
    { configuration: null },
    { configuration: "  " },
    {},
  ]);
  assert.deepEqual(options, ["Studio", "1.5 BHK", "2 BHK", "3 BHK", "10 BHK", "Duplex", "Penthouse"]);
  assert.deepEqual(configurationOptions([{ configuration: null }, {}]), []);
});

test("hasConfiguration ignores case and spaces at the ends; older units never match", () => {
  assert.equal(hasConfiguration({ configuration: "2 BHK" }, "2 bhk"), true);
  assert.equal(hasConfiguration({ configuration: " 2 BHK " }, "2 BHK"), true);
  assert.equal(hasConfiguration({ configuration: "3 BHK" }, "2 BHK"), false);
  assert.equal(hasConfiguration({ configuration: null }, "2 BHK"), false);
});
