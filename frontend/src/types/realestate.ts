export type UnitStatus = "available" | "hold" | "booked" | "registered" | "sold";
export type UnitType = "residential" | "parking" | "shop" | "godown";
export type UnitFacing = "north" | "south" | "east" | "west" | "north_east" | "north_west" | "south_east" | "south_west";
export type SiteVisitFeedback = "hot" | "warm" | "cold";
export type BookingStep = 1 | 2 | 3 | 4;
export type BookingStatus = "draft" | "confirmed" | "cancelled";
export type PropertyType = "apartment" | "villa" | "plot" | "commercial";
export type PossessionPreference = "immediate" | "6_months" | "1_year" | "2_years" | "under_construction";

export interface Unit {
  id: string;
  projectId: string;
  towerId: string;
  floor: number;
  unitNumber: string;
  unitType: UnitType;
  area: number;
  areaUnit: "sqft" | "sqmt";
  facing: UnitFacing | null;
  view: string | null;
  basePrice: number;
  status: UnitStatus;
  updatedAt: string;
}

export interface Tower {
  id: string;
  projectId: string;
  name: string;
  totalFloors: number;
  units: Unit[];
}

export interface ProjectMedia {
  id: string;
  type: "brochure" | "floor_plan" | "image" | "video" | "virtual_tour";
  url: string;
  label: string | null;
}

export interface Project {
  id: string;
  name: string;
  builderName: string;
  location: string;
  city: string;
  reraNumber: string | null;
  towers: Tower[];
  media: ProjectMedia[];
  totalUnits: number;
  availableUnits: number;
  createdAt: string;
  updatedAt: string;
}

export interface SiteVisit {
  id: string;
  leadId: string;
  projectId: string;
  scheduledAt: string;
  assignedToId: string | null;
  feedback: SiteVisitFeedback | null;
  attended: boolean | null;
  notes: string | null;
  createdAt: string;
  project: { id: string; name: string } | null;
  lead: { id: string; leadNumber: number; contactName: string; contactPhone: string | null } | null;
}

export interface PricingLineItem {
  label: string;
  amount: number;
}

export interface PricingSnapshot {
  basePrice: number;
  floorRise: number;
  plc: number;
  parking: number;
  otherCharges: number;
  gstRate: number;
  subtotal: number;
  gstAmount: number;
  total: number;
  lineItems: PricingLineItem[];
}

export interface KycDocument {
  type: "aadhaar" | "pan" | "photo" | "other";
  fileName: string;
  uploadedAt: string;
}

export interface BookingCustomer {
  id: string;
  contactName: string;
  companyName: string;
  email: string | null;
}

export interface PaymentScheduleEntry {
  id: string;
  installmentName: string;
  dueDate: string;
  demandAmount: number;
  paidAmount: number;
  outstanding: number;
  isOverdue: boolean;
}

export type PaymentMode = "upi" | "neft" | "cheque" | "cash" | "card" | "other";

export interface PaymentReceipt {
  id: string;
  bookingId: string;
  scheduleId: string | null;
  amount: number;
  paidOn: string;
  mode: PaymentMode;
  reference: string | null;
  notes: string | null;
  createdAt: string;
}

export interface Booking {
  id: string;
  unitId: string;
  leadId: string | null;
  customerId: string | null;
  customer: BookingCustomer | null;
  paymentSchedules: PaymentScheduleEntry[];
  paymentReceipts: PaymentReceipt[];
  step: BookingStep;
  status: BookingStatus;
  kycDocuments: KycDocument[];
  pricingSnapshot: PricingSnapshot | null;
  scheduledDate: string | null;
  possessionChecklist: boolean[] | null;
  cancellationReason: string | null;
  bookingFormUrl: string | null;
  allotmentLetterUrl: string | null;
  createdAt: string;
  updatedAt: string;
  unit?: Pick<Unit, "id" | "unitNumber" | "floor" | "unitType" | "area" | "areaUnit" | "basePrice" | "status"> & { towerName: string; projectName: string };
}
