import type {
  ApiMessageResponse,
  Lead,
  LeadIndustry,
  LeadListResponse,
  PaginationQuery,
  SearchSortQuery,
  StageTransition
} from "../types";
import { buildQueryString } from "../utils/queryString";
import { apiClient } from "./http";


export interface LeadListQuery extends PaginationQuery, SearchSortQuery {
  customer_id?: string;
  industry?: LeadIndustry;
  stage_code?: string;
  source?: string;
  assigned_to_id?: string;
}

export interface LeadCreatePayload {
  // Optional in the request: backend falls back to the current user's
  // business_type when omitted (set at registration).
  industry?: LeadIndustry;
  title: string;
  contact_name: string;
  contact_email?: string | null;
  contact_phone?: string | null;
  company_name?: string | null;
  customer_id?: string | null;
  value?: string | number;
  // ISO 4217 code. Must be in the org's allowed list (defaults to INR).
  currency?: string;
  probability?: number;
  expected_close_date?: string | null;
  source?: string | null;
  interest?: string | null;
  assigned_to_id?: string | null;
  property_type?: string | null;
  budget_min?: number | null;
  budget_max?: number | null;
  preferred_location?: string | null;
  possession_preference?: string | null;
  notes?: string | null;
}

export interface LeadUpdatePayload {
  customer_id?: string;
  industry?: LeadIndustry;
  title?: string;
  contact_name?: string;
  contact_email?: string | null;
  contact_phone?: string | null;
  company_name?: string | null;
  value?: string | number;
  probability?: number;
  expected_close_date?: string | null;
  source?: string | null;
  interest?: string | null;
  assigned_to_id?: string | null;
}

export interface StageTransitionPayload {
  to_stage_code: string;
  comment: string;
  next_action_date?: string | null;
  attachment_path?: string | null;
  mentions?: string[];
}

export interface LeadImportResult {
  created: number;
  promoted: number;
  errors: { row: number; error: string }[];
}

export const leadsService = {
  async list(query: LeadListQuery = {}): Promise<LeadListResponse> {
    const { data } = await apiClient.get<LeadListResponse>(`/leads${buildQueryString(query)}`);
    return data;
  },

  async create(payload: LeadCreatePayload): Promise<Lead> {
    const { data } = await apiClient.post<Lead>("/leads", payload);
    return data;
  },

  async update(leadId: string, payload: LeadUpdatePayload): Promise<Lead> {
    const { data } = await apiClient.put<Lead>(`/leads/${leadId}`, payload);
    return data;
  },

  async remove(leadId: string): Promise<ApiMessageResponse> {
    const { data } = await apiClient.delete<ApiMessageResponse>(`/leads/${leadId}`);
    return data;
  },

  async transitions(leadId: string): Promise<StageTransition[]> {
    const { data } = await apiClient.get<StageTransition[]>(`/leads/${leadId}/transitions`);
    return data;
  },

  async createTransition(leadId: string, payload: StageTransitionPayload): Promise<StageTransition> {
    const { data } = await apiClient.post<StageTransition>(`/leads/${leadId}/transitions`, payload);
    return data;
  },

  async importCsv(file: File): Promise<LeadImportResult> {
    const formData = new FormData();
    formData.append("file", file);
    const { data } = await apiClient.post<LeadImportResult>("/leads/import", formData, {
      // Let axios infer the multipart boundary — overriding the default
      // `Content-Type: application/json` header set on the client.
      headers: { "Content-Type": "multipart/form-data" }
    });
    return data;
  }
};
