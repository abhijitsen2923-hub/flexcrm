import { useEffect, useState } from "react";
import { useLocation, useSearchParams } from "react-router-dom";
import { ClipboardCheck, Plus, Wallet } from "lucide-react";
import { Badge, Button, Card, ConfirmDialog, DataTable, EmptyState, Modal, useToast } from "../../components";
import type { DataTableColumn } from "../../components";
import { useBookings } from "../../hooks/useBookings";
import { useInventory } from "../../hooks/useInventory";
import { inventoryService } from "../../services/inventory";
import { LoadingBlock } from "../../components/ui/Spinner";
import { BookingWizard } from "./components/BookingWizard";
import { PaymentPlanModal } from "./components/PaymentPlanModal";
import type { Booking, Unit, UnitStatus } from "../../types/realestate";
import { extractErrorMessage } from "../../utils/errors";
import { formatDate, formatInr } from "../../utils/format";
import "./BookingsPage.css";

const STATUS_TONE = {
  draft: "warning",
  confirmed: "success",
  cancelled: "neutral",
} as const;

type WizardUnit = Pick<Unit, "id" | "unitNumber" | "floor" | "area" | "basePrice" | "status"> & {
  towerName: string;
  projectName: string;
};

export default function BookingsPage() {
  const [searchParams] = useSearchParams();
  const location = useLocation();
  const navState = location.state as { projectName?: string; towerName?: string } | null;
  const preselectedUnitId = searchParams.get("unitId");
  const { bookings, loading, refresh } = useBookings();
  const { projects, updateUnitStatus, refresh: refreshInventory } = useInventory();
  const toast = useToast();
  const [wizardUnit, setWizardUnit] = useState<WizardUnit | null>(null);
  const [wizardBooking, setWizardBooking] = useState<Booking | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  // Staged unit-lifecycle action (Booked → Registered → Sold) from the list.
  const [markAction, setMarkAction] = useState<{ unitId: string; label: string; target: UnitStatus } | null>(null);
  const [marking, setMarking] = useState(false);
  // Payment plan / collections modal for a booking.
  const [payBooking, setPayBooking] = useState<Booking | null>(null);

  // Available units across all projects, tagged with their tower/project names.
  const availableUnits = projects.flatMap((p) =>
    p.towers.flatMap((t) =>
      t.units
        .filter((u) => u.status === "available")
        .map((u) => ({ ...u, towerName: t.name, projectName: p.name }))
    )
  );

  // Resolve a unit id to its full context (unit + tower/project names) from the
  // loaded projects — used to resume a booking and to name deep-linked units.
  function unitContext(unitId: string): WizardUnit | null {
    for (const p of projects) {
      for (const t of p.towers) {
        const u = t.units.find((x) => x.id === unitId);
        if (u) return { ...u, towerName: t.name, projectName: p.name };
      }
    }
    return null;
  }

  // ?unitId= deep link from the inventory board.
  useEffect(() => {
    if (!preselectedUnitId) return;
    inventoryService.getUnit(preselectedUnitId).then((unit) => {
      const ctx = unitContext(preselectedUnitId);
      setWizardBooking(null);
      setWizardUnit({
        ...unit,
        towerName: navState?.towerName ?? ctx?.towerName ?? "Tower",
        projectName: navState?.projectName ?? ctx?.projectName ?? "Project",
      });
    }).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [preselectedUnitId, navState?.towerName, navState?.projectName]);

  // If a deep-linked unit resolved to placeholder names (projects hadn't loaded
  // yet), patch them once inventory arrives. Guarded against re-render loops.
  useEffect(() => {
    setWizardUnit((prev) => {
      if (!prev || (prev.towerName !== "Tower" && prev.projectName !== "Project")) return prev;
      const ctx = unitContext(prev.id);
      if (!ctx) return prev;
      const towerName = navState?.towerName ?? ctx.towerName;
      const projectName = navState?.projectName ?? ctx.projectName;
      if (towerName === prev.towerName && projectName === prev.projectName) return prev;
      return { ...prev, towerName, projectName };
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projects]);

  function pickUnit(u: WizardUnit) {
    setWizardBooking(null);
    setWizardUnit(u);
    setPickerOpen(false);
  }

  // Resume/edit an existing (e.g. draft) booking — reopen the wizard at its step.
  async function resumeBooking(b: Booking) {
    const ctx = unitContext(b.unitId);
    if (ctx) {
      setWizardBooking(b);
      setWizardUnit(ctx);
      return;
    }
    try {
      const unit = await inventoryService.getUnit(b.unitId);
      setWizardBooking(b);
      setWizardUnit({ ...unit, towerName: "Tower", projectName: "Project" });
    } catch { /* ignore */ }
  }

  function closeWizard() {
    setWizardUnit(null);
    setWizardBooking(null);
  }

  // Staged unit-lifecycle actions from the booking list: Booked → Registered → Sold.
  function askMark(ctx: WizardUnit, target: UnitStatus) {
    setMarkAction({
      unitId: ctx.id,
      label: `${ctx.projectName} · ${ctx.towerName} · ${ctx.unitNumber}`,
      target,
    });
  }

  async function confirmMark() {
    if (!markAction) return;
    setMarking(true);
    try {
      await updateUnitStatus(markAction.unitId, markAction.target);
      toast.success(
        markAction.target === "registered" ? "Marked Registered" : "Marked Sold",
        markAction.label
      );
      setMarkAction(null);
    } catch (err) {
      toast.error("Update failed", extractErrorMessage(err));
    } finally {
      setMarking(false);
    }
  }

  const columns: DataTableColumn<Booking>[] = [
    {
      key: "id",
      header: "Booking",
      render: (b) => (
        <div>
          <div style={{ fontWeight: 600 }}>{b.customer?.contactName ?? "—"}</div>
          <div className="mono muted text-xs">{b.id.slice(0, 8)}…</div>
        </div>
      ),
    },
    {
      key: "unit",
      header: "Unit",
      render: (b) => {
        const ctx = unitContext(b.unitId);
        return ctx ? `${ctx.projectName} · ${ctx.towerName} · ${ctx.unitNumber}` : "—";
      },
    },
    { key: "step", header: "Step", render: (b) => `${b.step} / 4` },
    {
      key: "status",
      header: "Status",
      render: (b) => (
        <Badge tone={STATUS_TONE[b.status] ?? "neutral"}>
          {b.status.charAt(0).toUpperCase() + b.status.slice(1)}
        </Badge>
      ),
    },
    {
      key: "stage",
      header: "Registration / Sale",
      render: (b) => {
        const ctx = unitContext(b.unitId);
        // Only a confirmed booking has a booked unit; nothing to progress before then.
        if (!ctx || ctx.status === "available" || ctx.status === "hold") {
          return <span className="muted text-xs">—</span>;
        }
        if (ctx.status === "sold") return <Badge tone="neutral">Sold</Badge>;
        const target: UnitStatus = ctx.status === "booked" ? "registered" : "sold";
        const label = ctx.status === "booked" ? "Mark Registered" : "Mark Sold";
        return (
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <Badge tone={ctx.status === "booked" ? "info" : "primary"}>
              {ctx.status === "booked" ? "Booked" : "Registered"}
            </Badge>
            <Button
              size="sm"
              variant="secondary"
              onClick={(e) => {
                e.stopPropagation();
                askMark(ctx, target);
              }}
            >
              {label}
            </Button>
          </div>
        );
      },
    },
    {
      key: "payments",
      header: "Payments",
      render: (b) => {
        const demand = b.paymentSchedules.reduce((n, p) => n + p.demandAmount, 0);
        const paid = b.paymentSchedules.reduce((n, p) => n + p.paidAmount, 0);
        return (
          <Button
            size="sm"
            variant="secondary"
            icon={<Wallet size={14} />}
            onClick={(e) => {
              e.stopPropagation();
              setPayBooking(b);
            }}
          >
            {b.paymentSchedules.length === 0 ? "Set up" : `${formatInr(paid)} / ${formatInr(demand)}`}
          </Button>
        );
      },
    },
    {
      key: "scheduledDate",
      header: "Registration Date",
      render: (b) => (b.scheduledDate ? formatDate(b.scheduledDate) : "—"),
    },
    { key: "createdAt", header: "Created", render: (b) => formatDate(b.createdAt) },
  ];

  if (loading) return <LoadingBlock label="Loading bookings…" />;

  return (
    <div className="bookings-page">
      <div className="page-header">
        <h1 className="page-title">Bookings</h1>
        <Button variant="primary" icon={<Plus size={16} />} onClick={() => setPickerOpen(true)}>
          New Booking
        </Button>
      </div>

      {bookings.length === 0 ? (
        <EmptyState
          icon={<ClipboardCheck size={32} />}
          title="No bookings yet"
          description="Click New Booking to pick a unit, or start one from the Inventory board."
        />
      ) : (
        <Card>
          <DataTable
            columns={columns}
            rows={bookings}
            rowKey={(b) => b.id}
            onRowClick={(b) => void resumeBooking(b)}
          />
        </Card>
      )}

      {/* New Booking — pick an available unit */}
      <Modal
        open={pickerOpen}
        title="New booking — choose an available unit"
        onClose={() => setPickerOpen(false)}
        footer={<Button variant="secondary" onClick={() => setPickerOpen(false)}>Cancel</Button>}
      >
        {availableUnits.length === 0 ? (
          <EmptyState
            title="No available units"
            description="Add units to a project (Projects → open a project → Add tower → Add units), then book an available one."
          />
        ) : (
          <ul style={{ listStyle: "none", margin: 0, padding: 0, maxHeight: 360, overflowY: "auto" }}>
            {availableUnits.map((u) => (
              <li key={u.id}>
                <button
                  type="button"
                  onClick={() => pickUnit(u)}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    gap: "0.75rem",
                    width: "100%",
                    padding: "0.6rem 0.75rem",
                    border: "none",
                    borderBottom: "1px solid var(--color-border)",
                    background: "none",
                    cursor: "pointer",
                    textAlign: "left",
                  }}
                >
                  <span>
                    <strong>{u.unitNumber}</strong>{" "}
                    <span className="muted text-xs">· {u.projectName} · {u.towerName} · Floor {u.floor}</span>
                  </span>
                  <span className="muted text-sm">{formatInr(u.basePrice)}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </Modal>

      {wizardUnit && (
        <BookingWizard
          unit={wizardUnit}
          initialBooking={wizardBooking}
          onClose={closeWizard}
          onComplete={() => {
            refresh();
            // Confirm booked the unit server-side — re-fetch inventory so the
            // staged actions appear and the unit leaves the available picker.
            void refreshInventory();
            closeWizard();
          }}
        />
      )}

      {payBooking && (
        <PaymentPlanModal
          booking={payBooking}
          onClose={() => setPayBooking(null)}
          onChanged={(updated) => {
            setPayBooking(updated);
            void refresh();
          }}
        />
      )}

      <ConfirmDialog
        open={markAction !== null}
        title={markAction?.target === "registered" ? "Mark unit Registered?" : "Mark unit Sold?"}
        description={
          markAction
            ? `${markAction.label} will be set to ${markAction.target === "registered" ? "Registered" : "Sold"}. This updates the Inventory board too.`
            : ""
        }
        confirmLabel={markAction?.target === "registered" ? "Mark Registered" : "Mark Sold"}
        cancelLabel="Cancel"
        loading={marking}
        onCancel={() => setMarkAction(null)}
        onConfirm={() => void confirmMark()}
      />
    </div>
  );
}
