import { useRef, useState } from "react";
import { Button, Modal, TextField, useToast } from "../../../components";
import { bookingsService } from "../../../services/bookings";
import { customersService } from "../../../services/customers";
import { PriceCalculator } from "../../inventory/components/PriceCalculator";
import { DocumentPreview } from "./DocumentPreview";
import type { Booking, PricingSnapshot, Unit } from "../../../types/realestate";
import type { Customer } from "../../../types";
import "./BookingWizard.css";

const STEPS = ["Unit", "Customer & KYC", "Pricing", "Schedule & Documents"] as const;

interface Props {
  unit: Pick<Unit, "id" | "unitNumber" | "floor" | "area" | "basePrice"> & { towerName: string; projectName: string };
  onClose: () => void;
  onComplete: (booking: Booking) => void;
  // When resuming an existing (e.g. draft) booking, pass it here — the wizard
  // opens at its current step instead of creating a new booking.
  initialBooking?: Booking | null;
}

export function BookingWizard({ unit, onClose, onComplete, initialBooking = null }: Props) {
  const toast = useToast();
  const [step, setStep] = useState(
    initialBooking && initialBooking.step >= 1 && initialBooking.step <= 4 ? initialBooking.step : 1
  );
  const [booking, setBooking] = useState<Booking | null>(initialBooking);
  const [saving, setSaving] = useState(false);
  const [pricing, setPricing] = useState<PricingSnapshot | null>(null);
  const [docHtml, setDocHtml] = useState<string | null>(null);
  const [docTitle, setDocTitle] = useState<string>("");

  // Step 2 state
  const [customerId, setCustomerId] = useState("");
  const [customerName, setCustomerName] = useState("");
  const [customerQuery, setCustomerQuery] = useState("");
  const [customerResults, setCustomerResults] = useState<Customer[]>([]);
  const [searchingCust, setSearchingCust] = useState(false);
  const [kycFile, setKycFile] = useState<File | null>(null);
  const [kycDocType, setKycDocType] = useState<string>("aadhaar");
  const fileRef = useRef<HTMLInputElement>(null);

  async function searchCustomers(q: string) {
    setCustomerQuery(q);
    if (q.trim().length < 2) {
      setCustomerResults([]);
      return;
    }
    setSearchingCust(true);
    try {
      const res = await customersService.list({ search: q.trim(), page_size: 8 });
      setCustomerResults(res.items);
    } catch {
      setCustomerResults([]);
    } finally {
      setSearchingCust(false);
    }
  }

  function selectCustomer(c: Customer) {
    setCustomerId(c.id);
    setCustomerName([c.contact_name, c.company_name].filter(Boolean).join(" · "));
    setCustomerQuery("");
    setCustomerResults([]);
  }

  // Step 4 state
  const [scheduledDate, setScheduledDate] = useState("");

  const handleCreateBooking = async () => {
    // Resuming an existing booking — don't create a second one.
    if (booking) {
      setStep(2);
      return;
    }
    setSaving(true);
    try {
      const created = await bookingsService.create({ unitId: unit.id });
      setBooking(created);
      setStep(2);
    } catch {
      toast.error("Failed to start booking");
    } finally {
      setSaving(false);
    }
  };

  const handleKycUpload = async () => {
    if (!booking || !kycFile) return;
    setSaving(true);
    try {
      await bookingsService.uploadKyc(booking.id, kycFile, kycDocType);
      // Keep the existing booking (the /kyc endpoint returns the doc, not the
      // booking) — attach the selected customer as we advance.
      if (customerId) {
        const updated = await bookingsService.advanceStep(booking.id, 2, { customer_id: customerId });
        setBooking(updated);
      }
      setStep(3);
    } catch {
      toast.error("KYC upload failed");
    } finally {
      setSaving(false);
    }
  };

  const handleSavePricing = async () => {
    if (!booking || !pricing) return;
    setSaving(true);
    try {
      const updated = await bookingsService.setPricing(booking.id, pricing);
      setBooking(updated);
      setStep(4);
    } catch {
      toast.error("Failed to save pricing");
    } finally {
      setSaving(false);
    }
  };

  const handleGenerate = async (docType: "booking_form" | "allotment_letter") => {
    if (!booking) return;
    setSaving(true);
    try {
      const { html, title } = await bookingsService.getDocumentHtml(booking.id, docType);
      setDocHtml(html);
      setDocTitle(title);
    } catch {
      toast.error("Document generation failed");
    } finally {
      setSaving(false);
    }
  };

  const handleConfirm = async () => {
    if (!booking) return;
    setSaving(true);
    try {
      const updated = await bookingsService.advanceStep(booking.id, 4, { scheduled_date: scheduledDate || null });
      toast.success("Booking confirmed!");
      onComplete(updated);
    } catch {
      toast.error("Failed to confirm booking");
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <Modal open title="New Booking" size="lg" onClose={onClose}>
        <div className="booking-wizard">
          {/* Step indicator */}
          <div className="booking-wizard__steps" role="list">
            {STEPS.map((label, i) => {
              const stepNum = i + 1;
              const done = stepNum < step;
              const active = stepNum === step;
              return (
                <div
                  key={label}
                  className={["bw-step", active ? "bw-step--active" : done ? "bw-step--done" : ""].filter(Boolean).join(" ")}
                  role="listitem"
                  aria-current={active ? "step" : undefined}
                >
                  <div className="bw-step__circle">{done ? "✓" : stepNum}</div>
                  <span className="bw-step__label">{label}</span>
                  {i < STEPS.length - 1 && <div className="bw-step__line" />}
                </div>
              );
            })}
          </div>

          {/* Step 1 — Unit summary */}
          {step === 1 && (
            <div className="bw-body">
              <div className="bw-unit-summary">
                <div className="bw-unit-summary__field"><span>Project</span><strong>{unit.projectName}</strong></div>
                <div className="bw-unit-summary__field"><span>Tower</span><strong>{unit.towerName}</strong></div>
                <div className="bw-unit-summary__field"><span>Unit</span><strong>{unit.unitNumber}</strong></div>
                <div className="bw-unit-summary__field"><span>Floor</span><strong>{unit.floor}</strong></div>
                <div className="bw-unit-summary__field"><span>Area</span><strong>{unit.area} sqft</strong></div>
                <div className="bw-unit-summary__field"><span>Base Price</span><strong style={{ fontSize: "var(--text-display-lg)" }}>₹{unit.basePrice.toLocaleString("en-IN")}</strong></div>
              </div>
              <div className="bw-footer">
                <Button variant="secondary" onClick={onClose}>Cancel</Button>
                <Button variant="primary" loading={saving} onClick={handleCreateBooking}>
                  Start Booking →
                </Button>
              </div>
            </div>
          )}

          {/* Step 2 — Customer + KYC */}
          {step === 2 && (
            <div className="bw-body">
              {customerId ? (
                <div className="row row--between" style={{ alignItems: "center", padding: "0.4rem 0" }}>
                  <span><strong>Customer:</strong> {customerName || "Selected"}</span>
                  <Button variant="ghost" size="sm" onClick={() => { setCustomerId(""); setCustomerName(""); }}>
                    Change
                  </Button>
                </div>
              ) : (
                <div style={{ position: "relative" }}>
                  <TextField
                    label="Customer (search by name or email)"
                    placeholder="Type at least 2 characters…"
                    value={customerQuery}
                    onChange={(e) => void searchCustomers(e.target.value)}
                    hint="Optional — link this booking to a customer"
                  />
                  {searchingCust && <p className="muted text-xs">Searching…</p>}
                  {customerResults.length > 0 && (
                    <ul
                      style={{
                        listStyle: "none",
                        margin: "0.25rem 0 0",
                        padding: 0,
                        border: "1px solid var(--color-border)",
                        borderRadius: "var(--radius-md)",
                        maxHeight: 200,
                        overflowY: "auto",
                        background: "var(--color-surface)",
                      }}
                    >
                      {customerResults.map((c) => (
                        <li key={c.id}>
                          <button
                            type="button"
                            onClick={() => selectCustomer(c)}
                            style={{
                              display: "block",
                              width: "100%",
                              textAlign: "left",
                              padding: "0.5rem 0.75rem",
                              border: "none",
                              background: "none",
                              cursor: "pointer",
                            }}
                          >
                            <strong>{c.contact_name}</strong>
                            {c.company_name ? ` · ${c.company_name}` : ""}
                            {c.email ? <span className="muted text-xs"> · {c.email}</span> : null}
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                  {customerQuery.trim().length >= 2 && !searchingCust && customerResults.length === 0 && (
                    <p className="muted text-xs">No customers found. Add them in Customers first.</p>
                  )}
                </div>
              )}
              <div className="bw-kyc">
                <label className="bw-kyc__label">KYC Document</label>
                <select
                  className="form-select"
                  value={kycDocType}
                  onChange={(e) => setKycDocType(e.target.value)}
                >
                  <option value="aadhaar">Aadhaar Card</option>
                  <option value="pan">PAN Card</option>
                  <option value="photo">Passport Photo</option>
                  <option value="other">Other</option>
                </select>
                <input
                  type="file"
                  ref={fileRef}
                  accept="image/*,application/pdf"
                  onChange={(e) => setKycFile(e.target.files?.[0] ?? null)}
                  className="bw-kyc__input"
                />
                {kycFile && <p className="bw-kyc__filename">{kycFile.name}</p>}
              </div>
              <div className="bw-footer">
                <Button variant="secondary" onClick={() => setStep(1)}>← Back</Button>
                <Button
                  variant="primary"
                  loading={saving}
                  disabled={!kycFile}
                  onClick={handleKycUpload}
                >
                  Upload & Continue →
                </Button>
              </div>
            </div>
          )}

          {/* Step 3 — Pricing */}
          {step === 3 && (
            <div className="bw-body">
              <PriceCalculator
                basePrice={unit.basePrice}
                floor={unit.floor}
                onPricingChange={setPricing}
              />
              <div className="bw-footer">
                <Button variant="secondary" onClick={() => setStep(2)}>← Back</Button>
                <Button
                  variant="primary"
                  loading={saving}
                  disabled={!pricing}
                  onClick={handleSavePricing}
                >
                  Save Pricing →
                </Button>
              </div>
            </div>
          )}

          {/* Step 4 — Schedule + Documents */}
          {step === 4 && (
            <div className="bw-body">
              <TextField
                label="Registration Date"
                type="date"
                value={scheduledDate}
                onChange={(e) => setScheduledDate(e.target.value)}
              />
              <div className="bw-doc-actions">
                <Button
                  variant="secondary"
                  loading={saving}
                  onClick={() => handleGenerate("booking_form")}
                >
                  Generate Booking Form
                </Button>
                <Button
                  variant="secondary"
                  loading={saving}
                  onClick={() => handleGenerate("allotment_letter")}
                >
                  Generate Allotment Letter
                </Button>
              </div>
              <div className="bw-footer">
                <Button variant="secondary" onClick={() => setStep(3)}>← Back</Button>
                <Button variant="primary" loading={saving} onClick={handleConfirm}>
                  Confirm Booking
                </Button>
              </div>
            </div>
          )}
        </div>
      </Modal>

      {docHtml && (
        <Modal open title={docTitle} size="lg" onClose={() => setDocHtml(null)}>
          <DocumentPreview html={docHtml} title={docTitle} onClose={() => setDocHtml(null)} />
        </Modal>
      )}
    </>
  );
}
