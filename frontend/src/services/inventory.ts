import { apiClient } from "./http";
import type { Project, Unit, UnitStatus } from "../types/realestate";

export const inventoryService = {
  listProjects(): Promise<Project[]> {
    return apiClient.get<Project[]>("/inventory/projects").then((r) => r.data);
  },

  getProject(id: string): Promise<Project> {
    return apiClient.get<Project>(`/inventory/projects/${id}`).then((r) => r.data);
  },

  createProject(payload: Partial<Project>): Promise<Project> {
    return apiClient.post<Project>("/inventory/projects", payload).then((r) => r.data);
  },

  updateUnitStatus(unitId: string, status: UnitStatus): Promise<Unit> {
    return apiClient.patch<Unit>(`/inventory/units/${unitId}/status`, { status }).then((r) => r.data);
  },

  getUnit(unitId: string): Promise<Unit> {
    return apiClient.get<Unit>(`/inventory/units/${unitId}`).then((r) => r.data);
  },
};
