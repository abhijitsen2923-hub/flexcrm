import { Plus, Trash2 } from "lucide-react";
import { SelectField, TextField, Button } from "../../../components";
import type { GarageOption, Tower } from "../../../types/realestate";
import {
  MAX_FLOORS,
  MAX_UNITS_PER_FLOOR,
  PARKING_TYPES,
  PARKING_TYPE_LABEL,
  TOWER_UNIT_TYPES,
  describeAdds,
  newTowerCard,
  newUnitSpec,
  plannedAdds,
  plannedParkingAdds,
  parkingTotal,
  plural,
  setCardFloors,
  totalOf,
  updateCardSpec,
  type LayoutDetails,
  type ParkingCountsForm,
  type ProjectRates,
  type TowerCard,
  type TowerUnitType,
  type UnitSpecForm,
} from "../../../utils/projectInventory";

const SPEC_TYPE_OPTIONS: { value: TowerUnitType; label: string }[] = [
  { value: "residential", label: "Flats" },
  { value: "shop", label: "Shops / Commercial" },
  { value: "godown", label: "Godowns / Warehouse" },
];

interface Props {
  cards: TowerCard[];
  onCardsChange: (cards: TowerCard[]) => void;
  details: LayoutDetails;
  rates: ProjectRates;
  // The project's towers as they are now ([] when creating) — for "has N units · Save adds M".
  existingTowers: Tower[];
  parkingSelected: GarageOption[];
  parkingCounts: ParkingCountsForm;
  onParkingChange: (selected: GarageOption[], counts: ParkingCountsForm) => void;
  existingParking: { byType: Record<GarageOption, number>; untyped: number };
  declaredGarages: number | null;
}

/**
 * The Towers + Parking part of the project form (Create and Edit). Save builds what it describes: every tower's
 * flats (numbered R101 … per tower) and the parking spots per type (CP01 … across the project). Saving again only
 * adds what's missing; existing units are never changed or removed.
 */
export function ProjectInventoryEditor({
  cards,
  onCardsChange,
  details,
  rates,
  existingTowers,
  parkingSelected,
  parkingCounts,
  onParkingChange,
  existingParking,
  declaredGarages,
}: Props) {
  const towersById = new Map(existingTowers.map((t) => [t.id, t]));

  const setCard = (index: number, next: TowerCard) => onCardsChange(cards.map((c, i) => (i === index ? next : c)));
  const setSpec = (ci: number, si: number, patch: Partial<UnitSpecForm>) =>
    setCard(ci, updateCardSpec(cards[ci], si, patch, rates));

  const parkingAdds = plannedParkingAdds(parkingSelected, parkingCounts, existingParking.byType);
  const total = parkingTotal(parkingSelected, parkingCounts);

  return (
    <>
      <div className="stack inv-editor" style={{ gap: "0.6rem", borderTop: "1px solid var(--color-border)", paddingTop: "0.85rem" }}>
        <div className="row row--between" style={{ alignItems: "center" }}>
          <strong>Towers &amp; units</strong>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            icon={<Plus size={14} />}
            onClick={() => onCardsChange([...cards, newTowerCard(cards.length, details, rates, cards.map((c) => c.name))])}
          >
            Add tower
          </Button>
        </div>
        <p className="muted text-xs" style={{ margin: 0 }}>
          Filled in from Total towers, Total floors and Flats per floor above. Enter each tower's flat size and price —
          Save creates the flats (R101, R102 … on each floor). Saving again only adds what's missing; existing units and
          bookings are never changed.
        </p>
        {cards.length === 0 && (
          <p className="muted text-sm" style={{ margin: 0 }}>
            No towers yet — enter Total towers above, or use “Add tower”.
          </p>
        )}

        {cards.map((card, ci) => {
          const tower = card.towerId ? towersById.get(card.towerId) : undefined;
          const existingUnits = tower?.units ?? [];
          const adds = plannedAdds(card, existingUnits);
          const addCount = totalOf(adds);
          return (
            <div key={card.key} className="card inv-editor__tower" data-testid="tower-card">
              <div className="row row--between" style={{ alignItems: "center", gap: "0.5rem" }}>
                <span className="text-xs" aria-live="polite">
                  {tower ? (
                    <span className="muted">Has {existingUnits.length.toLocaleString("en-IN")} units · </span>
                  ) : (
                    <span className="muted">New tower · </span>
                  )}
                  {addCount > 0 ? (
                    <strong className="inv-editor__adds">Save adds {describeAdds(adds)}</strong>
                  ) : (
                    <span className="muted">nothing to add</span>
                  )}
                </span>
                {!card.towerId && (
                  <button
                    type="button"
                    className="btn btn--ghost btn--icon"
                    onClick={() => onCardsChange(cards.filter((_, i) => i !== ci))}
                    aria-label={`Remove ${card.name || "tower"}`}
                  >
                    <Trash2 size={14} />
                  </button>
                )}
              </div>
              <div className="form-grid">
                <TextField
                  id={`tower-name-${ci}`}
                  label="Tower name"
                  value={card.name}
                  maxLength={100}
                  required
                  onChange={(e) => setCard(ci, { ...card, name: e.target.value })}
                  placeholder="e.g. Tower A"
                />
                <TextField
                  id={`tower-floors-${ci}`}
                  label="Floors"
                  type="number"
                  min={1}
                  max={MAX_FLOORS}
                  required
                  value={card.total_floors}
                  onChange={(e) => setCard(ci, { ...setCardFloors(card, e.target.value), auto: false })}
                />
              </div>

              {card.unitSpecs.map((spec, si) => {
                const noun = SPEC_TYPE_OPTIONS.find((o) => o.value === spec.unit_type)?.label ?? "Units";
                return (
                  <div key={si} className="inv-editor__spec">
                    <div className="inv-editor__spec-grid">
                      <SelectField
                        id={`t${ci}-type-${si}`}
                        label="Type"
                        value={spec.unit_type}
                        onChange={(e) => setSpec(ci, si, { unit_type: e.target.value as TowerUnitType })}
                        options={SPEC_TYPE_OPTIONS}
                      />
                      <TextField
                        id={`t${ci}-perfloor-${si}`}
                        label="Per floor"
                        type="number"
                        min={0}
                        max={MAX_UNITS_PER_FLOOR}
                        value={spec.units_per_floor}
                        onChange={(e) => setSpec(ci, si, { units_per_floor: e.target.value })}
                      />
                      <TextField
                        id={`t${ci}-area-${si}`}
                        label="Size (sq ft)"
                        type="number"
                        min={0}
                        step="any"
                        value={spec.area}
                        onChange={(e) => setSpec(ci, si, { area: e.target.value })}
                        placeholder="Super built-up"
                      />
                      <TextField
                        id={`t${ci}-price-${si}`}
                        label="Price (₹)"
                        type="number"
                        min={0}
                        step="any"
                        value={spec.base_price}
                        onChange={(e) => setSpec(ci, si, { base_price: e.target.value })}
                        hint={!spec.priceTouched && spec.base_price ? "Size × project rate" : undefined}
                      />
                    </div>
                    <details className="inv-editor__more">
                      <summary className="text-xs">
                        More for {noun.toLowerCase()} — floors {spec.floor_from || "?"}–{spec.floor_to || "?"}, carpet /
                        built-up area, unit number prefix
                      </summary>
                      <div className="inv-editor__spec-grid">
                        <TextField
                          id={`t${ci}-from-${si}`}
                          label="From floor"
                          type="number"
                          min={0}
                          value={spec.floor_from}
                          onChange={(e) => setSpec(ci, si, { floor_from: e.target.value })}
                          hint="0 = ground"
                        />
                        <TextField
                          id={`t${ci}-to-${si}`}
                          label="To floor"
                          type="number"
                          min={0}
                          value={spec.floor_to}
                          onChange={(e) => setSpec(ci, si, { floor_to: e.target.value })}
                        />
                        <TextField
                          id={`t${ci}-carpet-${si}`}
                          label="Carpet area (sq ft)"
                          type="number"
                          min={0}
                          step="any"
                          value={spec.carpet_area}
                          onChange={(e) => setSpec(ci, si, { carpet_area: e.target.value })}
                        />
                        <TextField
                          id={`t${ci}-builtup-${si}`}
                          label="Built-up area (sq ft)"
                          type="number"
                          min={0}
                          step="any"
                          value={spec.built_up_area}
                          onChange={(e) => setSpec(ci, si, { built_up_area: e.target.value })}
                        />
                        <TextField
                          id={`t${ci}-prefix-${si}`}
                          label="Unit number prefix"
                          maxLength={8}
                          value={spec.unit_prefix}
                          onChange={(e) => setSpec(ci, si, { unit_prefix: e.target.value })}
                          placeholder={spec.unit_type === "residential" ? "R" : spec.unit_type === "shop" ? "S" : "G"}
                        />
                      </div>
                    </details>
                    {card.unitSpecs.length > 1 && (
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        icon={<Trash2 size={13} />}
                        onClick={() => setCard(ci, { ...card, unitSpecs: card.unitSpecs.filter((_, j) => j !== si) })}
                      >
                        Remove {noun.toLowerCase()}
                      </Button>
                    )}
                  </div>
                );
              })}
              <div>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  icon={<Plus size={14} />}
                  onClick={() => {
                    const used = new Set(card.unitSpecs.map((s) => s.unit_type));
                    const type = TOWER_UNIT_TYPES.find((t) => !used.has(t)) ?? "shop";
                    const floors = Number(card.total_floors) || 1;
                    setCard(ci, { ...card, unitSpecs: [...card.unitSpecs, newUnitSpec(type, floors, null, rates)] });
                  }}
                >
                  Add shops / godowns / another flat type
                </Button>
              </div>
            </div>
          );
        })}
      </div>

      <div className="stack inv-editor" style={{ gap: "0.6rem", borderTop: "1px solid var(--color-border)", paddingTop: "0.85rem" }}>
        <div>
          <strong>Parking / garages</strong>
          <p className="muted text-xs" style={{ margin: "0.15rem 0 0" }}>
            Tick each type offered and enter how many. Spots are numbered per type across the whole project (CP01,
            CP02 … OP01 …) and priced at the Garage / Parking amount above.
          </p>
        </div>
        <div className="inv-editor__parking">
          {PARKING_TYPES.map((type) => {
            const checked = parkingSelected.includes(type);
            const existing = existingParking.byType[type];
            const add = parkingAdds[type] ?? 0;
            return (
              <div key={type} className="inv-editor__parking-row">
                <label className="row" style={{ gap: 6, alignItems: "center", cursor: "pointer", minWidth: 0 }}>
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() =>
                      onParkingChange(
                        checked ? parkingSelected.filter((t) => t !== type) : PARKING_TYPES.filter((t) => t === type || parkingSelected.includes(t)),
                        parkingCounts
                      )
                    }
                  />
                  <span className="text-sm">
                    {PARKING_TYPE_LABEL[type]} ({type})
                  </span>
                </label>
                {checked && (
                  <input
                    className="input inv-editor__parking-count"
                    type="number"
                    min={0}
                    max={5000}
                    aria-label={`How many ${PARKING_TYPE_LABEL[type]} spots`}
                    value={parkingCounts[type]}
                    placeholder="0"
                    onChange={(e) => onParkingChange(parkingSelected, { ...parkingCounts, [type]: e.target.value })}
                  />
                )}
                {checked && (existing > 0 || add > 0) && (
                  <span className="muted text-xs">
                    {existing > 0 ? `${existing} exist` : ""}
                    {existing > 0 && add > 0 ? " · " : ""}
                    {add > 0 ? <strong className="inv-editor__adds">Save adds {add}</strong> : ""}
                  </span>
                )}
              </div>
            );
          })}
        </div>
        <div className="text-sm">
          Total parking: <strong data-testid="parking-total">{total.toLocaleString("en-IN")}</strong>
          {existingParking.untyped > 0 && (
            <span className="muted text-xs">
              {" "}
              · plus {plural(existingParking.untyped, "parking")} numbered before types (kept as they are)
            </span>
          )}
        </div>
        {total === 0 && declaredGarages != null && declaredGarages > 0 && parkingSelected.length !== 1 && (
          <p className="muted text-xs" style={{ margin: 0 }}>
            This project lists {declaredGarages.toLocaleString("en-IN")} garages — tick the types and split them above
            so they appear in Inventory.
          </p>
        )}
      </div>
    </>
  );
}
