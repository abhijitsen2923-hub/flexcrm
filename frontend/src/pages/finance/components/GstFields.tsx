import { SelectField, TextField } from "../../../components";
import type { GstInput, GstTreatment } from "../../../types/finance";
import { formatCurrency } from "../../../utils/format";

// Client-side mirror of app/finance/gst.py (server recomputes authoritatively).
function preview(v: GstInput) {
  const amt = Number(v.amount_entered) || 0;
  const tds = Number(v.tds_amount) || 0;
  if (!v.gst_applicable || !v.gst_rate) {
    return { taxable: amt, gst: 0, total: amt, net: amt - tds };
  }
  const r = Number(v.gst_rate) / 100;
  const taxable = v.gst_inclusive ? amt / (1 + r) : amt;
  const gst = v.gst_inclusive ? amt - taxable : taxable * r;
  const total = taxable + gst;
  return { taxable, gst, total, net: total - tds };
}

interface Props {
  value: GstInput;
  onChange: (next: GstInput) => void;
}

export function GstFields({ value, onChange }: Props) {
  const set = (patch: Partial<GstInput>) => onChange({ ...value, ...patch });
  const p = preview(value);

  return (
    <>
      <div className="form-grid">
        <TextField
          id="g-amount"
          label="Amount (₹)"
          type="number"
          min="0"
          step="0.01"
          value={value.amount_entered === 0 && !value.gst_applicable ? String(value.amount_entered) : String(value.amount_entered ?? "")}
          onChange={(e) => set({ amount_entered: Number(e.target.value) })}
          required
        />
        <div className="field">
          <label className="field__label">GST</label>
          <label className="row" style={{ gap: "0.5rem", alignItems: "center", height: "2.4rem" }}>
            <input
              type="checkbox"
              checked={value.gst_applicable}
              onChange={(e) => set({ gst_applicable: e.target.checked })}
            />
            <span>GST applicable</span>
          </label>
        </div>
      </div>

      {value.gst_applicable && (
        <div className="form-grid">
          <TextField
            id="g-rate"
            label="GST rate %"
            type="number"
            min="0"
            max="100"
            step="0.01"
            value={value.gst_rate === null ? "" : String(value.gst_rate)}
            onChange={(e) => set({ gst_rate: e.target.value === "" ? null : Number(e.target.value) })}
          />
          <SelectField
            id="g-treat"
            label="Tax type"
            value={value.gst_treatment ?? "intra_state"}
            onChange={(e) => set({ gst_treatment: e.target.value as GstTreatment })}
            options={[
              { value: "intra_state", label: "Intra-state (CGST + SGST)" },
              { value: "inter_state", label: "Inter-state (IGST)" }
            ]}
          />
          <SelectField
            id="g-incl"
            label="Amount is"
            value={value.gst_inclusive ? "incl" : "excl"}
            onChange={(e) => set({ gst_inclusive: e.target.value === "incl" })}
            options={[
              { value: "excl", label: "Exclusive of GST" },
              { value: "incl", label: "Inclusive of GST" }
            ]}
          />
        </div>
      )}

      <TextField
        id="g-tds"
        label="TDS deducted (₹, optional)"
        type="number"
        min="0"
        step="0.01"
        value={value.tds_amount ? String(value.tds_amount) : ""}
        onChange={(e) => set({ tds_amount: Number(e.target.value) || 0 })}
      />

      <div className="muted text-sm" style={{ padding: "0.25rem 0" }}>
        Taxable {formatCurrency(p.taxable, "INR")} · GST {formatCurrency(p.gst, "INR")} ·
        Total {formatCurrency(p.total, "INR")} · <strong>Net payable {formatCurrency(p.net, "INR")}</strong>
      </div>
    </>
  );
}

export const EMPTY_GST: GstInput = {
  amount_entered: 0,
  gst_applicable: false,
  gst_treatment: "intra_state",
  gst_inclusive: false,
  gst_rate: 18,
  tds_amount: 0
};
