import type { ModuleKey, Organization } from "../types";
import { apiClient } from "./http";


export const adminService = {
  async listOrganizations(includeArchived = false): Promise<Organization[]> {
    const { data } = await apiClient.get<Organization[]>("/admin/organizations", {
      params: { include_archived: includeArchived },
    });
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

  async setOrgActive(orgId: string, isActive: boolean): Promise<Organization> {
    const { data } = await apiClient.patch<Organization>(
      `/admin/organizations/${orgId}/status`,
      { is_active: isActive },
    );
    return data;
  },

  async archiveOrganization(orgId: string): Promise<Organization> {
    const { data } = await apiClient.delete<Organization>(`/admin/organizations/${orgId}`);
    return data;
  },

  async restoreOrganization(orgId: string): Promise<Organization> {
    const { data } = await apiClient.post<Organization>(
      `/admin/organizations/${orgId}/restore`,
    );
    return data;
  },

  async purgeOrganization(orgId: string): Promise<void> {
    await apiClient.delete(`/admin/organizations/${orgId}/permanent`);
  },
};
