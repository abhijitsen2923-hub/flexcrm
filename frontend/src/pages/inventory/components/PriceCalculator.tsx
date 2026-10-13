import { useMemo, useState } from "react";
import { SelectField, TextField } from "../../../components";
import { formatInr } from "../../../utils/format";
import { PARKING_TYPE_LABEL } from "../../../utils/projectInventory";
import { floorRiseSteps, seedPricing, type PriceDefaults } from "../../../utils/priceDefaults";
import type { ParkingType, PricingBasis, PricingSnapshot, UnitType } from "../../../types/realestate";
import "./PriceCalculator.css";

// Kept here too so existing `import type { PriceDefaults } from ".../PriceCalculator"` keep working.
export type { PriceDefaults } from "../../../utils/priceDefaults";

const GST_OPTIONS = [
  { value: "0", label: "0% (Plot / exempt)" },
  { value: "5", label: "5% (Affordable housing)" },
  { value: "12", label: "12% (Under construction)" },
  { value: "18", label: "18% (Commercial)" },
];

// How the basis area is named after "× 850" in the flat-value line (super built-up stays unnamed, as before).
const BASIS_SUFFIX: Record<PricingBasis, string> = { super_built_up: "", built_up: " built-up", carpet: " carpet" };

interface Props {
  basePrice?: number;
  floor?: number;
  // Super built-up (saleable) area. When the area the rate applies to is known, the base price is entered as a
  // ₹/sqft rate ("box price") and derived as rate × area, matching how units are quoted.
  area?: number;
  // The other two areas — used when the project prices on carpet or built-up area.
  carpetArea?: number | null;
  builtUpArea?: number | null;
  // The unit's flat type is marked PLC (corner / view) — seeds the PLC charge from the project's PLC rate.
  hasPlc?: boolean;
  // The unit's category: a parking spot is priced on its own, so it never gets the parking charge on top.
  unitType?: UnitType;
  readOnly?: boolean;
  // Project defaults — used only to seed the initial input values (the unit's own base price still wins for the
  // rate when the area is known).
  defaults?: PriceDefaults;
  onPricingChange?: (snapshot: PricingSnapshot) => void;
}

const asInput = (v: number): string => String(v);
const sqft = (v: number): string => v.toLocaleString("en-IN", { maximumFractionDigits: 2 });

export function PriceCalculator({
  basePrice: initialBase = 0,
  floor: initialFloor = 1,
  area = 0,
  carpetArea = null,
  builtUpArea = null,
  hasPlc = false,
  unitType,
  readOnly = false,
  defaults,
  onPricingChange,
}: Props) {
  // Seeded once, when the calculator opens — after that every figure is the user's to change.
  const [seed] = useState(() =>
    seedPricing({ basePrice: initialBase, floor: initialFloor, area: Number(area) || 0, carpetArea, builtUpArea, hasPlc, unitType }, defaults)
  );
  const areaNum = seed.basisArea;
  const hasArea = areaNum > 0;
  const d = defaults ?? {};
  const [base, setBase] = useState(String(initialBase));
  const [rate, setRate] = useState(asInput(seed.rate));
  const [floorRisePerFloor, setFloorRisePerFloor] = useState(asInput(seed.floorRisePerFloor));
  const [floor, setFloor] = useState(String(initialFloor));
  const [plc, setPlc] = useState(asInput(seed.plc));
  const [parking, setParking] = useState(asInput(seed.parking));
  const [parkingType, setParkingType] = useState<ParkingType | "">("");
  // RERA "Box Price" components.
  const [generator, setGenerator] = useState("0");
  const [amenities, setAmenities] = useState(asInput(seed.amenities));
  const [sinkingFund, setSinkingFund] = useState(asInput(seed.sinkingFund));
  const [legalFees, setLegalFees] = useState(asInput(seed.legalFees));
  const [overhead, setOverhead] = useState(asInput(seed.overhead));
  const [otherCharges, setOtherCharges] = useState(asInput(seed.otherCharges));
  const [gstRate, setGstRate] = useState("12");
  // Statutory charges at registry.
  const [stampDutyRate, setStampDutyRate] = useState("0");
  const [registrationRate, setRegistrationRate] = useState("0");

  const floorRiseFrom = seed.floorRiseFrom;
  const basisSuffix = BASIS_SUFFIX[seed.basis];

  function chooseParkingType(next: ParkingType | "") {
    setParkingType(next);
    setParking(next ? asInput(Number(d.parkingPrices?.[next] ?? 0)) : "0");
  }

  const snapshot = useMemo<PricingSnapshot>(() => {
    const rateVal = Number(rate) || 0;
    // With a known area the base is the "box price" (rate × area); otherwise the
    // manually-entered base amount.
    const baseVal = hasArea ? Math.round(rateVal * areaNum) : Number(base) || 0;
    // A blank / unreadable floor counts as floor 1 (as before); a real 0 (ground-floor shop) stays 0.
    const floorVal = floor.trim() !== "" && Number.isFinite(Number(floor)) ? Number(floor) : 1;
    const floorRiseVal = Number(floorRisePerFloor) || 0;
    const plcVal = Number(plc) || 0;
    const parkingVal = Number(parking) || 0;
    const generatorVal = Number(generator) || 0;
    const amenitiesVal = Number(amenities) || 0;
    const sinkingVal = Number(sinkingFund) || 0;
    const legalVal = Number(legalFees) || 0;
    const overheadVal = Number(overhead) || 0;
    const otherVal = Number(otherCharges) || 0;
    const gst = Number(gstRate) || 0;
    const stampRate = Number(stampDutyRate) || 0;
    const regRate = Number(registrationRate) || 0;

    const steps = floorRiseSteps(floorVal, floorRiseFrom);
    const floorRiseTotal = floorRiseVal * steps;
    // Box Price = the all-inclusive flat value + components (pre-tax).
    const boxPrice = baseVal + floorRiseTotal + plcVal + parkingVal + generatorVal + amenitiesVal + sinkingVal + legalVal + overheadVal + otherVal;
    const gstAmount = Math.round((boxPrice * gst) / 100);
    const stampDutyAmount = Math.round((boxPrice * stampRate) / 100);
    const registrationAmount = Math.round((boxPrice * regRate) / 100);
    const total = boxPrice + gstAmount + stampDutyAmount + registrationAmount;

    const floorRiseLabel =
      floorRiseFrom === 2 ? `Floor Rise (×${steps})` : `Floor Rise (×${steps}, from floor ${floorRiseFrom})`;
    const lineItems = [
      { label: hasArea ? `Flat Value (₹${rateVal.toLocaleString("en-IN")}/sqft × ${areaNum}${basisSuffix})` : "Flat Value", amount: baseVal },
      ...(floorRiseTotal ? [{ label: floorRiseLabel, amount: floorRiseTotal }] : []),
      ...(plcVal ? [{ label: "PLC", amount: plcVal }] : []),
      ...(parkingVal ? [{ label: parkingType ? `Garage / Parking (${parkingType})` : "Garage / Parking", amount: parkingVal }] : []),
      ...(generatorVal ? [{ label: "Generator", amount: generatorVal }] : []),
      ...(amenitiesVal ? [{ label: "Amenities / Club", amount: amenitiesVal }] : []),
      ...(sinkingVal ? [{ label: "Sinking Fund (1-yr maint.)", amount: sinkingVal }] : []),
      ...(legalVal ? [{ label: "Legal / Documentation", amount: legalVal }] : []),
      ...(overheadVal ? [{ label: "Overhead", amount: overheadVal }] : []),
      ...(otherVal ? [{ label: "Other Charges", amount: otherVal }] : []),
    ];

    const s: PricingSnapshot = {
      ratePerSqft: hasArea ? rateVal : undefined,
      area: hasArea ? areaNum : undefined,
      basis: hasArea ? seed.basis : undefined,
      basePrice: baseVal, floorRise: floorRiseTotal, floorRiseFrom, plc: plcVal, parking: parkingVal,
      parkingType: parkingType || undefined,
      generator: generatorVal, amenities: amenitiesVal, sinkingFund: sinkingVal,
      legalFees: legalVal, overhead: overheadVal, otherCharges: otherVal,
      boxPrice, gstRate: gst, gstAmount,
      stampDutyRate: stampRate, stampDutyAmount, registrationRate: regRate, registrationAmount,
      subtotal: boxPrice, total, lineItems,
    };
    onPricingChange?.(s);
    return s;
  }, [base, rate, hasArea, areaNum, basisSuffix, seed.basis, floor, floorRiseFrom, floorRisePerFloor, plc, parking, parkingType, generator, amenities, sinkingFund, legalFees, overhead, otherCharges, gstRate, stampDutyRate, registrationRate]);

  // Short notes under the seeded fields, so staff can see where a figure came from.
  const riseRate = Number(d.floorRiseRate) || 0;
  const steps = floorRiseSteps(floor.trim() !== "" && Number.isFinite(Number(floor)) ? Number(floor) : 1, floorRiseFrom);
  const floorRiseHint = [
    riseRate > 0 && d.floorRiseBasis !== "per_floor" && hasArea ? `₹${sqft(riseRate)}/sq ft × ${sqft(areaNum)} sq ft` : "",
    `${steps} paying ${steps === 1 ? "floor" : "floors"} (from floor ${floorRiseFrom})`,
  ].filter(Boolean).join(" · ");
  const plcRate = Number(d.plcRate) || 0;
  const plcHint = hasPlc && plcRate > 0 && hasArea ? `₹${sqft(plcRate)}/sq ft × ${sqft(areaNum)} sq ft` : undefined;
  const amenitiesRate = Number(d.amenitiesRate) || 0;
  const amenitiesHint = amenitiesRate > 0 && hasArea ? `₹${sqft(amenitiesRate)}/sq ft × ${sqft(areaNum)} sq ft` : undefined;
  const parkingOptions = [
    { value: "", label: "None" },
    ...seed.parkingTypes.map((type) => ({
      value: type,
      label: `${PARKING_TYPE_LABEL[type] ?? type} — ${formatInr(Number(d.parkingPrices?.[type] ?? 0))}`,
    })),
  ];

  return (
    <div className="price-calculator">
      {!readOnly && (
        <div className="price-calculator__inputs">
          {hasArea ? (
            <TextField label="Rate (₹/sqft)" type="number" min="0" value={rate} onChange={(e) => setRate(e.target.value)} hint={`Flat value = rate × ${areaNum} sqft${basisSuffix}`} />
          ) : (
            <TextField label="Flat Value (₹)" type="number" min="0" value={base} onChange={(e) => setBase(e.target.value)} />
          )}
          <TextField label="Floor Number" type="number" min="0" value={floor} onChange={(e) => setFloor(e.target.value)} />
          <TextField label="Floor Rise per Floor (₹)" type="number" min="0" value={floorRisePerFloor} onChange={(e) => setFloorRisePerFloor(e.target.value)} hint={floorRiseHint} />
          <TextField label="PLC (₹)" type="number" min="0" value={plc} onChange={(e) => setPlc(e.target.value)} hint={plcHint} />
          {seed.parkingTypes.length > 0 && (
            <SelectField
              label="Parking type"
              options={parkingOptions}
              value={parkingType}
              onChange={(e) => chooseParkingType(e.target.value as ParkingType | "")}
              hint="Sets the parking charge to that type's price."
            />
          )}
          <TextField label="Garage / Parking (₹)" type="number" min="0" value={parking} onChange={(e) => setParking(e.target.value)} />
          <TextField label="Generator (₹)" type="number" min="0" value={generator} onChange={(e) => setGenerator(e.target.value)} />
          <TextField label="Amenities / Club (₹)" type="number" min="0" value={amenities} onChange={(e) => setAmenities(e.target.value)} hint={amenitiesHint} />
          <TextField label="Sinking Fund / 1-yr Maint. (₹)" type="number" min="0" value={sinkingFund} onChange={(e) => setSinkingFund(e.target.value)} />
          <TextField label="Legal / Documentation (₹)" type="number" min="0" value={legalFees} onChange={(e) => setLegalFees(e.target.value)} />
          <TextField label="Overhead (₹)" type="number" min="0" value={overhead} onChange={(e) => setOverhead(e.target.value)} />
          <TextField label="Other Charges (₹)" type="number" min="0" value={otherCharges} onChange={(e) => setOtherCharges(e.target.value)} />
          <SelectField label="GST Rate" options={GST_OPTIONS} value={gstRate} onChange={(e) => setGstRate(e.target.value)} />
          <TextField label="Stamp Duty (%)" type="number" min="0" value={stampDutyRate} onChange={(e) => setStampDutyRate(e.target.value)} hint="At registry (e.g. 7%)" />
          <TextField label="Registration (%)" type="number" min="0" value={registrationRate} onChange={(e) => setRegistrationRate(e.target.value)} />
        </div>
      )}

      <div className="price-calculator__breakdown">
        {snapshot.lineItems.map((item) => (
          <div key={item.label} className="price-calculator__line">
            <span>{item.label}</span>
            <span>{formatInr(item.amount)}</span>
          </div>
        ))}
        <div className="price-calculator__line" style={{ fontWeight: 600, borderTop: "1px solid var(--color-border)", paddingTop: 6 }}>
          <span>Box Price</span>
          <span>{formatInr(snapshot.boxPrice ?? snapshot.subtotal)}</span>
        </div>
        {snapshot.gstRate > 0 && (
          <div className="price-calculator__line price-calculator__line--gst">
            <span>GST ({snapshot.gstRate}%)</span>
            <span>{formatInr(snapshot.gstAmount)}</span>
          </div>
        )}
        {(snapshot.stampDutyRate ?? 0) > 0 && (
          <div className="price-calculator__line">
            <span>Stamp Duty ({snapshot.stampDutyRate}%)</span>
            <span>{formatInr(snapshot.stampDutyAmount ?? 0)}</span>
          </div>
        )}
        {(snapshot.registrationRate ?? 0) > 0 && (
          <div className="price-calculator__line">
            <span>Registration ({snapshot.registrationRate}%)</span>
            <span>{formatInr(snapshot.registrationAmount ?? 0)}</span>
          </div>
        )}
        <div className="price-calculator__total">
          <span>Total Consideration</span>
          <span style={{ fontSize: "var(--text-display-lg)", fontWeight: 700 }}>
            {formatInr(snapshot.total)}
          </span>
        </div>
      </div>
    </div>
  );
}
