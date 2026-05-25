import { useCallback, useEffect } from "react";

import {
  leadsService,
  type LeadCreatePayload,
  type LeadListQuery,
  type LeadUpdatePayload,
  type StageTransitionPayload
} from "../services/leads";
import type { LeadListResponse } from "../types";
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
  const { data, loading, error, execute } = useAsyncResource(leadsService.list, initialLeadsResponse);

  const refresh = useCallback(async () => {
    await execute(query);
  }, [execute, query]);

  const createLead = useCallback(
    async (payload: LeadCreatePayload) => {
      await leadsService.create(payload);
      await refresh();
    },
    [refresh]
  );

  const updateLead = useCallback(
    async (leadId: string, payload: LeadUpdatePayload) => {
      await leadsService.update(leadId, payload);
      await refresh();
    },
    [refresh]
  );

  const deleteLead = useCallback(
    async (leadId: string) => {
      await leadsService.remove(leadId);
      await refresh();
    },
    [refresh]
  );

  const transitionLead = useCallback(
    async (leadId: string, payload: StageTransitionPayload) => {
      await leadsService.createTransition(leadId, payload);
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
    error,
    refresh,
    createLead,
    updateLead,
    deleteLead,
    transitionLead
  };
}
