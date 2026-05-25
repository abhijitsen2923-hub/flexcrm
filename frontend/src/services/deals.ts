import type { ApiMessageResponse, Deal, DealListResponse, PaginationQuery, SearchSortQuery } from "../types";
import { buildQueryString } from "../utils/queryString";
import { apiClient } from "./http";


export interface DealListQuery extends PaginationQuery, SearchSortQuery {
  customer_id?: string;
  stage?: string;
  status?: string;
}

export interface DealPayload {
  customer_id: string;
  title: string;
  amount: string | number;
  stage: string;
  expected_close?: string | null;
  status?: string;
}

export const dealsService = {
  async list(query: DealListQuery = {}): Promise<DealListResponse> {
    const { data } = await apiClient.get<DealListResponse>(`/deals${buildQueryString(query)}`);
    return data;
  },

  async create(payload: DealPayload): Promise<Deal> {
    const { data } = await apiClient.post<Deal>("/deals", payload);
    return data;
  },

  async update(dealId: string, payload: Partial<DealPayload>): Promise<Deal> {
    const { data } = await apiClient.put<Deal>(`/deals/${dealId}`, payload);
    return data;
  },

  async remove(dealId: string): Promise<ApiMessageResponse> {
    const { data } = await apiClient.delete<ApiMessageResponse>(`/deals/${dealId}`);
    return data;
  }
};
