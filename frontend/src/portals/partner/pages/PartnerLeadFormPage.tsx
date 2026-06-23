import { type FormEvent, useState } from "react";
import { Button, SelectField, TextField, useToast } from "../../../components";
import { leadsService } from "../../../services/leads";
import { extractErrorMessage } from "../../../utils/errors";

interface FormState {
  contact_name: string;
  contact_phone: string;
  contact_email: string;
  preferred_location: string;
  property_type: string;
  budget_min: string;
  budget_max: string;
  notes: string;
}

const BLANK: FormState = {
  contact_name: "",
  contact_phone: "",
  contact_email: "",
  preferred_location: "",
  property_type: "",
  budget_min: "",
  budget_max: "",
  notes: "",
};

export default function PartnerLeadFormPage() {
  const [form, setForm] = useState<FormState>(BLANK);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const toast = useToast();

  function set<K extends keyof FormState>(key: K, val: string) {
    setForm((prev) => ({ ...prev, [key]: val }));
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await leadsService.create({
        industry: "real_estate",
        title: `${form.contact_name} — ${form.preferred_location || "Referral"}`,
        contact_name: form.contact_name,
        contact_phone: form.contact_phone || null,
        contact_email: form.contact_email || null,
        source: "partner_referral",
        interest: form.preferred_location || null,
        property_type: form.property_type || null,
        budget_min: form.budget_min ? Number(form.budget_min) : null,
        budget_max: form.budget_max ? Number(form.budget_max) : null,
        notes: form.notes || null,
      } as Parameters<typeof leadsService.create>[0]);
      toast.success("Lead submitted", `${form.contact_name} has been added to the pipeline.`);
      setForm(BLANK);
      setSubmitted(true);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      <div className="page-header">
        <div className="page-header__titles">
          <h1>Submit a Lead</h1>
          <p>Refer a prospective buyer and track their progress here.</p>
        </div>
      </div>

      {submitted && (
        <div
          className="card"
          style={{
            background: "var(--status-available-soft)",
            border: "1px solid var(--status-available)",
            padding: "var(--space-4)",
            marginBottom: "var(--space-4)",
            borderRadius: "var(--radius-md)",
          }}
        >
          Lead submitted successfully.{" "}
          <button
            type="button"
            className="link"
            onClick={() => setSubmitted(false)}
          >
            Submit another
          </button>
        </div>
      )}

      <div className="card" style={{ maxWidth: 560 }}>
        <form className="form" onSubmit={handleSubmit}>
          <TextField
            id="pf-name"
            label="Contact name"
            value={form.contact_name}
            onChange={(e) => set("contact_name", e.target.value)}
            required
            placeholder="Buyer's full name"
          />
          <div className="form-grid">
            <TextField
              id="pf-phone"
              label="Phone"
              value={form.contact_phone}
              onChange={(e) => set("contact_phone", e.target.value)}
              placeholder="+91 …"
            />
            <TextField
              id="pf-email"
              label="Email"
              type="email"
              value={form.contact_email}
              onChange={(e) => set("contact_email", e.target.value)}
              placeholder="Optional"
            />
          </div>
          <SelectField
            id="pf-property-type"
            label="Property type"
            value={form.property_type}
            onChange={(e) => set("property_type", e.target.value)}
            options={[
              { value: "apartment", label: "Apartment" },
              { value: "villa", label: "Villa / Independent house" },
              { value: "plot", label: "Plot / Land" },
              { value: "commercial", label: "Commercial" },
            ]}
          />
          <TextField
            id="pf-location"
            label="Preferred location"
            value={form.preferred_location}
            onChange={(e) => set("preferred_location", e.target.value)}
            placeholder="e.g. Whitefield, Bengaluru"
          />
          <div className="form-grid">
            <TextField
              id="pf-budget-min"
              label="Budget min (₹)"
              type="number"
              min={0}
              step="100000"
              value={form.budget_min}
              onChange={(e) => set("budget_min", e.target.value)}
              placeholder="e.g. 5000000"
            />
            <TextField
              id="pf-budget-max"
              label="Budget max (₹)"
              type="number"
              min={0}
              step="100000"
              value={form.budget_max}
              onChange={(e) => set("budget_max", e.target.value)}
              placeholder="e.g. 10000000"
            />
          </div>
          <TextField
            id="pf-notes"
            label="Notes"
            value={form.notes}
            onChange={(e) => set("notes", e.target.value)}
            placeholder="Any additional context (optional)"
          />
          {error && <div className="error-banner">{error}</div>}
          <div style={{ display: "flex", justifyContent: "flex-end" }}>
            <Button type="submit" loading={submitting} disabled={!form.contact_name}>
              Submit lead
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
