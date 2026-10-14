// Project wizard step 2 — towers and their flat types. Each flat type is one flat on every floor of its range, so
// the number of types IS the number of flats per floor (A-101 = Type A, A-102 = Type B …).
import type { ReactNode } from "react";
import { Building, Layers, Plus, Store, Trash2, Undo2, Wand2 } from "lucide-react";
import { Button, TextField } from "../../../components";
import {
  CONFIGURATION_SUGGESTIONS,
  MAX_FLAT_TYPES,
  MAX_OTHER_ROWS,
  addFlatType,
  areaOrderWarning,
  blankOtherUnit,
  conversionWarning,
  convertLegacyTower,
  estimateAdds,
  existingTopFloor,
  fieldKey,
  flatsFooterText,
  isEditableTower,
  legacySummaryText,
  newTowerForm,
  removedTypesWithUnits,
  renameTower,
  revertLegacyTower,
  toInt,
  type FlatTypeForm,
  type OtherUnitForm,
  type TowerForm,
} from "../../../utils/projectWizard";
import { CellInput, Note, Req, StepErrors, StepIntro, fieldError, type StepProps } from "./ProjectWizardParts";

const CONFIG_LIST_ID = "pw-configurations";

export function TowersStep({ state, update, check }: StepProps) {
  const setTower = (key: string, change: (tower: TowerForm) => TowerForm) =>
    update((s) => ({ ...s, towers: s.towers.map((t) => (t.key === key ? change(t) : t)) }));
  const removeTower = (key: string) => update((s) => ({ ...s, towers: s.towers.filter((t) => t.key !== key) }));
  const addTower = () =>
    update((s) => {
      // Copy the last tower that has flat types (an older read-only tower has none to copy).
      const previous = [...s.towers].reverse().find((t) => isEditableTower(t) && t.flatTypes.length > 0) ?? s.towers[s.towers.length - 1];
      return { ...s, towers: [...s.towers, newTowerForm(previous, s.towers.map((t) => t.name))] };
    });

  return (
    <div className="pw-step">
      <StepIntro title="Towers & flat types">
        Each flat type is one flat on every floor — 4 types make 4 flats per floor. Its letter is its position:
        A-101 is Type A, A-102 is Type B, A-201 is Type A on floor 2.
      </StepIntro>
      <StepErrors check={check} />
      <datalist id={CONFIG_LIST_ID}>
        {CONFIGURATION_SUGGESTIONS.map((c) => (
          <option key={c} value={c} />
        ))}
      </datalist>

      {state.towers.length === 0 && (
        <div className="pw-empty">
          <p className="muted" style={{ margin: 0 }}>
            No towers yet. Add one now, or save the project and add towers later from Edit project.
          </p>
        </div>
      )}

      {state.towers.map((tower) =>
        isEditableTower(tower) ? (
          <TowerCard
            key={tower.key}
            tower={tower}
            check={check}
            onChange={(change) => setTower(tower.key, change)}
            onRemove={tower.towerId ? undefined : () => removeTower(tower.key)}
            onRevert={tower.converted ? () => setTower(tower.key, revertLegacyTower) : undefined}
          />
        ) : (
          <LegacyTowerCard key={tower.key} tower={tower} onConvert={() => setTower(tower.key, convertLegacyTower)} />
        )
      )}

      <div>
        <Button variant="secondary" icon={<Plus size={16} />} onClick={addTower}>
          Add tower
        </Button>
      </div>
    </div>
  );
}

function LegacyTowerCard({ tower, onConvert }: { tower: TowerForm; onConvert: () => void }) {
  return (
    <section className="pw-card pw-tower">
      <header className="pw-card__head">
        <div className="pw-card__title">
          <Building size={16} />
          <span>{tower.name}</span>
          <span className="badge">Has {tower.existingUnits.length.toLocaleString("en-IN")} units</span>
        </div>
      </header>
      <div className="pw-card__body">
        <p style={{ margin: 0 }}>{legacySummaryText(tower)}</p>
        <div className="row" style={{ gap: "0.75rem" }}>
          <Button variant="secondary" size="sm" icon={<Wand2 size={14} />} onClick={onConvert}>
            Set up flat types
          </Button>
          <span className="muted text-sm">Until you do, Save leaves this tower exactly as it is.</span>
        </div>
      </div>
    </section>
  );
}

function TowerCard({
  tower,
  check,
  onChange,
  onRemove,
  onRevert,
}: {
  tower: TowerForm;
  check: StepProps["check"];
  onChange: (change: (tower: TowerForm) => TowerForm) => void;
  onRemove?: () => void;
  onRevert?: () => void;
}) {
  const err = (key: string) => fieldError(check, key);
  const top = toInt(tower.floors);
  const existingTop = existingTopFloor(tower);
  const removed = removedTypesWithUnits(tower);
  const adds = tower.towerId ? estimateAdds(tower) : null;
  const addsTotal = adds ? adds.flats + adds.shops + adds.godowns : 0;
  const converting = conversionWarning(tower);
  const setType = (code: string, patch: Partial<FlatTypeForm>) =>
    onChange((t) => ({ ...t, flatTypes: t.flatTypes.map((x) => (x.code === code ? { ...x, ...patch } : x)) }));
  const setOther = (key: string, patch: Partial<OtherUnitForm>) =>
    onChange((t) => ({ ...t, others: t.others.map((x) => (x.key === key ? { ...x, ...patch } : x)) }));
  const prefixExample = tower.prefix.trim() ? `${tower.prefix.trim()}101, ${tower.prefix.trim()}102 …` : "e.g. A- gives A-101";

  return (
    <section className="pw-card pw-tower">
      <header className="pw-card__head">
        <div className="pw-card__title">
          <Building size={16} />
          <span>{tower.name.trim() || "New tower"}</span>
          {tower.towerId ? (
            <span className="badge">Has {tower.existingUnits.length.toLocaleString("en-IN")} units</span>
          ) : (
            <span className="badge badge--success">New</span>
          )}
          {adds && addsTotal > 0 && <span className="badge badge--info">Save adds about {addsTotal.toLocaleString("en-IN")}</span>}
        </div>
        <div className="pw-card__actions">
          {onRevert && (
            <Button variant="ghost" size="sm" icon={<Undo2 size={14} />} onClick={onRevert}>
              Undo flat types
            </Button>
          )}
          {onRemove && (
            <Button variant="ghost" size="sm" icon={<Trash2 size={14} />} onClick={onRemove}>
              Remove tower
            </Button>
          )}
        </div>
      </header>
      <div className="pw-card__body">
        <div className="pw-grid pw-grid--3">
          <TextField
            id={`pw-tower-name-${tower.key}`}
            label={<Req>Tower name</Req>}
            value={tower.name}
            maxLength={100}
            onChange={(e) => onChange((t) => renameTower(t, e.target.value))}
            error={err(fieldKey.tower(tower.key, "name"))}
          />
          <TextField
            id={`pw-tower-floors-${tower.key}`}
            label={<Req>Number of floors</Req>}
            type="number"
            min={1}
            max={200}
            inputMode="numeric"
            value={tower.floors}
            onChange={(e) => onChange((t) => ({ ...t, floors: e.target.value }))}
            error={err(fieldKey.tower(tower.key, "floors"))}
            hint="Not counting the ground floor."
          />
          <TextField
            id={`pw-tower-prefix-${tower.key}`}
            label={<Req>Unit number prefix</Req>}
            value={tower.prefix}
            maxLength={8}
            onChange={(e) => onChange((t) => ({ ...t, prefix: e.target.value, prefixTouched: true }))}
            error={err(fieldKey.tower(tower.key, "prefix"))}
            hint={prefixExample}
          />
        </div>

        {tower.towerId && top != null && top >= 1 && top < existingTop && (
          <Note tone="warn">
            Floors above {top} already have units — they're kept and the tower keeps {existingTop} floors. Archive them
            from the project's unit list if they shouldn't exist.
          </Note>
        )}
        {tower.towerId && tower.originalPrefix != null && tower.prefix.trim() !== tower.originalPrefix.trim() && (
          <Note>A new prefix only applies to units added from now on; existing units keep their numbers.</Note>
        )}
        {converting && <Note tone="warn">{converting}</Note>}

        <div className="pw-subhead">
          <Layers size={15} aria-hidden="true" />
          <strong>Flat types</strong>
          <span className="muted text-sm">— one flat of each type on every floor</span>
        </div>
        {tower.flatTypes.length > 0 && (
          <div className="pw-table-wrap">
            <table className="pw-table pw-table--types">
              <thead>
                <tr>
                  <th className="pw-col-code">Type</th>
                  <th>Configuration</th>
                  <th className="pw-col-area">Carpet</th>
                  <th className="pw-col-area">Built-up</th>
                  <th className="pw-col-area">
                    <Req>Super built-up</Req>
                  </th>
                  <th className="pw-col-plc" title="Corner / view — adds the PLC charge">
                    PLC
                  </th>
                  <th className="pw-col-floors">Floors</th>
                  <th className="pw-col-del" aria-label="Remove" />
                </tr>
              </thead>
              <tbody>
                {tower.flatTypes.map((type) => (
                  <FlatTypeRow
                    key={type.code}
                    towerKey={tower.key}
                    type={type}
                    top={top}
                    check={check}
                    onChange={(patch) => setType(type.code, patch)}
                    onRemove={() => onChange((t) => ({ ...t, flatTypes: t.flatTypes.filter((x) => x.code !== type.code) }))}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
        {err(fieldKey.tower(tower.key, "units")) && <div className="field__error">{err(fieldKey.tower(tower.key, "units"))}</div>}
        <div className="row" style={{ gap: "0.5rem" }}>
          <Button
            variant="ghost"
            size="sm"
            icon={<Plus size={14} />}
            disabled={tower.flatTypes.length >= MAX_FLAT_TYPES}
            onClick={() => onChange((t) => addFlatType(t) ?? t)}
          >
            Add flat type
          </Button>
          <span className="muted text-xs">PLC: tick corner / view types — they get the PLC charge from Pricing.</span>
        </div>
        {tower.flatTypes.length > 0 && (
          <div className="pw-grid pw-grid--3">
            <TextField
              id={`pw-tower-skip-${tower.key}`}
              label="Floors with no flats"
              value={tower.skipFloors}
              placeholder="e.g. 5, 12"
              onChange={(e) => onChange((t) => ({ ...t, skipFloors: e.target.value }))}
              error={err(fieldKey.tower(tower.key, "skipFloors"))}
              hint="Refuge floors and the like — no flat type gets a flat there. Leave blank if every floor has flats."
            />
          </div>
        )}
        {removed.length > 0 && (
          <Note tone="warn">
            {removed.map((r) => `Type ${r.code} (${r.units} flat${r.units === 1 ? "" : "s"})`).join(", ")}{" "}
            {removed.length === 1 ? "is" : "are"} no longer listed. Existing flats are kept; archive them from the
            project's unit list if they shouldn't exist.
          </Note>
        )}
        <div className="pw-summary">{flatsFooterText(tower)}</div>

        <div className="pw-subhead">
          <Store size={15} aria-hidden="true" />
          <strong>Shops / godowns</strong>
          <span className="muted text-sm">— optional, e.g. shops on the ground floor (floor 0)</span>
        </div>
        {tower.others.length > 0 && (
          <div className="pw-table-wrap">
            <table className="pw-table pw-table--others">
              <thead>
                <tr>
                  <th className="pw-col-kind">Kind</th>
                  <th className="pw-col-count">Per floor</th>
                  <th className="pw-col-floors">Floors</th>
                  <th className="pw-col-area">
                    <Req>Super built-up</Req>
                  </th>
                  <th className="pw-col-area">Carpet</th>
                  <th className="pw-col-area">Built-up</th>
                  <th className="pw-col-del" aria-label="Remove" />
                </tr>
              </thead>
              <tbody>
                {tower.others.map((o) => {
                  const e = (field: "perFloor" | "floors" | "area" | "carpet" | "builtUp") => err(fieldKey.other(tower.key, o.key, field));
                  const warning = areaOrderWarning({ carpet: o.carpet, builtUp: o.builtUp, superBuiltUp: o.area });
                  return (
                    <OtherRows key={o.key} warning={warning}>
                      <td>
                        <select
                          className="select"
                          value={o.unitType}
                          aria-label="Kind"
                          onChange={(ev) => setOther(o.key, { unitType: ev.target.value as OtherUnitForm["unitType"] })}
                        >
                          <option value="shop">Shop</option>
                          <option value="godown">Godown</option>
                        </select>
                      </td>
                      <td>
                        <CellInput type="number" min={1} max={200} inputMode="numeric" value={o.perFloor} aria-label="How many per floor" onChange={(ev) => setOther(o.key, { perFloor: ev.target.value })} error={e("perFloor")} />
                      </td>
                      <td>
                        <FloorRange
                          from={o.floorFrom}
                          to={o.floorTo}
                          onChange={(from, to) => setOther(o.key, { floorFrom: from, floorTo: to })}
                          error={e("floors")}
                        />
                      </td>
                      <td>
                        <CellInput type="number" min={0} inputMode="decimal" value={o.area} aria-label="Super built-up area (sq ft)" onChange={(ev) => setOther(o.key, { area: ev.target.value })} error={e("area")} />
                      </td>
                      <td>
                        <CellInput type="number" min={0} inputMode="decimal" value={o.carpet} aria-label="Carpet area (sq ft)" onChange={(ev) => setOther(o.key, { carpet: ev.target.value })} error={e("carpet")} />
                      </td>
                      <td>
                        <CellInput type="number" min={0} inputMode="decimal" value={o.builtUp} aria-label="Built-up area (sq ft)" onChange={(ev) => setOther(o.key, { builtUp: ev.target.value })} error={e("builtUp")} />
                      </td>
                      <td className="pw-col-del">
                        <button
                          type="button"
                          className="btn btn--ghost btn--icon"
                          onClick={() => onChange((t) => ({ ...t, others: t.others.filter((x) => x.key !== o.key) }))}
                          aria-label="Remove row"
                        >
                          <Trash2 size={14} />
                        </button>
                      </td>
                    </OtherRows>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        <div>
          <Button
            variant="ghost"
            size="sm"
            icon={<Plus size={14} />}
            disabled={tower.others.length >= MAX_OTHER_ROWS}
            onClick={() => onChange((t) => ({ ...t, others: [...t.others, blankOtherUnit("shop")] }))}
          >
            Add shops / godowns
          </Button>
        </div>
        {tower.towerId && tower.others.length < 1 && tower.existingUnits.some((u) => u.unitType !== "residential") && (
          <Note>This tower's existing shops / godowns are kept.</Note>
        )}
      </div>
    </section>
  );
}

function OtherRows({ warning, children }: { warning: string | null; children: ReactNode }) {
  return (
    <>
      <tr className={warning ? "has-note" : undefined}>{children}</tr>
      {warning && (
        <tr className="pw-row-note">
          <td colSpan={7}>{warning}</td>
        </tr>
      )}
    </>
  );
}

function FlatTypeRow({
  towerKey,
  type,
  top,
  check,
  onChange,
  onRemove,
}: {
  towerKey: string;
  type: FlatTypeForm;
  top: number | null;
  check: StepProps["check"];
  onChange: (patch: Partial<FlatTypeForm>) => void;
  onRemove: () => void;
}) {
  const e = (field: "super" | "carpet" | "builtUp" | "floors" | "configuration") => fieldError(check, fieldKey.flatType(towerKey, type.code, field));
  const warning = areaOrderWarning(type);
  return (
    <>
      <tr className={warning ? "has-note" : undefined}>
        <td className="pw-col-code">
          <span className="pw-code" title={`Type ${type.code} — position ${type.code} on every floor`}>
            {type.code}
          </span>
        </td>
        <td>
          <CellInput
            list={CONFIG_LIST_ID}
            value={type.configuration}
            maxLength={32}
            placeholder="e.g. 2 BHK"
            aria-label={`Type ${type.code} configuration`}
            onChange={(ev) => onChange({ configuration: ev.target.value })}
            error={e("configuration")}
          />
        </td>
        <td>
          <CellInput type="number" min={0} inputMode="decimal" value={type.carpet} placeholder="sq ft" aria-label={`Type ${type.code} carpet area (sq ft)`} onChange={(ev) => onChange({ carpet: ev.target.value })} error={e("carpet")} />
        </td>
        <td>
          <CellInput type="number" min={0} inputMode="decimal" value={type.builtUp} placeholder="sq ft" aria-label={`Type ${type.code} built-up area (sq ft)`} onChange={(ev) => onChange({ builtUp: ev.target.value })} error={e("builtUp")} />
        </td>
        <td>
          <CellInput type="number" min={0} inputMode="decimal" value={type.superBuiltUp} placeholder="sq ft" aria-label={`Type ${type.code} super built-up area (sq ft)`} onChange={(ev) => onChange({ superBuiltUp: ev.target.value })} error={e("super")} />
        </td>
        <td className="pw-col-plc">
          <input
            type="checkbox"
            className="pw-plc"
            checked={type.plc}
            title="Corner / view — adds the PLC charge"
            aria-label={`Type ${type.code}: corner / view (adds the PLC charge)`}
            onChange={(ev) => onChange({ plc: ev.target.checked })}
          />
        </td>
        <td className="pw-col-floors">
          {type.limitFloors ? (
            <div className="pw-floors">
              <FloorRange from={type.floorFrom} to={type.floorTo} onChange={(from, to) => onChange({ floorFrom: from, floorTo: to })} error={e("floors")} />
              <button type="button" className="pw-link" onClick={() => onChange({ limitFloors: false })}>
                All floors
              </button>
            </div>
          ) : (
            <span className="pw-floors-all">
              <span className="muted text-sm">{top != null && top >= 1 ? `All (1–${top})` : "All"}</span>
              <button
                type="button"
                className="pw-link"
                title="Limit this type to some floors (e.g. a penthouse on the top floor)"
                aria-label={`Limit type ${type.code} to some floors`}
                onClick={() => onChange({ limitFloors: true, floorFrom: "1", floorTo: top != null && top >= 1 ? String(top) : "1" })}
              >
                Limit
              </button>
            </span>
          )}
        </td>
        <td className="pw-col-del">
          <button type="button" className="btn btn--ghost btn--icon" onClick={onRemove} aria-label={`Remove type ${type.code}`}>
            <Trash2 size={14} />
          </button>
        </td>
      </tr>
      {warning && (
        <tr className="pw-row-note">
          <td colSpan={8}>Type {type.code}: {warning}</td>
        </tr>
      )}
    </>
  );
}

function FloorRange({ from, to, onChange, error }: { from: string; to: string; onChange: (from: string, to: string) => void; error?: string }) {
  return (
    <div className="pw-cell">
      <div className="pw-range">
        <input
          className={["input", error ? "is-invalid" : null].filter(Boolean).join(" ")}
          type="number"
          min={0}
          max={200}
          inputMode="numeric"
          value={from}
          aria-label="From floor"
          onChange={(e) => onChange(e.target.value, to)}
        />
        <span aria-hidden="true">–</span>
        <input
          className={["input", error ? "is-invalid" : null].filter(Boolean).join(" ")}
          type="number"
          min={0}
          max={200}
          inputMode="numeric"
          value={to}
          aria-label="To floor"
          onChange={(e) => onChange(from, e.target.value)}
        />
      </div>
      {error && <div className="pw-cell__error">{error}</div>}
    </div>
  );
}
