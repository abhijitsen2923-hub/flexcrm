import { useCallback, useEffect } from "react";

import { dealsService, type DealListQuery, type DealPayload } from "../services/deals";
import type { DealListResponse } from "../types";
import { useAsyncResource } from "./useAsyncResource";


const initialDealsResponse: DealListResponse = {
  items: [],
  pagination: {
    page: 1,
    page_size: 20,
    total: 0,
    total_pages: 1
  }
};

export function useDeals(query: DealListQuery = {}) {
  const { data, loading, error, execute } = useAsyncResource(dealsService.list, initialDealsResponse);

  const refresh = useCallback(async () => {
    await execute(query);
  }, [execute, query]);

  const createDeal = useCallback(
    async (payload: DealPayload) => {
      await dealsService.create(payload);
      await refresh();
    },
    [refresh]
  );

  const updateDeal = useCallback(
    async (dealId: string, payload: Partial<DealPayload>) => {
      await dealsService.update(dealId, payload);
      await refresh();
    },
    [refresh]
  );

  const deleteDeal = useCallback(
    async (dealId: string) => {
      await dealsService.remove(dealId);
      await refresh();
    },
    [refresh]
  );

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return {
    deals: data.items,
    pagination: data.pagination,
    loading,
    error,
    refresh,
    createDeal,
    updateDeal,
    deleteDeal
  };
}
