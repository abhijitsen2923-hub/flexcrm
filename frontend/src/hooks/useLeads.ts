import { useCallback, useEffect, useMemo } from "react";

import {
  leadsService,
  type LeadCreatePayload,
  type LeadListQuery,
  type LeadUpdatePayload,
  type StageTransitionPayload
} from "../services/leads";
import type { LeadListResponse } from "../types";
import { invalidate } from "./resourceCache";
import { useAsyncResource } from "./useAsyncResource";


const initialLeadsResponse: LeadListResponse = {
  items: [],
  pagination: {
    page: 1,
    page_size: 20,
    total: 0,
    total_pages: 1
  }
};

export function useLeads(query: LeadListQuery = {}) {
  const cacheKey = useMemo(() => `leads:${JSON.stringify(query)}`, [query]);
  const { data, loading, isValidating, slow, error, execute } = useAsyncResource(
    leadsService.list,
    initialLeadsResponse,
    { cacheKey }
  );

  const refresh = useCallback(async () => {
    await execute(query);
  }, [execute, query]);

  // Drop every cached leads view so the next visit (any filter/page) refetches.
  const createLead = useCallback(
    async (payload: LeadCreatePayload) => {
      await leadsService.create(payload);
      invalidate("leads:");
      await refresh();
    },
    [refresh]
  );

  const updateLead = useCallback(
    async (leadId: string, payload: LeadUpdatePayload) => {
      await leadsService.update(leadId, payload);
      invalidate("leads:");
      await refresh();
    },
    [refresh]
  );

  const deleteLead = useCallback(
    async (leadId: string) => {
      await leadsService.remove(leadId);
      invalidate("leads:");
      await refresh();
    },
    [refresh]
  );

  const transitionLead = useCallback(
    async (leadId: string, payload: StageTransitionPayload) => {
      await leadsService.createTransition(leadId, payload);
      invalidate("leads:");
      await refresh();
    },
    [refresh]
  );

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return {
    leads: data.items,
    pagination: data.pagination,
    loading,
    isValidating,
    slow,
    error,
    refresh,
    createLead,
    updateLead,
    deleteLead,
    transitionLead
  };
}
