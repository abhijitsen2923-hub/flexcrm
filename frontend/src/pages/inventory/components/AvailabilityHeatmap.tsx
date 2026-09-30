import type { Project, Tower } from "../../../types/realestate";
import { PARKING_TYPE_LABEL, groupParkingByType, isParkingBlock } from "../../../utils/projectInventory";
import "./AvailabilityHeatmap.css";

interface Props {
  projects: Project[];
  onFloorClick: (floor: number) => void;
  selectedFloor: number | null;
}

function heatColor(ratio: number): string {
  // 0 = all sold (gray) → 1 = all available (green)
  const r = Math.round(22 + (1 - ratio) * 233);
  const g = Math.round(163 - (1 - ratio) * 40);
  const b = Math.round(74 - (1 - ratio) * 50);
  return `rgb(${r},${g},${b})`;
}

// The parking block: one cell per parking type (CP, OP …); a click filters the board to its level (floor 0).
function ParkingHeatmap({ tower, onFloorClick }: { tower: Tower; onFloorClick: (f: number) => void }) {
  return (
    <div className="heatmap-tower">
      <h4 className="heatmap-tower__name">{tower.name}</h4>
      <div className="heatmap-tower__grid">
        {groupParkingByType(tower.units).map(({ label, units }) => {
          const available = units.filter((u) => u.status === "available").length;
          const name = label in PARKING_TYPE_LABEL ? PARKING_TYPE_LABEL[label as keyof typeof PARKING_TYPE_LABEL] : "Other parking";
          return (
            <button
              key={label}
              className="heatmap-cell"
              style={{ background: heatColor(units.length > 0 ? available / units.length : 0) }}
              onClick={() => onFloorClick(units[0]?.floor ?? 0)}
              title={`${name}: ${available}/${units.length} available`}
              aria-label={`${name}, ${available} of ${units.length} spots available`}
            >
              <span className="heatmap-cell__floor">{label}</span>
              <span className="heatmap-cell__count">{available}/{units.length}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function TowerHeatmap({ tower, onFloorClick, selectedFloor }: { tower: Tower; onFloorClick: (f: number) => void; selectedFloor: number | null }) {
  if (isParkingBlock(tower.name)) return <ParkingHeatmap tower={tower} onFloorClick={onFloorClick} />;
  const floorMap = new Map<number, { total: number; available: number }>();
  for (const unit of tower.units) {
    const entry = floorMap.get(unit.floor) ?? { total: 0, available: 0 };
    entry.total++;
    if (unit.status === "available") entry.available++;
    floorMap.set(unit.floor, entry);
  }
  const floors = Array.from(floorMap.keys()).sort((a, b) => b - a);

  return (
    <div className="heatmap-tower">
      <h4 className="heatmap-tower__name">{tower.name}</h4>
      <div className="heatmap-tower__grid">
        {floors.map((floor) => {
          const { total, available } = floorMap.get(floor)!;
          const ratio = total > 0 ? available / total : 0;
          const isSelected = floor === selectedFloor;
          return (
            <button
              key={floor}
              className={["heatmap-cell", isSelected ? "heatmap-cell--selected" : ""].filter(Boolean).join(" ")}
              style={{ background: heatColor(ratio) }}
              onClick={() => onFloorClick(floor)}
              title={`Floor ${floor}: ${available}/${total} available`}
              aria-label={`Floor ${floor}, ${available} of ${total} units available`}
              aria-pressed={isSelected}
            >
              <span className="heatmap-cell__floor">F{floor}</span>
              <span className="heatmap-cell__count">{available}/{total}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

export function AvailabilityHeatmap({ projects, onFloorClick, selectedFloor }: Props) {
  return (
    <div className="heatmap">
      <div className="heatmap__legend">
        <span style={{ background: heatColor(0) }} className="heatmap__swatch" />
        <span>Fully sold</span>
        <span style={{ background: heatColor(1) }} className="heatmap__swatch" />
        <span>Fully available</span>
      </div>

      {projects.map((project) => (
        <section key={project.id} className="heatmap-project">
          <h3 className="heatmap-project__name">
            {project.name}{" "}
            <span className="heatmap-project__meta">
              {project.availableUnits} / {project.totalUnits} units available
              {project.totalParking > 0 && ` · ${project.availableParking} / ${project.totalParking} parking`}
            </span>
          </h3>
          {project.towers.every((t) => t.units.length === 0) && (
            <p className="heatmap-project__empty">No units yet — add them from Projects → Edit project.</p>
          )}
          <div className="heatmap-project__towers">
            {project.towers.map((tower) => (
              <TowerHeatmap
                key={tower.id}
                tower={tower}
                onFloorClick={onFloorClick}
                selectedFloor={selectedFloor}
              />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
