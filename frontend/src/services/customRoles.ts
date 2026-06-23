import type { PermissionCode } from "../types";
import { apiClient } from "./http";

export interface CustomRole {
  id: string;
  name: string;
  description: string | null;
  permissions: PermissionCode[];
  is_active: boolean;
  assigned_user_count: number;
  created_at: string;
  updated_at: string;
}

export interface CreateCustomRolePayload {
  name: string;
  description?: string | null;
  permissions: PermissionCode[];
}

export interface UpdateCustomRolePayload {
  name?: string;
  description?: string | null;
  permissions?: PermissionCode[];
  is_active?: boolean;
}

export const customRolesService = {
  async list(): Promise<CustomRole[]> {
    const { data } = await apiClient.get<CustomRole[]>("/custom-roles");
    return data;
  },

  async get(id: string): Promise<CustomRole> {
    const { data } = await apiClient.get<CustomRole>(`/custom-roles/${id}`);
    return data;
  },

  async create(payload: CreateCustomRolePayload): Promise<CustomRole> {
    const { data } = await apiClient.post<CustomRole>("/custom-roles", payload);
    return data;
  },

  async update(id: string, payload: UpdateCustomRolePayload): Promise<CustomRole> {
    const { data } = await apiClient.put<CustomRole>(`/custom-roles/${id}`, payload);
    return data;
  },

  async delete(id: string): Promise<void> {
    await apiClient.delete(`/custom-roles/${id}`);
  },

  async assign(userId: string, customRoleId: string): Promise<{ message: string }> {
    const { data } = await apiClient.post<{ message: string }>(
      `/users/${userId}/custom-role`,
      { custom_role_id: customRoleId },
    );
    return data;
  },

  async unassign(userId: string, newRole: string): Promise<{ message: string }> {
    const { data } = await apiClient.delete<{ message: string }>(
      `/users/${userId}/custom-role`,
      { data: { new_role: newRole } },
    );
    return data;
  },
};
