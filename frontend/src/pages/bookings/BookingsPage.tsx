import { useEffect, useState } from "react";
import { useLocation, useSearchParams } from "react-router-dom";
import { ClipboardCheck, Download, Plus, Wallet } from "lucide-react";
import { Badge, Button, Card, ConfirmDialog, DataTable, EmptyState, Modal, SelectField, TextField, useToast } from "../../components";
import type { DataTableColumn } from "../../components";
import { useBookings } from "../../hooks/useBookings";
import { useInventory } from "../../hooks/useInventory";
import { usePermissions } from "../../hooks/usePermissions";
import { bookingsService } from "../../services/bookings";
import { inventoryService } from "../../services/inventory";
import { exportsService } from "../../services/exports";
import { LoadingBlock } from "../../components/ui/Spinner";
import { BookingWizard } from "./components/BookingWizard";
import { PaymentPlanModal } from "./components/PaymentPlanModal";
import type { PriceDefaults } from "../inventory/components/PriceCalculator";
import { priceDefaultsForProject } from "../../utils/priceDefaults";
import type { Booking, PaymentMode, Unit, UnitStatus } from "../../types/realestate";
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
  // Project box-price defaults for this unit's type (Phase B) — seeds the calculator.
  priceDefaults?: PriceDefaults | null;
};

export default function BookingsPage() {
  const [searchParams] = useSearchParams();
  const location = useLocation();
  const navState = location.state as { projectName?: string; towerName?: string } | null;
  const preselectedUnitId = searchParams.get("unitId");
  const { bookings, loading, refresh } = useBookings();
  const { projects, updateUnitStatus, refresh: refreshInventory } = useInventory();
  const toast = useToast();
  const { has: hasPerm } = usePermissions();
  const canExport = hasPerm("EXPORT_DATA");
  const [wizardUnit, setWizardUnit] = useState<WizardUnit | null>(null);
  const [wizardBooking, setWizardBooking] = useState<Booking | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  // Staged unit-lifecycle action (Booked → Registered → Sold) from the list.
  const [markAction, setMarkAction] = useState<{ unitId: string; label: string; target: UnitStatus } | null>(null);
  const [marking, setMarking] = useState(false);
  // Payment plan / collections modal for a booking.
  const [payBooking, setPayBooking] = useState<Booking | null>(null);
  // Cancel-booking modal. When the booking already has money collected, the same
  // modal collects refund details instead (a paid booking is cancelled via refund).
  const [cancelTarget, setCancelTarget] = useState<Booking | null>(null);
  const [cancelReason, setCancelReason] = useState("");
  const [cancelling, setCancelling] = useState(false);
  const [refundForm, setRefundForm] = useState<{ deduction: string; mode: PaymentMode; date: string; reference: string }>(
    { deduction: "0", mode: "neft", date: "", reference: "" }
  );
  // Registration modal (deed no. + sub-registrar office + date).
  const [registerTarget, setRegisterTarget] = useState<Booking | null>(null);
  const [regForm, setRegForm] = useState({ date: "", number: "", office: "" });
  const [registering, setRegistering] = useState(false);

  // Available units across all projects, tagged with their tower/project names.
  const availableUnits = projects.flatMap((p) =>
    p.towers.flatMap((t) =>
      t.units
        .filter((u) => u.status === "available")
        .map((u) => ({ ...u, towerName: t.name, projectName: p.name, priceDefaults: priceDefaultsForProject(p, u.unitType) }))
    )
  );

  // Resolve a unit id to its full context (unit + tower/project names) from the
  // loaded projects — used to resume a booking and to name deep-linked units.
  function unitContext(unitId: string): WizardUnit | null {
    for (const p of projects) {
      for (const t of p.towers) {
        const u = t.units.find((x) => x.id === unitId);
        if (u) return { ...u, towerName: t.name, projectName: p.name, priceDefaults: priceDefaultsForProject(p, u.unitType) };
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
        priceDefaults: ctx?.priceDefaults ?? null,
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
      return { ...prev, towerName, projectName, priceDefaults: ctx.priceDefaults };
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

  async function confirmCancel() {
    if (!cancelTarget) return;
    const paid = cancelTarget.paymentReceipts.reduce((n, r) => n + r.amount, 0);
    // A paid booking can only be cancelled by recording a refund (server blocks
    // a plain cancel once money is collected).
    if (paid > 0) {
      const deduction = Number(refundForm.deduction) || 0;
      if (!refundForm.date) {
        toast.error("Refund date is required");
        return;
      }
      if (deduction > paid) {
        toast.error("Deduction can't exceed the amount paid", formatInr(paid));
        return;
      }
      setCancelling(true);
      try {
        await bookingsService.refundBooking(cancelTarget.id, {
          deduction_amount: deduction,
          mode: refundForm.mode,
          refunded_on: refundForm.date,
          reference: refundForm.reference.trim() || null,
          reason: cancelReason.trim() || null,
        });
        toast.success("Booking refunded & cancelled", `Net refund ${formatInr(paid - deduction)}`);
        setCancelTarget(null);
        refresh();
        void refreshInventory();
      } catch (err) {
        toast.error("Could not refund", extractErrorMessage(err));
      } finally {
        setCancelling(false);
      }
      return;
    }
    setCancelling(true);
    try {
      await bookingsService.cancelBooking(cancelTarget.id, cancelReason.trim() || null);
      toast.success("Booking cancelled");
      setCancelTarget(null);
      refresh();
      // The unit was freed back to Available — refresh inventory too.
      void refreshInventory();
    } catch (err) {
      toast.error("Could not cancel", extractErrorMessage(err));
    } finally {
      setCancelling(false);
    }
  }

  function openRegister(b: Booking) {
    setRegForm({
      date: b.scheduledDate ?? new Date().toISOString().slice(0, 10),
      number: b.registrationNumber ?? "",
      office: b.subRegistrarOffice ?? "",
    });
    setRegisterTarget(b);
  }

  async function confirmRegister() {
    if (!registerTarget) return;
    if (!regForm.date) {
      toast.error("Registration date is required");
      return;
    }
    setRegistering(true);
    try {
      await bookingsService.registerBooking(registerTarget.id, {
        registration_date: regForm.date,
        registration_number: regForm.number.trim() || null,
        sub_registrar_office: regForm.office.trim() || null,
      });
      toast.success("Registered", "Unit marked Registered");
      setRegisterTarget(null);
      refresh();
      void refreshInventory();
    } catch (err) {
      toast.error("Could not register", extractErrorMessage(err));
    } finally {
      setRegistering(false);
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
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Badge tone={STATUS_TONE[b.status] ?? "neutral"}>
            {b.status.charAt(0).toUpperCase() + b.status.slice(1)}
          </Badge>
          {b.status !== "cancelled" && (
            <Button
              size="sm"
              variant="ghost"
              onClick={(e) => {
                e.stopPropagation();
                setCancelReason("");
                setRefundForm({ deduction: "0", mode: "neft", date: new Date().toISOString().slice(0, 10), reference: "" });
                setCancelTarget(b);
              }}
            >
              Cancel
            </Button>
          )}
        </div>
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
                if (ctx.status === "booked") openRegister(b);
                else askMark(ctx, "sold");
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
        <div className="row" style={{ gap: "0.5rem" }}>
          {canExport && (
            <Button
              variant="secondary"
              size="sm"
              icon={<Download size={14} />}
              onClick={() => void exportsService.bookings().catch((e) => toast.error("Export failed", extractErrorMessage(e)))}
            >
              Export CSV
            </Button>
          )}
          <Button variant="primary" icon={<Plus size={16} />} onClick={() => setPickerOpen(true)}>
            New Booking
          </Button>
        </div>
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
          priceDefaults={wizardUnit.priceDefaults}
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

      {cancelTarget && (() => {
        const paid = cancelTarget.paymentReceipts.reduce((n, r) => n + r.amount, 0);
        const isRefund = paid > 0;
        const deduction = Number(refundForm.deduction) || 0;
        const net = Math.max(0, paid - deduction);
        return (
          <Modal
            open
            title={isRefund ? "Refund & cancel booking" : "Cancel booking"}
            onClose={() => setCancelTarget(null)}
            footer={
              <>
                <Button variant="secondary" onClick={() => setCancelTarget(null)} disabled={cancelling}>
                  Keep booking
                </Button>
                <Button variant="danger" loading={cancelling} onClick={() => void confirmCancel()}>
                  {isRefund ? "Refund & cancel" : "Cancel booking"}
                </Button>
              </>
            }
          >
            <div className="stack" style={{ gap: "0.75rem" }}>
              <p className="text-sm">
                This frees{" "}
                {cancelTarget.unit
                  ? `${cancelTarget.unit.projectName} · ${cancelTarget.unit.towerName} · ${cancelTarget.unit.unitNumber}`
                  : "the unit"}{" "}
                back to Available.
              </p>
              {isRefund && (
                <>
                  <div className="row row--between text-sm" style={{ padding: "0.25rem 0" }}>
                    <span className="muted">Collected so far</span>
                    <strong>{formatInr(paid)}</strong>
                  </div>
                  <TextField
                    id="refund-deduction"
                    label="Deduction / forfeiture (₹)"
                    type="number"
                    min="0"
                    value={refundForm.deduction}
                    onChange={(e) => setRefundForm({ ...refundForm, deduction: e.target.value })}
                    hint="Cancellation charges withheld by the builder. 0 = full refund."
                  />
                  <div className="row row--between text-sm" style={{ padding: "0.25rem 0" }}>
                    <span className="muted">Net refund to buyer</span>
                    <strong style={{ fontSize: "var(--text-display-sm)" }}>{formatInr(net)}</strong>
                  </div>
                  <div className="form-grid">
                    <SelectField
                      id="refund-mode"
                      label="Refund mode"
                      value={refundForm.mode}
                      onChange={(e) => setRefundForm({ ...refundForm, mode: e.target.value as PaymentMode })}
                      options={[
                        { value: "neft", label: "NEFT / Bank transfer" },
                        { value: "upi", label: "UPI" },
                        { value: "cheque", label: "Cheque" },
                        { value: "cash", label: "Cash" },
                        { value: "card", label: "Card" },
                        { value: "other", label: "Other" },
                      ]}
                    />
                    <TextField
                      id="refund-date"
                      label="Refund date"
                      type="date"
                      value={refundForm.date}
                      onChange={(e) => setRefundForm({ ...refundForm, date: e.target.value })}
                      required
                    />
                  </div>
                  <TextField
                    id="refund-reference"
                    label="Reference (optional)"
                    value={refundForm.reference}
                    onChange={(e) => setRefundForm({ ...refundForm, reference: e.target.value })}
                    placeholder="e.g. UTR / cheque no."
                  />
                </>
              )}
              <TextField
                id="cancel-reason"
                label="Reason (optional)"
                value={cancelReason}
                onChange={(e) => setCancelReason(e.target.value)}
                placeholder="e.g. Customer backed out"
              />
            </div>
          </Modal>
        );
      })()}

      {registerTarget && (
        <Modal
          open
          title="Register unit"
          onClose={() => setRegisterTarget(null)}
          footer={
            <>
              <Button variant="secondary" onClick={() => setRegisterTarget(null)} disabled={registering}>
                Cancel
              </Button>
              <Button loading={registering} onClick={() => void confirmRegister()}>
                Mark Registered
              </Button>
            </>
          }
        >
          <div className="stack" style={{ gap: "0.75rem" }}>
            <p className="text-sm muted">
              Records the legal registration and moves the unit to Registered.
            </p>
            <TextField
              id="reg-date"
              label="Registration date"
              type="date"
              value={regForm.date}
              onChange={(e) => setRegForm({ ...regForm, date: e.target.value })}
              required
            />
            <TextField
              id="reg-number"
              label="Registration / deed no. (optional)"
              value={regForm.number}
              onChange={(e) => setRegForm({ ...regForm, number: e.target.value })}
              placeholder="e.g. SRO-2026-12345"
            />
            <TextField
              id="reg-office"
              label="Sub-registrar office (optional)"
              value={regForm.office}
              onChange={(e) => setRegForm({ ...regForm, office: e.target.value })}
              placeholder="e.g. SRO Whitefield"
            />
          </div>
        </Modal>
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
