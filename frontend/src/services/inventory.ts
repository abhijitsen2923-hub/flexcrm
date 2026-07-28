import { apiClient } from "./http";
import type {
  GarageOption,
  Project,
  ProjectMedia,
  ProjectPossessionRollup,
  Tower,
  Unit,
  UnitStatus,
  UnitType,
} from "../types/realestate";

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
  updated_at: string;
}

interface ApiTower {
  id: string;
  project_id: string;
  name: string;
  total_floors: number;
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
    updatedAt: u.updated_at,
  };
}

function mapTower(t: ApiTower): Tower {
  return {
    id: t.id,
    projectId: t.project_id,
    name: t.name,
    totalFloors: t.total_floors,
    units: (t.units ?? []).map(mapUnit),
  };
}

function mapProject(p: ApiProject): Project {
  const towers = (p.towers ?? []).map(mapTower);
  const allUnits = towers.flatMap((t) => t.units);
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
    towers,
    media: (p.media ?? []).map((m) => ({
      id: m.id,
      type: m.type as ProjectMedia["type"],
      url: m.url,
      label: m.label,
    })),
    totalUnits: allUnits.length,
    availableUnits: allUnits.filter((u) => u.status === "available").length,
    createdAt: p.created_at,
    updatedAt: p.updated_at,
  };
}

// Phase-B detail + default box-price fields (snake_case, all optional). Shared by
// the create and update payloads so both stay in sync with the backend schema.
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
  units?: UnitBatchPayload | null;
}

export interface ProjectFullPayload extends ProjectCreatePayload {
  towers: ProjectTowerPayload[];
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
