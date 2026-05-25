import type { Activity, ActivityListResponse, PaginationQuery, SearchSortQuery } from "../types";
import { buildQueryString } from "../utils/queryString";
import { apiClient } from "./http";


export interface ActivityListQuery extends PaginationQuery, SearchSortQuery {
  customer_id?: string;
  type?: string;
  created_by_id?: string;
}

export interface ActivityPayload {
  customer_id: string;
  type: string;
  note: string;
}

export const activitiesService = {
  async list(query: ActivityListQuery = {}): Promise<ActivityListResponse> {
    const { data } = await apiClient.get<ActivityListResponse>(`/activities${buildQueryString(query)}`);
    return data;
  },

  async create(payload: ActivityPayload): Promise<Activity> {
    const { data } = await apiClient.post<Activity>("/activities", payload);
    return data;
  }
};
