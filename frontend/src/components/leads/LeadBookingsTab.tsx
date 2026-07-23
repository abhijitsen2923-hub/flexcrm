import { useEffect, useState } from "react";
import { Badge, Button, EmptyState, LoadingBlock, Modal, SelectField, TextField, useToast } from "../../components";
import { bookingsService } from "../../services/bookings";
import { inventoryService } from "../../services/inventory";
import { BookingWizard } from "../../pages/bookings/components/BookingWizard";
import { PaymentPlanModal } from "../../pages/bookings/components/PaymentPlanModal";
import type { PriceDefaults } from "../../pages/inventory/components/PriceCalculator";
import type { Booking, PaymentMode } from "../../types/realestate";
import { priceDefaultsForProject } from "../../utils/priceDefaults";
import { extractErrorMessage } from "../../utils/errors";
import { formatDate, formatInr } from "../../utils/format";

type WizardUnit = {
  id: string;
  unitNumber: string;
  floor: number;
  area: number;
  basePrice: number;
  status: string;
  towerName: string;
  projectName: string;
  priceDefaults?: PriceDefaults | null;
};

const STATUS_TONE = { draft: "warning", confirmed: "success", cancelled: "neutral" } as const;

const PAYMENT_MODES: { value: PaymentMode; label: string }[] = [
  { value: "upi", label: "UPI" },
  { value: "neft", label: "NEFT / RTGS" },
  { value: "cheque", label: "Cheque" },
  { value: "cash", label: "Cash" },
  { value: "card", label: "Card" },
  { value: "other", label: "Other" },
];

interface Props {
  leadId: string;
  customerId: string | null;
  refreshKey?: number;
}

/**
 * "Booking & Payments" tab for a lead — makes the lead the source of truth for
 * its registration + money. Lists the lead's linked booking(s), lets staff
 * manage the payment plan/receipts (PaymentPlanModal), mark registration, and
 * start a new booking (linked back to the lead).
 */
export function LeadBookingsTab({ leadId, customerId, refreshKey }: Props) {
  const toast = useToast();
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [loading, setLoading] = useState(true);

  const [payBooking, setPayBooking] = useState<Booking | null>(null);

  // Start-booking flow: pick an available unit → wizard (linked to this lead).
  const [pickerOpen, setPickerOpen] = useState(false);
  const [availUnits, setAvailUnits] = useState<WizardUnit[]>([]);
  const [pickerLoading, setPickerLoading] = useState(false);
  const [wizardUnit, setWizardUnit] = useState<WizardUnit | null>(null);

  // Registration.
  const [registerTarget, setRegisterTarget] = useState<Booking | null>(null);
  const [regForm, setRegForm] = useState({ date: "", number: "", office: "" });
  const [registering, setRegistering] = useState(false);

  // Token / booking amount.
  const [tokenTarget, setTokenTarget] = useState<Booking | null>(null);
  const [tokenForm, setTokenForm] = useState<{ amount: string; date: string; mode: PaymentMode; reference: string }>({
    amount: "",
    date: "",
    mode: "neft",
    reference: "",
  });
  const [savingToken, setSavingToken] = useState(false);

  async function load() {
    setLoading(true);
    try {
      setBookings(await bookingsService.list({ leadId }));
    } catch (err) {
      toast.error("Could not load bookings", extractErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [leadId, refreshKey]);

  async function openPicker() {
    setPickerLoading(true);
    try {
      const projects = await inventoryService.listProjects();
      const units = projects.flatMap((p) =>
        p.towers.flatMap((t) =>
          t.units
            .filter((u) => u.status === "available")
            .map((u) => ({
              id: u.id,
              unitNumber: u.unitNumber,
              floor: u.floor,
              area: u.area,
              basePrice: u.basePrice,
              status: u.status,
              towerName: t.name,
              projectName: p.name,
              priceDefaults: priceDefaultsForProject(p, u.unitType),
            }))
        )
      );
      setAvailUnits(units);
      setPickerOpen(true);
    } catch (err) {
      toast.error("Could not load units", extractErrorMessage(err));
    } finally {
      setPickerLoading(false);
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
    if (!registerTarget || !regForm.date) {
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
      await load();
    } catch (err) {
      toast.error("Could not register", extractErrorMessage(err));
    } finally {
      setRegistering(false);
    }
  }

  function openToken(b: Booking) {
    setTokenForm({
      amount: b.tokenAmount != null ? String(b.tokenAmount) : "",
      date: b.tokenReceivedOn ?? new Date().toISOString().slice(0, 10),
      mode: b.tokenMode ?? "neft",
      reference: b.tokenReference ?? "",
    });
    setTokenTarget(b);
  }

  async function confirmToken() {
    if (!tokenTarget) return;
    const amount = Number(tokenForm.amount);
    if (!(amount > 0)) {
      toast.error("Enter a token amount greater than 0");
      return;
    }
    if (!tokenForm.date) {
      toast.error("Token date is required");
      return;
    }
    setSavingToken(true);
    try {
      await bookingsService.recordToken(tokenTarget.id, {
        token_amount: amount,
        token_received_on: tokenForm.date,
        token_mode: tokenForm.mode,
        token_reference: tokenForm.reference.trim() || null,
      });
      toast.success("Token recorded", formatInr(amount));
      setTokenTarget(null);
      await load();
    } catch (err) {
      toast.error("Could not record token", extractErrorMessage(err));
    } finally {
      setSavingToken(false);
    }
  }

  async function downloadTokenReceipt(b: Booking) {
    try {
      const { url } = await bookingsService.getTokenReceiptPdfUrl(b.id);
      window.open(url, "_blank", "noopener");
    } catch (err) {
      toast.error("Could not generate receipt", extractErrorMessage(err));
    }
  }

  if (loading) return <LoadingBlock label="Loading bookings…" />;

  return (
    <div className="stack" style={{ gap: "0.75rem" }}>
      <div className="row row--between" style={{ alignItems: "center" }}>
        <strong>Bookings</strong>
        <Button size="sm" variant="secondary" loading={pickerLoading} onClick={() => void openPicker()}>
          Start booking
        </Button>
      </div>

      {bookings.length === 0 ? (
        <EmptyState
          title="No booking yet"
          description="Start a booking for this lead to manage its payments and registration here."
        />
      ) : (
        bookings.map((b) => {
          const total = Number(b.pricingSnapshot?.total ?? b.unit?.basePrice ?? 0);
          const paid = b.paymentReceipts.reduce((n, r) => n + r.amount, 0);
          const demand = b.paymentSchedules.reduce((n, p) => n + p.demandAmount, 0);
          const registered = !!b.registrationNumber;
          return (
            <div key={b.id} className="card" style={{ padding: "0.85rem 1rem" }}>
              <div className="row row--between" style={{ alignItems: "center", marginBottom: "0.4rem" }}>
                <strong>
                  {b.unit ? `${b.unit.projectName} · ${b.unit.towerName} · ${b.unit.unitNumber}` : "Unit"}
                </strong>
                <Badge tone={STATUS_TONE[b.status] ?? "neutral"}>
                  {b.status.charAt(0).toUpperCase() + b.status.slice(1)}
                </Badge>
              </div>
              <div className="row" style={{ gap: "1.25rem", flexWrap: "wrap", marginBottom: "0.5rem" }}>
                <span className="text-sm"><span className="muted">Total</span> <strong>{formatInr(total)}</strong></span>
                <span className="text-sm"><span className="muted">Collected</span> <strong>{formatInr(paid)}</strong>{demand ? <span className="muted"> / {formatInr(demand)}</span> : null}</span>
                <span className="text-sm">
                  <span className="muted">Registration</span>{" "}
                  {registered ? (
                    <strong>{b.registrationNumber}</strong>
                  ) : b.scheduledDate ? (
                    <span>due {formatDate(b.scheduledDate)}</span>
                  ) : (
                    <span className="muted">—</span>
                  )}
                </span>
                <span className="text-sm">
                  <span className="muted">Token</span>{" "}
                  {b.tokenAmount != null ? (
                    <strong>{formatInr(b.tokenAmount)}</strong>
                  ) : (
                    <span className="muted">—</span>
                  )}
                  {b.tokenReceivedOn ? <span className="muted"> · {formatDate(b.tokenReceivedOn)}</span> : null}
                </span>
              </div>
              <div className="row" style={{ gap: "0.5rem", flexWrap: "wrap" }}>
                <Button size="sm" variant="secondary" onClick={() => setPayBooking(b)}>
                  Manage payments
                </Button>
                <Button size="sm" variant="ghost" onClick={() => openToken(b)}>
                  {b.tokenAmount != null ? "Update token" : "Record token"}
                </Button>
                {b.tokenAmount != null && (
                  <Button size="sm" variant="ghost" onClick={() => void downloadTokenReceipt(b)}>
                    Token receipt
                  </Button>
                )}
                {b.status === "confirmed" && !registered && (
                  <Button size="sm" variant="ghost" onClick={() => openRegister(b)}>
                    Mark registered
                  </Button>
                )}
              </div>
            </div>
          );
        })
      )}

      {payBooking && (
        <PaymentPlanModal
          booking={payBooking}
          onClose={() => setPayBooking(null)}
          onChanged={(updated) => {
            setPayBooking(updated);
            void load();
          }}
        />
      )}

      {wizardUnit && (
        <BookingWizard
          unit={wizardUnit}
          leadId={leadId}
          priceDefaults={wizardUnit.priceDefaults}
          onClose={() => setWizardUnit(null)}
          onComplete={() => {
            setWizardUnit(null);
            void load();
          }}
        />
      )}

      {pickerOpen && (
        <Modal
          open
          title="Start booking — choose an available unit"
          onClose={() => setPickerOpen(false)}
          footer={<Button variant="secondary" onClick={() => setPickerOpen(false)}>Cancel</Button>}
        >
          {availUnits.length === 0 ? (
            <EmptyState title="No available units" description="Add units in Projects, then start a booking." />
          ) : (
            <ul style={{ listStyle: "none", margin: 0, padding: 0, maxHeight: 360, overflowY: "auto" }}>
              {availUnits.map((u) => (
                <li key={u.id}>
                  <button
                    type="button"
                    onClick={() => { setWizardUnit(u); setPickerOpen(false); }}
                    style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem", width: "100%", padding: "0.6rem 0.75rem", border: "none", borderBottom: "1px solid var(--color-border)", background: "none", cursor: "pointer", textAlign: "left" }}
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
      )}

      {registerTarget && (
        <Modal
          open
          title="Register unit"
          onClose={() => setRegisterTarget(null)}
          footer={
            <>
              <Button variant="secondary" onClick={() => setRegisterTarget(null)} disabled={registering}>Cancel</Button>
              <Button loading={registering} onClick={() => void confirmRegister()}>Mark Registered</Button>
            </>
          }
        >
          <div className="stack" style={{ gap: "0.75rem" }}>
            <TextField id="lead-reg-date" label="Registration date" type="date" value={regForm.date} onChange={(e) => setRegForm({ ...regForm, date: e.target.value })} required />
            <TextField id="lead-reg-number" label="Registration / deed no. (optional)" value={regForm.number} onChange={(e) => setRegForm({ ...regForm, number: e.target.value })} placeholder="e.g. SRO-2026-12345" />
            <TextField id="lead-reg-office" label="Sub-registrar office (optional)" value={regForm.office} onChange={(e) => setRegForm({ ...regForm, office: e.target.value })} placeholder="e.g. SRO Whitefield" />
          </div>
        </Modal>
      )}

      {tokenTarget && (
        <Modal
          open
          title="Record token / booking amount"
          onClose={() => setTokenTarget(null)}
          footer={
            <>
              <Button variant="secondary" onClick={() => setTokenTarget(null)} disabled={savingToken}>Cancel</Button>
              <Button loading={savingToken} onClick={() => void confirmToken()}>Save token</Button>
            </>
          }
        >
          <div className="stack" style={{ gap: "0.75rem" }}>
            <TextField id="lead-token-amount" label="Token amount (₹)" type="number" min="0" value={tokenForm.amount} onChange={(e) => setTokenForm({ ...tokenForm, amount: e.target.value })} required />
            <TextField id="lead-token-date" label="Received on" type="date" value={tokenForm.date} onChange={(e) => setTokenForm({ ...tokenForm, date: e.target.value })} required />
            <SelectField id="lead-token-mode" label="Payment mode" value={tokenForm.mode} onChange={(e) => setTokenForm({ ...tokenForm, mode: e.target.value as PaymentMode })} options={PAYMENT_MODES} />
            <TextField id="lead-token-reference" label="Reference (optional)" value={tokenForm.reference} onChange={(e) => setTokenForm({ ...tokenForm, reference: e.target.value })} placeholder="e.g. UPI txn / cheque no." />
          </div>
        </Modal>
      )}

      {customerId === null && bookings.length === 0 && (
        <p className="muted text-xs">Tip: link a customer to this lead (on Sold) so the booking carries the buyer's details.</p>
      )}
    </div>
  );
}
