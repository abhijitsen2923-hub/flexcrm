import type { Organization } from "../types";
import { apiClient } from "./http";


export const organizationsService = {
  async me(): Promise<Organization> {
    const { data } = await apiClient.get<Organization>("/organizations/me");
    return data;
  },
  async updateMe(payload: Partial<Pick<Organization, "name" | "plan" | "features">>): Promise<Organization> {
    const { data } = await apiClient.patch<Organization>("/organizations/me", payload);
    return data;
  }
};
