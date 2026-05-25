import type { TeamScorecard } from "../types";
import { apiClient } from "./http";


export interface PerformanceSnapshot {
  id: string;
  user_id: string;
  snapshot_date: string;
  deals_closed: number;
  revenue: string;
  collections: string;
  conversion_rate: string;
  pipeline_velocity_days: string;
  activity_quality: string;
  retention: string;
  score: string;
  grade: string;
  computed_at: string;
}

export const hrService = {
  async teamScorecard(): Promise<TeamScorecard> {
    const { data } = await apiClient.get<TeamScorecard>("/hr/scorecards");
    return data;
  },
  async individual(userId: string): Promise<PerformanceSnapshot[]> {
    const { data } = await apiClient.get<PerformanceSnapshot[]>(`/hr/scorecards/${userId}`);
    return data;
  },
  async recompute(userId: string): Promise<PerformanceSnapshot> {
    const { data } = await apiClient.post<PerformanceSnapshot>(`/hr/scorecards/${userId}/recompute`);
    return data;
  }
};
