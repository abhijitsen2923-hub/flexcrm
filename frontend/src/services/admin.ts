import type { ModuleKey, Organization } from "../types";
import { apiClient } from "./http";


export const adminService = {
  async listOrganizations(): Promise<Organization[]> {
    const { data } = await apiClient.get<Organization[]>("/admin/organizations");
    return data;
  },

  async updateOrgModules(
    orgId: string,
    modules: Partial<Record<ModuleKey, boolean>>,
  ): Promise<Organization> {
    const { data } = await apiClient.patch<Organization>(
      `/admin/organizations/${orgId}/modules`,
      { modules },
    );
    return data;
  },
};
