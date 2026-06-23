import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useInventory } from "../../hooks/useInventory";
import { useToast } from "../../components";
import { InventoryBoard } from "./components/InventoryBoard";
import { AvailabilityHeatmap } from "./components/AvailabilityHeatmap";
import type { Unit, UnitStatus } from "../../types/realestate";
import "./InventoryPage.css";

type ViewMode = "board" | "heatmap";

export default function InventoryPage() {
  const { projects, loading, refresh, updateUnitStatus } = useInventory();
  const { push } = useToast();
  const navigate = useNavigate();
  const [view, setView] = useState<ViewMode>("board");
  const [filterFloor, setFilterFloor] = useState<number | null>(null);

  const handleStatusChange = async (unitId: string, status: UnitStatus) => {
    try {
      await updateUnitStatus(unitId, status);
      push({ message: "Unit status updated", tone: "success" });
    } catch {
      push({ message: "Failed to update unit status", tone: "danger" });
      throw new Error("status update failed");
    }
  };

  const handleFloorClick = (floor: number) => {
    setFilterFloor((prev) => (prev === floor ? null : floor));
    setView("board");
  };

  const handleStartBooking = (unit: Unit) => {
    navigate(`/bookings?unitId=${unit.id}`);
  };

  return (
    <div className="inventory-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Inventory</h1>
          {filterFloor !== null && (
            <p className="page-subtitle">
              Filtered to Floor {filterFloor} ·{" "}
              <button className="link-btn" onClick={() => setFilterFloor(null)}>Clear filter</button>
            </p>
          )}
        </div>
        <div className="inventory-page__toolbar">
          <div className="view-toggle" role="group" aria-label="View mode">
            <button
              className={["view-toggle__btn", view === "board" ? "is-active" : ""].filter(Boolean).join(" ")}
              onClick={() => setView("board")}
            >
              Board
            </button>
            <button
              className={["view-toggle__btn", view === "heatmap" ? "is-active" : ""].filter(Boolean).join(" ")}
              onClick={() => setView("heatmap")}
            >
              Heatmap
            </button>
          </div>
        </div>
      </div>

      {loading ? (
        <div className="inventory-page__loading">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="skeleton-card" aria-busy="true" style={{ height: 180 }} />
          ))}
        </div>
      ) : view === "board" ? (
        <InventoryBoard
          projects={projects}
          onStatusChange={handleStatusChange}
          onRefresh={refresh}
          filterFloor={filterFloor}
          onStartBooking={handleStartBooking}
        />
      ) : (
        <AvailabilityHeatmap
          projects={projects}
          onFloorClick={handleFloorClick}
          selectedFloor={filterFloor}
        />
      )}
    </div>
  );
}
