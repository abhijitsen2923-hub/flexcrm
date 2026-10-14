import { useEffect, useMemo, useState } from "react";
import axios from "axios";
import { FileDown, Plus, Trash2 } from "lucide-react";
import { Badge, Button, Modal, SelectField, TextField, useToast } from "../../../components";
import { usePermissions } from "../../../hooks/usePermissions";
import { bookingsService } from "../../../services/bookings";
import type { Booking, BookingInvoice, PaymentMode, PaymentScheduleEntry, PlanMilestone } from "../../../types/realestate";
import { extractErrorMessage } from "../../../utils/errors";
import { formatDate, formatInr } from "../../../utils/format";
import {
  dueOnText,
  formatPercent,
  isTokenOnlySchedule,
  localIsoDate,
  milestoneAmount,
  pendingMilestones,
  planBase,
} from "../../../utils/paymentPlan";

const MODE_OPTIONS: { value: PaymentMode; label: string }[] = [
  { value: "upi", label: "UPI" },
  { value: "neft", label: "NEFT / RTGS" },
  { value: "cheque", label: "Cheque" },
  { value: "cash", label: "Cash" },
  { value: "card", label: "Card" },
  { value: "other", label: "Other" },
];

type TemplateKey = "down_payment" | "construction" | "custom";

interface BuilderRow {
  installmentName: string;
  percentage: string;
  dueDate: string;
}

function isoAfter(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

function templateRows(key: TemplateKey): BuilderRow[] {
  if (key === "down_payment") {
    return [
      { installmentName: "Booking Amount", percentage: "10", dueDate: isoAfter(0) },
      { installmentName: "Within 60 days", percentage: "80", dueDate: isoAfter(60) },
      { installmentName: "On Possession", percentage: "10", dueDate: isoAfter(180) },
    ];
  }
  if (key === "construction") {
    // RERA construction-linked plan (India): booking token → Bhumi Puja →
    // structure milestones → registry. Percentages sum to 100.
    return [
      { installmentName: "On Booking (token)", percentage: "10", dueDate: isoAfter(0) },
      { installmentName: "Bhumi Puja", percentage: "10", dueDate: isoAfter(30) },
      { installmentName: "Plinth / Foundation", percentage: "15", dueDate: isoAfter(90) },
      { installmentName: "Slab Casting (floor-wise)", percentage: "25", dueDate: isoAfter(180) },
      { installmentName: "Brickwork & Plastering", percentage: "20", dueDate: isoAfter(270) },
      { installmentName: "Flooring & Finishing", percentage: "10", dueDate: isoAfter(330) },
      { installmentName: "On Registry", percentage: "10", dueDate: isoAfter(365) },
    ];
  }
  return [{ installmentName: "", percentage: "", dueDate: isoAfter(0) }];
}

interface Props {
  booking: Booking;
  onClose: () => void;
  onChanged: (updated: Booking) => void;
}

export function PaymentPlanModal({ booking: initial, onClose, onChanged }: Props) {
  const toast = useToast();
  const { has } = usePermissions();
  const canRaise = has("FINANCE_RECORD_PAYMENT");
  const [booking, setBooking] = useState<Booking>(initial);
  const total = Number(booking.pricingSnapshot?.total ?? booking.unit?.basePrice ?? 0);
  // A booking whose only row is the token's "Booking amount" (no project plan) has no plan yet: offer the builder,
  // or there'd be no way to set one up or record the next payment. A cancelled one keeps the schedule view with its
  // refund — there is nothing left to plan on it.
  const tokenOnly = booking.status !== "cancelled" && isTokenOnlySchedule(booking.paymentPlan, booking.paymentSchedules);
  // A booking that took its project's payment plan has a plan even before any demand is raised (e.g. every
  // milestone waits for a stage) — show the schedule view with what's still to come, not the plan builder.
  const hasPlan = !tokenOnly && (booking.paymentSchedules.length > 0 || (booking.paymentPlan?.length ?? 0) > 0);
  const pending = pendingMilestones(booking.paymentPlan, booking.paymentSchedules);
  // What plan percentages are taken of (box price + GST), for the "≈ ₹" estimates.
  const base = planBase(booking.pricingSnapshot, booking.unit?.basePrice ?? 0);

  // Raise-now state (a pending plan milestone raised on this booking).
  const [raiseFor, setRaiseFor] = useState<PlanMilestone | null>(null);
  const [raiseDate, setRaiseDate] = useState(localIsoDate());
  const [raising, setRaising] = useState(false);

  // Plan builder state (shown when there is no plan yet).
  const [template, setTemplate] = useState<TemplateKey>("down_payment");
  const [rows, setRows] = useState<BuilderRow[]>(templateRows("down_payment"));
  const [creating, setCreating] = useState(false);

  // Record-payment state (shown when a plan exists).
  const [recordFor, setRecordFor] = useState<PaymentScheduleEntry | null>(null);
  const [payAmount, setPayAmount] = useState("");
  const [payDate, setPayDate] = useState(isoAfter(0));
  const [payMode, setPayMode] = useState<PaymentMode>("upi");
  const [payRef, setPayRef] = useState("");
  const [saving, setSaving] = useState(false);

  // Invoices (demand notes) raised against this booking's installments.
  const [invoices, setInvoices] = useState<BookingInvoice[]>([]);

  const pctSum = useMemo(() => rows.reduce((n, r) => n + (Number(r.percentage) || 0), 0), [rows]);

  function applyTemplate(key: TemplateKey) {
    setTemplate(key);
    setRows(templateRows(key));
  }

  function setRow(i: number, patch: Partial<BuilderRow>) {
    setRows((prev) => prev.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  }

  async function createPlan() {
    const installments = rows
      .filter((r) => r.installmentName.trim() && Number(r.percentage) > 0)
      .map((r) => ({
        installment_name: r.installmentName.trim(),
        due_date: r.dueDate,
        percentage: Number(r.percentage),
      }));
    if (installments.length === 0) {
      toast.error("Add at least one installment with a name and %");
      return;
    }
    setCreating(true);
    try {
      const updated = await bookingsService.createPaymentPlan(booking.id, installments);
      setBooking(updated);
      onChanged(updated);
      toast.success("Payment plan created", `${installments.length} installments`);
    } catch (e) {
      toast.error("Could not create plan", extractErrorMessage(e));
    } finally {
      setCreating(false);
    }
  }

  function openRecord(inst: PaymentScheduleEntry) {
    setRaiseFor(null);
    setRecordFor(inst);
    setPayAmount(String(inst.outstanding));
    setPayDate(isoAfter(0));
    setPayMode("upi");
    setPayRef("");
  }

  async function submitPayment() {
    if (!recordFor) return;
    const amount = Number(payAmount);
    if (!(amount > 0)) {
      toast.error("Enter a valid amount");
      return;
    }
    setSaving(true);
    try {
      const updated = await bookingsService.recordPayment(booking.id, {
        schedule_id: recordFor.id,
        amount,
        paid_on: payDate,
        mode: payMode,
        reference: payRef.trim() || null,
      });
      setBooking(updated);
      onChanged(updated);
      setRecordFor(null);
      toast.success("Payment recorded", formatInr(amount));
    } catch (e) {
      toast.error("Could not record payment", extractErrorMessage(e));
    } finally {
      setSaving(false);
    }
  }

  function openRaise(milestone: PlanMilestone) {
    setRecordFor(null);
    setRaiseFor(milestone);
    setRaiseDate(localIsoDate());
  }

  async function submitRaise() {
    if (!raiseFor) return;
    if (!raiseDate) {
      toast.error("Pick the date this demand is due");
      return;
    }
    setRaising(true);
    try {
      const updated = await bookingsService.raiseMilestone(booking.id, raiseFor.key, raiseDate);
      setBooking(updated);
      onChanged(updated);
      const row = updated.paymentSchedules.find((p) => p.milestoneKey === raiseFor.key);
      toast.success("Demand raised", row ? `${raiseFor.label} · ${formatInr(row.demandAmount)}` : raiseFor.label);
      setRaiseFor(null);
    } catch (e) {
      toast.error("Could not raise the demand", extractErrorMessage(e));
      // Someone raised it meanwhile (or the project marked it reached) — show the booking as it is now.
      if (axios.isAxiosError(e) && e.response?.status === 409) {
        try {
          const fresh = await bookingsService.get(booking.id);
          setBooking(fresh);
          onChanged(fresh);
          setRaiseFor(null);
        } catch {
          /* keep the current view */
        }
      }
    } finally {
      setRaising(false);
    }
  }

  async function openReceipt(receiptId: string) {
    try {
      const { url } = await bookingsService.getReceiptPdfUrl(booking.id, receiptId);
      window.open(url, "_blank", "noopener");
    } catch {
      toast.error("Receipt unavailable", "File storage isn't configured yet.");
    }
  }

  async function loadInvoices() {
    try {
      setInvoices(await bookingsService.listInvoices(booking.id));
    } catch {
      /* ignore — an invoice-list error shouldn't break the plan/collections view */
    }
  }

  useEffect(() => {
    if (hasPlan) void loadInvoices();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [booking.id, hasPlan]);

  async function raiseInvoice(schedule: PaymentScheduleEntry) {
    try {
      await bookingsService.createInvoice(booking.id, { schedule_id: schedule.id });
      toast.success("Invoice raised", schedule.installmentName);
      await loadInvoices();
    } catch (e) {
      toast.error("Could not raise invoice", extractErrorMessage(e));
    }
  }

  async function openInvoicePdf(invoiceId: string) {
    try {
      const { url } = await bookingsService.getInvoicePdfUrl(booking.id, invoiceId);
      window.open(url, "_blank", "noopener");
    } catch {
      toast.error("Invoice unavailable", "File storage isn't configured yet.");
    }
  }

  async function toggleInvoicePaid(inv: BookingInvoice) {
    try {
      await bookingsService.updateInvoiceStatus(booking.id, inv.id, inv.status === "paid" ? "issued" : "paid");
      await loadInvoices();
    } catch (e) {
      toast.error("Could not update invoice", extractErrorMessage(e));
    }
  }

  const demandTotal = booking.paymentSchedules.reduce((n, p) => n + p.demandAmount, 0);
  const paidTotal = booking.paymentSchedules.reduce((n, p) => n + p.paidAmount, 0);
  const outstandingTotal = booking.paymentSchedules.reduce((n, p) => n + p.outstanding, 0);

  // Receipts show in both views: a token-only booking (plan builder) still lists the token it holds.
  const receiptsList =
    booking.paymentReceipts.length > 0 ? (
      <div>
        <div className="muted text-xs" style={{ textTransform: "uppercase", letterSpacing: ".04em", margin: "0.5rem 0" }}>
          Receipts
        </div>
        <div className="stack" style={{ gap: "0.4rem" }}>
          {booking.paymentReceipts.map((r) => (
            <div key={r.id} className="row row--between" style={{ alignItems: "center", padding: "0.4rem 0.6rem", border: "1px solid var(--color-border)", borderRadius: "var(--radius-sm)" }}>
              <span className="text-sm">
                {formatDate(r.paidOn)} · <strong>{formatInr(r.amount)}</strong>{" "}
                {r.isToken && <><Badge tone="info">Token</Badge>{" "}</>}
                <span className="muted">· {r.mode.toUpperCase()}{r.reference ? ` · ${r.reference}` : ""}</span>
              </span>
              <Button size="sm" variant="ghost" icon={<FileDown size={14} />} onClick={() => void openReceipt(r.id)}>
                Receipt
              </Button>
            </div>
          ))}
        </div>
      </div>
    ) : null;

  return (
    <Modal open title="Payment plan & collections" size="lg" onClose={onClose}>
      <div className="stack" style={{ gap: "1rem" }}>
        <div className="muted text-sm">
          {booking.unit ? `${booking.unit.projectName} · ${booking.unit.towerName} · ${booking.unit.unitNumber}` : "Unit"}
          {" · "}Total consideration <strong>{formatInr(total)}</strong>
        </div>

        {!hasPlan ? (
          /* ---- Plan builder ---- */
          <div className="stack" style={{ gap: "0.75rem" }}>
            <SelectField
              id="plan-template"
              label="Plan template"
              value={template}
              onChange={(e) => applyTemplate(e.target.value as TemplateKey)}
              options={[
                { value: "down_payment", label: "Down payment (10 / 80 / 10)" },
                { value: "construction", label: "Construction-linked (milestones)" },
                { value: "custom", label: "Custom" },
              ]}
            />

            <table className="table">
              <thead>
                <tr>
                  <th style={{ textAlign: "left" }}>Installment</th>
                  <th style={{ textAlign: "right", width: 90 }}>%</th>
                  <th style={{ textAlign: "right", width: 140 }}>Amount</th>
                  <th style={{ textAlign: "left", width: 160 }}>Due date</th>
                  <th style={{ width: 40 }} />
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={i}>
                    <td>
                      <input
                        className="input"
                        value={r.installmentName}
                        placeholder="e.g. On Booking"
                        onChange={(e) => setRow(i, { installmentName: e.target.value })}
                      />
                    </td>
                    <td>
                      <input
                        className="input"
                        type="number"
                        min={0}
                        max={100}
                        style={{ textAlign: "right" }}
                        value={r.percentage}
                        onChange={(e) => setRow(i, { percentage: e.target.value })}
                      />
                    </td>
                    <td style={{ textAlign: "right" }}>
                      {formatInr(((Number(r.percentage) || 0) / 100) * total)}
                    </td>
                    <td>
                      <input
                        className="input"
                        type="date"
                        value={r.dueDate}
                        onChange={(e) => setRow(i, { dueDate: e.target.value })}
                      />
                    </td>
                    <td>
                      <button
                        type="button"
                        className="btn btn--ghost btn--icon"
                        onClick={() => setRows((prev) => prev.filter((_, idx) => idx !== i))}
                        aria-label="Remove installment"
                      >
                        <Trash2 size={14} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            <div className="row row--between" style={{ alignItems: "center" }}>
              <Button
                size="sm"
                variant="ghost"
                icon={<Plus size={14} />}
                onClick={() => setRows((prev) => [...prev, { installmentName: "", percentage: "", dueDate: isoAfter(0) }])}
              >
                Add installment
              </Button>
              <span className={pctSum === 100 ? "muted text-sm" : "text-sm"} style={{ color: pctSum === 100 ? undefined : "var(--color-danger,#b91c1c)" }}>
                Total: {pctSum}% {pctSum !== 100 && "(should be 100%)"}
              </span>
            </div>

            {tokenOnly && (
              <p className="muted text-sm" style={{ margin: 0 }}>The token already received is applied to the first instalment.</p>
            )}

            <div className="row" style={{ justifyContent: "flex-end", gap: "0.5rem" }}>
              <Button variant="secondary" onClick={onClose}>Cancel</Button>
              <Button loading={creating} onClick={() => void createPlan()}>Create plan</Button>
            </div>

            {receiptsList}
          </div>
        ) : (
          /* ---- Schedule + collections ---- */
          <div className="stack" style={{ gap: "0.75rem" }}>
            <table className="table">
              <thead>
                <tr>
                  <th style={{ textAlign: "left" }}>Installment</th>
                  <th style={{ textAlign: "left" }}>Due</th>
                  <th style={{ textAlign: "right" }}>Demand</th>
                  <th style={{ textAlign: "right" }}>Paid</th>
                  <th style={{ textAlign: "right" }}>Outstanding</th>
                  <th style={{ width: 90 }} />
                </tr>
              </thead>
              <tbody>
                {booking.paymentSchedules.length === 0 && (
                  <tr>
                    <td colSpan={6} className="muted text-sm">No demands raised yet — the plan's milestones are listed below.</td>
                  </tr>
                )}
                {booking.paymentSchedules.map((p) => (
                  <tr key={p.id}>
                    <td data-label="Installment">
                      {p.installmentName}
                      {/* A plan row keeps following the booking's price until it's paid, invoiced or edited. */}
                      {p.percent != null && <div className="muted text-xs">{formatPercent(p.percent)} of price</div>}
                    </td>
                    <td data-label="Due">
                      {formatDate(p.dueDate)} {p.isOverdue && <Badge tone="danger">Overdue</Badge>}
                    </td>
                    <td data-label="Demand" style={{ textAlign: "right" }}>{formatInr(p.demandAmount)}</td>
                    <td data-label="Paid" style={{ textAlign: "right" }}>{formatInr(p.paidAmount)}</td>
                    <td data-label="Outstanding" style={{ textAlign: "right" }}>{formatInr(p.outstanding)}</td>
                    <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                      {p.outstanding > 0 && (
                        <Button size="sm" variant="secondary" onClick={() => openRecord(p)}>Record</Button>
                      )}{" "}
                      <Button size="sm" variant="ghost" onClick={() => void raiseInvoice(p)}>Invoice</Button>
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr style={{ fontWeight: 600 }}>
                  <td colSpan={2}>Total</td>
                  <td style={{ textAlign: "right" }}>{formatInr(demandTotal)}</td>
                  <td style={{ textAlign: "right" }}>{formatInr(paidTotal)}</td>
                  <td style={{ textAlign: "right" }}>{formatInr(outstandingTotal)}</td>
                  <td />
                </tr>
              </tfoot>
            </table>

            {recordFor && (
              <div className="card" style={{ padding: "0.85rem 1rem" }}>
                <div style={{ fontWeight: 600, marginBottom: "0.5rem" }}>Record payment — {recordFor.installmentName}</div>
                <div className="form-grid">
                  <TextField id="pay-amount" label="Amount (₹)" type="number" min={1} value={payAmount} onChange={(e) => setPayAmount(e.target.value)} />
                  <TextField id="pay-date" label="Paid on" type="date" value={payDate} onChange={(e) => setPayDate(e.target.value)} />
                  <SelectField id="pay-mode" label="Mode" value={payMode} onChange={(e) => setPayMode(e.target.value as PaymentMode)} options={MODE_OPTIONS} />
                  <TextField id="pay-ref" label="Reference (optional)" value={payRef} onChange={(e) => setPayRef(e.target.value)} placeholder="UTR / cheque no." />
                </div>
                <div className="row" style={{ justifyContent: "flex-end", gap: "0.5rem", marginTop: "0.6rem" }}>
                  <Button variant="secondary" onClick={() => setRecordFor(null)}>Cancel</Button>
                  <Button loading={saving} onClick={() => void submitPayment()}>Save payment</Button>
                </div>
              </div>
            )}

            {pending.length > 0 && (
              <div>
                <div className="muted text-xs" style={{ textTransform: "uppercase", letterSpacing: ".04em", margin: "0.5rem 0" }}>
                  Still to be raised
                </div>
                <p className="muted text-xs" style={{ margin: "0 0 0.5rem" }}>
                  From the project's payment plan. Stage, possession and registration milestones are raised on every
                  booking when they're marked reached on the project page{canRaise ? " — or raise one here for this booking" : ""}.
                </p>
                <div className="stack" style={{ gap: "0.4rem" }}>
                  {pending.map((ms) => (
                    <div
                      key={ms.key}
                      className="row row--between"
                      style={{ alignItems: "center", flexWrap: "wrap", gap: "0.5rem", padding: "0.4rem 0.6rem", border: "1px dashed var(--color-border)", borderRadius: "var(--radius-sm)" }}
                    >
                      <span className="text-sm">
                        <strong>{ms.label}</strong> · {formatPercent(ms.percent)}{" "}
                        <span className="muted">
                          · {dueOnText(ms, formatDate)}
                          {base > 0 ? ` · ≈ ${formatInr(milestoneAmount(ms.percent, base))}` : ""}
                        </span>
                      </span>
                      {canRaise && booking.status !== "cancelled" && (
                        <Button size="sm" variant="secondary" onClick={() => openRaise(ms)}>
                          Raise now
                        </Button>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {raiseFor && (
              <div className="card" style={{ padding: "0.85rem 1rem" }}>
                <div style={{ fontWeight: 600, marginBottom: "0.5rem" }}>
                  Raise demand — {raiseFor.label} ({formatPercent(raiseFor.percent)})
                </div>
                <div className="form-grid">
                  <TextField id="raise-due" label="Due on" type="date" value={raiseDate} onChange={(e) => setRaiseDate(e.target.value)} required />
                </div>
                <p className="muted text-xs" style={{ margin: "0.4rem 0 0" }}>
                  {formatPercent(raiseFor.percent)} of the booking's price (box price + GST)
                  {base > 0 ? ` ≈ ${formatInr(milestoneAmount(raiseFor.percent, base))}` : ""}.
                </p>
                <div className="row" style={{ justifyContent: "flex-end", gap: "0.5rem", marginTop: "0.6rem" }}>
                  <Button variant="secondary" onClick={() => setRaiseFor(null)} disabled={raising}>Cancel</Button>
                  <Button loading={raising} onClick={() => void submitRaise()}>Raise demand</Button>
                </div>
              </div>
            )}

            {receiptsList}

            {invoices.length > 0 && (
              <div>
                <div className="muted text-xs" style={{ textTransform: "uppercase", letterSpacing: ".04em", margin: "0.5rem 0" }}>
                  Invoices
                </div>
                <div className="stack" style={{ gap: "0.4rem" }}>
                  {invoices.map((inv) => (
                    <div key={inv.id} className="row row--between" style={{ alignItems: "center", padding: "0.4rem 0.6rem", border: "1px solid var(--color-border)", borderRadius: "var(--radius-sm)" }}>
                      <span className="text-sm">
                        <strong>{inv.invoiceNumber}</strong> · {inv.installmentName} · {formatInr(inv.amount)}
                        {inv.dueDate ? <span className="muted"> · due {formatDate(inv.dueDate)}</span> : null}{" "}
                        <Badge tone={inv.status === "paid" ? "success" : inv.status === "void" ? "neutral" : "warning"}>{inv.status}</Badge>
                      </span>
                      <span className="row" style={{ gap: 4, alignItems: "center" }}>
                        <Button size="sm" variant="ghost" onClick={() => void toggleInvoicePaid(inv)}>
                          {inv.status === "paid" ? "Mark issued" : "Mark paid"}
                        </Button>
                        <Button size="sm" variant="ghost" icon={<FileDown size={14} />} onClick={() => void openInvoicePdf(inv.id)}>
                          PDF
                        </Button>
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {booking.refunds.length > 0 && (
              <div>
                <div className="muted text-xs" style={{ textTransform: "uppercase", letterSpacing: ".04em", margin: "0.5rem 0" }}>
                  Refunds
                </div>
                <div className="stack" style={{ gap: "0.4rem" }}>
                  {booking.refunds.map((r) => (
                    <div key={r.id} className="row row--between" style={{ alignItems: "center", padding: "0.4rem 0.6rem", border: "1px solid var(--color-border)", borderRadius: "var(--radius-sm)" }}>
                      <span className="text-sm">
                        {formatDate(r.refundedOn)} · <strong>{formatInr(r.refundAmount)}</strong> refunded{" "}
                        <span className="muted">
                          · {r.mode.toUpperCase()}
                          {r.deductionAmount > 0 ? ` · ${formatInr(r.deductionAmount)} withheld` : ""}
                          {r.reference ? ` · ${r.reference}` : ""}
                        </span>
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </Modal>
  );
}
