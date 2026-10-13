// Unit tests for the inventory helpers (src/utils/projectInventory.ts): inventory counts, parking per type (incl.
// Dependent Parking) and the toast wording. The project wizard's helpers are tested in projectWizard.test.ts.
import assert from "node:assert/strict";
import { test } from "node:test";

import type { Tower, Unit, UnitStatus, UnitType } from "../src/types/realestate.ts";
import {
  PARKING_TYPES,
  PARKING_TYPE_LABEL,
  describeCreated,
  groupParkingByType,
  inventoryCounts,
  isParkingBlock,
  parkingCountsByType,
  parkingTypeOf,
} from "../src/utils/projectInventory.ts";

let seq = 0;
function unit(unitNumber: string, floor: number, unitType: UnitType = "residential", status: UnitStatus = "available"): Unit {
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
    status,
    flatType: null,
    configuration: null,
    hasPlc: false,
    updatedAt: "2026-09-30T00:00:00Z",
  };
}

function tower(id: string, name: string, totalFloors: number, units: Unit[]): Tower {
  return { id, projectId: "p1", name, totalFloors, layout: null, units };
}

test("parking types: DP is added last, so the older types keep their order", () => {
  assert.deepEqual(PARKING_TYPES, ["MLP", "CP", "IP", "OP", "DP"]);
  assert.equal(PARKING_TYPE_LABEL.DP, "Dependent Parking");
  assert.equal(parkingTypeOf("cp07"), "CP");
  assert.equal(parkingTypeOf("MLP12"), "MLP");
  assert.equal(parkingTypeOf("DP03"), "DP");
  assert.equal(parkingTypeOf("P101"), null);
  assert.ok(isParkingBlock(" parking "));
});

test("inventory counts keep units and parking apart; parking rows group by type", () => {
  const towers = [
    tower("t1", "Tower A", 1, [unit("R101", 1), unit("R102", 1, "residential", "booked"), unit("S001", 0, "shop")]),
    tower("pk", "Parking", 1, [
      unit("CP02", 0, "parking"),
      unit("CP10", 0, "parking", "sold"),
      unit("OP01", 0, "parking"),
      unit("DP01", 0, "parking"),
      unit("P1", 0, "parking"),
    ]),
  ];
  assert.deepEqual(inventoryCounts(towers), { units: 3, unitsAvailable: 2, parking: 5, parkingAvailable: 4 });
  assert.deepEqual(parkingCountsByType(towers), { byType: { MLP: 0, CP: 2, IP: 0, OP: 1, DP: 1 }, untyped: 1 });
  assert.deepEqual(
    groupParkingByType(towers[1].units).map((g) => [g.label, g.units.map((u) => u.unitNumber)]),
    [["CP", ["CP02", "CP10"]], ["OP", ["OP01"]], ["DP", ["DP01"]], ["Other", ["P1"]]]
  );
});

test("describeCreated reads naturally", () => {
  assert.equal(describeCreated({ towers: 2, units: 288, parking: 112 }), "2 towers, 288 units and 112 parking spots added.");
  assert.equal(describeCreated({ towers: 0, units: 1, parking: 0 }), "1 unit added.");
  assert.equal(describeCreated({ towers: 0, units: 0, parking: 0 }), "No new towers or units were needed.");
});
