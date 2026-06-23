import { apiClient } from "./http";


export interface PaymentScheduleEntry {
  id: string;
  booking_id: string;
  installment_name: string;
  due_date: string;
  demand_amount: number;
  paid_amount: number;
  outstanding: number;
  is_overdue: boolean;
}

export interface CustomerDocument {
  id: string;
  name: string;
  type: "booking_form" | "allotment_letter" | "demand_note" | "receipt" | "possession_letter";
  url: string;
  created_at: string;
}

export interface ServiceRequest {
  id: string;
  category: "maintenance" | "query" | "complaint" | "other";
  description: string;
  status: "open" | "in_progress" | "resolved";
  created_at: string;
  resolved_at: string | null;
}

export interface CreateServiceRequestPayload {
  category: ServiceRequest["category"];
  description: string;
}

export interface SubmitReferralPayload {
  contact_name: string;
  contact_phone?: string;
  contact_email?: string;
  preferred_location?: string;
  notes?: string;
}

export const customerPortalService = {
  async getPayments(): Promise<PaymentScheduleEntry[]> {
    const { data } = await apiClient.get<PaymentScheduleEntry[]>("/customer/payments");
    return data;
  },

  async getDocuments(): Promise<CustomerDocument[]> {
    const { data } = await apiClient.get<CustomerDocument[]>("/customer/documents");
    return data;
  },

  async getDocumentUrl(docId: string): Promise<string> {
    const { data } = await apiClient.get<{ url: string }>(`/customer/documents/${docId}/download`);
    return data.url;
  },

  async listServiceRequests(): Promise<ServiceRequest[]> {
    const { data } = await apiClient.get<ServiceRequest[]>("/customer/service-requests");
    return data;
  },

  async createServiceRequest(payload: CreateServiceRequestPayload): Promise<ServiceRequest> {
    const { data } = await apiClient.post<ServiceRequest>("/customer/service-requests", payload);
    return data;
  },

  async submitReferral(payload: SubmitReferralPayload): Promise<void> {
    await apiClient.post("/customer/referrals", payload);
  }
};
