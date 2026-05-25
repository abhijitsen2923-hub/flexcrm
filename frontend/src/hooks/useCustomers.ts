import { useCallback, useEffect } from "react";

import { customersService, type CustomerListQuery, type CustomerPayload } from "../services/customers";
import type { CustomerListResponse } from "../types";
import { useAsyncResource } from "./useAsyncResource";


const initialCustomersResponse: CustomerListResponse = {
  items: [],
  pagination: {
    page: 1,
    page_size: 20,
    total: 0,
    total_pages: 1
  }
};

export function useCustomers(query: CustomerListQuery = {}) {
  const { data, loading, error, execute } = useAsyncResource(customersService.list, initialCustomersResponse);

  const refresh = useCallback(async () => {
    await execute(query);
  }, [execute, query]);

  const createCustomer = useCallback(
    async (payload: CustomerPayload) => {
      await customersService.create(payload);
      await refresh();
    },
    [refresh]
  );

  const updateCustomer = useCallback(
    async (customerId: string, payload: Partial<CustomerPayload>) => {
      await customersService.update(customerId, payload);
      await refresh();
    },
    [refresh]
  );

  const deleteCustomer = useCallback(
    async (customerId: string) => {
      await customersService.remove(customerId);
      await refresh();
    },
    [refresh]
  );

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return {
    customers: data.items,
    pagination: data.pagination,
    loading,
    error,
    refresh,
    createCustomer,
    updateCustomer,
    deleteCustomer
  };
}
