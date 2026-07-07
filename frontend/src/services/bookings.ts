import { apiClient } from "./http";
import type { Booking, BookingStatus, BookingStep, PricingSnapshot } from "../types/realestate";

export interface CreateBookingPayload {
  unitId: string;
  leadId?: string | null;
  customerId?: string | null;
}

// The API speaks snake_case; the app models are camelCase. Map at the boundary
// (same pattern as the inventory service).
interface ApiBooking {
  id: string;
  unit_id: string;
  lead_id: string | null;
  customer_id: string | null;
  step: number;
  status: BookingStatus;
  pricing_snapshot: unknown | null;
  scheduled_date: string | null;
  created_at: string;
  updated_at: string;
  kyc_documents?: { doc_type?: string; type?: string; file_path?: string | null; created_at?: string }[];
}

function mapBooking(b: ApiBooking): Booking {
  return {
    id: b.id,
    unitId: b.unit_id,
    leadId: b.lead_id,
    customerId: b.customer_id,
    step: b.step as BookingStep,
    status: b.status,
    kycDocuments: (b.kyc_documents ?? []).map((d) => ({
      type: (d.type ?? d.doc_type ?? "other") as "aadhaar" | "pan" | "photo" | "other",
      fileName: d.file_path ?? "",
      uploadedAt: d.created_at ?? "",
    })),
    pricingSnapshot: (b.pricing_snapshot as PricingSnapshot | null) ?? null,
    scheduledDate: b.scheduled_date,
    bookingFormUrl: null,
    allotmentLetterUrl: null,
    createdAt: b.created_at,
    updatedAt: b.updated_at,
  };
}

export const bookingsService = {
  list(params?: { unitId?: string; customerId?: string; status?: string }): Promise<Booking[]> {
    return apiClient
      .get<ApiBooking[]>("/bookings", {
        params: { unit_id: params?.unitId, customer_id: params?.customerId, status: params?.status },
      })
      .then((r) => r.data.map(mapBooking));
  },

  get(id: string): Promise<Booking> {
    return apiClient.get<ApiBooking>(`/bookings/${id}`).then((r) => mapBooking(r.data));
  },

  create(payload: CreateBookingPayload): Promise<Booking> {
    return apiClient
      .post<ApiBooking>("/bookings", {
        unit_id: payload.unitId,
        lead_id: payload.leadId ?? null,
        customer_id: payload.customerId ?? null,
      })
      .then((r) => mapBooking(r.data));
  },

  advanceStep(id: string, step: BookingStep, data: Record<string, unknown>): Promise<Booking> {
    return apiClient.post<ApiBooking>(`/bookings/${id}/step/${step}`, data).then((r) => mapBooking(r.data));
  },

  setPricing(id: string, pricing: PricingSnapshot): Promise<Booking> {
    return apiClient
      .put<ApiBooking>(`/bookings/${id}/pricing`, { pricing_snapshot: pricing })
      .then((r) => mapBooking(r.data));
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
    return apiClient.post<ApiBooking>(`/bookings/${id}/kyc`, form).then((r) => mapBooking(r.data));
  },
};
