import { useMemo, useState } from "react";
import { SelectField, TextField } from "../../../components";
import { formatInr } from "../../../utils/format";
import type { PricingSnapshot } from "../../../types/realestate";
import "./PriceCalculator.css";

const GST_OPTIONS = [
  { value: "0", label: "0% (Plot / exempt)" },
  { value: "5", label: "5% (Affordable housing)" },
  { value: "12", label: "12% (Under construction)" },
  { value: "18", label: "18% (Commercial)" },
];

interface Props {
  basePrice?: number;
  floor?: number;
  // Carpet / saleable area. When > 0 the base price is entered as a ₹/sqft rate
  // ("box price") and derived as rate × area, matching how units are quoted.
  area?: number;
  readOnly?: boolean;
  onPricingChange?: (snapshot: PricingSnapshot) => void;
}

export function PriceCalculator({ basePrice: initialBase = 0, floor: initialFloor = 1, area = 0, readOnly = false, onPricingChange }: Props) {
  const areaNum = Number(area) || 0;
  const hasArea = areaNum > 0;
  const [base, setBase] = useState(String(initialBase));
  // Seed the rate from the unit's base price when we know the area.
  const [rate, setRate] = useState(hasArea && initialBase > 0 ? String(Math.round(initialBase / areaNum)) : "0");
  const [floorRisePerFloor, setFloorRisePerFloor] = useState("0");
  const [floor, setFloor] = useState(String(initialFloor));
  const [plc, setPlc] = useState("0");
  const [parking, setParking] = useState("0");
  const [otherCharges, setOtherCharges] = useState("0");
  const [gstRate, setGstRate] = useState("12");

  const snapshot = useMemo<PricingSnapshot>(() => {
    const rateVal = Number(rate) || 0;
    // With a known area the base is the "box price" (rate × area); otherwise the
    // manually-entered base amount.
    const baseVal = hasArea ? Math.round(rateVal * areaNum) : Number(base) || 0;
    const floorVal = Number(floor) || 1;
    const floorRiseVal = Number(floorRisePerFloor) || 0;
    const plcVal = Number(plc) || 0;
    const parkingVal = Number(parking) || 0;
    const otherVal = Number(otherCharges) || 0;
    const gst = Number(gstRate) || 0;

    const floorRiseTotal = floorRiseVal * (floorVal - 1);
    const subtotal = baseVal + floorRiseTotal + plcVal + parkingVal + otherVal;
    const gstAmount = Math.round((subtotal * gst) / 100);
    const total = subtotal + gstAmount;

    const lineItems = [
      { label: hasArea ? `Base Price (₹${rateVal.toLocaleString("en-IN")}/sqft × ${areaNum})` : "Base Price", amount: baseVal },
      ...(floorRiseTotal ? [{ label: `Floor Rise (×${floorVal - 1})`, amount: floorRiseTotal }] : []),
      ...(plcVal ? [{ label: "PLC", amount: plcVal }] : []),
      ...(parkingVal ? [{ label: "Parking", amount: parkingVal }] : []),
      ...(otherVal ? [{ label: "Other Charges", amount: otherVal }] : []),
    ];

    const s: PricingSnapshot = {
      ratePerSqft: hasArea ? rateVal : undefined,
      area: hasArea ? areaNum : undefined,
      basePrice: baseVal, floorRise: floorRiseTotal, plc: plcVal, parking: parkingVal, otherCharges: otherVal, gstRate: gst, subtotal, gstAmount, total, lineItems,
    };
    onPricingChange?.(s);
    return s;
  }, [base, rate, hasArea, areaNum, floor, floorRisePerFloor, plc, parking, otherCharges, gstRate]);

  return (
    <div className="price-calculator">
      {!readOnly && (
        <div className="price-calculator__inputs">
          {hasArea ? (
            <TextField label="Rate (₹/sqft)" type="number" min="0" value={rate} onChange={(e) => setRate(e.target.value)} hint={`Base = rate × ${areaNum} sqft`} />
          ) : (
            <TextField label="Base Price (₹)" type="number" min="0" value={base} onChange={(e) => setBase(e.target.value)} />
          )}
          <TextField label="Floor Number" type="number" min="1" value={floor} onChange={(e) => setFloor(e.target.value)} />
          <TextField label="Floor Rise per Floor (₹)" type="number" min="0" value={floorRisePerFloor} onChange={(e) => setFloorRisePerFloor(e.target.value)} />
          <TextField label="PLC (₹)" type="number" min="0" value={plc} onChange={(e) => setPlc(e.target.value)} />
          <TextField label="Parking (₹)" type="number" min="0" value={parking} onChange={(e) => setParking(e.target.value)} />
          <TextField label="Other Charges (₹)" type="number" min="0" value={otherCharges} onChange={(e) => setOtherCharges(e.target.value)} />
          <SelectField label="GST Rate" options={GST_OPTIONS} value={gstRate} onChange={(e) => setGstRate(e.target.value)} />
        </div>
      )}

      <div className="price-calculator__breakdown">
        {snapshot.lineItems.map((item) => (
          <div key={item.label} className="price-calculator__line">
            <span>{item.label}</span>
            <span>{formatInr(item.amount)}</span>
          </div>
        ))}
        {snapshot.gstRate > 0 && (
          <div className="price-calculator__line price-calculator__line--gst">
            <span>GST ({snapshot.gstRate}%)</span>
            <span>{formatInr(snapshot.gstAmount)}</span>
          </div>
        )}
        <div className="price-calculator__total">
          <span>Total</span>
          <span style={{ fontSize: "var(--text-display-lg)", fontWeight: 700 }}>
            {formatInr(snapshot.total)}
          </span>
        </div>
      </div>
    </div>
  );
}
