import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { Badge, Button, SelectField } from "../../../components";
import { usePermissions } from "../../../hooks/usePermissions";
import { bookingsService } from "../../../services/bookings";
import { formatDate, formatInr } from "../../../utils/format";
import type { Booking, Unit, UnitStatus, UnitType } from "../../../types/realestate";
import "./UnitDetailPanel.css";

const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

const STATUS_OPTIONS: { value: UnitStatus; label: string }[] = [
  { value: "available", label: "Available" },
  { value: "hold", label: "Hold" },
  { value: "booked", label: "Booked" },
  { value: "registered", label: "Registered" },
  { value: "sold", label: "Sold" },
];

const STATUS_TONE: Record<UnitStatus, "success" | "warning" | "primary" | "info" | "neutral"> = {
  available: "success",
  hold: "warning",
  booked: "primary",
  registered: "info",
  sold: "neutral",
};

const UNIT_TYPE_LABEL: Record<UnitType, string> = {
  residential: "Residential",
  parking: "Parking",
  shop: "Shop",
  godown: "Godown",
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

  // Booking history for this unit (who booked / sold details). Available units
  // have no bookings, so skip the fetch for them. Best-effort — a viewer without
  // booking access just sees no history.
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [loadingBookings, setLoadingBookings] = useState(unit.status !== "available");

  useEffect(() => {
    if (unit.status === "available") {
      setBookings([]);
      return;
    }
    let alive = true;
    setLoadingBookings(true);
    bookingsService
      .list({ unitId: unit.id })
      .then((rows) => alive && setBookings(rows))
      .catch(() => alive && setBookings([]))
      .finally(() => alive && setLoadingBookings(false));
    return () => {
      alive = false;
    };
  }, [unit.id, unit.status]);

  // The unit's live booking (the confirmed one that holds it), else the latest row.
  const active = bookings.find((b) => b.status !== "cancelled") ?? bookings[0] ?? null;

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
            <span className="unit-panel__label">Type</span>
            <span>{UNIT_TYPE_LABEL[unit.unitType]}</span>
          </div>
          <div className="unit-panel__field">
            <span className="unit-panel__label">Super built-up area</span>
            <span>{unit.area} {unit.areaUnit}</span>
          </div>
          {unit.carpetArea != null && (
            <div className="unit-panel__field">
              <span className="unit-panel__label">Carpet area</span>
              <span>{unit.carpetArea} {unit.areaUnit}</span>
            </div>
          )}
          {unit.builtUpArea != null && (
            <div className="unit-panel__field">
              <span className="unit-panel__label">Built-up area</span>
              <span>{unit.builtUpArea} {unit.areaUnit}</span>
            </div>
          )}
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

        {unit.status !== "available" && (
          <div style={{ marginTop: "1rem", borderTop: "1px solid var(--color-border)", paddingTop: "0.85rem" }}>
            <div style={{ fontWeight: 600, marginBottom: "0.6rem" }}>Booking</div>
            {loadingBookings ? (
              <p className="muted text-sm">Loading booking…</p>
            ) : !active ? (
              <p className="muted text-sm">No booking record for this unit.</p>
            ) : (
              <>
                <div className="unit-panel__grid">
                  <div className="unit-panel__field">
                    <span className="unit-panel__label">Booked by</span>
                    <span>{active.customer?.contactName ?? "—"}</span>
                  </div>
                  <div className="unit-panel__field">
                    <span className="unit-panel__label">Booking status</span>
                    <span>
                      <Badge tone={active.status === "confirmed" ? "success" : active.status === "cancelled" ? "neutral" : "warning"}>
                        {cap(active.status)}
                      </Badge>
                    </span>
                  </div>
                  <div className="unit-panel__field">
                    <span className="unit-panel__label">Total consideration</span>
                    <span>{formatInr(Number(active.pricingSnapshot?.total ?? unit.basePrice))}</span>
                  </div>
                  <div className="unit-panel__field">
                    <span className="unit-panel__label">Collected</span>
                    <span>
                      {formatInr(active.paymentReceipts.reduce((n, r) => n + r.amount, 0))}
                      {(() => {
                        const demand = active.paymentSchedules.reduce((n, p) => n + p.demandAmount, 0);
                        return demand ? <span className="muted"> / {formatInr(demand)}</span> : null;
                      })()}
                    </span>
                  </div>
                  {active.tokenAmount != null && (
                    <div className="unit-panel__field">
                      <span className="unit-panel__label">Token</span>
                      <span>{formatInr(active.tokenAmount)}{active.tokenReceivedOn ? ` · ${formatDate(active.tokenReceivedOn)}` : ""}</span>
                    </div>
                  )}
                  {active.registrationNumber && (
                    <div className="unit-panel__field">
                      <span className="unit-panel__label">Registration</span>
                      <span>{active.registrationNumber}{active.scheduledDate ? ` · ${formatDate(active.scheduledDate)}` : ""}</span>
                    </div>
                  )}
                  {active.subRegistrarOffice && (
                    <div className="unit-panel__field">
                      <span className="unit-panel__label">Sub-registrar</span>
                      <span>{active.subRegistrarOffice}</span>
                    </div>
                  )}
                </div>

                {bookings.length > 1 && (
                  <div style={{ marginTop: "0.85rem" }}>
                    <span className="unit-panel__label">History</span>
                    <div className="stack" style={{ gap: 0, marginTop: "0.35rem" }}>
                      {bookings.map((b) => (
                        <div
                          key={b.id}
                          style={{ display: "flex", flexWrap: "wrap", gap: 4, alignItems: "baseline", padding: "0.4rem 0", borderBottom: "1px solid var(--color-border)" }}
                        >
                          <span className="text-sm">
                            {formatDate(b.createdAt)} · <strong>{cap(b.status)}</strong>
                            <span className="muted"> · {b.customer?.contactName ?? "—"} · {formatInr(Number(b.pricingSnapshot?.total ?? unit.basePrice))}</span>
                          </span>
                          {b.status === "cancelled" && b.refunds.length > 0 && (
                            <span className="muted text-xs">refunded {formatInr(b.refunds.reduce((n, r) => n + r.refundAmount, 0))}</span>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        )}

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
