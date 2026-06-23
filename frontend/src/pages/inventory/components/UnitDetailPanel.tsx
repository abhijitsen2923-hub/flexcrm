import { useState } from "react";
import { X } from "lucide-react";
import { Badge, Button, SelectField } from "../../../components";
import { usePermissions } from "../../../hooks/usePermissions";
import { formatInr } from "../../../utils/format";
import type { Unit, UnitStatus } from "../../../types/realestate";
import "./UnitDetailPanel.css";

const STATUS_OPTIONS: { value: UnitStatus; label: string }[] = [
  { value: "available", label: "Available" },
  { value: "reserved", label: "Reserved" },
  { value: "booked", label: "Booked" },
  { value: "sold", label: "Sold" },
];

const STATUS_TONE: Record<UnitStatus, "success" | "warning" | "primary" | "neutral"> = {
  available: "success",
  reserved: "warning",
  booked: "primary",
  sold: "neutral",
};

interface Props {
  unit: Unit & { towerName: string; projectName: string };
  onClose: () => void;
  onStatusChange: (unitId: string, status: UnitStatus) => Promise<void>;
  onStartBooking?: (unit: Unit) => void;
}

export function UnitDetailPanel({ unit, onClose, onStatusChange, onStartBooking }: Props) {
  const { has } = usePermissions();
  const [status, setStatus] = useState<UnitStatus>(unit.status);
  const [saving, setSaving] = useState(false);

  const handleStatusChange = async (next: UnitStatus) => {
    setStatus(next);
    setSaving(true);
    try {
      await onStatusChange(unit.id, next);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="unit-panel drawer is-open" role="dialog" aria-label={`Unit ${unit.unitNumber} detail`}>
      <div className="drawer__header">
        <div>
          <h2 className="drawer__title">Unit {unit.unitNumber}</h2>
          <p className="drawer__subtitle">{unit.projectName} · {unit.towerName} · Floor {unit.floor}</p>
        </div>
        <button className="drawer__close" onClick={onClose} aria-label="Close panel">
          <X size={18} />
        </button>
      </div>

      <div className="drawer__body unit-panel__body">
        <div className="unit-panel__status-row">
          <Badge tone={STATUS_TONE[status]}>{status.charAt(0).toUpperCase() + status.slice(1)}</Badge>
          {has("LEAD_MANAGE") && (
            <SelectField
              label=""
              options={STATUS_OPTIONS}
              value={status}
              onChange={(e) => handleStatusChange(e.target.value as UnitStatus)}
              disabled={saving}
            />
          )}
        </div>

        <div className="unit-panel__grid">
          <div className="unit-panel__field">
            <span className="unit-panel__label">Area</span>
            <span>{unit.area} {unit.areaUnit}</span>
          </div>
          <div className="unit-panel__field">
            <span className="unit-panel__label">Base Price</span>
            <span style={{ fontSize: "var(--text-display-lg)", fontWeight: 700 }}>{formatInr(unit.basePrice)}</span>
          </div>
          {unit.facing && (
            <div className="unit-panel__field">
              <span className="unit-panel__label">Facing</span>
              <span>{unit.facing.replace(/_/g, " ")}</span>
            </div>
          )}
          {unit.view && (
            <div className="unit-panel__field">
              <span className="unit-panel__label">View</span>
              <span>{unit.view}</span>
            </div>
          )}
        </div>

        {status === "available" && has("LEAD_MANAGE") && onStartBooking && (
          <Button
            variant="primary"
            onClick={() => onStartBooking(unit)}
            className="unit-panel__book-btn"
          >
            Start Booking
          </Button>
        )}
      </div>
    </div>
  );
}
