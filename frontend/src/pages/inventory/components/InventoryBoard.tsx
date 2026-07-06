import { useState } from "react";
import { useRealtimeEvent } from "../../../realtime";
import { formatInr } from "../../../utils/format";
import type { Project, Tower, Unit, UnitStatus, UnitType } from "../../../types/realestate";
import { UnitDetailPanel } from "./UnitDetailPanel";
import "./InventoryBoard.css";

const STATUS_LABEL: Record<UnitStatus, string> = {
  available: "Available",
  hold: "Hold",
  booked: "Booked",
  registered: "Registered",
  sold: "Sold",
};

const UNIT_TYPE_LABEL: Record<UnitType, string> = {
  residential: "Residential",
  parking: "Parking",
  shop: "Shop",
  godown: "Godown",
};

interface UnitCellProps {
  unit: Unit;
  onClick: () => void;
}

function UnitCell({ unit, onClick }: UnitCellProps) {
  return (
    <button
      className={`inv-cell inv-cell--${unit.status}`}
      onClick={onClick}
      title={`Unit ${unit.unitNumber} · ${UNIT_TYPE_LABEL[unit.unitType]} · ${formatInr(unit.basePrice)} · ${STATUS_LABEL[unit.status]}`}
      aria-label={`Unit ${unit.unitNumber}, ${UNIT_TYPE_LABEL[unit.unitType]}, ${STATUS_LABEL[unit.status]}`}
    >
      {unit.unitNumber}
    </button>
  );
}

interface FloorRowProps {
  floor: number;
  units: Unit[];
  onUnitClick: (unit: Unit) => void;
}

function FloorRow({ floor, units, onUnitClick }: FloorRowProps) {
  return (
    <div className="inv-floor">
      <span className="inv-floor__label">F{floor}</span>
      <div className="inv-floor__units">
        {units.map((u) => (
          <UnitCell key={u.id} unit={u} onClick={() => onUnitClick(u)} />
        ))}
      </div>
    </div>
  );
}

interface TowerGridProps {
  tower: Tower;
  projectName: string;
  filterFloor: number | null;
  typeFilter: UnitType | "all";
  onUnitClick: (unit: Unit & { towerName: string; projectName: string }) => void;
}

function TowerGrid({ tower, projectName, filterFloor, typeFilter, onUnitClick }: TowerGridProps) {
  const floorMap = new Map<number, Unit[]>();
  for (const unit of tower.units) {
    if (typeFilter !== "all" && unit.unitType !== typeFilter) continue;
    const existing = floorMap.get(unit.floor) ?? [];
    existing.push(unit);
    floorMap.set(unit.floor, existing);
  }
  if (floorMap.size === 0) return null;
  const floors = Array.from(floorMap.keys())
    .filter((f) => filterFloor == null || f === filterFloor)
    .sort((a, b) => b - a);

  return (
    <div className="inv-tower">
      <h3 className="inv-tower__name">{tower.name}</h3>
      <div className="inv-tower__floors">
        {floors.map((floor) => (
          <FloorRow
            key={floor}
            floor={floor}
            units={floorMap.get(floor)!}
            onUnitClick={(u) => onUnitClick({ ...u, towerName: tower.name, projectName })}
          />
        ))}
      </div>
    </div>
  );
}

interface Props {
  projects: Project[];
  onStatusChange: (unitId: string, status: UnitStatus) => Promise<void>;
  onRefresh: () => void;
  filterFloor?: number | null;
  onStartBooking?: (unit: Unit) => void;
}

export function InventoryBoard({ projects, onStatusChange, onRefresh, filterFloor = null, onStartBooking }: Props) {
  const [selectedUnit, setSelectedUnit] = useState<(Unit & { towerName: string; projectName: string }) | null>(null);
  const [typeFilter, setTypeFilter] = useState<UnitType | "all">("all");

  useRealtimeEvent((event) => {
    if (event.event === "unit.status_changed") {
      onRefresh();
    }
  });

  if (projects.length === 0) {
    return (
      <div className="inv-board inv-board--empty">
        <p>No projects found. Add a project to get started.</p>
      </div>
    );
  }

  return (
    <div className="inv-board">
      <div className="inv-legend">
        {(Object.keys(STATUS_LABEL) as UnitStatus[]).map((s) => (
          <span key={s} className={`inv-legend__item inv-legend__item--${s}`}>
            {STATUS_LABEL[s]}
          </span>
        ))}
        <label className="inv-type-filter">
          Type:{" "}
          <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value as UnitType | "all")}>
            <option value="all">All</option>
            {(Object.keys(UNIT_TYPE_LABEL) as UnitType[]).map((t) => (
              <option key={t} value={t}>{UNIT_TYPE_LABEL[t]}</option>
            ))}
          </select>
        </label>
      </div>

      {projects.map((project) => (
        <section key={project.id} className="inv-project">
          <div className="inv-project__header">
            <h2>{project.name}</h2>
            <span className="inv-project__meta">{project.availableUnits} / {project.totalUnits} available</span>
          </div>
          <div className="inv-project__towers">
            {project.towers.map((tower) => (
              <TowerGrid
                key={tower.id}
                tower={tower}
                projectName={project.name}
                filterFloor={filterFloor}
                typeFilter={typeFilter}
                onUnitClick={setSelectedUnit}
              />
            ))}
          </div>
        </section>
      ))}

      {selectedUnit && (
        <>
          <div className="drawer-backdrop" onClick={() => setSelectedUnit(null)} />
          <UnitDetailPanel
            unit={selectedUnit}
            onClose={() => setSelectedUnit(null)}
            onStatusChange={onStatusChange}
            onStartBooking={onStartBooking}
          />
        </>
      )}
    </div>
  );
}
