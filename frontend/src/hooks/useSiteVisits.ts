import { useCallback, useEffect, useState } from "react";
import { siteVisitsService, type CreateSiteVisitPayload } from "../services/site-visits";
import type { SiteVisit, SiteVisitFeedback } from "../types/realestate";

export function useSiteVisits(filters?: { projectId?: string; leadId?: string; date?: string }) {
  const [visits, setVisits] = useState<SiteVisit[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await siteVisitsService.list(filters);
      setVisits(data);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, [filters?.projectId, filters?.leadId, filters?.date]);

  useEffect(() => { refresh(); }, [refresh]);

  const schedule = useCallback(async (payload: CreateSiteVisitPayload) => {
    const created = await siteVisitsService.create(payload);
    setVisits((prev) => [created, ...prev]);
    return created;
  }, []);

  const updateFeedback = useCallback(
    async (id: string, patch: { attended?: boolean; feedback?: SiteVisitFeedback | null; notes?: string }) => {
      const updated = await siteVisitsService.update(id, patch);
      setVisits((prev) => prev.map((v) => (v.id === id ? updated : v)));
      return updated;
    },
    []
  );

  return { visits, loading, error, refresh, schedule, updateFeedback };
}
