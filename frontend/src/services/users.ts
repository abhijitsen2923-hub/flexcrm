import type { ApiMessageResponse, PaginationQuery, SearchSortQuery, User } from "../types";
import type { PaginatedResponse } from "../types/common";
import { buildQueryString } from "../utils/queryString";
import { apiClient } from "./http";


export interface UserListQuery extends PaginationQuery, SearchSortQuery {
  role?: string;
  status?: string;
}

export interface UserPayload {
  first_name: string;
  last_name: string;
  email: string;
  password: string;
  role: string;
  phone?: string | null;
  status?: string;
  custom_role_id?: string | null;
}

export const usersService = {
  async list(query: UserListQuery = {}): Promise<PaginatedResponse<User>> {
    const { data } = await apiClient.get<PaginatedResponse<User>>(`/users${buildQueryString(query)}`);
    return data;
  },

  async get(userId: string): Promise<User> {
    const { data } = await apiClient.get<User>(`/users/${userId}`);
    return data;
  },

  async create(payload: UserPayload): Promise<User> {
    const { data } = await apiClient.post<User>("/users", payload);
    return data;
  },

  async update(userId: string, payload: Partial<UserPayload>): Promise<User> {
    const { data } = await apiClient.put<User>(`/users/${userId}`, payload);
    return data;
  },

  async remove(userId: string): Promise<ApiMessageResponse> {
    const { data } = await apiClient.delete<ApiMessageResponse>(`/users/${userId}`);
    return data;
  }
};
