import type { ApiMessageResponse, GrantedPermission, UserPermissions } from "../types";
import { apiClient } from "./http";


export const permissionsService = {
  /** Caller's own effective permission set — used to refresh sidebar/buttons
   * after an admin grants something mid-session. */
  async me(): Promise<UserPermissions> {
    const { data } = await apiClient.get<UserPermissions>("/me/permissions");
    return data;
  },

  /** Admin view of one user's role defaults, explicit grants, and effective set. */
  async getForUser(userId: string): Promise<UserPermissions> {
    const { data } = await apiClient.get<UserPermissions>(`/users/${userId}/permissions`);
    return data;
  },

  async grant(userId: string, permission_code: string): Promise<GrantedPermission> {
    const { data } = await apiClient.post<GrantedPermission>(
      `/users/${userId}/permissions`,
      { permission_code },
    );
    return data;
  },

  async revoke(userId: string, permissionCode: string): Promise<ApiMessageResponse> {
    const { data } = await apiClient.delete<ApiMessageResponse>(
      `/users/${userId}/permissions/${permissionCode}`,
    );
    return data;
  },
};
