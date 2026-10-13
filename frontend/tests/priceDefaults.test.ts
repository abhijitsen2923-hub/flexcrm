// Unit tests for the booking price calculator's starting figures (src/utils/priceDefaults.ts): the rate from the
// unit's own price on the project's pricing basis, floor rise steps, PLC only for PLC flats, per-sq-ft amenities,
// per-type parking, and a parking spot never charged parking twice. Projects set up before the wizard (no new
// pricing fields) must seed exactly as before. Run: npm test
import assert from "node:assert/strict";
import { test } from "node:test";

import type { Project } from "../src/types/realestate.ts";
import {
  basisAreaFor,
  floorRiseSteps,
  priceDefaultsForProject,
  pricedParkingTypes,
  seedPricing,
  type PriceDefaults,
  type PricingUnit,
} from "../src/utils/priceDefaults.ts";

function unit(overrides: Partial<PricingUnit> = {}): PricingUnit {
  return { basePrice: 6_250_000, floor: 5, area: 1250, carpetArea: 850, builtUpArea: 1050, hasPlc: false, unitType: "residential", ...overrides };
}

// A project set up before the wizard: only the Phase-B lump sums.
const LEGACY: PriceDefaults = {
  rate: 5000,
  parking: 300_000,
  amenities: 150_000,
  sinkingFund: 50_000,
  legalFees: 25_000,
  overhead: 10_000,
  otherCharges: 5_000,
};

test("basisAreaFor picks the project's basis, falling back to super built-up when the unit lacks that area", () => {
  assert.deepEqual(basisAreaFor(null, unit()), { basis: "super_built_up", area: 1250 });
  assert.deepEqual(basisAreaFor("super_built_up", unit()), { basis: "super_built_up", area: 1250 });
  assert.deepEqual(basisAreaFor("carpet", unit()), { basis: "carpet", area: 850 });
  assert.deepEqual(basisAreaFor("built_up", unit()), { basis: "built_up", area: 1050 });
  assert.deepEqual(basisAreaFor("carpet", unit({ carpetArea: null })), { basis: "super_built_up", area: 1250 });
  assert.deepEqual(basisAreaFor("built_up", unit({ builtUpArea: 0 })), { basis: "super_built_up", area: 1250 });
  assert.deepEqual(basisAreaFor("carpet", unit({ area: 0, carpetArea: null })), { basis: "super_built_up", area: 0 });
});

test("floor rise steps: from floor 2 by default (= floor − 1), never negative", () => {
  assert.equal(floorRiseSteps(1, null), 0);
  assert.equal(floorRiseSteps(2, null), 1);
  assert.equal(floorRiseSteps(10, undefined), 9);
  assert.equal(floorRiseSteps(0, null), 0); // ground-floor shop
  assert.equal(floorRiseSteps(10, 5), 6);
  assert.equal(floorRiseSteps(4, 5), 0);
  assert.equal(floorRiseSteps(3, 1), 3);
});

test("an older project seeds exactly as before", () => {
  const seed = seedPricing(unit(), LEGACY);
  assert.equal(seed.basis, "super_built_up");
  assert.equal(seed.basisArea, 1250);
  assert.equal(seed.rate, 5000); // 62,50,000 / 1,250
  assert.equal(seed.floorRisePerFloor, 0);
  assert.equal(seed.floorRiseFrom, 2);
  assert.equal(seed.plc, 0);
  assert.equal(seed.amenities, 150_000);
  assert.equal(seed.parking, 300_000);
  assert.deepEqual(seed.parkingTypes, []);
  assert.equal(seed.sinkingFund, 50_000);
  assert.equal(seed.legalFees, 25_000);
  assert.equal(seed.overhead, 10_000);
  assert.equal(seed.otherCharges, 5_000);
  // No defaults at all → zeros, rate from the unit's price.
  const bare = seedPricing(unit(), null);
  assert.equal(bare.rate, 5000);
  assert.equal(bare.parking + bare.amenities + bare.legalFees, 0);
});

test("the unit's own price wins for the rate; the project rate is used only without one", () => {
  assert.equal(seedPricing(unit({ basePrice: 6_250_000 }), { rate: 4000 }).rate, 5000);
  assert.equal(seedPricing(unit({ basePrice: 0 }), { rate: 4000 }).rate, 4000);
  // A rate that isn't a whole number keeps its paise, so rate × area gives back the unit's price.
  assert.equal(seedPricing(unit({ basePrice: 6_250_625, area: 1250 }), null).rate, 5000.5);
});

test("on a carpet basis the rate and every per-sq-ft charge use the carpet area", () => {
  const seed = seedPricing(unit({ basePrice: 6_800_000, hasPlc: true }), {
    pricingBasis: "carpet",
    floorRiseRate: 50,
    floorRiseBasis: "per_sqft",
    plcRate: 100,
    amenitiesRate: 150,
    amenities: 999_999, // the older lump sum loses to the per-sq-ft rate
  });
  assert.equal(seed.basis, "carpet");
  assert.equal(seed.basisArea, 850);
  assert.equal(seed.rate, 8000);
  assert.equal(seed.floorRisePerFloor, 42_500); // 50 × 850
  assert.equal(seed.plc, 85_000); // 100 × 850
  assert.equal(seed.amenities, 127_500); // 150 × 850
});

test("floor rise per floor: ₹ per sq ft × area, or a flat ₹ per floor; start floor carried", () => {
  assert.equal(seedPricing(unit(), { floorRiseRate: 30, floorRiseBasis: "per_sqft" }).floorRisePerFloor, 37_500);
  assert.equal(seedPricing(unit(), { floorRiseRate: 30 }).floorRisePerFloor, 37_500); // no basis = per sq ft
  assert.equal(seedPricing(unit(), { floorRiseRate: 20_000, floorRiseBasis: "per_floor" }).floorRisePerFloor, 20_000);
  assert.equal(seedPricing(unit(), { floorRiseFrom: 5 }).floorRiseFrom, 5);
  assert.equal(seedPricing(unit(), { floorRiseFrom: null }).floorRiseFrom, 2);
});

test("PLC only for a flat type marked PLC", () => {
  assert.equal(seedPricing(unit({ hasPlc: false }), { plcRate: 100 }).plc, 0);
  assert.equal(seedPricing(unit({ hasPlc: true }), { plcRate: 100 }).plc, 125_000);
  assert.equal(seedPricing(unit({ hasPlc: true }), { plcRate: null }).plc, 0);
});

test("per-type parking prices: offered as a choice that starts at None", () => {
  const defaults: PriceDefaults = { parking: 300_000, parkingPrices: { DP: 350_000, CP: 400_000, OP: 0 } };
  const seed = seedPricing(unit(), defaults);
  assert.deepEqual(seed.parkingTypes, ["CP", "OP", "DP"]);
  assert.equal(seed.parking, 0);
  assert.deepEqual(pricedParkingTypes({ parkingPrices: null }), []);
  assert.deepEqual(pricedParkingTypes({ parkingPrices: {} }), []);
});

test("a parking spot is priced on its own — no parking charge on top", () => {
  const spot = unit({ unitType: "parking", area: 0, carpetArea: null, builtUpArea: null, basePrice: 400_000, floor: 0 });
  const legacy = seedPricing(spot, LEGACY);
  assert.equal(legacy.parking, 0);
  assert.equal(legacy.basisArea, 0);
  // None of the flat's lump sums ride along on a standalone spot either.
  const lumps = seedPricing(spot, {
    amenities: 150_000, sinkingFund: 50_000, legalFees: 25_000, overhead: 10_000, otherCharges: 5_000, parking: 300_000,
  });
  assert.deepEqual(
    [lumps.amenities, lumps.sinkingFund, lumps.legalFees, lumps.overhead, lumps.otherCharges, lumps.parking],
    [0, 0, 0, 0, 0, 0]
  );
  // A flat keeps them.
  const flat = seedPricing(unit({ unitType: "residential" }), { amenities: 150_000, legalFees: 25_000 });
  assert.equal(flat.amenities, 150_000);
  assert.equal(flat.legalFees, 25_000);
  const priced = seedPricing(spot, { parkingPrices: { CP: 400_000 } });
  assert.equal(priced.parking, 0);
  assert.deepEqual(priced.parkingTypes, []);
});

test("priceDefaultsForProject: rate per category (godown falls back to the commercial rate) + wizard fields", () => {
  const project = {
    rateA: 5000,
    rateB: 9000,
    rateC: null,
    parkingCost: 300_000,
    amenitiesCharges: 150_000,
    sinkingFund: null,
    legalFees: 25_000,
    overheadCost: null,
    otherCharges: null,
    pricingBasis: "built_up",
    floorRiseRate: 50,
    floorRiseBasis: "per_sqft",
    floorRiseFrom: 3,
    plcRate: 100,
    amenitiesRate: 120,
    parkingPrices: { CP: 400_000 },
  } as unknown as Project;
  assert.equal(priceDefaultsForProject(project, "residential").rate, 5000);
  assert.equal(priceDefaultsForProject(project, "parking").rate, 5000);
  assert.equal(priceDefaultsForProject(project, "shop").rate, 9000);
  assert.equal(priceDefaultsForProject(project, "godown").rate, 9000);
  assert.equal(priceDefaultsForProject({ ...project, rateC: 7000 } as Project, "godown").rate, 7000);
  const d = priceDefaultsForProject(project, "residential");
  assert.equal(d.pricingBasis, "built_up");
  assert.equal(d.floorRiseFrom, 3);
  assert.equal(d.plcRate, 100);
  assert.equal(d.amenitiesRate, 120);
  assert.deepEqual(d.parkingPrices, { CP: 400_000 });
  assert.equal(d.parking, 300_000);
  assert.equal(d.amenities, 150_000);
});
