import { useCallback, useEffect, useState } from "react";

import { dashboardService } from "../services/dashboard";
import type {
  AnalyticsConversion,
  AnalyticsLeads,
  AnalyticsRevenue,
  DashboardCharts,
  DashboardSummary,
  RecentActivities
} from "../types";


const initialSummary: DashboardSummary = {
  total_customers: 0,
  active_leads: 0,
  open_deals_value: "0",
  overdue_tasks: 0,
  recent_activity_count: 0
};

const initialCharts: DashboardCharts = {
  revenue_trend: [],
  lead_stage_breakdown: [],
  task_status_breakdown: []
};

const initialRecentActivities: RecentActivities = { items: [] };
const initialRevenue: AnalyticsRevenue = { total_closed_revenue: "0", open_pipeline_value: "0", monthly_revenue: [] };
const initialLeads: AnalyticsLeads = { total_leads: 0, won_leads: 0, stage_breakdown: [], source_breakdown: [] };
const initialConversion: AnalyticsConversion = { lead_to_win_rate: 0, deal_win_rate: 0, average_probability: 0 };

export function useDashboard() {
  const [summary, setSummary] = useState(initialSummary);
  const [charts, setCharts] = useState(initialCharts);
  const [recentActivities, setRecentActivities] = useState(initialRecentActivities);
  const [revenueAnalytics, setRevenueAnalytics] = useState(initialRevenue);
  const [leadAnalytics, setLeadAnalytics] = useState(initialLeads);
  const [conversionAnalytics, setConversionAnalytics] = useState(initialConversion);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);
  // True once the first fetch has completed (success or failure). Pages guard their
  // full-screen loader on `!initialized` — so a background refetch never blanks the page,
  // and a legitimate zero value (new / lead-only / no-revenue org) doesn't keep the loader up.
  const [initialized, setInitialized] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const [summaryResponse, chartsResponse, recentResponse, revenueResponse, leadsResponse, conversionResponse] =
        await Promise.all([
          dashboardService.summary(),
          dashboardService.charts(),
          dashboardService.recentActivities(),
          dashboardService.revenueAnalytics(),
          dashboardService.leadsAnalytics(),
          dashboardService.conversionAnalytics()
        ]);

      setSummary(summaryResponse);
      setCharts(chartsResponse);
      setRecentActivities(recentResponse);
      setRevenueAnalytics(revenueResponse);
      setLeadAnalytics(leadsResponse);
      setConversionAnalytics(conversionResponse);
    } catch (requestError) {
      setError(requestError);
      throw requestError;
    } finally {
      setLoading(false);
      setInitialized(true);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return {
    summary,
    charts,
    recentActivities,
    revenueAnalytics,
    leadAnalytics,
    conversionAnalytics,
    loading,
    error,
    initialized,
    refresh
  };
}
