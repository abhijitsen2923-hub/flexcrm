export type UnitStatus = "available" | "hold" | "booked" | "registered" | "sold";
export type UnitType = "residential" | "parking" | "shop" | "godown";
// Garage / parking types a project offers (Multi-Level, Covered, Independent, Open). Kept to the original
// four: `garage_options` is also read by older backends, which reject anything else.
export type GarageOption = "MLP" | "CP" | "IP" | "OP";
// Every parking type a spot can be — adds Dependent Parking. Used for counts and per-type prices.
export type ParkingType = GarageOption | "DP";
export type ProjectType = "residential" | "commercial" | "mixed";
// The area a unit's basic price is worked out on (null = super built-up, as before).
export type PricingBasis = "super_built_up" | "built_up" | "carpet";
export type FloorRiseBasis = "per_sqft" | "per_floor";
// When a payment-plan milestone falls due. The last three are EVENTS: they become a demand only when the
// builder marks them reached (project / tower) or raises them on one booking.
export type PlanDueOn =
  | "on_booking"
  | "days_after_booking"
  | "on_date"
  | "on_stage"
  | "on_possession"
  | "on_registration";

// One payment-plan milestone, exactly as the API stores it (snake_case both ways). The label is the
// builder's own name; percent is a share of the booking's price (box price + GST).
export interface PlanMilestone {
  key: string;
  label: string;
  percent: number;
  due_on: PlanDueOn;
  days: number | null;      // days_after_booking only
  due_date: string | null;  // on_date only (YYYY-MM-DD)
}

export interface MilestoneReached {
  key: string;
  towerId: string | null;   // null = the whole project
  reachedOn: string;        // YYYY-MM-DD
}

// A tower's saved wizard layout, as the API stores it (snake_case both ways).
export interface FlatTypeLayout {
  code: string;                       // "A", "B" … — fixes the position on the floor (A → x01)
  configuration: string | null;       // "2 BHK"
  carpet_area: number | null;
  built_up_area: number | null;
  super_built_up_area: number;
  has_plc: boolean;
  floor_from: number | null;          // null = 1
  floor_to: number | null;            // null = the tower's top floor
}

export interface OtherUnitLayout {
  unit_type: "shop" | "godown";
  per_floor: number;
  floor_from: number;
  floor_to: number;
  area: number;                       // super built-up
  carpet_area: number | null;
  built_up_area: number | null;
  unit_prefix: string | null;
}

export interface TowerLayout {
  unit_prefix: string;                // "A-" → A-101
  flat_types: FlatTypeLayout[];
  others: OtherUnitLayout[];
  skip_floors?: number[];             // floors with no flats (refuge floors …); absent on older layouts = none
}
export type UnitFacing = "north" | "south" | "east" | "west" | "north_east" | "north_west" | "south_east" | "south_west";
export type SiteVisitFeedback = "hot" | "warm" | "cold";
export type SiteVisitStatus = "scheduled" | "completed" | "cancelled";
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
  area: number;               // super built-up (saleable) — drives pricing/display
  carpetArea: number | null;
  builtUpArea: number | null;
  areaUnit: "sqft" | "sqmt";
  facing: UnitFacing | null;
  view: string | null;
  basePrice: number;
  status: UnitStatus;
  flatType: string | null;            // "A" — null on older units, parking, shops, godowns
  configuration: string | null;       // "2 BHK"
  hasPlc: boolean;
  updatedAt: string;
}

export interface Tower {
  id: string;
  projectId: string;
  name: string;
  totalFloors: number;
  // The wizard layout last saved for this tower; null for towers set up before flat types existed.
  layout: TowerLayout | null;
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
  // --- Project detail (Phase B) — declared specs. ---
  pinCode: string | null;
  landmark: string | null;
  totalTowers: number | null;
  totalFloors: number | null;
  flatsPerFloor: number | null;
  totalGarages: number | null;
  garageOptions: GarageOption[] | null;
  // --- Default box-price components (Phase B). rate* are ₹/sqft; rest are lump sums. ---
  rateA: number | null;
  rateB: number | null;
  rateC: number | null;
  parkingCost: number | null;
  legalFees: number | null;
  overheadCost: number | null;
  otherCharges: number | null;
  sinkingFund: number | null;
  amenitiesCharges: number | null;
  demandSchedule: { label: string; percent: number; due_date: string }[] | null;
  // --- Add Project wizard ---
  projectType: ProjectType | null;
  pricingBasis: PricingBasis | null;
  floorRiseRate: number | null;
  floorRiseBasis: FloorRiseBasis | null;
  floorRiseFrom: number | null;
  plcRate: number | null;             // ₹/sq ft, for units with hasPlc
  amenitiesRate: number | null;       // ₹/sq ft (amenitiesCharges stays the older lump sum)
  parkingPrices: Partial<Record<ParkingType, number>> | null;
  paymentPlan: PlanMilestone[] | null;
  milestonesReached: MilestoneReached[] | null;
  towers: Tower[];
  media: ProjectMedia[];
  // Inventory counts: units = everything except parking (flats, shops, godowns); parking counted apart.
  totalUnits: number;
  availableUnits: number;
  totalParking: number;
  availableParking: number;
  createdAt: string;
  updatedAt: string;
}

export interface ProjectPossessionUnit {
  unitId: string;
  unitNumber: string;
  towerName: string | null;
  floor: number;
  unitStatus: UnitStatus;
  bookingId: string | null;
  customerName: string | null;
  registrationNumber: string | null;
  registered: boolean;
  possessionDone: number;
  possessionTotal: number;
}

export interface ProjectPossessionSummary {
  totalUnits: number;
  booked: number;
  registered: number;
  possessionComplete: number;
}

export interface ProjectPossessionRollup {
  projectId: string;
  projectName: string;
  summary: ProjectPossessionSummary;
  units: ProjectPossessionUnit[];
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
  status: SiteVisitStatus;
  createdAt: string;
  project: { id: string; name: string } | null;
  lead: { id: string; leadNumber: number; contactName: string; contactPhone: string | null } | null;
}

export interface PricingLineItem {
  label: string;
  amount: number;
}

export interface PricingSnapshot {
  // "Box price" inputs — when the unit area is known, base = ratePerSqft × area.
  // Both optional so older snapshots (base entered as a flat amount) still parse.
  ratePerSqft?: number;
  area?: number;
  // The area the rate was applied to (optional; older snapshots omit it = super built-up).
  basis?: PricingBasis;
  basePrice: number;
  floorRise: number;
  // First floor that paid floor rise (optional; older snapshots omit it = floor 2, i.e. floor − 1 steps).
  floorRiseFrom?: number;
  plc: number;
  parking: number;
  parkingType?: ParkingType; // the parking type chosen in the calculator (optional)
  // RERA "Box Price" components (optional; older snapshots omit them).
  generator?: number;
  amenities?: number;
  sinkingFund?: number; // 1-year maintenance / corpus
  legalFees?: number;   // legal / documentation charges (optional; older snapshots omit)
  overhead?: number;    // builder overhead (optional; older snapshots omit)
  otherCharges: number;
  // Box Price = flat + floor-rise + PLC + garage/parking + generator + amenities
  //           + sinking fund + legal + overhead + other (pre-tax). Kept in
  //           `subtotal` too for back-compat.
  boxPrice?: number;
  gstRate: number;
  gstAmount: number;
  // Statutory charges collected at registry (optional).
  stampDutyRate?: number;
  stampDutyAmount?: number;
  registrationRate?: number;
  registrationAmount?: number;
  subtotal: number;
  total: number;
  lineItems: PricingLineItem[];
}

export interface KycDocument {
  // Free-text document name typed at upload (e.g. "Aadhaar Card", "PAN Card").
  // The backend stores it as a free-form doc_type, so this is an open string.
  type: string;
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
  milestoneKey: string | null;        // set on rows a payment plan generated
  percent: number | null;             // while set, the amount follows the booking's price
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
  // The token / booking amount, recorded as a receipt (one per booking) — counted once, never on top of tokenAmount.
  isToken: boolean;
  createdAt: string;
}

export interface BookingRefund {
  id: string;
  bookingId: string;
  grossPaid: number;
  deductionAmount: number;
  refundAmount: number;
  mode: PaymentMode;
  refundedOn: string;
  reference: string | null;
  reason: string | null;
  createdAt: string;
}

export type BookingInvoiceStatus = "draft" | "issued" | "paid" | "refunded" | "void";

export interface BookingInvoice {
  id: string;
  bookingId: string;
  scheduleId: string | null;
  invoiceNumber: string;
  installmentName: string;
  amount: number;
  dueDate: string | null;
  status: BookingInvoiceStatus;
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
  refunds: BookingRefund[];
  step: BookingStep;
  status: BookingStatus;
  kycDocuments: KycDocument[];
  pricingSnapshot: PricingSnapshot | null;
  scheduledDate: string | null;
  possessionChecklist: boolean[] | null;
  cancellationReason: string | null;
  registrationNumber: string | null;
  subRegistrarOffice: string | null;
  // Token / booking amount (Phase C).
  tokenAmount: number | null;
  tokenReceivedOn: string | null;
  tokenMode: PaymentMode | null;
  tokenReference: string | null;
  bookingFormUrl: string | null;
  allotmentLetterUrl: string | null;
  // The payment plan this booking took from its project (null = none / replaced by a manual plan). A milestone
  // with no paymentSchedules row carrying its key is still to be raised.
  paymentPlan: PlanMilestone[] | null;
  createdAt: string;
  updatedAt: string;
  unit?: Pick<
    Unit,
    | "id"
    | "unitNumber"
    | "floor"
    | "unitType"
    | "area"
    | "carpetArea"
    | "builtUpArea"
    | "areaUnit"
    | "basePrice"
    | "status"
    | "flatType"
    | "configuration"
    | "hasPlc"
  > & { towerName: string; projectName: string };
}
