import type { PriceDefaults } from "../pages/inventory/components/PriceCalculator";
import type { Project, UnitType } from "../types/realestate";

// Pick the project's per-sqft rate for a unit type (residential/parking → A,
// shop → B, godown → C) and bundle it with the lump-sum cost defaults so the
// booking PriceCalculator can pre-fill from the project instead of every field
// at ₹0 (Phase B). All fields may be null when a project set no defaults.
export function priceDefaultsForProject(p: Project, unitType: UnitType): PriceDefaults {
  const rate = unitType === "shop" ? p.rateB : unitType === "godown" ? p.rateC : p.rateA;
  return {
    rate,
    parking: p.parkingCost,
    amenities: p.amenitiesCharges,
    sinkingFund: p.sinkingFund,
    legalFees: p.legalFees,
    overhead: p.overheadCost,
    otherCharges: p.otherCharges,
  };
}
