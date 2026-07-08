import { apiClient } from "./http";
import type { Booking, BookingStatus, BookingStep, PricingSnapshot, UnitStatus, UnitType } from "../types/realestate";

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
  possession_checklist?: boolean[] | null;
  created_at: string;
  updated_at: string;
  unit?: {
    id: string;
    unit_number: string;
    floor: number;
    unit_type: string;
    area: number | string;
    area_unit: string;
    base_price: number | string;
    status: string;
    tower_name: string | null;
    project_name: string | null;
  } | null;
  customer?: { id: string; contact_name: string; company_name: string; email: string | null } | null;
  kyc_documents?: { doc_type?: string; type?: string; file_path?: string | null; created_at?: string }[];
  payment_schedules?: {
    id: string;
    installment_name: string;
    due_date: string;
    demand_amount: number | string;
    paid_amount: number | string;
    outstanding: number | string;
    is_overdue: boolean;
  }[];
}

function mapBooking(b: ApiBooking): Booking {
  return {
    id: b.id,
    unitId: b.unit_id,
    leadId: b.lead_id,
    customerId: b.customer_id,
    step: b.step as BookingStep,
    status: b.status,
    customer: b.customer
      ? {
          id: b.customer.id,
          contactName: b.customer.contact_name,
          companyName: b.customer.company_name,
          email: b.customer.email ?? null,
        }
      : null,
    paymentSchedules: (b.payment_schedules ?? []).map((p) => ({
      id: p.id,
      installmentName: p.installment_name,
      dueDate: p.due_date,
      demandAmount: Number(p.demand_amount),
      paidAmount: Number(p.paid_amount),
      outstanding: Number(p.outstanding),
      isOverdue: p.is_overdue,
    })),
    kycDocuments: (b.kyc_documents ?? []).map((d) => ({
      type: (d.type ?? d.doc_type ?? "other") as "aadhaar" | "pan" | "photo" | "other",
      fileName: d.file_path ?? "",
      uploadedAt: d.created_at ?? "",
    })),
    pricingSnapshot: (b.pricing_snapshot as PricingSnapshot | null) ?? null,
    scheduledDate: b.scheduled_date,
    possessionChecklist: b.possession_checklist ?? null,
    unit: b.unit
      ? {
          id: b.unit.id,
          unitNumber: b.unit.unit_number,
          floor: b.unit.floor,
          unitType: b.unit.unit_type as UnitType,
          area: Number(b.unit.area),
          areaUnit: b.unit.area_unit as "sqft" | "sqmt",
          basePrice: Number(b.unit.base_price),
          status: b.unit.status as UnitStatus,
          towerName: b.unit.tower_name ?? "",
          projectName: b.unit.project_name ?? "",
        }
      : undefined,
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

  savePossessionChecklist(id: string, checklist: boolean[]): Promise<Booking> {
    return apiClient
      .put<ApiBooking>(`/bookings/${id}/possession`, { checklist })
      .then((r) => mapBooking(r.data));
  },

  getDocumentHtml(
    id: string,
    docType: "booking_form" | "allotment_letter" | "receipt"
  ): Promise<{ html: string; title: string }> {
    return apiClient
      .get<{ html: string; title: string }>(`/bookings/${id}/documents/${docType}`)
      .then((r) => r.data);
  },

  // The /kyc endpoint records a KYC doc (doc_type + file name) and returns the
  // doc — NOT the booking. Server-side file storage isn't wired yet, so we send
  // the filename as file_path. Returns void so callers don't mistake the doc for
  // the booking (which would corrupt booking.id for the next step).
  uploadKyc(id: string, file: File, docType: string): Promise<void> {
    return apiClient
      .post(`/bookings/${id}/kyc`, { doc_type: docType, file_path: file.name })
      .then(() => undefined);
  },
};
