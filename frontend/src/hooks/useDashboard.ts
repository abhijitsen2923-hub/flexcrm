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
import { getCached, setCached } from "./resourceCache";


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

// The dashboard aggregates six endpoints, so it's cached as one combined payload
// under a single key — a revisit paints the last snapshot instantly and refreshes
// in the background.
const CACHE_KEY = "dashboard:v1";

interface DashboardPayload {
  summary: DashboardSummary;
  charts: DashboardCharts;
  recentActivities: RecentActivities;
  revenueAnalytics: AnalyticsRevenue;
  leadAnalytics: AnalyticsLeads;
  conversionAnalytics: AnalyticsConversion;
}

// `includeAnalytics` controls the three /analytics/* calls (revenue, leads,
// conversion), which require ANALYTICS_VIEW. The Dashboard doesn't display any
// of them, so it passes false and never requests them — that alone stops the
// 403s a lead role (e.g. sales_executive, which has DASHBOARD_VIEW but not
// ANALYTICS_VIEW) used to hit. The Analytics page needs them, so it keeps the
// default (true); there the calls are tolerated per-endpoint (a 403 leaves that
// slice empty instead of blanking the page).
export function useDashboard({ includeAnalytics = true }: { includeAnalytics?: boolean } = {}) {
  const cached = () => getCached<DashboardPayload>(CACHE_KEY);

  const [summary, setSummary] = useState(() => cached()?.summary ?? initialSummary);
  const [charts, setCharts] = useState(() => cached()?.charts ?? initialCharts);
  const [recentActivities, setRecentActivities] = useState(() => cached()?.recentActivities ?? initialRecentActivities);
  const [revenueAnalytics, setRevenueAnalytics] = useState(() => cached()?.revenueAnalytics ?? initialRevenue);
  const [leadAnalytics, setLeadAnalytics] = useState(() => cached()?.leadAnalytics ?? initialLeads);
  const [conversionAnalytics, setConversionAnalytics] = useState(() => cached()?.conversionAnalytics ?? initialConversion);
  const [loading, setLoading] = useState(false);
  const [isValidating, setIsValidating] = useState(false);
  const [slow, setSlow] = useState(false);
  const [error, setError] = useState<unknown>(null);
  // True once we have data to show — from cache immediately, or after the first
  // fetch. Pages gate their full-screen loader on `!initialized`, so a warm cache
  // or a background refetch never blanks the page.
  const [initialized, setInitialized] = useState(() => getCached<DashboardPayload>(CACHE_KEY) !== undefined);

  const refresh = useCallback(async () => {
    const warm = getCached<DashboardPayload>(CACHE_KEY) !== undefined;
    if (warm) {
      setIsValidating(true);
    } else {
      setLoading(true);
    }
    setError(null);
    setSlow(false);
    const slowTimer = setTimeout(() => setSlow(true), 4000);

    try {
      // Core dashboard data — every dashboard role has DASHBOARD_VIEW, so a
      // failure here is a genuine error worth surfacing.
      const [summaryResponse, chartsResponse, recentResponse] = await Promise.all([
        dashboardService.summary(),
        dashboardService.charts(),
        dashboardService.recentActivities()
      ]);
      setSummary(summaryResponse);
      setCharts(chartsResponse);
      setRecentActivities(recentResponse);

      // Analytics (ANALYTICS_VIEW-gated) — only where displayed, and each
      // tolerated so a 403 for a role without the permission leaves that slice
      // empty rather than rejecting the whole load / firing the error toast.
      let revenueResponse: AnalyticsRevenue = initialRevenue;
      let leadsResponse: AnalyticsLeads = initialLeads;
      let conversionResponse: AnalyticsConversion = initialConversion;
      if (includeAnalytics) {
        const [rev, leads, conv] = await Promise.all([
          dashboardService.revenueAnalytics().catch(() => null),
          dashboardService.leadsAnalytics().catch(() => null),
          dashboardService.conversionAnalytics().catch(() => null)
        ]);
        if (rev) { revenueResponse = rev; setRevenueAnalytics(rev); }
        if (leads) { leadsResponse = leads; setLeadAnalytics(leads); }
        if (conv) { conversionResponse = conv; setConversionAnalytics(conv); }
      }

      setCached(CACHE_KEY, {
        summary: summaryResponse,
        charts: chartsResponse,
        recentActivities: recentResponse,
        revenueAnalytics: revenueResponse,
        leadAnalytics: leadsResponse,
        conversionAnalytics: conversionResponse
      });
    } catch (requestError) {
      setError(requestError);
      throw requestError;
    } finally {
      clearTimeout(slowTimer);
      setLoading(false);
      setIsValidating(false);
      setSlow(false);
      setInitialized(true);
    }
  }, [includeAnalytics]);

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
    isValidating,
    slow,
    error,
    initialized,
    refresh
  };
}
