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
  auth_type: string; // "oauth" (Connect Facebook) | "byo" (System-User token)
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

// A Page surfaced by the OAuth round-trip for the admin to pick from.
export interface MetaOAuthPage {
  id: string;
  name: string | null;
  has_instagram: boolean;
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

  // --- OAuth "Connect Facebook" (one-click) ---
  // start → returns the Facebook consent URL to redirect the browser to. Meta then
  // bounces back to /integrations?meta_oauth=<handle>, which the page exchanges for the
  // user's Pages (getMetaOAuthSession) before connecting the chosen ones (connectMetaOAuth).
  async startMetaOAuth(): Promise<{ authorize_url: string }> {
    const { data } = await apiClient.get<{ authorize_url: string }>("/integrations/meta/oauth/start");
    return data;
  },
  async getMetaOAuthSession(handle: string): Promise<MetaOAuthPage[]> {
    const { data } = await apiClient.get<MetaOAuthPage[]>(
      `/integrations/meta/oauth/session/${encodeURIComponent(handle)}`
    );
    return data;
  },
  async connectMetaOAuth(handle: string, pageIds: string[]): Promise<MetaConnection[]> {
    const { data } = await apiClient.post<MetaConnection[]>("/integrations/meta/oauth/connect", {
      handle,
      page_ids: pageIds,
    });
    return data;
  },
};

// --- 99acres (push-portal) lead ingestion ---
export interface LeadSourceConnection {
  id: string;
  provider: string;
  label: string | null;
  external_account_id: string | null;
  default_industry: string;
  status: string; // ok | error
  status_detail: string | null;
  last_lead_at: string | null;
  is_active: boolean;
  created_at: string;
}

// Returned once on connect: the per-account webhook URL + token are shown a single time
// (only the token's hash is stored server-side).
export interface LeadSourceConnectResult {
  connection: LeadSourceConnection;
  webhook_url: string;
  token: string;
}

export const leadSourceService = {
  async list99acres(): Promise<LeadSourceConnection[]> {
    const { data } = await apiClient.get<LeadSourceConnection[]>("/integrations/99acres");
    return data;
  },
  async connect99acres(label: string | null): Promise<LeadSourceConnectResult> {
    const { data } = await apiClient.post<LeadSourceConnectResult>("/integrations/99acres/connect", {
      label,
    });
    return data;
  },
  async disconnect99acres(id: string): Promise<void> {
    await apiClient.delete(`/integrations/99acres/${id}`);
  },
};

// Google Sheet lead sync (pull). The tenant shares their sheet (Viewer) with the platform
// service-account email, pastes the Sheet ID, and connect() verifies read access before saving.
export interface GoogleSheetConnectResult {
  connection: LeadSourceConnection;
  service_account_email: string | null;
}

export const googleSheetsService = {
  async serviceAccountEmail(): Promise<string | null> {
    const { data } = await apiClient.get<{ email: string | null }>(
      "/integrations/google-sheets/service-account",
    );
    return data.email;
  },
  async list(): Promise<LeadSourceConnection[]> {
    const { data } = await apiClient.get<LeadSourceConnection[]>("/integrations/google-sheets");
    return data;
  },
  async connect(sheetId: string, label: string | null): Promise<GoogleSheetConnectResult> {
    const { data } = await apiClient.post<GoogleSheetConnectResult>(
      "/integrations/google-sheets/connect",
      { sheet_id: sheetId, label },
    );
    return data;
  },
  async disconnect(id: string): Promise<void> {
    await apiClient.delete(`/integrations/google-sheets/${id}`);
  },
};
