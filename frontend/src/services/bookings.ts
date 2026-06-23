import { apiClient } from "./http";
import type { Booking, BookingStep, PricingSnapshot } from "../types/realestate";

export interface CreateBookingPayload {
  unitId: string;
  leadId?: string | null;
  customerId?: string | null;
}

export const bookingsService = {
  list(params?: { unitId?: string; customerId?: string; status?: string }): Promise<Booking[]> {
    return apiClient.get<Booking[]>("/bookings", { params }).then((r) => r.data);
  },

  get(id: string): Promise<Booking> {
    return apiClient.get<Booking>(`/bookings/${id}`).then((r) => r.data);
  },

  create(payload: CreateBookingPayload): Promise<Booking> {
    return apiClient.post<Booking>("/bookings", payload).then((r) => r.data);
  },

  advanceStep(id: string, step: BookingStep, data: Record<string, unknown>): Promise<Booking> {
    return apiClient.post<Booking>(`/bookings/${id}/step/${step}`, data).then((r) => r.data);
  },

  setPricing(id: string, pricing: PricingSnapshot): Promise<Booking> {
    return apiClient.put<Booking>(`/bookings/${id}/pricing`, pricing).then((r) => r.data);
  },

  getDocumentUrl(id: string, docType: "booking_form" | "allotment_letter" | "receipt"): Promise<string> {
    return apiClient
      .get<{ url: string }>(`/bookings/${id}/documents/${docType}`)
      .then((r) => r.data.url);
  },

  uploadKyc(id: string, file: File, docType: string): Promise<Booking> {
    const form = new FormData();
    form.append("file", file);
    form.append("doc_type", docType);
    return apiClient.post<Booking>(`/bookings/${id}/kyc`, form).then((r) => r.data);
  },
};
