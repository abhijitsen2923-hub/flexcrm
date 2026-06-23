import { useRef, useState } from "react";
import { Button, Modal, TextField, useToast } from "../../../components";
import { bookingsService } from "../../../services/bookings";
import { PriceCalculator } from "../../inventory/components/PriceCalculator";
import { DocumentPreview } from "./DocumentPreview";
import type { Booking, PricingSnapshot, Unit } from "../../../types/realestate";
import "./BookingWizard.css";

const STEPS = ["Unit", "Customer & KYC", "Pricing", "Schedule & Documents"] as const;

interface Props {
  unit: Pick<Unit, "id" | "unitNumber" | "floor" | "area" | "basePrice"> & { towerName: string; projectName: string };
  onClose: () => void;
  onComplete: (booking: Booking) => void;
}

export function BookingWizard({ unit, onClose, onComplete }: Props) {
  const { push } = useToast();
  const [step, setStep] = useState(1);
  const [booking, setBooking] = useState<Booking | null>(null);
  const [saving, setSaving] = useState(false);
  const [pricing, setPricing] = useState<PricingSnapshot | null>(null);
  const [docUrl, setDocUrl] = useState<string | null>(null);
  const [docTitle, setDocTitle] = useState<string>("");

  // Step 2 state
  const [customerId, setCustomerId] = useState("");
  const [kycFile, setKycFile] = useState<File | null>(null);
  const [kycDocType, setKycDocType] = useState<string>("aadhaar");
  const fileRef = useRef<HTMLInputElement>(null);

  // Step 4 state
  const [scheduledDate, setScheduledDate] = useState("");

  const handleCreateBooking = async () => {
    setSaving(true);
    try {
      const created = await bookingsService.create({ unitId: unit.id });
      setBooking(created);
      setStep(2);
    } catch {
      push({ message: "Failed to start booking", tone: "danger" });
    } finally {
      setSaving(false);
    }
  };

  const handleKycUpload = async () => {
    if (!booking || !kycFile) return;
    setSaving(true);
    try {
      const updated = await bookingsService.uploadKyc(booking.id, kycFile, kycDocType);
      setBooking(updated);
      setStep(3);
    } catch {
      push({ message: "KYC upload failed", tone: "danger" });
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
      push({ message: "Failed to save pricing", tone: "danger" });
    } finally {
      setSaving(false);
    }
  };

  const handleGenerate = async (docType: "booking_form" | "allotment_letter") => {
    if (!booking) return;
    setSaving(true);
    try {
      const url = await bookingsService.getDocumentUrl(booking.id, docType);
      setDocUrl(url);
      setDocTitle(docType === "booking_form" ? "Booking Form" : "Allotment Letter");
    } catch {
      push({ message: "Document generation failed", tone: "danger" });
    } finally {
      setSaving(false);
    }
  };

  const handleConfirm = async () => {
    if (!booking) return;
    setSaving(true);
    try {
      const updated = await bookingsService.advanceStep(booking.id, 4, { scheduledDate });
      push({ message: "Booking confirmed!", tone: "success" });
      onComplete(updated);
    } catch {
      push({ message: "Failed to confirm booking", tone: "danger" });
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
              <TextField
                label="Customer ID or search"
                placeholder="Enter customer ID…"
                value={customerId}
                onChange={(e) => setCustomerId(e.target.value)}
                hint="Lookup by email or enter customer ID"
              />
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

      {docUrl && (
        <Modal open title={docTitle} size="lg" onClose={() => setDocUrl(null)}>
          <DocumentPreview url={docUrl} title={docTitle} onClose={() => setDocUrl(null)} />
        </Modal>
      )}
    </>
  );
}
