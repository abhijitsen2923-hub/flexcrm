// Project wizard steps 6 (Preview — the server's plan of exactly what Save creates) and 7 (Review & save).
import { useState, type ReactNode } from "react";
import { Building, Car, ChevronLeft, ChevronRight, ClipboardList, IndianRupee, ListChecks, Pencil, RefreshCw, Sparkles } from "lucide-react";
import { Button, KpiCard } from "../../../components";
import { LoadingBlock } from "../../../components/ui/Spinner";
import type { InventoryPreview, PlannedUnit } from "../../../services/inventory";
import type { Project } from "../../../types/realestate";
import { formatDate, formatInr } from "../../../utils/format";
import {
  FLOOR_RISE_BASIS_OPTIONS,
  PRICING_BASIS_OPTIONS,
  PROJECT_TYPE_OPTIONS,
  STEP_INFO,
  STEP_PARKING,
  STEP_PLAN,
  STEP_PRICING,
  STEP_TOWERS,
  WIZARD_PARKING_LABEL,
  WIZARD_PARKING_TYPES,
  dueOnText,
  flatsSummary,
  isEditableTower,
  legacySummary,
  parkingTotal,
  planTotal,
  positionOfCode,
  pricingNumbers,
  toInt,
  toNum,
  type ExistingParking,
  type WizardState,
} from "../../../utils/projectWizard";
import { Note, StepIntro, WizardCard, rupees, sqft } from "./ProjectWizardParts";

export type PreviewState =
  | { status: "idle" }
  | { status: "loading"; key: string }
  | { status: "ok"; key: string; data: InventoryPreview }
  | { status: "error"; key: string; message: string };

const FLOORS_PER_PAGE = 30;

/** "Types A–D" / "Types A, C" / "Type A". */
function typesText(codes: string[]): string {
  if (codes.length === 0) return "";
  if (codes.length === 1) return `Type ${codes[0]}`;
  const positions = codes.map((c) => positionOfCode(c) ?? 0);
  const contiguous = positions.every((p, i) => i === 0 || p === positions[i - 1] + 1);
  return contiguous ? `Types ${codes[0]}–${codes[codes.length - 1]}` : `Types ${codes.join(", ")}`;
}

function count(n: number, one: string, many: string): string {
  return `${n.toLocaleString("en-IN")} ${n === 1 ? one : many}`;
}

function unitTitle(u: PlannedUnit): string {
  return [
    u.unitNumber,
    u.flatType ? `Type ${u.flatType}` : u.unitType === "shop" ? "Shop" : u.unitType === "godown" ? "Godown" : null,
    u.configuration,
    sqft(u.area),
    u.basePrice != null ? `Basic ${formatInr(u.basePrice)}` : "No price yet",
    u.hasPlc ? "PLC" : null,
  ]
    .filter(Boolean)
    .join(" · ");
}

// ---------------------------------------------------------------------------------------------------------------
// Step 6 — Preview
// ---------------------------------------------------------------------------------------------------------------

export function PreviewStep({ preview, onRetry, editing }: { preview: PreviewState; onRetry: () => void; editing: boolean }) {
  return (
    <div className="pw-step">
      <StepIntro title="Preview">
        Exactly what Save will create{editing ? " (existing units stay as they are)" : ""}. Nothing is saved yet.
      </StepIntro>
      {(preview.status === "idle" || preview.status === "loading") && <LoadingBlock label="Working out the units…" />}
      {preview.status === "error" && (
        <div className="error-banner pw-errors" role="alert">
          <div>{preview.message}</div>
          <div>
            <Button variant="secondary" size="sm" icon={<RefreshCw size={14} />} onClick={onRetry}>
              Try again
            </Button>
          </div>
        </div>
      )}
      {preview.status === "ok" && <PreviewResult data={preview.data} />}
    </div>
  );
}

function PreviewResult({ data }: { data: InventoryPreview }) {
  const parking = data.parking.filter((p) => p.newNumbers.length > 0 || p.existing > 0);
  if (data.newUnits === 0 && data.newParking === 0) {
    return (
      <>
        <div className="pw-empty">
          <Sparkles size={22} aria-hidden="true" />
          <p style={{ margin: 0 }}>
            <strong>Nothing new to add.</strong> Save keeps every unit and parking spot as it is.
          </p>
        </div>
        {data.notes.length > 0 && <NotesCard notes={data.notes} />}
      </>
    );
  }
  return (
    <>
      <div className="kpi-grid">
        <KpiCard label="New units" value={data.newUnits.toLocaleString("en-IN")} hint="Flats, shops and godowns" />
        <KpiCard label="New parking spots" value={data.newParking.toLocaleString("en-IN")} />
      </div>
      {data.towers.map((tower) => (
        <TowerPreview key={tower.towerId ?? tower.name} tower={tower} />
      ))}
      {parking.length > 0 && (
        <WizardCard title="Parking" icon={<Car size={16} />}>
          <ul className="pw-list">
            {parking.map((p) => {
              const nums = p.newNumbers;
              const range = nums.length === 0 ? null : nums.length === 1 ? nums[0] : `${nums[0]}–${nums[nums.length - 1]}`;
              return (
                <li key={p.parkingType}>
                  <strong>
                    {WIZARD_PARKING_LABEL[p.parkingType]} ({p.parkingType})
                  </strong>
                  {": "}
                  {range ? `${range} (${nums.length} new)` : "nothing new"}
                  {p.existing > 0 && <span className="muted"> · {p.existing} exist</span>}
                  {range && p.price != null && <span className="muted"> · {formatInr(p.price)} each</span>}
                </li>
              );
            })}
          </ul>
        </WizardCard>
      )}
      {data.notes.length > 0 && <NotesCard notes={data.notes} />}
    </>
  );
}

function NotesCard({ notes }: { notes: string[] }) {
  return (
    <Note>
      {notes.length === 1 ? (
        notes[0]
      ) : (
        <ul className="pw-list">
          {notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      )}
    </Note>
  );
}

function TowerPreview({ tower }: { tower: InventoryPreview["towers"][number] }) {
  const [page, setPage] = useState(0);
  const units = tower.newUnits;
  const flats = units.filter((u) => u.unitType === "residential");
  const shops = units.filter((u) => u.unitType === "shop").length;
  const godowns = units.filter((u) => u.unitType === "godown").length;
  const codes = [...new Set(flats.map((u) => u.flatType).filter((c): c is string => !!c))].sort(
    (a, b) => (positionOfCode(a) ?? 999) - (positionOfCode(b) ?? 999)
  );
  // Columns: one per flat type, then flats without a type, shops, godowns.
  const columns: { key: string; label: string; match: (u: PlannedUnit) => boolean }[] = [
    ...codes.map((code) => ({ key: code, label: code, match: (u: PlannedUnit) => u.unitType === "residential" && u.flatType === code })),
    ...(flats.some((u) => !u.flatType)
      ? [{ key: "flats", label: "Flats", match: (u: PlannedUnit) => u.unitType === "residential" && !u.flatType }]
      : []),
    ...(shops ? [{ key: "shops", label: "Shops", match: (u: PlannedUnit) => u.unitType === "shop" }] : []),
    ...(godowns ? [{ key: "godowns", label: "Godowns", match: (u: PlannedUnit) => u.unitType === "godown" }] : []),
  ];
  const floors = [...new Set(units.map((u) => u.floor))].sort((a, b) => b - a); // top floor first
  const pages = Math.max(1, Math.ceil(floors.length / FLOORS_PER_PAGE));
  const current = Math.min(page, pages - 1);
  const shown = floors.slice(current * FLOORS_PER_PAGE, (current + 1) * FLOORS_PER_PAGE);
  const byCell = new Map<string, PlannedUnit[]>();
  for (const u of units) {
    const column = columns.find((c) => c.match(u));
    if (!column) continue;
    const key = `${u.floor}|${column.key}`;
    byCell.set(key, [...(byCell.get(key) ?? []), u]);
  }

  const parts = [
    `${count(flats.length, "new flat", "new flats")}${codes.length ? ` (${typesText(codes)})` : ""}`,
    ...(shops ? [count(shops, "new shop", "new shops")] : []),
    ...(godowns ? [count(godowns, "new godown", "new godowns")] : []),
    `${tower.existingUnits.toLocaleString("en-IN")} existing`,
  ];

  return (
    <WizardCard title={tower.name} icon={<Building size={16} />} subtitle={parts.join(" · ")}>
      {units.length === 0 ? (
        <p className="muted text-sm" style={{ margin: 0 }}>
          Nothing new in this tower.
        </p>
      ) : (
        <>
          <div className="pw-table-wrap">
            <table className="pw-grid-table">
              <thead>
                <tr>
                  <th scope="col">Floor</th>
                  {columns.map((c) => (
                    <th key={c.key} scope="col">
                      {c.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {shown.map((floor) => (
                  <tr key={floor}>
                    <th scope="row">{floor === 0 ? "Ground" : floor}</th>
                    {columns.map((c) => (
                      <td key={c.key}>
                        <div className="pw-units">
                          {(byCell.get(`${floor}|${c.key}`) ?? []).map((u) => (
                            <span key={u.unitNumber} className={`pw-unit${u.hasPlc ? " pw-unit--plc" : ""}`} title={unitTitle(u)}>
                              {u.unitNumber}
                            </span>
                          ))}
                        </div>
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {pages > 1 && (
            <div className="pw-pager">
              <Button variant="ghost" size="sm" icon={<ChevronLeft size={14} />} disabled={current === 0} onClick={() => setPage(current - 1)}>
                Higher floors
              </Button>
              <span className="muted text-sm">
                Floors {shown[0]}–{shown[shown.length - 1]} · {floors.length} floors
              </span>
              <Button variant="ghost" size="sm" disabled={current >= pages - 1} onClick={() => setPage(current + 1)}>
                Lower floors <ChevronRight size={14} />
              </Button>
            </div>
          )}
          {units.some((u) => u.hasPlc) && <p className="muted text-xs" style={{ margin: 0 }}>Outlined units carry the PLC charge.</p>}
        </>
      )}
    </WizardCard>
  );
}

// ---------------------------------------------------------------------------------------------------------------
// Step 7 — Review & save
// ---------------------------------------------------------------------------------------------------------------

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <>
      <dt>{label}</dt>
      <dd>{children}</dd>
    </>
  );
}

export function ReviewStep({
  state,
  project,
  existingParking,
  preview,
  coverFileName,
  saveError,
  goTo,
}: {
  state: WizardState;
  project: Project | null;
  existingParking: ExistingParking;
  preview: PreviewState; // the server's plan for exactly what's on the page now
  coverFileName: string | null;
  saveError: string | null;
  goTo: (step: number) => void;
}) {
  const { info, pricing, parking, plan, towers } = state;
  const p = pricingNumbers(pricing);
  const edit = (step: number) => (
    <Button variant="ghost" size="sm" icon={<Pencil size={13} />} onClick={() => goTo(step)}>
      Edit
    </Button>
  );
  const flats = towers.reduce((sum, t) => sum + (isEditableTower(t) ? flatsSummary(t).flats : legacySummary(t).flats), 0);
  const fixed = (p.legal ?? 0) + (p.other ?? 0) + (p.sinking ?? 0) + (p.overhead ?? 0);
  const total = planTotal(plan);
  const parkingOn = WIZARD_PARKING_TYPES.filter((t) => parking[t].on);

  return (
    <div className="pw-step">
      <StepIntro title="Review & save">Check everything, then save. You can change any of it later from Edit project.</StepIntro>
      {saveError && (
        <div className="error-banner" role="alert">
          {saveError}
        </div>
      )}

      <WizardCard title="What Save does" icon={<Sparkles size={16} />}>
        {preview.status === "error" ? (
          <div className="pw-problem">{preview.message}</div>
        ) : (
          <p style={{ margin: 0 }}>
            {preview.status === "ok"
              ? preview.data.newUnits + preview.data.newParking === 0
                ? project
                  ? "Saves the project's details. No new units or parking spots are needed."
                  : "Creates the project. It has no units or parking spots yet."
                : `${project ? "Saves the project's details and adds" : "Creates the project with"} ${count(preview.data.newUnits, "unit", "units")} and ${count(preview.data.newParking, "parking spot", "parking spots")}.`
              : "Working out exactly what Save creates…"}
            {project ? " Existing units, prices and bookings are never changed." : ""}
          </p>
        )}
      </WizardCard>

      <div className="pw-review">
        <WizardCard title="Project info" icon={<ClipboardList size={16} />} actions={edit(STEP_INFO)}>
          <dl className="pw-dl">
            <Row label="Name">{info.name.trim()}</Row>
            <Row label="Builder">{info.builder.trim()}</Row>
            <Row label="Type">{PROJECT_TYPE_OPTIONS.find((o) => o.value === info.projectType)?.label ?? "—"}</Row>
            <Row label="Location">
              {info.location.trim()}, {info.city.trim()}
              {info.pinCode.trim() ? ` ${info.pinCode.trim()}` : ""}
            </Row>
            {info.landmark.trim() && <Row label="Landmark">{info.landmark.trim()}</Row>}
            <Row label="RERA">{info.rera.trim() || "—"}</Row>
            <Row label="Cover image">{coverFileName ?? (project?.media.some((m) => m.type === "image") ? "Unchanged" : "None")}</Row>
          </dl>
        </WizardCard>

        <WizardCard
          title="Towers"
          icon={<Building size={16} />}
          subtitle={`${count(towers.length, "tower", "towers")} · ${count(flats, "flat", "flats")}`}
          actions={edit(STEP_TOWERS)}
        >
          {towers.length === 0 ? (
            <p className="muted text-sm" style={{ margin: 0 }}>
              No towers yet.
            </p>
          ) : (
            <ul className="pw-list">
              {towers.map((t) => {
                if (!isEditableTower(t)) {
                  return (
                    <li key={t.key}>
                      <strong>{t.name}</strong> — set up before flat types, kept as it is ({count(t.existingUnits.length, "unit", "units")})
                    </li>
                  );
                }
                const s = flatsSummary(t);
                const perFloor = s.perFloorMin === s.perFloorMax ? `${s.perFloorMax}` : `${s.perFloorMin}–${s.perFloorMax}`;
                return (
                  <li key={t.key}>
                    <strong>{t.name.trim()}</strong> — {count(toInt(t.floors) ?? 0, "floor", "floors")} · {count(t.flatTypes.length, "type", "types")} ·{" "}
                    {perFloor} per floor · {count(s.flats, "flat", "flats")}
                    {s.shops ? ` · ${count(s.shops, "shop", "shops")}` : ""}
                    {s.godowns ? ` · ${count(s.godowns, "godown", "godowns")}` : ""}
                    <span className="muted"> · {t.prefix.trim()}101 …</span>
                  </li>
                );
              })}
            </ul>
          )}
        </WizardCard>

        <WizardCard title="Pricing" icon={<IndianRupee size={16} />} actions={edit(STEP_PRICING)}>
          <dl className="pw-dl">
            <Row label="Basis">{PRICING_BASIS_OPTIONS.find((o) => o.value === pricing.basis)?.label}</Row>
            <Row label="Flats">{p.rateFlats != null ? `${rupees(p.rateFlats)} / sq ft` : "—"}</Row>
            {(p.rateShops != null || p.rateGodowns != null) && (
              <Row label="Shops / godowns">
                {p.rateShops != null ? `${rupees(p.rateShops)} / sq ft` : "—"}
                {p.rateGodowns != null ? ` · godowns ${rupees(p.rateGodowns)} / sq ft` : ""}
              </Row>
            )}
            <Row label="Floor rise">
              {p.floorRise
                ? `${rupees(p.floorRise)} ${FLOOR_RISE_BASIS_OPTIONS.find((o) => o.value === p.floorRiseBasis)?.label.replace("₹ ", "")} from floor ${p.floorRiseFrom}`
                : "—"}
            </Row>
            <Row label="PLC / view">{p.plcRate ? `${rupees(p.plcRate)} / sq ft` : "—"}</Row>
            <Row label="Amenities">{p.amenitiesRate ? `${rupees(p.amenitiesRate)} / sq ft` : "—"}</Row>
            <Row label="Fixed charges">{fixed ? rupees(fixed) : "—"}</Row>
          </dl>
        </WizardCard>

        <WizardCard
          title="Parking"
          icon={<Car size={16} />}
          subtitle={`${parkingTotal(parking).toLocaleString("en-IN")} spots${existingParking.untyped ? ` + ${existingParking.untyped} other` : ""}`}
          actions={edit(STEP_PARKING)}
        >
          {parkingOn.length === 0 ? (
            <p className="muted text-sm" style={{ margin: 0 }}>
              No parking.
            </p>
          ) : (
            <ul className="pw-list">
              {parkingOn.map((t) => {
                const price = toNum(parking[t].price);
                return (
                  <li key={t}>
                    <strong>
                      {WIZARD_PARKING_LABEL[t]} ({t})
                    </strong>
                    : {(toInt(parking[t].count) ?? 0).toLocaleString("en-IN")}
                    {price != null ? ` × ${formatInr(price)}` : ""}
                  </li>
                );
              })}
            </ul>
          )}
        </WizardCard>

        <WizardCard
          title="Payment plan"
          icon={<ListChecks size={16} />}
          subtitle={plan.length ? `${count(plan.length, "milestone", "milestones")} · ${total} %` : undefined}
          actions={edit(STEP_PLAN)}
        >
          {plan.length === 0 ? (
            <p className="muted text-sm" style={{ margin: 0 }}>
              No payment plan.
            </p>
          ) : (
            <ol className="pw-list pw-list--numbered">
              {plan.map((m) => (
                <li key={m.key}>
                  <strong>{m.label.trim()}</strong> — {toNum(m.percent) ?? 0}% · {dueOnText(m, (iso) => formatDate(iso))}
                </li>
              ))}
            </ol>
          )}
          {project && state.planLegacy && !state.planDirty && (
            <p className="muted text-xs" style={{ margin: 0 }}>
              The older dated schedule is kept as it is.
            </p>
          )}
        </WizardCard>
      </div>
    </div>
  );
}
