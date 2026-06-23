import { type FormEvent, useState } from "react";
import { customerPortalService } from "../../../services/customerPortal";

interface FormState {
  contact_name: string;
  contact_phone: string;
  contact_email: string;
  preferred_location: string;
  notes: string;
}

const BLANK: FormState = {
  contact_name: "",
  contact_phone: "",
  contact_email: "",
  preferred_location: "",
  notes: "",
};

export default function ReferralSubmitPage() {
  const [form, setForm] = useState<FormState>(BLANK);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  function set<K extends keyof FormState>(key: K, val: string) {
    setForm((prev) => ({ ...prev, [key]: val }));
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await customerPortalService.submitReferral({
        contact_name: form.contact_name.trim(),
        contact_phone: form.contact_phone.trim() || undefined,
        contact_email: form.contact_email.trim() || undefined,
        preferred_location: form.preferred_location.trim() || undefined,
        notes: form.notes.trim() || undefined,
      });
      setSuccess(true);
      setForm(BLANK);
    } catch {
      setError("Could not submit referral. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <h1 className="cp-page-title">Refer a Friend</h1>

      <p style={{ fontSize: "var(--cp-font-sm)", color: "var(--cp-text-muted)", marginTop: 0, marginBottom: "var(--space-4)" }}>
        Know someone looking to buy a property? Share their details and earn a referral reward once they book.
      </p>

      {success && (
        <div
          className="cp-card"
          style={{ background: "#dcfce7", border: "1px solid #16a34a", marginBottom: "var(--space-4)" }}
        >
          <div style={{ fontSize: "1.5rem", marginBottom: "var(--space-2)" }}>🎉</div>
          <div style={{ fontWeight: 700, color: "#15803d" }}>Referral submitted!</div>
          <div style={{ fontSize: "var(--cp-font-sm)", color: "#166534", marginTop: 4 }}>
            We'll reach out to your contact shortly.
          </div>
          <button
            type="button"
            className="cp-btn cp-btn--secondary"
            style={{ marginTop: "var(--space-4)" }}
            onClick={() => setSuccess(false)}
          >
            Refer another person
          </button>
        </div>
      )}

      {!success && (
        <div className="cp-card">
          <form onSubmit={handleSubmit}>
            <div className="cp-field">
              <label className="cp-label" htmlFor="ref-name">Their name *</label>
              <input
                id="ref-name"
                className="cp-input"
                value={form.contact_name}
                onChange={(e) => set("contact_name", e.target.value)}
                placeholder="Full name"
                required
              />
            </div>

            <div className="cp-field">
              <label className="cp-label" htmlFor="ref-phone">Phone number</label>
              <input
                id="ref-phone"
                className="cp-input"
                type="tel"
                value={form.contact_phone}
                onChange={(e) => set("contact_phone", e.target.value)}
                placeholder="+91 …"
              />
            </div>

            <div className="cp-field">
              <label className="cp-label" htmlFor="ref-email">Email</label>
              <input
                id="ref-email"
                className="cp-input"
                type="email"
                value={form.contact_email}
                onChange={(e) => set("contact_email", e.target.value)}
                placeholder="Optional"
              />
            </div>

            <div className="cp-field">
              <label className="cp-label" htmlFor="ref-loc">Preferred location</label>
              <input
                id="ref-loc"
                className="cp-input"
                value={form.preferred_location}
                onChange={(e) => set("preferred_location", e.target.value)}
                placeholder="e.g. Whitefield, Bengaluru"
              />
            </div>

            <div className="cp-field">
              <label className="cp-label" htmlFor="ref-notes">Notes</label>
              <textarea
                id="ref-notes"
                className="cp-input"
                rows={3}
                style={{ resize: "vertical" }}
                value={form.notes}
                onChange={(e) => set("notes", e.target.value)}
                placeholder="Budget range, timeline, anything helpful…"
              />
            </div>

            {error && (
              <div style={{ color: "var(--cp-danger)", fontSize: "var(--cp-font-sm)", marginBottom: "var(--space-3)" }}>
                {error}
              </div>
            )}

            <button
              type="submit"
              className="cp-btn"
              disabled={submitting || !form.contact_name.trim()}
            >
              {submitting ? "Submitting…" : "Submit referral"}
            </button>
          </form>
        </div>
      )}
    </>
  );
}
