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

  // Idempotent repair of tenant schemas whose enum columns are tenant-local
  // shadows of the public enum types (older tenants). Returns a per-tenant report.
  async repairTenantEnums(dryRun = false): Promise<{ dry_run: boolean; results: TenantRepairResult[] }> {
    const { data } = await apiClient.post("/admin/tenant-enums/repair", null, {
      params: { dry_run: dryRun },
    });
    return data;
  },

  // Run tenant Alembic migrations (upgrade head) on every existing tenant schema.
  // Idempotent — applies newly deployed tenant columns/tables to existing tenants.
  async upgradeTenantSchemas(): Promise<{ results: TenantUpgradeResult[] }> {
    const { data } = await apiClient.post("/admin/tenant-schemas/upgrade");
    return data;
  },
};

export interface TenantUpgradeResult {
  org?: string;
  schema?: string;
  status?: string;
  skipped?: string;
  error?: string;
}

export interface TenantRepairResult {
  org?: string;
  schema?: string;
  repaired?: string[];
  dropped_types?: string[];
  skipped?: string[] | string;
  error?: string;
}
