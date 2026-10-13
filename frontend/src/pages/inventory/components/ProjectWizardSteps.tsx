// Project wizard steps 1 (Project info), 3 (Pricing), 4 (Parking) and 5 (Payment plan). Step 2 is in
// ProjectWizardTowers.tsx; 6 and 7 in ProjectWizardReview.tsx.
import { useRef } from "react";
import {
  ArrowDown,
  ArrowUp,
  Building2,
  Calculator,
  Car,
  CheckCircle2,
  ImagePlus,
  IndianRupee,
  ListChecks,
  Plus,
  Trash2,
  Wand2,
} from "lucide-react";
import { Button, SelectField, TextField } from "../../../components";
import { formatInr } from "../../../utils/format";
import {
  DUE_ON_OPTIONS,
  FLOOR_RISE_BASIS_OPTIONS,
  PRICING_BASIS_OPTIONS,
  PROJECT_TYPE_OPTIONS,
  WIZARD_PARKING_LABEL,
  WIZARD_PARKING_TYPES,
  blankMilestone,
  fieldKey,
  hasFlatTypes,
  hasOthers,
  legacyPlanWarning,
  parkingAdds,
  parkingTotal,
  planTotal,
  priceCheckRows,
  pricingNumbers,
  samplePlan,
  type ExistingParking,
  type ParkingRowForm,
  type PlanRowForm,
  type PricingForm,
} from "../../../utils/projectWizard";
import type { ParkingType, PlanDueOn } from "../../../types/realestate";
import { CellInput, Note, Req, StepErrors, StepIntro, WizardCard, fieldError, rupees, sqft, type StepProps } from "./ProjectWizardParts";

// ---------------------------------------------------------------------------------------------------------------
// Step 1 — Project info
// ---------------------------------------------------------------------------------------------------------------

export interface CoverPick {
  file: File | null;
  previewUrl: string | null; // the picked file, shown before it uploads
  existingUrl: string | null; // Edit: the project's current cover
  error: string | null;
  onPick: (file: File | null) => void;
}

export function InfoStep({ state, update, check, cover }: StepProps & { cover: CoverPick }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const info = state.info;
  const set = (patch: Partial<typeof info>) => update((s) => ({ ...s, info: { ...s.info, ...patch } }));
  const err = (key: string) => fieldError(check, key);
  const shownUrl = cover.previewUrl ?? cover.existingUrl;

  return (
    <div className="pw-step">
      <StepIntro title="Project info">The basics your team and buyers see.</StepIntro>
      <StepErrors check={check} />
      <WizardCard title="Project details" icon={<Building2 size={16} />}>
        <div className="pw-grid">
          <TextField
            id="pw-name"
            label={<Req>Project name</Req>}
            value={info.name}
            maxLength={255}
            aria-required
            onChange={(e) => set({ name: e.target.value })}
            placeholder="e.g. Prestige Lakeside Habitat"
            error={err("name")}
          />
          <TextField
            id="pw-builder"
            label={<Req>Builder / Developer</Req>}
            value={info.builder}
            maxLength={255}
            aria-required
            onChange={(e) => set({ builder: e.target.value })}
            placeholder="e.g. Prestige Group"
            error={err("builder")}
          />
          <fieldset className="pw-fieldset pw-span-2">
            <legend className="field__label">
              <Req>Project type</Req>
            </legend>
            <div className="pw-choices" role="radiogroup">
              {PROJECT_TYPE_OPTIONS.map((o) => (
                <label key={o.value} className="pw-choice">
                  <input
                    type="radio"
                    name="pw-project-type"
                    value={o.value}
                    checked={info.projectType === o.value}
                    onChange={() => set({ projectType: o.value })}
                  />
                  <span>{o.label}</span>
                </label>
              ))}
            </div>
            {err("projectType") && <div className="field__error">{err("projectType")}</div>}
          </fieldset>
          <TextField
            id="pw-location"
            label={<Req>Location / Area</Req>}
            value={info.location}
            maxLength={255}
            aria-required
            onChange={(e) => set({ location: e.target.value })}
            placeholder="e.g. Whitefield"
            error={err("location")}
          />
          <TextField
            id="pw-city"
            label={<Req>City</Req>}
            value={info.city}
            maxLength={100}
            aria-required
            onChange={(e) => set({ city: e.target.value })}
            placeholder="e.g. Bengaluru"
            error={err("city")}
          />
          <TextField
            id="pw-pin"
            label="PIN code"
            inputMode="numeric"
            value={info.pinCode}
            maxLength={12}
            onChange={(e) => set({ pinCode: e.target.value })}
            placeholder="e.g. 560066"
            error={err("pinCode")}
          />
          <TextField
            id="pw-landmark"
            label="Landmark"
            value={info.landmark}
            maxLength={255}
            onChange={(e) => set({ landmark: e.target.value })}
            placeholder="e.g. Near ITPL"
          />
          <TextField
            id="pw-rera"
            label="RERA number"
            value={info.rera}
            maxLength={64}
            onChange={(e) => set({ rera: e.target.value })}
            placeholder="Optional"
          />
        </div>
      </WizardCard>

      <WizardCard title="Cover image" icon={<ImagePlus size={16} />} subtitle="JPG or PNG, up to 5 MB. It uploads when you save the project.">
        <div className="pw-cover">
          <div className="pw-cover__thumb">
            {shownUrl ? <img src={shownUrl} alt="Project cover" /> : <ImagePlus size={28} aria-hidden="true" />}
          </div>
          <div className="pw-cover__actions">
            <div className="row" style={{ gap: "0.5rem" }}>
              <Button variant="secondary" size="sm" icon={<ImagePlus size={14} />} onClick={() => fileRef.current?.click()}>
                {shownUrl ? "Choose another image" : "Choose image"}
              </Button>
              {cover.file && (
                <Button variant="ghost" size="sm" onClick={() => cover.onPick(null)}>
                  Remove
                </Button>
              )}
            </div>
            <input
              ref={fileRef}
              type="file"
              accept="image/jpeg,image/png"
              className="sr-only"
              tabIndex={-1}
              aria-label="Cover image"
              onChange={(e) => {
                cover.onPick(e.target.files?.[0] ?? null);
                e.target.value = "";
              }}
            />
            <p className="muted text-sm" style={{ margin: 0 }}>
              {cover.file
                ? cover.file.name
                : cover.existingUrl
                  ? "The project's current cover. A new image becomes the cover; the old one stays in the Media Repository."
                  : "Optional — shown with the project."}
            </p>
            {cover.error && <div className="field__error">{cover.error}</div>}
          </div>
        </div>
      </WizardCard>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------------------
// Step 3 — Pricing
// ---------------------------------------------------------------------------------------------------------------

function pricingChanged(form: PricingForm, project: NonNullable<StepProps["project"]>): boolean {
  const p = pricingNumbers(form);
  const same = (a: number | null, b: number | null) => (a ?? null) === (b ?? null);
  return !(
    (project.pricingBasis ?? "super_built_up") === form.basis &&
    same(p.rateFlats, project.rateA) &&
    same(p.rateShops, project.rateB) &&
    same(p.rateGodowns, project.rateC) &&
    same(p.floorRise, project.floorRiseRate) &&
    (p.floorRise == null || ((project.floorRiseBasis ?? "per_sqft") === p.floorRiseBasis && (project.floorRiseFrom ?? 2) === p.floorRiseFrom)) &&
    same(p.plcRate, project.plcRate) &&
    same(p.amenitiesRate, project.amenitiesRate) &&
    same(p.legal, project.legalFees) &&
    same(p.other, project.otherCharges) &&
    same(p.sinking, project.sinkingFund) &&
    same(p.overhead, project.overheadCost)
  );
}

export function PricingStep({ state, update, check, project }: StepProps) {
  const pricing = state.pricing;
  const set = (patch: Partial<PricingForm>) => update((s) => ({ ...s, pricing: { ...s.pricing, ...patch } }));
  const err = (key: string) => fieldError(check, key);
  const anyFlats = hasFlatTypes(state.towers);
  const anyShops = hasOthers(state.towers, "shop");
  const anyGodowns = hasOthers(state.towers, "godown");
  const rows = priceCheckRows(state.towers, pricing);
  const money = (key: keyof PricingForm, label: string, hint?: string) => (
    <TextField
      id={`pw-${key}`}
      label={label}
      type="number"
      min={0}
      inputMode="decimal"
      value={pricing[key] as string}
      onChange={(e) => set({ [key]: e.target.value } as Partial<PricingForm>)}
      error={err(key)}
      hint={hint}
    />
  );

  return (
    <div className="pw-step">
      <StepIntro title="Pricing">
        Each unit's price is worked out from these rates when it's created. The booking price calculator starts from
        them too.
      </StepIntro>
      <StepErrors check={check} />
      {project && pricingChanged(pricing, project) && (
        <Note>
          New rates apply to flats added from now on and to new bookings' price calculator; existing flats keep their
          saved price.
        </Note>
      )}

      <WizardCard title="Base price" icon={<IndianRupee size={16} />}>
        <fieldset className="pw-fieldset">
          <legend className="field__label">
            <Req>Pricing basis</Req> <span className="muted">— the area the rate is multiplied by</span>
          </legend>
          <div className="pw-choices" role="radiogroup">
            {PRICING_BASIS_OPTIONS.map((o) => (
              <label key={o.value} className="pw-choice">
                <input type="radio" name="pw-basis" value={o.value} checked={pricing.basis === o.value} onChange={() => set({ basis: o.value })} />
                <span>{o.label}</span>
              </label>
            ))}
          </div>
        </fieldset>
        <div className="pw-grid pw-grid--3">
          <TextField
            id="pw-rateFlats"
            label={anyFlats ? <Req>Base rate — flats (₹/sq ft)</Req> : "Base rate — flats (₹/sq ft)"}
            type="number"
            min={0}
            inputMode="decimal"
            value={pricing.rateFlats}
            onChange={(e) => set({ rateFlats: e.target.value })}
            error={err("rateFlats")}
            placeholder="e.g. 5000"
          />
          <TextField
            id="pw-rateShops"
            label={anyShops ? <Req>Base rate — shops / commercial (₹/sq ft)</Req> : "Base rate — shops / commercial (₹/sq ft)"}
            type="number"
            min={0}
            inputMode="decimal"
            value={pricing.rateShops}
            onChange={(e) => set({ rateShops: e.target.value })}
            error={err("rateShops")}
          />
          {(anyGodowns || pricing.rateGodowns.trim() !== "") &&
            money("rateGodowns", "Godown rate (₹/sq ft)", "Blank uses the shops rate.")}
        </div>
      </WizardCard>

      <WizardCard title="Extra charges" icon={<Calculator size={16} />} subtitle="Optional. Per-sq-ft charges use the pricing basis area.">
        <div className="pw-floor-rise">
          <TextField
            id="pw-floorRise"
            label="Floor rise (₹)"
            type="number"
            min={0}
            inputMode="decimal"
            value={pricing.floorRise}
            onChange={(e) => set({ floorRise: e.target.value })}
            error={err("floorRise")}
            placeholder="e.g. 20"
          />
          <SelectField
            id="pw-floorRiseBasis"
            label="Charged"
            value={pricing.floorRiseBasis}
            options={FLOOR_RISE_BASIS_OPTIONS}
            onChange={(e) => set({ floorRiseBasis: e.target.value as PricingForm["floorRiseBasis"] })}
          />
          <TextField
            id="pw-floorRiseFrom"
            label="From floor"
            type="number"
            min={1}
            inputMode="numeric"
            value={pricing.floorRiseFrom}
            onChange={(e) => set({ floorRiseFrom: e.target.value })}
            error={err("floorRiseFrom")}
            hint="Floors below it pay none."
          />
        </div>
        <div className="pw-grid">
          {money("plcRate", "PLC / view charge (₹/sq ft)", "For flat types ticked PLC (corner / view).")}
          {money("amenitiesRate", "Amenities / club (₹/sq ft)")}
          {money("legal", "Legal / documentation (₹, fixed)")}
          {money("other", "Other charges (₹, fixed)")}
        </div>
        <details className="pw-more">
          <summary>More charges</summary>
          <div className="pw-grid" style={{ marginTop: "0.75rem" }}>
            {money("sinking", "Sinking fund (₹, fixed)")}
            {money("overhead", "Overhead (₹, fixed)")}
          </div>
        </details>
      </WizardCard>

      <WizardCard
        title="Price check"
        icon={<CheckCircle2 size={16} />}
        subtitle="List price before GST = basic + floor rise + PLC + amenities + fixed charges."
      >
        {rows.length === 0 ? (
          <p className="muted text-sm" style={{ margin: 0 }}>
            Add flat types in Towers &amp; flat types to see their prices here.
          </p>
        ) : (
          <div className="pw-table-wrap">
            <table className="pw-table pw-table--check">
              <thead>
                <tr>
                  <th>Tower</th>
                  <th>Type</th>
                  <th>Configuration</th>
                  <th className="pw-num">Area</th>
                  <th className="pw-num">Basic</th>
                  <th className="pw-num">List price · lowest floor</th>
                  <th className="pw-num">List price · top floor</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.key}>
                    <td>{r.tower}</td>
                    <td>
                      <strong>{r.label}</strong>
                    </td>
                    <td>{r.configuration || "—"}</td>
                    <td className="pw-num">{sqft(r.area)}</td>
                    <td className="pw-num">{r.problem ? <span className="pw-problem">{r.problem}</span> : rupees(r.basic)}</td>
                    <td className="pw-num">
                      {r.lowPrice != null ? (
                        <>
                          {rupees(r.lowPrice)} <span className="muted text-xs">floor {r.lowFloor}</span>
                        </>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="pw-num">
                      {r.topPrice != null ? (
                        <>
                          {rupees(r.topPrice)} <span className="muted text-xs">floor {r.topFloor}</span>
                        </>
                      ) : (
                        "—"
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </WizardCard>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------------------
// Step 4 — Parking
// ---------------------------------------------------------------------------------------------------------------

export function ParkingStep({ state, update, check, project, existing }: StepProps & { existing: ExistingParking }) {
  const parking = state.parking;
  const setRow = (type: ParkingType, patch: Partial<ParkingRowForm>) =>
    update((s) => ({ ...s, parking: { ...s.parking, [type]: { ...s.parking[type], ...patch } } }));
  const adds = parkingAdds(parking, existing);
  const total = parkingTotal(parking);
  const olderPrice = project?.parkingCost ?? null;

  return (
    <div className="pw-step">
      <StepIntro title="Parking">
        Tick each type you offer. Spots are numbered per type across the whole project: CP01, CP02 … DP01 …
      </StepIntro>
      <StepErrors check={check} />
      <WizardCard title="Parking spots" icon={<Car size={16} />}>
        <div className="pw-table-wrap">
          <table className="pw-table pw-table--parking">
            <thead>
              <tr>
                <th>Type</th>
                <th>Quantity</th>
                <th>Price (₹ per spot)</th>
                <th>On Save</th>
              </tr>
            </thead>
            <tbody>
              {WIZARD_PARKING_TYPES.map((type) => {
                const row = parking[type];
                const built = existing.byType[type] ?? 0;
                return (
                  <tr key={type} className={row.on ? undefined : "is-off"}>
                    <td>
                      <label className="pw-check">
                        <input
                          type="checkbox"
                          checked={row.on}
                          // Spots that exist keep their type ticked — Save never removes them.
                          disabled={built > 0}
                          title={built > 0 ? `${built} spots exist — this type stays` : undefined}
                          onChange={(e) => setRow(type, { on: e.target.checked })}
                        />
                        <span>
                          <strong>{WIZARD_PARKING_LABEL[type]}</strong> <span className="muted">({type})</span>
                        </span>
                      </label>
                    </td>
                    <td>
                      <CellInput
                        type="number"
                        min={built}
                        max={5000}
                        inputMode="numeric"
                        disabled={!row.on}
                        value={row.count}
                        placeholder="0"
                        aria-label={`How many ${WIZARD_PARKING_LABEL[type]} spots`}
                        onChange={(e) => setRow(type, { count: e.target.value })}
                        error={fieldError(check, fieldKey.parking(type, "count"))}
                      />
                    </td>
                    <td>
                      <CellInput
                        type="number"
                        min={0}
                        inputMode="decimal"
                        disabled={!row.on}
                        value={row.price}
                        placeholder={olderPrice != null ? String(olderPrice) : "e.g. 300000"}
                        aria-label={`Price per ${WIZARD_PARKING_LABEL[type]} spot`}
                        onChange={(e) => setRow(type, { price: e.target.value })}
                        error={fieldError(check, fieldKey.parking(type, "price"))}
                      />
                    </td>
                    <td className="text-sm">
                      {built > 0 && <span className="muted">{built} exist</span>}
                      {built > 0 && adds[type] ? " · " : null}
                      {adds[type] ? <strong className="pw-adds">+{adds[type]} new</strong> : null}
                      {!built && !adds[type] ? <span className="muted">—</span> : null}
                    </td>
                  </tr>
                );
              })}
              {existing.untyped > 0 && (
                <tr className="is-off">
                  <td>
                    <strong>Other (kept)</strong>
                  </td>
                  <td colSpan={3} className="muted text-sm">
                    {existing.untyped} older spot{existing.untyped === 1 ? "" : "s"} numbered before parking types — kept as{" "}
                    {existing.untyped === 1 ? "it is" : "they are"}.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="pw-summary">
          Total parking: <strong>{total.toLocaleString("en-IN")}</strong>
          {existing.untyped > 0 && <span className="muted"> + {existing.untyped} other</span>}
        </div>
        <p className="muted text-xs" style={{ margin: 0 }}>
          {olderPrice != null
            ? `A blank price uses the project's older parking price, ${formatInr(olderPrice)}. `
            : "Leave a price blank if that type isn't sold separately. "}
          Existing spots keep their price; lowering a quantity never removes spots.
        </p>
      </WizardCard>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------------------
// Step 5 — Payment plan
// ---------------------------------------------------------------------------------------------------------------

export function PlanStep({ state, update, check }: StepProps) {
  const rows = state.plan;
  const setPlan = (change: (rows: PlanRowForm[]) => PlanRowForm[]) =>
    update((s) => ({ ...s, plan: change(s.plan), planDirty: true }));
  const setRow = (key: string, patch: Partial<PlanRowForm>) =>
    setPlan((prev) => prev.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  const move = (index: number, by: -1 | 1) =>
    setPlan((prev) => {
      const next = [...prev];
      const [row] = next.splice(index, 1);
      next.splice(index + by, 0, row);
      return next;
    });
  const total = planTotal(rows);
  const totalOk = Math.abs(total - 100) <= 0.01;
  const err = (key: string, field: "label" | "percent" | "days" | "date") => fieldError(check, fieldKey.milestone(key, field));
  const legacyWarning = legacyPlanWarning(rows, { dirty: state.planDirty, legacy: state.planLegacy });

  return (
    <div className="pw-step">
      <StepIntro title="Payment plan">When buyers pay. Name each milestone the way you do.</StepIntro>
      <StepErrors check={check} />
      {legacyWarning && <Note tone="warn">{legacyWarning}</Note>}
      <WizardCard
        title="Milestones"
        icon={<ListChecks size={16} />}
        subtitle="% of the booking's price (box price + GST). Stage / possession / registration milestones are demanded when you mark them reached on the project page."
      >
        {rows.length === 0 ? (
          <div className="pw-empty">
            <p className="muted" style={{ margin: 0 }}>
              No payment plan yet. A plan is optional — bookings can still get one of their own.
            </p>
            <div className="row" style={{ gap: "0.5rem", justifyContent: "center" }}>
              <Button variant="secondary" size="sm" icon={<Wand2 size={14} />} onClick={() => setPlan(() => samplePlan())}>
                Start from a sample plan
              </Button>
              <Button variant="ghost" size="sm" icon={<Plus size={14} />} onClick={() => setPlan(() => [blankMilestone([])])}>
                Add milestone
              </Button>
            </div>
          </div>
        ) : (
          <>
            <div className="pw-table-wrap">
              <table className="pw-table pw-table--plan">
                <thead>
                  <tr>
                    <th className="pw-col-order" aria-label="Order" />
                    <th>
                      <Req>Milestone name</Req>
                    </th>
                    <th className="pw-col-pct">
                      <Req>%</Req>
                    </th>
                    <th>
                      <Req>Due on</Req>
                    </th>
                    <th className="pw-col-when">When</th>
                    <th className="pw-col-del" aria-label="Remove" />
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => (
                    <tr key={r.key}>
                      <td className="pw-col-order">
                        <div className="pw-order">
                          <button type="button" className="btn btn--ghost btn--icon" disabled={i === 0} onClick={() => move(i, -1)} aria-label="Move up">
                            <ArrowUp size={13} />
                          </button>
                          <button
                            type="button"
                            className="btn btn--ghost btn--icon"
                            disabled={i === rows.length - 1}
                            onClick={() => move(i, 1)}
                            aria-label="Move down"
                          >
                            <ArrowDown size={13} />
                          </button>
                        </div>
                      </td>
                      <td>
                        <CellInput
                          value={r.label}
                          maxLength={120}
                          placeholder={i === 0 ? "e.g. Booking amount" : i === 1 ? "e.g. Agreement" : "e.g. Foundation complete"}
                          aria-label="Milestone name"
                          onChange={(e) => setRow(r.key, { label: e.target.value })}
                          error={err(r.key, "label")}
                        />
                      </td>
                      <td>
                        <CellInput
                          type="number"
                          min={0}
                          max={100}
                          step="0.01"
                          inputMode="decimal"
                          value={r.percent}
                          aria-label="Percent"
                          onChange={(e) => setRow(r.key, { percent: e.target.value })}
                          error={err(r.key, "percent")}
                        />
                      </td>
                      <td>
                        <select
                          className="select"
                          value={r.dueOn}
                          aria-label="Due on"
                          onChange={(e) => setRow(r.key, { dueOn: e.target.value as PlanDueOn })}
                        >
                          {DUE_ON_OPTIONS.map((o) => (
                            <option key={o.value} value={o.value}>
                              {o.label}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td>
                        {r.dueOn === "days_after_booking" ? (
                          <div className="pw-days">
                            <CellInput
                              type="number"
                              min={1}
                              max={3650}
                              inputMode="numeric"
                              value={r.days}
                              aria-label="Days after booking"
                              onChange={(e) => setRow(r.key, { days: e.target.value })}
                              error={err(r.key, "days")}
                            />
                            <span className="muted text-sm">days</span>
                          </div>
                        ) : r.dueOn === "on_date" ? (
                          <CellInput
                            type="date"
                            value={r.dueDate}
                            aria-label="Due date"
                            onChange={(e) => setRow(r.key, { dueDate: e.target.value })}
                            error={err(r.key, "date")}
                          />
                        ) : (
                          <span className="muted text-sm">
                            {r.dueOn === "on_booking" ? "The booking date" : "When you mark it reached"}
                          </span>
                        )}
                      </td>
                      <td className="pw-col-del">
                        <button
                          type="button"
                          className="btn btn--ghost btn--icon"
                          onClick={() => setPlan((prev) => prev.filter((x) => x.key !== r.key))}
                          aria-label={`Remove ${r.label || "milestone"}`}
                        >
                          <Trash2 size={14} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="row row--between" style={{ alignItems: "center" }}>
              <Button
                variant="ghost"
                size="sm"
                icon={<Plus size={14} />}
                onClick={() => setPlan((prev) => [...prev, blankMilestone(prev.map((r) => r.key))])}
              >
                Add milestone
              </Button>
              <div className={`pw-total ${totalOk ? "pw-total--ok" : "pw-total--bad"}`} role="status">
                Total: {total}%{totalOk ? " ✓" : ` — must be 100%`}
              </div>
            </div>
          </>
        )}
      </WizardCard>
    </div>
  );
}
