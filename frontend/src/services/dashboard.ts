import type {
  AnalyticsConversion,
  AnalyticsLeads,
  AnalyticsRevenue,
  DashboardCharts,
  DashboardSummary,
  RecentActivities
} from "../types";
import { apiClient } from "./http";


export const dashboardService = {
  async summary(): Promise<DashboardSummary> {
    const { data } = await apiClient.get<DashboardSummary>("/dashboard/summary");
    return data;
  },

  async charts(): Promise<DashboardCharts> {
    const { data } = await apiClient.get<DashboardCharts>("/dashboard/charts");
    return data;
  },

  async recentActivities(): Promise<RecentActivities> {
    const { data } = await apiClient.get<RecentActivities>("/dashboard/recent-activities");
    return data;
  },

  async revenueAnalytics(): Promise<AnalyticsRevenue> {
    const { data } = await apiClient.get<AnalyticsRevenue>("/analytics/revenue");
    return data;
  },

  async leadsAnalytics(): Promise<AnalyticsLeads> {
    const { data } = await apiClient.get<AnalyticsLeads>("/analytics/leads");
    return data;
  },

  async conversionAnalytics(): Promise<AnalyticsConversion> {
    const { data } = await apiClient.get<AnalyticsConversion>("/analytics/conversion");
    return data;
  }
};
