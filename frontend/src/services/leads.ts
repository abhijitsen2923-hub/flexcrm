import type {
  ApiMessageResponse,
  Lead,
  LeadCallLog,
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
  contact_phone_alt?: string | null;
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
  partner_id?: string | null;
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

export interface LeadImportDuplicate {
  row: number;
  contact_name: string | null;
  contact_email: string | null;
  contact_phone: string | null;
  matched: string;        // existing lead numbers, e.g. "#89004, #89003"
  skipped: boolean;       // true = dropped by "skip duplicates"; false = imported anyway
}

export interface LeadImportResult {
  created: number;
  promoted: number;
  skipped: number;
  errors: { row: number; error: string }[];
  duplicates: LeadImportDuplicate[];
}

export interface LeadDuplicate {
  id: string;
  lead_number: number;
  title: string;
  contact_name: string;
  contact_email?: string | null;
  contact_phone?: string | null;
  stage_code: string;
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

  // Warn-but-allow duplicate check for the New Lead form. Returns active leads
  // in the caller's tenant matching the email (case-insensitive) or phone
  // (digits-only). Returns [] when both inputs are blank or nothing matches.
  async checkDuplicates(email?: string | null, phone?: string | null): Promise<LeadDuplicate[]> {
    if (!email?.trim() && !phone?.trim()) {
      return [];
    }
    const { data } = await apiClient.get<LeadDuplicate[]>(
      `/leads/duplicates${buildQueryString({ email: email ?? undefined, phone: phone ?? undefined })}`
    );
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

  // Manager bulk reassignment — one owner for many leads.
  async bulkReassign(leadIds: string[], assignedToId: string): Promise<ApiMessageResponse> {
    const { data } = await apiClient.post<ApiMessageResponse>("/leads/bulk-reassign", {
      lead_ids: leadIds,
      assigned_to_id: assignedToId,
    });
    return data;
  },

  // Per-(lead, user) call tracking.
  async calls(leadId: string): Promise<LeadCallLog[]> {
    const { data } = await apiClient.get<LeadCallLog[]>(`/leads/${leadId}/calls`);
    return data;
  },

  async logCall(leadId: string, callType: "first_call" | "follow_up", notes?: string | null): Promise<LeadCallLog> {
    const { data } = await apiClient.post<LeadCallLog>(`/leads/${leadId}/calls`, {
      call_type: callType,
      notes: notes ?? null,
    });
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

  async importCsv(file: File, skipDuplicates = false): Promise<LeadImportResult> {
    const formData = new FormData();
    formData.append("file", file);
    const { data } = await apiClient.post<LeadImportResult>(
      `/leads/import${buildQueryString({ skip_duplicates: skipDuplicates })}`,
      formData,
      {
        // Let axios infer the multipart boundary — overriding the default
        // `Content-Type: application/json` header set on the client.
        headers: { "Content-Type": "multipart/form-data" }
      }
    );
    return data;
  },

  // Fetch the CSV template through apiClient (adds the auth header + the backend
  // base URL) as a blob and trigger a download. A plain window.open on the
  // relative "/api/v1/..." path would hit the frontend SPA (404) and can't send
  // the Authorization header.
  async downloadImportTemplate(): Promise<void> {
    const { data } = await apiClient.get("/leads/import/template.csv", { responseType: "blob" });
    const url = window.URL.createObjectURL(data as Blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "leads-import-template.csv";
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  }
};
