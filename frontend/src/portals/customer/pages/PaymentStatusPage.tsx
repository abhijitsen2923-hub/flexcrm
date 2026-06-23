import { useEffect, useState } from "react";
import {
  customerPortalService,
  type PaymentScheduleEntry
} from "../../../services/customerPortal";
import { formatInr } from "../../../utils/format";

type LoadState = "loading" | "ok" | "error";

function PaymentPill({ entry }: { entry: PaymentScheduleEntry }) {
  if (entry.outstanding === 0)
    return <span className="cp-pill cp-pill--success">Cleared</span>;
  if (entry.is_overdue)
    return <span className="cp-pill cp-pill--danger">Overdue</span>;
  return <span className="cp-pill cp-pill--warning">Pending</span>;
}

export default function PaymentStatusPage() {
  const [entries, setEntries] = useState<PaymentScheduleEntry[]>([]);
  const [state, setState] = useState<LoadState>("loading");

  useEffect(() => {
    void customerPortalService
      .getPayments()
      .then((rows) => { setEntries(rows); setState("ok"); })
      .catch(() => setState("error"));
  }, []);

  const totalDemand = entries.reduce((s, e) => s + e.demand_amount, 0);
  const totalPaid   = entries.reduce((s, e) => s + e.paid_amount, 0);
  const totalDue    = entries.reduce((s, e) => s + e.outstanding, 0);

  if (state === "loading") {
    return (
      <div className="cp-empty">
        <div className="cp-empty__icon">⏳</div>
        <div className="cp-empty__title">Loading payments…</div>
      </div>
    );
  }

  if (state === "error") {
    return (
      <div className="cp-empty">
        <div className="cp-empty__icon">⚠️</div>
        <div className="cp-empty__title">Could not load payment data</div>
        <div className="cp-empty__desc">Check your connection and try again.</div>
      </div>
    );
  }

  return (
    <>
      <h1 className="cp-page-title">Payments</h1>

      {/* Summary strip */}
      {entries.length > 0 && (
        <div
          className="cp-card"
          style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", textAlign: "center", gap: 0, padding: "var(--space-3)" }}
        >
          {[
            { label: "Total demand", value: formatInr(totalDemand), color: "var(--cp-text)" },
            { label: "Paid",         value: formatInr(totalPaid),   color: "var(--cp-success)" },
            { label: "Outstanding",  value: formatInr(totalDue),    color: totalDue > 0 ? "var(--cp-danger)" : "var(--cp-text-muted)" },
          ].map(({ label, value, color }) => (
            <div key={label}>
              <div style={{ fontSize: "var(--cp-font-xs)", color: "var(--cp-text-muted)", marginBottom: 2 }}>
                {label}
              </div>
              <div style={{ fontSize: "1rem", fontWeight: 700, color }}>{value}</div>
            </div>
          ))}
        </div>
      )}

      {entries.length === 0 ? (
        <div className="cp-empty">
          <div className="cp-empty__icon">💳</div>
          <div className="cp-empty__title">No payment schedule yet</div>
          <div className="cp-empty__desc">Your installment plan will appear here once a booking is confirmed.</div>
        </div>
      ) : (
        entries.map((entry) => (
          <div key={entry.id} className="cp-card">
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "flex-start",
                marginBottom: "var(--space-2)"
              }}
            >
              <div>
                <div style={{ fontWeight: 600 }}>{entry.installment_name}</div>
                <div
                  style={{
                    fontSize: "var(--cp-font-xs)",
                    color: entry.is_overdue ? "var(--cp-danger)" : "var(--cp-text-muted)",
                    marginTop: 2
                  }}
                >
                  Due {new Date(entry.due_date).toLocaleDateString(undefined, {
                    day: "numeric", month: "short", year: "numeric"
                  })}
                </div>
              </div>
              <PaymentPill entry={entry} />
            </div>

            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end" }}>
              <div>
                <div
                  style={{
                    fontSize: "1.5rem",
                    fontWeight: 800,
                    color: entry.is_overdue ? "var(--cp-danger)" : "var(--cp-text)"
                  }}
                >
                  {formatInr(entry.outstanding > 0 ? entry.outstanding : entry.demand_amount)}
                </div>
                {entry.paid_amount > 0 && (
                  <div style={{ fontSize: "var(--cp-font-xs)", color: "var(--cp-success)", marginTop: 2 }}>
                    ✓ {formatInr(entry.paid_amount)} paid
                  </div>
                )}
              </div>
            </div>
          </div>
        ))
      )}
    </>
  );
}
