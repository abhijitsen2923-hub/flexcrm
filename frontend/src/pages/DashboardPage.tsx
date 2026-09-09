import { Phone, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
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
  SkeletonCard,
  SkeletonKpiRow,
  useToast
} from "../components";
import { mergeModules } from "../config/features";
import { CHART_AXIS, CHART_GRID, CHART_PALETTE, CHART_PRIMARY } from "../config/chartTheme";
import { useOrg } from "../context/OrgContext";
import { usePipelines } from "../context/PipelineContext";
import { useDashboard } from "../hooks/useDashboard";
import { usePermissions } from "../hooks/usePermissions";
import { useRealtimeRefresh } from "../realtime";
import { channelPartnersService } from "../services/channelPartners";
import { leadsService } from "../services/leads";
import type { Lead, LeadIndustry, PipelineStage } from "../types";
import type { ChannelPartnerListItem } from "../types/partner";
import { telHref } from "../utils/contactLinks";
import { formatCurrency, formatInr, formatNumber, formatRelative } from "../utils/format";


const PIE_COLORS = CHART_PALETTE;


export default function DashboardPage() {
  const { org, modules } = useOrg();
  const FEATURES = mergeModules(modules);
  // A freshly-provisioned tenant has no optional modules until the provider
  // grants them. Wait for `org` to load so the notice doesn't flash on refresh.
  const noModules = org !== null && Object.values(FEATURES).every((enabled) => !enabled);
  // The dashboard shows no analytics (revenue/leads/conversion) — those live on
  // the Analytics page. Skip fetching them here so a role with DASHBOARD_VIEW but
  // not ANALYTICS_VIEW (e.g. sales_executive) doesn't 403 and blank the page.
  const dashboard = useDashboard({ includeAnalytics: false });
  const toast = useToast();
  const { has } = usePermissions();
  const { getStage } = usePipelines();

  // "Today's follow-ups": leads whose next action is due today or is overdue,
  // scoped to what the user can see (the leads endpoint enforces that). Soonest
  // first. Reuses the existing list endpoint — no new backend.
  const [followUps, setFollowUps] = useState<Lead[] | null>(null);
  const loadFollowUps = useCallback(() => {
    const now = new Date();
    const endOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 23, 59, 59, 999);
    void leadsService
      .list({
        next_action_from: new Date(0).toISOString(),
        next_action_to: endOfToday.toISOString(),
        page_size: 6,
      })
      .then((res) => {
        const sorted = [...res.items].sort((a, b) => {
          const da = a.next_action_date ? Date.parse(a.next_action_date) : Infinity;
          const db = b.next_action_date ? Date.parse(b.next_action_date) : Infinity;
          return da - db;
        });
        setFollowUps(sorted);
      })
      .catch(() => setFollowUps([]));
  }, []);
  useEffect(() => {
    loadFollowUps();
  }, [loadFollowUps]);

  // Segregated dashboard (FR-5): the Channel-Partner overview renders only for
  // users who can view partners in a real-estate org. Direct-lead users (no
  // USER_VIEW) and non-real-estate orgs never see it; brokers get their own
  // portal dashboard.
  const showChannelPartners = has("USER_VIEW") && (FEATURES.bookings || FEATURES.inventory);
  const [partners, setPartners] = useState<ChannelPartnerListItem[] | null>(null);
  useEffect(() => {
    if (!showChannelPartners) return;
    let cancelled = false;
    void channelPartnersService
      .list()
      .then((rows) => { if (!cancelled) setPartners(rows); })
      .catch(() => { if (!cancelled) setPartners([]); });
    return () => { cancelled = true; };
  }, [showChannelPartners]);

  const cp = partners
    ? {
        total: partners.length,
        active: partners.filter((p) => p.is_active).length,
        referred: partners.reduce((n, p) => n + p.stats.leads_total, 0),
        sold: partners.reduce((n, p) => n + p.stats.leads_sold, 0),
        outstanding: partners.reduce((n, p) => n + Number(p.stats.brokerage_outstanding), 0),
        top: [...partners].sort((a, b) => b.stats.leads_total - a.stats.leads_total).slice(0, 5),
      }
    : null;

  const refresh = useCallback(() => {
    loadFollowUps();
    void dashboard.refresh().catch(() => {
      toast.error("Failed to refresh dashboard.");
    });
  }, [dashboard, toast, loadFollowUps]);

  useEffect(() => {
    if (dashboard.error) {
      toast.error("Could not load dashboard data.");
    }
  }, [dashboard.error, toast]);

  // Coalesce realtime-driven refreshes — a bulk lead import (Google Sheet sync / CSV) broadcasts
  // many events at once, and refetching the dashboard's 6 endpoints per event trips the rate
  // limiter. useRealtimeRefresh collapses a burst into at most one refresh per few seconds.
  useRealtimeRefresh(
    (event) =>
      event.event.startsWith("customer.") ||
      event.event.startsWith("lead.") ||
      event.event.startsWith("deal.") ||
      event.event.startsWith("task.") ||
      event.event.startsWith("unit."),
    () => {
      void dashboard.refresh();
      loadFollowUps();
    },
  );

  if (dashboard.loading && !dashboard.initialized) {
    return (
      <>
        <div className="page-header">
          <div className="page-header__titles">
            <h1>Dashboard</h1>
            <p>Real-time snapshot of your pipeline, tasks, and activity.</p>
          </div>
        </div>
        <SkeletonKpiRow count={4} />
        <div className="dashboard-grid" style={{ marginTop: "1rem" }}>
          <SkeletonCard rows={6} />
          <SkeletonCard rows={6} />
        </div>
        {dashboard.slow && (
          <p className="muted text-sm" style={{ marginTop: "0.75rem" }}>
            Waking the server, one moment…
          </p>
        )}
      </>
    );
  }

  const { summary, charts, recentActivities } = dashboard;

  // Optional real-estate fields — populated only when inventory module is active
  type InventorySummary = typeof summary & {
    units_available?: number;
    units_booked_month?: number;
    collection_month?: number;
    inventory_status_breakdown?: { label: string; value: number }[];
  };
  const invSummary = summary as InventorySummary;
  const invCharts = charts as typeof charts & {
    inventory_status_breakdown?: { label: string; value: number }[];
  };

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

      {noModules && (
        <div className="notice-banner" role="status">
          <strong>Modules are managed by your provider.</strong> Your workspace doesn’t have any
          additional modules enabled yet. Please contact your SaaS provider to request access to
          modules like Deals, Tasks, Finance, and more.
        </div>
      )}

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

      <div className="chart-grid" style={{ marginTop: "1.5rem" }}>
        <FollowUpsCard items={followUps} getStage={getStage} />
      </div>

      {FEATURES.inventory && (
        <div className="kpi-grid" style={{ marginTop: 0 }}>
          <KpiCard
            label="Units available"
            value={formatNumber(invSummary.units_available ?? 0)}
          />
          <KpiCard
            label="Units booked (month)"
            value={formatNumber(invSummary.units_booked_month ?? 0)}
          />
          <KpiCard
            label="Collection (month)"
            value={formatInr(invSummary.collection_month ?? 0)}
          />
        </div>
      )}

      {showChannelPartners && cp && cp.total > 0 && (
        <>
          <div className="kpi-grid" style={{ marginTop: 0 }}>
            <KpiCard label="Channel partners" value={formatNumber(cp.total)} />
            <KpiCard label="Active partners" value={formatNumber(cp.active)} />
            <KpiCard
              label="Partner-referred leads"
              value={formatNumber(cp.referred)}
              hint={cp.sold > 0 ? `${cp.sold} sold` : undefined}
            />
            <KpiCard label="Brokerage outstanding" value={formatInr(cp.outstanding)} />
          </div>
          <div className="chart-grid">
            <Card title="Top channel partners" subtitle="By referred leads">
              <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: "0.6rem" }}>
                {cp.top.map((p) => (
                  <li key={p.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid var(--color-border)", paddingBottom: "0.5rem" }}>
                    <div>
                      <strong style={{ fontSize: "0.9rem" }}>{p.company_name}</strong>
                      <div className="muted text-xs">{p.stats.leads_total} referred · {p.stats.leads_sold} sold</div>
                    </div>
                    <span className="text-sm">{formatInr(Number(p.stats.brokerage_outstanding))}</span>
                  </li>
                ))}
              </ul>
            </Card>
          </div>
        </>
      )}

      <div className={FEATURES.deals || FEATURES.finance ? "chart-grid chart-grid--2-1" : "chart-grid"}>
        {(FEATURES.deals || FEATURES.finance) && (
          <Card title="Revenue trend" subtitle="Closed-won monthly totals">
            {charts.revenue_trend.length === 0 ? (
              <EmptyState title="No revenue data yet" description="Close a deal to see it here." />
            ) : (
              <div style={{ height: 240 }}>
                <ResponsiveContainer>
                  <LineChart data={charts.revenue_trend}>
                    <CartesianGrid stroke={CHART_GRID} vertical={false} />
                    <XAxis dataKey="label" stroke={CHART_AXIS} fontSize={12} />
                    <YAxis stroke={CHART_AXIS} fontSize={12} />
                    <Tooltip />
                    <Line type="monotone" dataKey="value" stroke={CHART_PRIMARY} strokeWidth={2} dot={false} isAnimationActive={false} />
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
                    isAnimationActive={false}
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

      {FEATURES.inventory && (
        <div className="chart-grid">
          <Card title="Inventory status" subtitle="Units by lifecycle stage">
            {!invCharts.inventory_status_breakdown?.length ? (
              <EmptyState title="No inventory data yet" description="Add a project and units to see the breakdown." />
            ) : (
              <div style={{ height: 240 }}>
                <ResponsiveContainer>
                  <PieChart>
                    <Pie
                      data={invCharts.inventory_status_breakdown}
                      isAnimationActive={false}
                      dataKey="value"
                      nameKey="label"
                      innerRadius={50}
                      outerRadius={80}
                    >
                      {invCharts.inventory_status_breakdown.map((entry, index) => {
                        const STATUS_COLORS: Record<string, string> = {
                          Available: "#16a34a",
                          Reserved: "#f59e0b",
                          Booked: "#2563eb",
                          Sold: "#6b7280"
                        };
                        return <Cell key={index} fill={STATUS_COLORS[entry.label] ?? PIE_COLORS[index % PIE_COLORS.length]} />;
                      })}
                    </Pie>
                    <Tooltip />
                    <Legend />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            )}
          </Card>
        </div>
      )}

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
                      <CartesianGrid stroke={CHART_GRID} vertical={false} />
                      <XAxis dataKey="label" stroke={CHART_AXIS} fontSize={12} />
                      <YAxis stroke={CHART_AXIS} fontSize={12} />
                      <Tooltip />
                      <Bar dataKey="value" fill={CHART_PRIMARY} radius={[4, 4, 0, 0]} isAnimationActive={false} />
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


type DueState = "overdue" | "today";

/** Overdue vs due-today, from a next-action ISO datetime (local day compare). */
function dueState(dateStr: string | null | undefined): DueState {
  if (!dateStr) return "today";
  const d = new Date(dateStr);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const day = new Date(d);
  day.setHours(0, 0, 0, 0);
  return day.getTime() < today.getTime() ? "overdue" : "today";
}


/**
 * "Today's follow-ups" — the leads whose next call/action is due today or is
 * already overdue, each with a one-tap call button. Surfaced near the top so a
 * rep sees who to chase first thing.
 */
function FollowUpsCard({
  items,
  getStage,
}: {
  items: Lead[] | null;
  getStage: (industry: LeadIndustry, code: string) => PipelineStage | null | undefined;
}) {
  return (
    <Card title="Today's follow-ups" subtitle="Calls & actions due today or overdue">
      {items === null ? (
        <div className="muted text-sm">Loading…</div>
      ) : items.length === 0 ? (
        <EmptyState title="You're all caught up" description="No follow-ups due today." />
      ) : (
        <>
          <ul className="followups">
            {items.map((lead) => {
              const state = dueState(lead.next_action_date);
              const stage = getStage(lead.industry, lead.stage_code);
              const phone = lead.contact_phone || lead.contact_phone_alt || "";
              const tel = telHref(phone);
              const name = lead.contact_name || lead.title;
              return (
                <li key={lead.id} className="followup">
                  <div className="followup__text">
                    <div className="followup__name">{name}</div>
                    <div className="followup__sub">
                      {stage ? stage.name : lead.stage_code}
                      {phone ? ` · ${phone}` : ""}
                    </div>
                  </div>
                  <span className={`followup__pill followup__pill--${state}`}>
                    {state === "overdue" ? "Overdue" : "Today"}
                  </span>
                  {tel && (
                    <a className="followup__call" href={tel} aria-label={`Call ${name}`} title={`Call ${phone}`}>
                      <Phone size={15} aria-hidden="true" />
                    </a>
                  )}
                </li>
              );
            })}
          </ul>
          <div style={{ marginTop: "0.75rem" }}>
            <Link className="link text-sm" to="/leads">View all in Leads →</Link>
          </div>
        </>
      )}
    </Card>
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
