import { useEffect, useState } from "react";
import { Card, EmptyState, LoadingBlock, useToast } from "../../../components";
import { partnerPortalService } from "../../../services/partnerPortal";
import { extractErrorMessage } from "../../../utils/errors";
import { formatDate, formatInr } from "../../../utils/format";
import type { PartnerDashboard } from "../../../types/partner";

export default function PartnerDashboardPage() {
  const [data, setData] = useState<PartnerDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const toast = useToast();

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    void partnerPortalService
      .dashboard()
      .then((d) => { if (!cancelled) setData(d); })
      .catch((err) => { if (!cancelled) toast.error("Could not load dashboard", extractErrorMessage(err)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [toast]);

  if (loading) return <LoadingBlock label="Loading your dashboard…" />;
  if (!data) {
    return (
      <EmptyState
        title="Dashboard unavailable"
        description="We couldn't load your partner dashboard. Try again shortly."
      />
    );
  }

  const { partner, stats, stage_breakdown, recent_payouts } = data;
  const conversionPct = Math.round((stats.conversion_rate || 0) * 100);
  const maxStage = Math.max(1, ...stage_breakdown.map((s) => s.count));

  return (
    <div>
      <div className="page-header">
        <div className="page-header__titles">
          <h1>Welcome, {partner.contact_name}</h1>
          <p>{partner.company_name} · your referral performance at a glance.</p>
        </div>
      </div>

      <div className="kpi-grid" style={{ marginBottom: "var(--space-4)" }}>
        <div className="kpi">
          <div className="kpi__label">Leads referred</div>
          <div className="kpi__value">{stats.leads_total}</div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Active</div>
          <div className="kpi__value">{stats.leads_active}</div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Sold</div>
          <div className="kpi__value">{stats.leads_sold} <span className="muted text-xs">({conversionPct}%)</span></div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Brokerage earned</div>
          <div className="kpi__value">{formatInr(Number(stats.brokerage_accrued))}</div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Outstanding</div>
          <div className="kpi__value">{formatInr(Number(stats.brokerage_outstanding))}</div>
        </div>
      </div>

      <div className="grid-2col" style={{ display: "grid", gap: "var(--space-4)", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))" }}>
        <Card title="Pipeline breakdown">
          {stage_breakdown.length === 0 ? (
            <p className="muted text-sm">No referrals yet.</p>
          ) : (
            <div className="stack" style={{ gap: "0.6rem" }}>
              {stage_breakdown.map((s) => (
                <div key={s.stage_code}>
                  <div className="row row--between text-sm" style={{ marginBottom: 2 }}>
                    <span>{s.label}</span>
                    <strong>{s.count}</strong>
                  </div>
                  <div style={{ height: 6, background: "var(--color-border)", borderRadius: 3, overflow: "hidden" }}>
                    <div style={{ width: `${(s.count / maxStage) * 100}%`, height: "100%", background: "var(--color-primary)" }} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card title="Recent brokerage">
          {recent_payouts.length === 0 ? (
            <p className="muted text-sm">Brokerage appears here once a referred lead is Sold.</p>
          ) : (
            <div className="stack" style={{ gap: "0.4rem" }}>
              {recent_payouts.map((p) => (
                <div key={p.id} className="row row--between" style={{ alignItems: "center", padding: "0.4rem 0.6rem", border: "1px solid var(--color-border)", borderRadius: "var(--radius-sm)" }}>
                  <span className="text-sm">
                    {formatDate(p.created_at)} · <strong>{formatInr(Number(p.amount))}</strong>
                  </span>
                  <span className="muted text-xs">{p.status}</span>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
