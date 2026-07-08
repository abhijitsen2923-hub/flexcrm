import { apiClient } from "./http";
import type { Project, ProjectMedia, Tower, Unit, UnitStatus, UnitType } from "../types/realestate";

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
  created_at: string;
  updated_at: string;
  towers?: ApiTower[];
  media?: ApiProjectMedia[];
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

export interface ProjectCreatePayload {
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
  area: number;
  base_price: number;
  area_unit?: string;
  facing?: string | null;
  unit_prefix?: string | null;
}

export const inventoryService = {
  listProjects(): Promise<Project[]> {
    return apiClient.get<ApiProject[]>("/inventory/projects").then((r) => r.data.map(mapProject));
  },

  getProject(id: string): Promise<Project> {
    return apiClient.get<ApiProject>(`/inventory/projects/${id}`).then((r) => mapProject(r.data));
  },

  createProject(payload: ProjectCreatePayload): Promise<Project> {
    return apiClient.post<ApiProject>("/inventory/projects", payload).then((r) => mapProject(r.data));
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
