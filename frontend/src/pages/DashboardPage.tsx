import { RefreshCw } from "lucide-react";
import { useCallback, useEffect } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";

import {
  Badge,
  Button,
  Card,
  EmptyState,
  LoadingBlock,
  useToast
} from "../components";
import { FEATURES } from "../config/features";
import { useDashboard } from "../hooks/useDashboard";
import { useRealtimeEvent } from "../realtime";
import { formatCurrency, formatNumber, formatRelative } from "../utils/format";


const PIE_COLORS = ["#2563eb", "#0ea5e9", "#16a34a", "#d97706", "#dc2626", "#7c3aed"];


export default function DashboardPage() {
  const dashboard = useDashboard();
  const toast = useToast();

  const refresh = useCallback(() => {
    void dashboard.refresh().catch(() => {
      toast.error("Failed to refresh dashboard.");
    });
  }, [dashboard, toast]);

  useEffect(() => {
    if (dashboard.error) {
      toast.error("Could not load dashboard data.");
    }
  }, [dashboard.error, toast]);

  useRealtimeEvent((event) => {
    if (
      event.event.startsWith("customer.") ||
      event.event.startsWith("lead.") ||
      event.event.startsWith("deal.") ||
      event.event.startsWith("task.")
    ) {
      void dashboard.refresh();
    }
  });

  if (dashboard.loading && dashboard.summary.total_customers === 0) {
    return <LoadingBlock label="Loading dashboard…" />;
  }

  const { summary, charts, recentActivities } = dashboard;

  return (
    <>
      <div className="page-header">
        <div className="page-header__titles">
          <h1>Dashboard</h1>
          <p>Real-time snapshot of your pipeline, tasks, and activity.</p>
        </div>
        <div className="page-header__actions">
          <Button
            variant="secondary"
            size="sm"
            icon={<RefreshCw size={14} />}
            onClick={refresh}
            loading={dashboard.loading}
          >
            Refresh
          </Button>
        </div>
      </div>

      <div className="kpi-grid">
        <KpiCard label="Customers" value={formatNumber(summary.total_customers)} />
        <KpiCard label="Active leads" value={formatNumber(summary.active_leads)} />
        {FEATURES.deals && (
          <KpiCard label="Open pipeline" value={formatCurrency(summary.open_deals_value)} />
        )}
        {FEATURES.tasks && (
          <KpiCard
            label="Overdue tasks"
            value={formatNumber(summary.overdue_tasks)}
            hint={summary.overdue_tasks > 0 ? "Review overdue tasks" : undefined}
          />
        )}
        {FEATURES.activities && (
          <KpiCard label="Recent activity (7d)" value={formatNumber(summary.recent_activity_count)} />
        )}
      </div>

      <div className={FEATURES.deals || FEATURES.finance ? "chart-grid chart-grid--2-1" : "chart-grid"}>
        {(FEATURES.deals || FEATURES.finance) && (
          <Card title="Revenue trend" subtitle="Closed-won monthly totals">
            {charts.revenue_trend.length === 0 ? (
              <EmptyState title="No revenue data yet" description="Close a deal to see it here." />
            ) : (
              <div style={{ height: 240 }}>
                <ResponsiveContainer>
                  <LineChart data={charts.revenue_trend}>
                    <CartesianGrid stroke="#e5e7eb" vertical={false} />
                    <XAxis dataKey="label" stroke="#6b7280" fontSize={12} />
                    <YAxis stroke="#6b7280" fontSize={12} />
                    <Tooltip />
                    <Line type="monotone" dataKey="value" stroke="#2563eb" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}
          </Card>
        )}
        <Card title="Lead stage breakdown">
          {charts.lead_stage_breakdown.length === 0 ? (
            <EmptyState title="No leads yet" />
          ) : (
            <div style={{ height: 240 }}>
              <ResponsiveContainer>
                <PieChart>
                  <Pie
                    data={charts.lead_stage_breakdown}
                    dataKey="value"
                    nameKey="label"
                    innerRadius={50}
                    outerRadius={80}
                  >
                    {charts.lead_stage_breakdown.map((_, index) => (
                      <Cell key={index} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>
      </div>

      {(FEATURES.tasks || FEATURES.activities) && (
        <div className={FEATURES.tasks && FEATURES.activities ? "chart-grid chart-grid--1-1" : "chart-grid"}>
          {FEATURES.tasks && (
            <Card title="Task status">
              {charts.task_status_breakdown.length === 0 ? (
                <EmptyState title="No tasks yet" />
              ) : (
                <div style={{ height: 220 }}>
                  <ResponsiveContainer>
                    <BarChart data={charts.task_status_breakdown}>
                      <CartesianGrid stroke="#e5e7eb" vertical={false} />
                      <XAxis dataKey="label" stroke="#6b7280" fontSize={12} />
                      <YAxis stroke="#6b7280" fontSize={12} />
                      <Tooltip />
                      <Bar dataKey="value" fill="#2563eb" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </Card>
          )}
          {FEATURES.activities && (
            <Card title="Recent activities" subtitle="Last 10 events">
              {recentActivities.items.length === 0 ? (
                <EmptyState title="No recent activity" />
              ) : (
                <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                  {recentActivities.items.slice(0, 10).map((item) => (
                    <li key={item.id} style={{ borderBottom: "1px solid var(--color-border)", paddingBottom: "0.5rem" }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.5rem" }}>
                        <strong style={{ fontSize: "0.85rem" }}>{item.customer_name}</strong>
                        <Badge tone="info">{item.type}</Badge>
                      </div>
                      <div className="muted text-sm" style={{ marginTop: "0.25rem" }}>{item.note}</div>
                      <div className="text-xs muted" style={{ marginTop: "0.2rem" }}>{formatRelative(item.created_at)}</div>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          )}
        </div>
      )}
    </>
  );
}


interface KpiCardProps {
  label: string;
  value: string;
  hint?: string;
}


function KpiCard({ label, value, hint }: KpiCardProps) {
  return (
    <div className="kpi">
      <div className="kpi__label">{label}</div>
      <div className="kpi__value">{value}</div>
      {hint && <div className="kpi__hint">{hint}</div>}
    </div>
  );
}
