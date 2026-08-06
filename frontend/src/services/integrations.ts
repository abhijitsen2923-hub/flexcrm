import { apiClient } from "./http";

export interface MetaValidateResult {
  ok: boolean;
  page_name?: string | null;
  form_count?: number | null;
  // invalid_token | missing_lead_access | error
  reason?: string | null;
  detail?: string | null;
}

export interface MetaConnection {
  id: string;
  provider: string;
  page_id: string;
  page_name: string | null;
  default_industry: string;
  field_map: Record<string, string> | null;
  status: string; // ok | needs_reauth | error
  status_detail: string | null;
  last_synced_at: string | null;
  is_active: boolean;
  created_at: string;
}

export interface MetaConnectPayload {
  page_id: string;
  token: string;
  field_map?: Record<string, string> | null;
}

// Tenant Meta (Facebook/Instagram) Lead Ads connection management. The access
// token is only ever sent, never returned.
export const integrationsService = {
  async validateMeta(pageId: string, token: string): Promise<MetaValidateResult> {
    const { data } = await apiClient.post<MetaValidateResult>("/integrations/meta/validate", {
      page_id: pageId,
      token,
    });
    return data;
  },
  async listMeta(): Promise<MetaConnection[]> {
    const { data } = await apiClient.get<MetaConnection[]>("/integrations/meta");
    return data;
  },
  async connectMeta(payload: MetaConnectPayload): Promise<MetaConnection> {
    const { data } = await apiClient.post<MetaConnection>("/integrations/meta", payload);
    return data;
  },
  async updateMeta(
    id: string,
    payload: { token?: string; field_map?: Record<string, string> | null; is_active?: boolean }
  ): Promise<MetaConnection> {
    const { data } = await apiClient.patch<MetaConnection>(`/integrations/meta/${id}`, payload);
    return data;
  },
  async disconnectMeta(id: string): Promise<void> {
    await apiClient.delete(`/integrations/meta/${id}`);
  },
};
