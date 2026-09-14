import { apiClient } from "./http";


export interface CallyzerConnection {
  id: string;
  label: string | null;
  status: string; // ok | needs_reauth | error
  status_detail: string | null;
  last_synced_at: string | null;
  last_call_at: string | null;
  is_active: boolean;
  created_at: string;
}

/** A call synced from Callyzer (matched to a lead by number at read time). */
export interface ExternalCall {
  id: string;
  provider: string;
  external_id: string;
  client_number: string | null;
  client_name: string | null;
  emp_number: string | null;
  emp_name: string | null;
  call_type: string | null;   // Incoming | Outgoing | Missed | Rejected
  call_method: string | null; // PhoneCall | WhatsAppCall
  call_mode: string | null;   // Voice | Video
  duration_seconds: number | null;
  call_at: string | null;
  note: string | null;
  crm_status: string | null;
  reminder_at: string | null;
  recording_url: string | null;
  created_at: string;
  lead: { id: string; lead_number: number; contact_name: string } | null;
}

export interface CallsListResponse {
  items: ExternalCall[];
  pagination: { page: number; page_size: number; total: number; total_pages: number };
}

export interface CallsQuery {
  call_type?: string;
  q?: string;
  matched?: boolean;
  date_from?: string;
  date_to?: string;
  page?: number;
  page_size?: number;
}


/** Tenant-facing Callyzer connection management (Integrations page). */
export const callyzerService = {
  async list(): Promise<CallyzerConnection[]> {
    const { data } = await apiClient.get<CallyzerConnection[]>("/integrations/callyzer");
    return data;
  },
  async connect(token: string, label: string | null): Promise<CallyzerConnection> {
    const { data } = await apiClient.post<CallyzerConnection>("/integrations/callyzer/connect", {
      token,
      label,
    });
    return data;
  },
  async disconnect(id: string): Promise<void> {
    await apiClient.delete(`/integrations/callyzer/${id}`);
  },
};


/** Reading synced calls — the Calls page + the per-lead list in the lead drawer. */
export const callsService = {
  async list(params: CallsQuery = {}): Promise<CallsListResponse> {
    const { data } = await apiClient.get<CallsListResponse>("/calls", { params });
    return data;
  },
  async forLead(leadId: string): Promise<ExternalCall[]> {
    const { data } = await apiClient.get<ExternalCall[]>(`/calls/lead/${leadId}`);
    return data;
  },
};
