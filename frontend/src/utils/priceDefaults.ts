// The booking price calculator's starting figures, taken from the project's pricing so a booking pre-fills
// instead of every field at ₹0 (Phase B; per-sq-ft charges from the Add Project wizard). Pure, no React, no
// runtime imports (unit-tested in tests/priceDefaults.test.ts). Every figure stays editable in the calculator.
import type { FloorRiseBasis, ParkingType, PricingBasis, Project, UnitType } from "../types/realestate";

// Project-level defaults that seed the box-price fields. All may be null when a project set no defaults.
export interface PriceDefaults {
  rate?: number | null;             // ₹/sq ft for this unit's category
  parking?: number | null;          // older single parking price (lump sum)
  amenities?: number | null;        // older amenities lump sum
  sinkingFund?: number | null;
  legalFees?: number | null;
  overhead?: number | null;
  otherCharges?: number | null;
  // --- Add Project wizard pricing (null on projects set up before it) ---
  pricingBasis?: PricingBasis | null;       // the area the rate applies to (null = super built-up)
  floorRiseRate?: number | null;
  floorRiseBasis?: FloorRiseBasis | null;   // null = ₹ per sq ft per floor
  floorRiseFrom?: number | null;            // first floor that pays (null = 2)
  plcRate?: number | null;                  // ₹/sq ft, only for units marked PLC
  amenitiesRate?: number | null;            // ₹/sq ft — wins over the lump sum when set
  parkingPrices?: Partial<Record<ParkingType, number>> | null;
}

// Pick the project's per-sqft rate for a unit category (residential/parking → rate A, shop → B, godown → C,
// falling back to the commercial rate like the server does) and bundle it with the other defaults.
export function priceDefaultsForProject(p: Project, unitType: UnitType): PriceDefaults {
  const rate = unitType === "shop" ? p.rateB : unitType === "godown" ? p.rateC ?? p.rateB : p.rateA;
  return {
    rate,
    parking: p.parkingCost,
    amenities: p.amenitiesCharges,
    sinkingFund: p.sinkingFund,
    legalFees: p.legalFees,
    overhead: p.overheadCost,
    otherCharges: p.otherCharges,
    pricingBasis: p.pricingBasis,
    floorRiseRate: p.floorRiseRate,
    floorRiseBasis: p.floorRiseBasis,
    floorRiseFrom: p.floorRiseFrom,
    plcRate: p.plcRate,
    amenitiesRate: p.amenitiesRate,
    parkingPrices: p.parkingPrices,
  };
}

// The unit being priced (what the booking wizard knows about it).
export interface PricingUnit {
  basePrice: number;
  floor: number;
  area: number;                     // super built-up
  carpetArea?: number | null;
  builtUpArea?: number | null;
  hasPlc?: boolean;
  unitType?: UnitType;
}

export const DEFAULT_FLOOR_RISE_FROM = 2;
// Same order as the parking setup (MLP, CP, IP, OP, then Dependent).
const PARKING_ORDER: ParkingType[] = ["MLP", "CP", "IP", "OP", "DP"];

const positive = (v: number | null | undefined): number => (v != null && Number.isFinite(Number(v)) && Number(v) > 0 ? Number(v) : 0);
const rupees = (v: number): number => Math.round(v);
const paise = (v: number): number => Math.round(v * 100) / 100;

/**
 * The area the rate applies to. A unit without that area (one set up before flat types) is priced on its
 * super built-up area instead, and the basis says so.
 */
export function basisAreaFor(
  basis: PricingBasis | null | undefined,
  unit: Pick<PricingUnit, "area" | "carpetArea" | "builtUpArea">
): { basis: PricingBasis; area: number } {
  if (basis === "carpet" && positive(unit.carpetArea) > 0) return { basis, area: positive(unit.carpetArea) };
  if (basis === "built_up" && positive(unit.builtUpArea) > 0) return { basis, area: positive(unit.builtUpArea) };
  return { basis: "super_built_up", area: positive(unit.area) };
}

/** Floors that pay floor rise: from floor 2 (the default) floor 2 pays 1, floor 10 pays 9; below it, none. */
export function floorRiseSteps(floor: number, from: number | null | undefined): number {
  const start = from != null && from >= 1 ? from : DEFAULT_FLOOR_RISE_FROM;
  return Math.max(0, (Number(floor) || 0) - start + 1);
}

/** Parking types the project priced (None is offered as well), in the setup's order. */
export function pricedParkingTypes(defaults: Pick<PriceDefaults, "parkingPrices"> | null | undefined): ParkingType[] {
  const prices = defaults?.parkingPrices ?? {};
  return PARKING_ORDER.filter((type) => {
    const price = prices[type];
    return price != null && Number.isFinite(Number(price)) && Number(price) >= 0;
  });
}

export interface PriceSeed {
  basis: PricingBasis;          // the basis actually used for this unit
  basisArea: number;            // 0 = no area → the flat value is typed in
  rate: number;                 // ₹/sq ft
  floorRisePerFloor: number;    // ₹ per paying floor, for this unit
  floorRiseFrom: number;
  plc: number;
  amenities: number;
  parking: number;
  parkingTypes: ParkingType[];  // non-empty → the calculator offers a "Parking type" choice (starts at None)
  sinkingFund: number;
  legalFees: number;
  overhead: number;
  otherCharges: number;
}

/**
 * The calculator's starting figures. The unit's own price wins for the rate (it was priced when it was made);
 * per-sq-ft charges are worked out on the same basis area; PLC only for a unit marked PLC; a parking spot never
 * gets the parking charge on top of its own price.
 */
export function seedPricing(unit: PricingUnit, defaults: PriceDefaults | null | undefined): PriceSeed {
  const d = defaults ?? {};
  const { basis, area } = basisAreaFor(d.pricingBasis, unit);
  const ownPrice = positive(unit.basePrice);
  const rate = area > 0 && ownPrice > 0 ? paise(ownPrice / area) : positive(d.rate);

  const riseRate = positive(d.floorRiseRate);
  const floorRisePerFloor = d.floorRiseBasis === "per_floor" ? riseRate : rupees(riseRate * area);

  const isParkingSpot = unit.unitType === "parking";
  const parkingTypes = isParkingSpot ? [] : pricedParkingTypes(d);
  const parking = isParkingSpot || parkingTypes.length > 0 ? 0 : positive(d.parking);

  return {
    basis,
    basisArea: area,
    rate,
    floorRisePerFloor,
    floorRiseFrom: d.floorRiseFrom != null && d.floorRiseFrom >= 1 ? d.floorRiseFrom : DEFAULT_FLOOR_RISE_FROM,
    plc: unit.hasPlc ? rupees(positive(d.plcRate) * area) : 0,
    amenities: positive(d.amenitiesRate) > 0 ? rupees(positive(d.amenitiesRate) * area) : positive(d.amenities),
    parking,
    parkingTypes,
    sinkingFund: positive(d.sinkingFund),
    legalFees: positive(d.legalFees),
    overhead: positive(d.overhead),
    otherCharges: positive(d.otherCharges),
  };
}
