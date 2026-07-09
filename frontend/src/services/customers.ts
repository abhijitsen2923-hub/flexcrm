import type { ApiMessageResponse, Customer, CustomerListResponse, PaginationQuery, SearchSortQuery } from "../types";
import { buildQueryString } from "../utils/queryString";
import { apiClient } from "./http";


export interface CustomerListQuery extends PaginationQuery, SearchSortQuery {
  status?: string;
  source?: string;
  created_by_id?: string;
}

export interface CustomerPayload {
  company_name: string;
  contact_name: string;
  email?: string | null;
  phone?: string | null;
  address?: string | null;
  source?: string | null;
  status?: string;
}

export const customersService = {
  async list(query: CustomerListQuery = {}): Promise<CustomerListResponse> {
    const { data } = await apiClient.get<CustomerListResponse>(`/customers${buildQueryString(query)}`);
    return data;
  },

  async get(customerId: string): Promise<Customer> {
    const { data } = await apiClient.get<Customer>(`/customers/${customerId}`);
    return data;
  },

  async create(payload: CustomerPayload): Promise<Customer> {
    const { data } = await apiClient.post<Customer>("/customers", payload);
    return data;
  },

  async update(customerId: string, payload: Partial<CustomerPayload>): Promise<Customer> {
    const { data } = await apiClient.put<Customer>(`/customers/${customerId}`, payload);
    return data;
  },

  async remove(customerId: string): Promise<ApiMessageResponse> {
    const { data } = await apiClient.delete<ApiMessageResponse>(`/customers/${customerId}`);
    return data;
  },

  // Provision a buyer self-service portal login; returns temp credentials to share.
  async grantPortalAccess(customerId: string): Promise<{ email: string; temporary_password: string }> {
    const { data } = await apiClient.post<{ email: string; temporary_password: string }>(
      `/customers/${customerId}/portal-access`
    );
    return data;
  }
};
