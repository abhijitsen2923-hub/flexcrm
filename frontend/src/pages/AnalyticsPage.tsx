import { useEffect } from "react";
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

import { Card, EmptyState, LoadingBlock, useToast } from "../components";
import { CHART_AXIS, CHART_GRID, CHART_PALETTE, CHART_PRIMARY } from "../config/chartTheme";
import { useDashboard } from "../hooks/useDashboard";
import { formatCurrency, formatNumber } from "../utils/format";


const PIE_COLORS = CHART_PALETTE;


export default function AnalyticsPage() {
  const dashboard = useDashboard();
  const toast = useToast();

  useEffect(() => {
    if (dashboard.error) {
      toast.error("Failed to load analytics.");
    }
  }, [dashboard.error, toast]);

  if (dashboard.loading && dashboard.revenueAnalytics.total_closed_revenue === "0") {
    return <LoadingBlock label="Loading analytics…" />;
  }

  const { revenueAnalytics, leadAnalytics, conversionAnalytics } = dashboard;

  return (
    <>
      <div className="page-header">
        <div className="page-header__titles">
          <h1>Analytics</h1>
          <p>Revenue, lead funnel, and conversion metrics.</p>
        </div>
      </div>

      <div className="kpi-grid">
        <Kpi label="Closed revenue" value={formatCurrency(revenueAnalytics.total_closed_revenue)} />
        <Kpi label="Open pipeline" value={formatCurrency(revenueAnalytics.open_pipeline_value)} />
        <Kpi label="Total leads" value={formatNumber(leadAnalytics.total_leads)} />
        <Kpi label="Won leads" value={formatNumber(leadAnalytics.won_leads)} />
        <Kpi label="Lead → win rate" value={`${conversionAnalytics.lead_to_win_rate}%`} />
        <Kpi label="Deal win rate" value={`${conversionAnalytics.deal_win_rate}%`} />
        <Kpi label="Avg. probability" value={`${conversionAnalytics.average_probability}%`} />
      </div>

      <div className="chart-grid chart-grid--2-1">
        <Card title="Monthly revenue">
          {revenueAnalytics.monthly_revenue.length === 0 ? (
            <EmptyState title="No revenue data yet" />
          ) : (
            <div style={{ height: 260 }}>
              <ResponsiveContainer>
                <LineChart data={revenueAnalytics.monthly_revenue}>
                  <CartesianGrid stroke={CHART_GRID} vertical={false} />
                  <XAxis dataKey="label" stroke={CHART_AXIS} fontSize={12} />
                  <YAxis stroke={CHART_AXIS} fontSize={12} />
                  <Tooltip />
                  <Line type="monotone" dataKey="value" stroke={CHART_PRIMARY} strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>
        <Card title="Lead stage breakdown">
          {leadAnalytics.stage_breakdown.length === 0 ? (
            <EmptyState title="No leads yet" />
          ) : (
            <div style={{ height: 260 }}>
              <ResponsiveContainer>
                <PieChart>
                  <Pie
                    data={leadAnalytics.stage_breakdown}
                    dataKey="value"
                    nameKey="label"
                    innerRadius={50}
                    outerRadius={80}
                  >
                    {leadAnalytics.stage_breakdown.map((_, index) => (
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

      <Card title="Lead source breakdown">
        {leadAnalytics.source_breakdown.length === 0 ? (
          <EmptyState title="No lead sources captured yet" />
        ) : (
          <div style={{ height: 240 }}>
            <ResponsiveContainer>
              <BarChart data={leadAnalytics.source_breakdown}>
                <CartesianGrid stroke={CHART_GRID} vertical={false} />
                <XAxis dataKey="label" stroke={CHART_AXIS} fontSize={12} />
                <YAxis stroke={CHART_AXIS} fontSize={12} />
                <Tooltip />
                <Bar dataKey="value" fill={CHART_PRIMARY} radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </Card>
    </>
  );
}


function Kpi({ label, value }: { label: string; value: string }) {
  return (
    <div className="kpi">
      <div className="kpi__label">{label}</div>
      <div className="kpi__value">{value}</div>
    </div>
  );
}
