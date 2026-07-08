import { useMemo, useState } from "react";
import { FileDown, Plus, Trash2 } from "lucide-react";
import { Badge, Button, Modal, SelectField, TextField, useToast } from "../../../components";
import { bookingsService } from "../../../services/bookings";
import type { Booking, PaymentMode, PaymentScheduleEntry } from "../../../types/realestate";
import { extractErrorMessage } from "../../../utils/errors";
import { formatDate, formatInr } from "../../../utils/format";

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
    return [
      { installmentName: "On Booking", percentage: "10", dueDate: isoAfter(0) },
      { installmentName: "Foundation", percentage: "20", dueDate: isoAfter(60) },
      { installmentName: "Superstructure", percentage: "30", dueDate: isoAfter(150) },
      { installmentName: "Walls & Plastering", percentage: "20", dueDate: isoAfter(240) },
      { installmentName: "Finishing", percentage: "10", dueDate: isoAfter(300) },
      { installmentName: "On Possession", percentage: "10", dueDate: isoAfter(365) },
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
  const [booking, setBooking] = useState<Booking>(initial);
  const total = Number(booking.pricingSnapshot?.total ?? booking.unit?.basePrice ?? 0);
  const hasPlan = booking.paymentSchedules.length > 0;

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

  async function openReceipt(receiptId: string) {
    try {
      const { url } = await bookingsService.getReceiptPdfUrl(booking.id, receiptId);
      window.open(url, "_blank", "noopener");
    } catch {
      toast.error("Receipt unavailable", "File storage isn't configured yet.");
    }
  }

  const demandTotal = booking.paymentSchedules.reduce((n, p) => n + p.demandAmount, 0);
  const paidTotal = booking.paymentSchedules.reduce((n, p) => n + p.paidAmount, 0);
  const outstandingTotal = booking.paymentSchedules.reduce((n, p) => n + p.outstanding, 0);

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

            <div className="row" style={{ justifyContent: "flex-end", gap: "0.5rem" }}>
              <Button variant="secondary" onClick={onClose}>Cancel</Button>
              <Button loading={creating} onClick={() => void createPlan()}>Create plan</Button>
            </div>
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
                {booking.paymentSchedules.map((p) => (
                  <tr key={p.id}>
                    <td>{p.installmentName}</td>
                    <td>
                      {formatDate(p.dueDate)} {p.isOverdue && <Badge tone="danger">Overdue</Badge>}
                    </td>
                    <td style={{ textAlign: "right" }}>{formatInr(p.demandAmount)}</td>
                    <td style={{ textAlign: "right" }}>{formatInr(p.paidAmount)}</td>
                    <td style={{ textAlign: "right" }}>{formatInr(p.outstanding)}</td>
                    <td style={{ textAlign: "right" }}>
                      {p.outstanding > 0 && (
                        <Button size="sm" variant="secondary" onClick={() => openRecord(p)}>Record</Button>
                      )}
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

            {booking.paymentReceipts.length > 0 && (
              <div>
                <div className="muted text-xs" style={{ textTransform: "uppercase", letterSpacing: ".04em", margin: "0.5rem 0" }}>
                  Receipts
                </div>
                <div className="stack" style={{ gap: "0.4rem" }}>
                  {booking.paymentReceipts.map((r) => (
                    <div key={r.id} className="row row--between" style={{ alignItems: "center", padding: "0.4rem 0.6rem", border: "1px solid var(--color-border)", borderRadius: "var(--radius-sm)" }}>
                      <span className="text-sm">
                        {formatDate(r.paidOn)} · <strong>{formatInr(r.amount)}</strong>{" "}
                        <span className="muted">· {r.mode.toUpperCase()}{r.reference ? ` · ${r.reference}` : ""}</span>
                      </span>
                      <Button size="sm" variant="ghost" icon={<FileDown size={14} />} onClick={() => void openReceipt(r.id)}>
                        Receipt
                      </Button>
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
