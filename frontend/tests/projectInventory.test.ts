// Unit tests for the one-page project form helpers (src/utils/projectInventory.ts): tower cards from the Project
// details, what Save will add (mirrors the backend rules), parking per type, validation and the inventory counts.
import assert from "node:assert/strict";
import { test } from "node:test";

import type { Tower, Unit, UnitStatus, UnitType } from "../src/types/realestate.ts";
import {
  EMPTY_PARKING_COUNTS,
  applyRates,
  cardFromTower,
  cardPayload,
  describeCreated,
  groupParkingByType,
  initialCards,
  initialParkingCounts,
  inventoryCounts,
  isParkingBlock,
  newTowerCard,
  parkingCountsByType,
  parkingPayload,
  parkingTotal,
  parkingTypeOf,
  plannedAdds,
  plannedParkingAdds,
  setCardFloors,
  specFloors,
  syncCardsWithDetails,
  totalOf,
  updateCardSpec,
  validateLayout,
  type ProjectRates,
} from "../src/utils/projectInventory.ts";

const NO_RATES: ProjectRates = { rateA: null, rateB: null, rateC: null };
const RATES: ProjectRates = { rateA: 5000, rateB: 9000, rateC: null };

let seq = 0;
function unit(unitNumber: string, floor: number, unitType: UnitType = "residential", status: UnitStatus = "available", extra: Partial<Unit> = {}): Unit {
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
    updatedAt: "2026-09-30T00:00:00Z",
    ...extra,
  } as Unit;
}

function tower(id: string, name: string, totalFloors: number, units: Unit[]): Tower {
  return { id, projectId: "p1", name, totalFloors, units } as Tower;
}

function flatsTower(id: string, name: string, floors: number, perFloor: number): Tower {
  const units: Unit[] = [];
  for (let f = 1; f <= floors; f += 1) {
    for (let n = 1; n <= perFloor; n += 1) units.push(unit(`R${f}${String(n).padStart(2, "0")}`, f));
  }
  return tower(id, name, floors, units);
}

test("details drive the tower cards: count, floors, flats per floor", () => {
  const details = { towers: 2, floors: 12, flatsPerFloor: 12 };
  const cards = syncCardsWithDetails([], details, NO_RATES);
  assert.deepEqual(cards.map((c) => [c.name, c.total_floors, c.towerId]), [["Tower 1", "12", null], ["Tower 2", "12", null]]);
  assert.deepEqual(specFloors(cards[0].unitSpecs[0]).length, 12);
  assert.equal(cards[0].unitSpecs[0].units_per_floor, "12");
  assert.equal(totalOf(plannedAdds(cards[0], [])), 144);

  // Fewer towers drops trailing new cards nobody touched; floors follow the details.
  const fewer = syncCardsWithDetails(cards, { towers: 1, floors: 15, flatsPerFloor: 8 }, NO_RATES);
  assert.equal(fewer.length, 1);
  assert.equal(fewer[0].total_floors, "15");
  assert.equal(fewer[0].unitSpecs[0].floor_to, "15");
  assert.equal(fewer[0].unitSpecs[0].units_per_floor, "8");
});

test("a card the user edited stops following the details and is never auto-removed", () => {
  const [card] = syncCardsWithDetails([], { towers: 1, floors: 10, flatsPerFloor: 4 }, NO_RATES);
  const edited = updateCardSpec(card, 0, { units_per_floor: "6" }, NO_RATES);
  const after = syncCardsWithDetails([edited], { towers: 0, floors: 20, flatsPerFloor: 2 }, NO_RATES);
  assert.equal(after.length, 1);
  assert.equal(after[0].total_floors, "10");
  assert.equal(after[0].unitSpecs[0].units_per_floor, "6");
});

test("existing towers are laid out from their units, so an unchanged Save adds nothing", () => {
  const t1 = flatsTower("t1", "Tower A", 3, 4);
  t1.units.push(unit("S001", 0, "shop"), unit("S002", 0, "shop"), unit("P101", 1, "parking"));
  const card = cardFromTower(t1, { towers: null, floors: null, flatsPerFloor: null }, NO_RATES);
  assert.equal(card.towerId, "t1");
  assert.deepEqual(
    card.unitSpecs.map((s) => [s.unit_type, s.units_per_floor, s.floor_from, s.floor_to, s.area, s.base_price]),
    [["residential", "4", "1", "3", "1200", "6000000"], ["shop", "2", "0", "0", "1200", "6000000"]]
  );
  assert.deepEqual(plannedAdds(card, t1.units), {});
  assert.deepEqual(cardPayload(card).tower_id, "t1");

  // One more floor: only that floor's flats are added.
  const taller = setCardFloors(card, "4");
  assert.equal(taller.unitSpecs[0].floor_to, "4");
  assert.equal(taller.unitSpecs[1].floor_to, "0"); // ground-floor shops stay put
  assert.deepEqual(plannedAdds(taller, t1.units), { residential: 4 });
});

test("the old-style project (details, no towers) opens with cards from its details", () => {
  const cards = initialCards([], { towers: 2, floors: 12, flatsPerFloor: 12 }, RATES);
  assert.equal(cards.length, 2);
  // Size still to be entered per tower — Save is blocked until it is.
  assert.match(validateLayout(cards, 288) ?? "", /Tower 1: enter the size/);
  const sized = cards.map((c) => updateCardSpec(c, 0, { area: "1100" }, RATES));
  assert.equal(sized[0].unitSpecs[0].base_price, String(1100 * 5000)); // size × Rate A
  assert.equal(validateLayout(sized, 288), null);
});

test("the parking block is not a tower card", () => {
  const cards = initialCards(
    [flatsTower("t1", "Tower A", 1, 2), tower("pk", "Parking", 1, [unit("CP01", 0, "parking")])],
    { towers: null, floors: null, flatsPerFloor: null },
    NO_RATES
  );
  assert.deepEqual(cards.map((c) => c.name), ["Tower A"]);
  assert.ok(isParkingBlock(" parking "));
});

test("floors typed by hand: a spec running to the top follows the tower even after the box was cleared", () => {
  const card = newTowerCard(0, { towers: 1, floors: 12, flatsPerFloor: 4 }, NO_RATES);
  const cleared = setCardFloors(card, "");
  const retyped = setCardFloors(cleared, "8");
  assert.equal(retyped.unitSpecs[0].floor_to, "8");
  // Set the top by hand below the tower's top: it stops following.
  const custom = updateCardSpec(retyped, 0, { floor_to: "5" }, NO_RATES);
  assert.equal(setCardFloors(custom, "10").unitSpecs[0].floor_to, "5");
});

test("prices: suggested from size × rate until the user types one; rate changes re-suggest untouched ones", () => {
  const card = newTowerCard(0, { towers: 1, floors: 2, flatsPerFloor: 2 }, RATES);
  const sized = updateCardSpec(card, 0, { area: "1000" }, RATES);
  assert.equal(sized.unitSpecs[0].base_price, "5000000");
  const [rerated] = applyRates([sized], { ...RATES, rateA: 6000 });
  assert.equal(rerated.unitSpecs[0].base_price, "6000000");
  const typed = updateCardSpec(rerated, 0, { base_price: "7500000" }, RATES);
  const [kept] = applyRates([typed], { ...RATES, rateA: 1 });
  assert.equal(kept.unitSpecs[0].base_price, "7500000");
});

test("tower names: blank, duplicate and the reserved parking name are caught before Save", () => {
  const [a, b] = syncCardsWithDetails([], { towers: 2, floors: 1, flatsPerFloor: null }, NO_RATES);
  assert.match(validateLayout([{ ...a, name: "  " }], 0) ?? "", /enter a tower name/);
  assert.match(validateLayout([a, { ...b, name: " tower 1 " }], 0) ?? "", /Two towers are named/);
  assert.match(validateLayout([{ ...a, name: "Parking" }], 0) ?? "", /kept for the project's parking/);
  assert.match(validateLayout([a], 5001) ?? "", /more than 5,000 in one save/);
  const tooHigh = updateCardSpec(updateCardSpec(a, 0, { units_per_floor: "2", area: "900", base_price: "1" }, NO_RATES), 0, { floor_to: "3" }, NO_RATES);
  assert.match(validateLayout([tooHigh], 0) ?? "", /go up to floor 3, above the tower's 1 floors/);
});

test("new cards never reuse an existing tower's name", () => {
  const cards = syncCardsWithDetails(
    [cardFromTower(flatsTower("t1", "Tower 2", 1, 1), { towers: null, floors: null, flatsPerFloor: null }, NO_RATES)],
    { towers: 3, floors: 1, flatsPerFloor: 1 },
    NO_RATES
  );
  assert.deepEqual(cards.map((c) => c.name), ["Tower 2", "Tower 3", "Tower 4"]);
});

test("parking: per-type counts, total, what Save adds, and the Edit prefill", () => {
  assert.equal(parkingTypeOf("cp07"), "CP");
  assert.equal(parkingTypeOf("MLP12"), "MLP");
  assert.equal(parkingTypeOf("P101"), null);
  const selected = ["CP", "OP"] as const;
  const counts = { ...EMPTY_PARKING_COUNTS, CP: "100", OP: "12", MLP: "9" };
  assert.deepEqual(parkingPayload([...selected], counts), { CP: 100, OP: 12 }); // MLP isn't ticked
  assert.equal(parkingTotal([...selected], counts), 112);
  assert.deepEqual(plannedParkingAdds([...selected], counts, { MLP: 0, CP: 90, IP: 0, OP: 20 }), { CP: 10 });

  // Old project: one type offered and a declared total → prefilled; several types → left for the user to split.
  assert.deepEqual(initialParkingCounts({ MLP: 0, CP: 0, IP: 0, OP: 0 }, ["CP"], 112).counts.CP, "112");
  const split = initialParkingCounts({ MLP: 0, CP: 0, IP: 0, OP: 0 }, ["CP", "OP"], 112);
  assert.deepEqual([split.selected, split.counts.CP, split.counts.OP], [["CP", "OP"], "", ""]);
  // Built spots win over the declared total.
  assert.deepEqual(initialParkingCounts({ MLP: 0, CP: 40, IP: 0, OP: 0 }, [], 112).counts.CP, "40");
});

test("inventory counts keep units and parking apart; parking rows group by type", () => {
  const towers = [
    tower("t1", "Tower A", 1, [unit("R101", 1), unit("R102", 1, "residential", "booked"), unit("S001", 0, "shop")]),
    tower("pk", "Parking", 1, [unit("CP02", 0, "parking"), unit("CP10", 0, "parking", "sold"), unit("OP01", 0, "parking"), unit("P1", 0, "parking")]),
  ];
  assert.deepEqual(inventoryCounts(towers), { units: 3, unitsAvailable: 2, parking: 4, parkingAvailable: 3 });
  assert.deepEqual(parkingCountsByType(towers), { byType: { MLP: 0, CP: 2, IP: 0, OP: 1 }, untyped: 1 });
  assert.deepEqual(
    groupParkingByType(towers[1].units).map((g) => [g.label, g.units.map((u) => u.unitNumber)]),
    [["CP", ["CP02", "CP10"]], ["OP", ["OP01"]], ["Other", ["P1"]]]
  );
});

test("plannedAdds mirrors the server: two specs of one type share a floor's count", () => {
  const card = newTowerCard(0, { towers: 1, floors: 1, flatsPerFloor: 2 }, NO_RATES);
  const twoTypes = { ...card, unitSpecs: [card.unitSpecs[0], { ...card.unitSpecs[0], units_per_floor: "1" }] };
  assert.deepEqual(plannedAdds(twoTypes, []), { residential: 3 });
  assert.deepEqual(plannedAdds(twoTypes, [unit("R101", 1), unit("R102", 1)]), { residential: 1 });
});

test("describeCreated reads naturally", () => {
  assert.equal(describeCreated({ towers: 2, units: 288, parking: 112 }), "2 towers, 288 units and 112 parking spots added.");
  assert.equal(describeCreated({ towers: 0, units: 1, parking: 0 }), "1 unit added.");
  assert.equal(describeCreated({ towers: 0, units: 0, parking: 0 }), "No new towers or units were needed.");
});
