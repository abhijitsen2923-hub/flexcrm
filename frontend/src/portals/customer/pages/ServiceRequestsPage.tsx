import { type FormEvent, useEffect, useState } from "react";
import {
  customerPortalService,
  type ServiceRequest
} from "../../../services/customerPortal";

type LoadState = "loading" | "ok" | "error";

const CATEGORY_LABELS: Record<ServiceRequest["category"], string> = {
  maintenance: "Maintenance",
  query:       "Query",
  complaint:   "Complaint",
  other:       "Other",
};

const STATUS_CLASS: Record<ServiceRequest["status"], string> = {
  open:        "cp-pill--warning",
  in_progress: "cp-pill--info",
  resolved:    "cp-pill--success",
};

const STATUS_LABELS: Record<ServiceRequest["status"], string> = {
  open:        "Open",
  in_progress: "In Progress",
  resolved:    "Resolved",
};

export default function ServiceRequestsPage() {
  const [requests, setRequests] = useState<ServiceRequest[]>([]);
  const [state, setState] = useState<LoadState>("loading");
  const [showForm, setShowForm] = useState(false);
  const [category, setCategory] = useState<ServiceRequest["category"]>("query");
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  async function load() {
    try {
      const rows = await customerPortalService.listServiceRequests();
      setRequests(rows);
      setState("ok");
    } catch {
      setState("error");
    }
  }

  useEffect(() => { void load(); }, []);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!description.trim()) return;
    setSubmitting(true);
    setFormError(null);
    try {
      const created = await customerPortalService.createServiceRequest({ category, description: description.trim() });
      setRequests((prev) => [created, ...prev]);
      setDescription("");
      setShowForm(false);
    } catch {
      setFormError("Could not submit request. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  if (state === "loading") {
    return (
      <div className="cp-empty">
        <div className="cp-empty__icon">⏳</div>
        <div className="cp-empty__title">Loading requests…</div>
      </div>
    );
  }

  return (
    <>
      <h1 className="cp-page-title">Service Requests</h1>

      {/* New request form */}
      {showForm ? (
        <div className="cp-card">
          <p className="cp-section-label">New Request</p>
          <form onSubmit={handleSubmit}>
            <div className="cp-field">
              <label className="cp-label" htmlFor="sr-category">Category</label>
              <select
                id="sr-category"
                className="cp-input cp-select"
                value={category}
                onChange={(e) => setCategory(e.target.value as ServiceRequest["category"])}
              >
                {(Object.keys(CATEGORY_LABELS) as ServiceRequest["category"][]).map((k) => (
                  <option key={k} value={k}>{CATEGORY_LABELS[k]}</option>
                ))}
              </select>
            </div>
            <div className="cp-field">
              <label className="cp-label" htmlFor="sr-desc">Description</label>
              <textarea
                id="sr-desc"
                className="cp-input"
                rows={4}
                style={{ resize: "vertical" }}
                placeholder="Describe your issue in detail…"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                required
              />
            </div>
            {formError && (
              <div style={{ color: "var(--cp-danger)", fontSize: "var(--cp-font-sm)", marginBottom: "var(--space-3)" }}>
                {formError}
              </div>
            )}
            <div style={{ display: "flex", gap: "var(--space-3)" }}>
              <button
                type="button"
                className="cp-btn cp-btn--secondary"
                onClick={() => setShowForm(false)}
                disabled={submitting}
              >
                Cancel
              </button>
              <button
                type="submit"
                className="cp-btn"
                disabled={submitting || !description.trim()}
              >
                {submitting ? "Submitting…" : "Submit"}
              </button>
            </div>
          </form>
        </div>
      ) : (
        <button className="cp-btn" style={{ marginBottom: "var(--space-4)" }} onClick={() => setShowForm(true)}>
          + New Request
        </button>
      )}

      {requests.length === 0 ? (
        <div className="cp-empty">
          <div className="cp-empty__icon">🛠️</div>
          <div className="cp-empty__title">No service requests yet</div>
          <div className="cp-empty__desc">Tap "New Request" to log a maintenance issue or query.</div>
        </div>
      ) : (
        requests.map((req) => (
          <div key={req.id} className="cp-card">
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "var(--space-2)" }}>
              <span className={`cp-pill ${STATUS_CLASS[req.status]}`}>
                {STATUS_LABELS[req.status]}
              </span>
              <span style={{ fontSize: "var(--cp-font-xs)", color: "var(--cp-text-muted)" }}>
                {new Date(req.created_at).toLocaleDateString()}
              </span>
            </div>
            <div style={{ fontWeight: 600, marginBottom: 4 }}>{CATEGORY_LABELS[req.category]}</div>
            <div style={{ fontSize: "var(--cp-font-sm)", color: "var(--cp-text-muted)", lineHeight: 1.5 }}>
              {req.description}
            </div>
            {req.resolved_at && (
              <div style={{ fontSize: "var(--cp-font-xs)", color: "var(--cp-success)", marginTop: "var(--space-2)" }}>
                Resolved {new Date(req.resolved_at).toLocaleDateString()}
              </div>
            )}
          </div>
        ))
      )}
    </>
  );
}
