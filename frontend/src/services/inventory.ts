import { apiClient } from "./http";
import type {
  FloorRiseBasis,
  GarageOption,
  MilestoneReached,
  ParkingType,
  PlanMilestone,
  PricingBasis,
  Project,
  ProjectMedia,
  ProjectPossessionRollup,
  ProjectType,
  Tower,
  TowerLayout,
  Unit,
  UnitStatus,
  UnitType,
} from "../types/realestate";
import { inventoryCounts, type TowerCardPayload } from "../utils/projectInventory";

// The API speaks snake_case and returns no computed inventory counts / media.
// The app models are camelCase with totalUnits/availableUnits/media derived from
// towers→units. Map at this boundary so pages/hooks work with a single shape.
interface ApiUnit {
  id: string;
  project_id: string;
  tower_id: string;
  floor: number;
  unit_number: string;
  unit_type: string;
  area: number | string;
  carpet_area?: number | string | null;
  built_up_area?: number | string | null;
  area_unit: string;
  facing: string | null;
  view: string | null;
  base_price: number | string;
  status: UnitStatus;
  flat_type?: string | null;
  configuration?: string | null;
  has_plc?: boolean;
  updated_at: string;
}

interface ApiTower {
  id: string;
  project_id: string;
  name: string;
  total_floors: number;
  layout?: TowerLayout | null;
  units?: ApiUnit[];
}

interface ApiProjectMedia {
  id: string;
  type: string;
  url: string;
  label: string | null;
}

interface ApiProject {
  id: string;
  name: string;
  builder_name: string;
  location: string;
  city: string;
  rera_number: string | null;
  // Phase B — detail specs (nullable) + default box-price components. Numerics
  // arrive as strings (Decimal) or numbers; coerced in mapProject.
  pin_code?: string | null;
  landmark?: string | null;
  total_towers?: number | null;
  total_floors?: number | null;
  flats_per_floor?: number | null;
  total_garages?: number | null;
  garage_options?: string[] | null;
  rate_a?: number | string | null;
  rate_b?: number | string | null;
  rate_c?: number | string | null;
  parking_cost?: number | string | null;
  legal_fees?: number | string | null;
  overhead_cost?: number | string | null;
  other_charges?: number | string | null;
  sinking_fund?: number | string | null;
  amenities_charges?: number | string | null;
  demand_schedule?: DemandMilestonePayload[] | null;
  project_type?: string | null;
  pricing_basis?: string | null;
  floor_rise_rate?: number | string | null;
  floor_rise_basis?: string | null;
  floor_rise_from?: number | null;
  plc_rate?: number | string | null;
  amenities_rate?: number | string | null;
  parking_prices?: Record<string, number | string> | null;
  payment_plan?: (Omit<PlanMilestone, "percent"> & { percent: number | string })[] | null;
  milestones_reached?: { key: string; tower_id: string | null; reached_on: string }[] | null;
  created_at: string;
  updated_at: string;
  towers?: ApiTower[];
  media?: ApiProjectMedia[];
}

// Decimal columns serialize to strings (or numbers); null stays null.
function numOrNull(v: number | string | null | undefined): number | null {
  return v === null || v === undefined || v === "" ? null : Number(v);
}

interface ApiPossessionUnit {
  unit_id: string;
  unit_number: string;
  tower_name: string | null;
  floor: number;
  unit_status: string;
  booking_id: string | null;
  customer_name: string | null;
  registration_number: string | null;
  registered: boolean;
  possession_done: number;
  possession_total: number;
}

interface ApiPossessionRollup {
  project_id: string;
  project_name: string;
  summary: { total_units: number; booked: number; registered: number; possession_complete: number };
  units: ApiPossessionUnit[];
}

function mapUnit(u: ApiUnit): Unit {
  return {
    id: u.id,
    projectId: u.project_id,
    towerId: u.tower_id,
    floor: u.floor,
    unitNumber: u.unit_number,
    unitType: (u.unit_type as Unit["unitType"]) ?? "residential",
    area: Number(u.area),
    carpetArea: numOrNull(u.carpet_area),
    builtUpArea: numOrNull(u.built_up_area),
    areaUnit: u.area_unit as Unit["areaUnit"],
    facing: u.facing as Unit["facing"],
    view: u.view,
    basePrice: Number(u.base_price),
    status: u.status,
    flatType: u.flat_type ?? null,
    configuration: u.configuration ?? null,
    hasPlc: Boolean(u.has_plc),
    updatedAt: u.updated_at,
  };
}

function mapParkingPrices(raw: Record<string, number | string> | null | undefined): Project["parkingPrices"] {
  if (!raw) return null;
  const out: Partial<Record<ParkingType, number>> = {};
  for (const [type, price] of Object.entries(raw)) out[type as ParkingType] = Number(price);
  return out;
}

export function mapPlan(raw: ApiProject["payment_plan"]): PlanMilestone[] | null {
  if (!raw) return null;
  return raw.map((m) => ({
    key: m.key,
    label: m.label,
    percent: Number(m.percent),
    due_on: m.due_on,
    days: m.days ?? null,
    due_date: m.due_date ?? null,
  }));
}

function mapTower(t: ApiTower): Tower {
  return {
    id: t.id,
    projectId: t.project_id,
    name: t.name,
    totalFloors: t.total_floors,
    layout: t.layout ?? null,
    units: (t.units ?? []).map(mapUnit),
  };
}

function mapProject(p: ApiProject): Project {
  const towers = (p.towers ?? []).map(mapTower);
  const counts = inventoryCounts(towers);
  return {
    id: p.id,
    name: p.name,
    builderName: p.builder_name,
    location: p.location,
    city: p.city,
    reraNumber: p.rera_number,
    pinCode: p.pin_code ?? null,
    landmark: p.landmark ?? null,
    totalTowers: p.total_towers ?? null,
    totalFloors: p.total_floors ?? null,
    flatsPerFloor: p.flats_per_floor ?? null,
    totalGarages: p.total_garages ?? null,
    garageOptions: (p.garage_options as GarageOption[] | null | undefined) ?? null,
    rateA: numOrNull(p.rate_a),
    rateB: numOrNull(p.rate_b),
    rateC: numOrNull(p.rate_c),
    parkingCost: numOrNull(p.parking_cost),
    legalFees: numOrNull(p.legal_fees),
    overheadCost: numOrNull(p.overhead_cost),
    otherCharges: numOrNull(p.other_charges),
    sinkingFund: numOrNull(p.sinking_fund),
    amenitiesCharges: numOrNull(p.amenities_charges),
    demandSchedule: p.demand_schedule ?? null,
    projectType: (p.project_type as ProjectType | null | undefined) ?? null,
    pricingBasis: (p.pricing_basis as PricingBasis | null | undefined) ?? null,
    floorRiseRate: numOrNull(p.floor_rise_rate),
    floorRiseBasis: (p.floor_rise_basis as FloorRiseBasis | null | undefined) ?? null,
    floorRiseFrom: p.floor_rise_from ?? null,
    plcRate: numOrNull(p.plc_rate),
    amenitiesRate: numOrNull(p.amenities_rate),
    parkingPrices: mapParkingPrices(p.parking_prices),
    paymentPlan: mapPlan(p.payment_plan),
    milestonesReached: p.milestones_reached
      ? p.milestones_reached.map(
          (r): MilestoneReached => ({ key: r.key, towerId: r.tower_id ?? null, reachedOn: r.reached_on })
        )
      : null,
    towers,
    media: (p.media ?? []).map((m) => ({
      id: m.id,
      type: m.type as ProjectMedia["type"],
      url: m.url,
      label: m.label,
    })),
    totalUnits: counts.units,
    availableUnits: counts.unitsAvailable,
    totalParking: counts.parking,
    availableParking: counts.parkingAvailable,
    createdAt: p.created_at,
    updatedAt: p.updated_at,
  };
}

// Phase-B detail + default box-price fields (snake_case, all optional). Shared by
// the create and update payloads so both stay in sync with the backend schema.
export interface DemandMilestonePayload {
  label: string;
  percent: number;
  due_date: string; // YYYY-MM-DD
}

export interface ProjectDetailsPayload {
  pin_code?: string | null;
  landmark?: string | null;
  total_towers?: number | null;
  total_floors?: number | null;
  flats_per_floor?: number | null;
  total_garages?: number | null;
  garage_options?: GarageOption[] | null;
  rate_a?: number | null;
  rate_b?: number | null;
  rate_c?: number | null;
  parking_cost?: number | null;
  legal_fees?: number | null;
  overhead_cost?: number | null;
  other_charges?: number | null;
  sinking_fund?: number | null;
  amenities_charges?: number | null;
  demand_schedule?: DemandMilestonePayload[] | null;
  // --- Add Project wizard ---
  project_type?: ProjectType | null;
  pricing_basis?: PricingBasis | null;
  floor_rise_rate?: number | null;
  floor_rise_basis?: FloorRiseBasis | null;
  floor_rise_from?: number | null;
  plc_rate?: number | null;
  amenities_rate?: number | null;
  parking_prices?: Partial<Record<ParkingType, number>> | null;
  // Writing a payment_plan clears the legacy demand_schedule on the server.
  payment_plan?: PlanMilestone[] | null;
}

export interface ProjectCreatePayload extends ProjectDetailsPayload {
  name: string;
  builder_name: string;
  location: string;
  city: string;
  rera_number?: string | null;
}

export interface TowerCreatePayload {
  name: string;
  total_floors: number;
}

export interface UnitBatchPayload {
  unit_type: UnitType;
  floors: { floor: number; count: number }[];
  area: number;                       // super built-up (saleable) — required
  carpet_area?: number | null;
  built_up_area?: number | null;
  base_price: number;
  area_unit?: string;
  facing?: string | null;
  unit_prefix?: string | null;
}

export interface ProjectTowerPayload {
  name: string;
  total_floors: number;
  unit_specs?: UnitBatchPayload[]; // several unit types per tower, each its own batch
  units?: UnitBatchPayload | null; // legacy single-spec (still accepted)
  // The wizard's tower: flat types + shops/godowns. When sent, the server builds (and prices) the units from it
  // and ignores unit_specs / units.
  layout?: TowerLayout | null;
}

// A wizard tower card on Edit: an existing tower (tower_id) or a new one.
export interface ProjectTowerSyncPayload extends ProjectTowerPayload {
  tower_id?: string | null;
}

// Parking spots per type (MLP / CP / IP / OP / DP), numbered per type across the whole project (CP01 …).
export type ParkingCountsPayload = Partial<Record<ParkingType, number>>;

export interface ProjectFullPayload extends ProjectCreatePayload {
  towers: ProjectTowerPayload[];
  parking?: ParkingCountsPayload;
}

// Edit project → Save: the page's tower cards (existing ones carry tower_id) + parking counts. The server adds
// only what's missing — never changes or removes existing units.
export interface ProjectInventoryPayload {
  towers: (TowerCardPayload | ProjectTowerSyncPayload)[];
  parking: ParkingCountsPayload;
}

// Preview for an existing project: the page's towers + parking + its (unsaved) pricing.
export interface ProjectInventoryPreviewPayload extends ProjectInventoryPayload {
  pricing_basis?: PricingBasis | null;
  rate_a?: number | null;
  rate_b?: number | null;
  rate_c?: number | null;
  parking_prices?: Partial<Record<ParkingType, number>> | null;
}

// What Save would build (same planner as Save, nothing written).
export interface PlannedUnit {
  floor: number;
  unitNumber: string;
  unitType: UnitType;
  flatType: string | null;
  configuration: string | null;
  area: number;
  carpetArea: number | null;
  builtUpArea: number | null;
  basePrice: number | null;
  hasPlc: boolean;
}

export interface InventoryPreview {
  towers: { towerId: string | null; name: string; existingUnits: number; newUnits: PlannedUnit[] }[];
  parking: { parkingType: ParkingType; existing: number; newNumbers: string[]; price: number | null }[];
  notes: string[];
  newUnits: number;
  newParking: number;
}

interface ApiInventoryPreview {
  towers: {
    tower_id: string | null;
    name: string;
    existing_units: number;
    new_units: {
      floor: number;
      unit_number: string;
      unit_type: string;
      flat_type: string | null;
      configuration: string | null;
      area: number | string;
      carpet_area: number | string | null;
      built_up_area: number | string | null;
      base_price: number | string | null;
      has_plc: boolean;
    }[];
  }[];
  parking: { parking_type: ParkingType; existing: number; new_numbers: string[]; price: number | string | null }[];
  notes: string[];
  new_units: number;
  new_parking: number;
}

function mapPreview(r: ApiInventoryPreview): InventoryPreview {
  return {
    towers: r.towers.map((t) => ({
      towerId: t.tower_id,
      name: t.name,
      existingUnits: t.existing_units,
      newUnits: t.new_units.map((u) => ({
        floor: u.floor,
        unitNumber: u.unit_number,
        unitType: u.unit_type as UnitType,
        flatType: u.flat_type,
        configuration: u.configuration,
        area: Number(u.area),
        carpetArea: numOrNull(u.carpet_area),
        builtUpArea: numOrNull(u.built_up_area),
        basePrice: numOrNull(u.base_price),
        hasPlc: u.has_plc,
      })),
    })),
    parking: r.parking.map((p) => ({
      parkingType: p.parking_type,
      existing: p.existing,
      newNumbers: p.new_numbers,
      price: numOrNull(p.price),
    })),
    notes: r.notes,
    newUnits: r.new_units,
    newParking: r.new_parking,
  };
}

export interface MilestoneReachedResult {
  raised: number;
  alreadyRaised: number;
  amount: number;
  project: Project;
}

export interface MilestoneUndoResult {
  removed: number;
  kept: number;
  project: Project;
}

export interface ProjectInventoryResult {
  project: Project;
  created: { towers: number; units: number; parking: number };
  notes: string[];
}

export interface ProjectUpdatePayload extends ProjectDetailsPayload {
  name?: string;
  builder_name?: string;
  location?: string;
  city?: string;
  rera_number?: string | null;
}

export interface TowerUpdatePayload {
  name?: string;
  total_floors?: number;
}

export interface UnitUpdatePayload {
  unit_number?: string;
  unit_type?: UnitType;
  area?: number;
  carpet_area?: number | null;
  built_up_area?: number | null;
  area_unit?: string;
  facing?: string | null;
  view?: string | null;
  base_price?: number;
  flat_type?: string | null;
  configuration?: string | null;
  has_plc?: boolean;
}

export const inventoryService = {
  listProjects(): Promise<Project[]> {
    return apiClient.get<ApiProject[]>("/inventory/projects").then((r) => r.data.map(mapProject));
  },

  getProject(id: string): Promise<Project> {
    return apiClient.get<ApiProject>(`/inventory/projects/${id}`).then((r) => mapProject(r.data));
  },

  // Project-wise possession & registration rollup (Phase C3).
  getProjectPossession(id: string): Promise<ProjectPossessionRollup> {
    return apiClient.get<ApiPossessionRollup>(`/inventory/projects/${id}/possession`).then((r) => ({
      projectId: r.data.project_id,
      projectName: r.data.project_name,
      summary: {
        totalUnits: r.data.summary.total_units,
        booked: r.data.summary.booked,
        registered: r.data.summary.registered,
        possessionComplete: r.data.summary.possession_complete,
      },
      units: r.data.units.map((u) => ({
        unitId: u.unit_id,
        unitNumber: u.unit_number,
        towerName: u.tower_name,
        floor: u.floor,
        unitStatus: u.unit_status as UnitStatus,
        bookingId: u.booking_id,
        customerName: u.customer_name,
        registrationNumber: u.registration_number,
        registered: u.registered,
        possessionDone: u.possession_done,
        possessionTotal: u.possession_total,
      })),
    }));
  },

  createProject(payload: ProjectCreatePayload): Promise<Project> {
    return apiClient.post<ApiProject>("/inventory/projects", payload).then((r) => mapProject(r.data));
  },

  // Create a project + its towers + each tower's units in one atomic call.
  createProjectFull(payload: ProjectFullPayload): Promise<Project> {
    return apiClient.post<ApiProject>("/inventory/projects/full", payload).then((r) => mapProject(r.data));
  },

  syncProjectInventory(projectId: string, payload: ProjectInventoryPayload): Promise<ProjectInventoryResult> {
    return apiClient
      .post<{ project: ApiProject; created: ProjectInventoryResult["created"]; notes: string[] }>(
        `/inventory/projects/${projectId}/inventory`,
        payload
      )
      .then((r) => ({ project: mapProject(r.data.project), created: r.data.created, notes: r.data.notes }));
  },

  // The wizard's preview step: what Create would build (nothing is written).
  previewNewProject(payload: ProjectFullPayload): Promise<InventoryPreview> {
    return apiClient
      .post<ApiInventoryPreview>("/inventory/projects/full/preview", payload)
      .then((r) => mapPreview(r.data));
  },

  // The wizard's preview step on Edit: what Save would add to this project (nothing is written).
  previewProjectInventory(projectId: string, payload: ProjectInventoryPreviewPayload): Promise<InventoryPreview> {
    return apiClient
      .post<ApiInventoryPreview>(`/inventory/projects/${projectId}/inventory/preview`, payload)
      .then((r) => mapPreview(r.data));
  },

  // Mark an event milestone (stage done / possession / registration) reached — raises its demand on every live
  // booking holding it, in the chosen towers (none = the whole project).
  markMilestoneReached(
    projectId: string,
    key: string,
    payload: { reached_on: string; tower_ids?: string[] | null }
  ): Promise<MilestoneReachedResult> {
    return apiClient
      .post<{ raised: number; already_raised: number; amount: number | string; project: ApiProject }>(
        `/inventory/projects/${projectId}/payment-plan/${encodeURIComponent(key)}/reached`,
        payload
      )
      .then((r) => ({
        raised: r.data.raised,
        alreadyRaised: r.data.already_raised,
        amount: Number(r.data.amount),
        project: mapProject(r.data.project),
      }));
  },

  // Undo a "reached" mark (towerId null = the whole-project mark): removes the demands it raised that have no
  // payment or invoice yet.
  undoMilestoneReached(projectId: string, key: string, towerId: string | null): Promise<MilestoneUndoResult> {
    return apiClient
      .delete<{ removed: number; kept: number; project: ApiProject }>(
        `/inventory/projects/${projectId}/payment-plan/${encodeURIComponent(key)}/reached`,
        { params: towerId ? { tower_id: towerId } : {} }
      )
      .then((r) => ({ removed: r.data.removed, kept: r.data.kept, project: mapProject(r.data.project) }));
  },

  createTower(projectId: string, payload: TowerCreatePayload): Promise<Tower> {
    return apiClient
      .post<ApiTower>(`/inventory/projects/${projectId}/towers`, payload)
      .then((r) => mapTower(r.data));
  },

  createUnitsBatch(towerId: string, payload: UnitBatchPayload): Promise<Unit[]> {
    return apiClient
      .post<ApiUnit[]>(`/inventory/towers/${towerId}/units/batch`, payload)
      .then((r) => r.data.map(mapUnit));
  },

  updateUnitStatus(unitId: string, status: UnitStatus): Promise<Unit> {
    return apiClient
      .patch<ApiUnit>(`/inventory/units/${unitId}/status`, { status })
      .then((r) => mapUnit(r.data));
  },

  updateProject(id: string, payload: ProjectUpdatePayload): Promise<Project> {
    return apiClient.patch<ApiProject>(`/inventory/projects/${id}`, payload).then((r) => mapProject(r.data));
  },

  archiveProject(id: string): Promise<void> {
    return apiClient.delete(`/inventory/projects/${id}`).then(() => undefined);
  },

  updateTower(id: string, payload: TowerUpdatePayload): Promise<Tower> {
    return apiClient.patch<ApiTower>(`/inventory/towers/${id}`, payload).then((r) => mapTower(r.data));
  },

  archiveTower(id: string): Promise<void> {
    return apiClient.delete(`/inventory/towers/${id}`).then(() => undefined);
  },

  updateUnit(id: string, payload: UnitUpdatePayload): Promise<Unit> {
    return apiClient.patch<ApiUnit>(`/inventory/units/${id}`, payload).then((r) => mapUnit(r.data));
  },

  archiveUnit(id: string): Promise<void> {
    return apiClient.delete(`/inventory/units/${id}`).then(() => undefined);
  },

  getUnit(unitId: string): Promise<Unit> {
    return apiClient.get<ApiUnit>(`/inventory/units/${unitId}`).then((r) => mapUnit(r.data));
  },

  uploadProjectMedia(
    projectId: string,
    file: File,
    mediaType: ProjectMedia["type"],
    label?: string | null
  ): Promise<ProjectMedia> {
    const form = new FormData();
    form.append("file", file);
    form.append("media_type", mediaType);
    if (label) form.append("label", label);
    return apiClient
      // Let axios infer the multipart boundary (overrides the JSON default).
      .post<ApiProjectMedia>(`/inventory/projects/${projectId}/media`, form, {
        headers: { "Content-Type": "multipart/form-data" },
      })
      .then((r) => ({
        id: r.data.id,
        type: r.data.type as ProjectMedia["type"],
        url: r.data.url,
        label: r.data.label,
      }));
  },

  deleteProjectMedia(mediaId: string): Promise<void> {
    return apiClient.delete(`/inventory/projects/media/${mediaId}`).then(() => undefined);
  },
};
