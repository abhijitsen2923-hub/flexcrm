import { apiClient } from "./http";
import type { SiteVisit, SiteVisitFeedback } from "../types/realestate";

export interface CreateSiteVisitPayload {
  leadId: string;
  projectId: string;
  scheduledAt: string;
  assignedToId?: string | null;
  notes?: string | null;
}

export const siteVisitsService = {
  list(params?: { projectId?: string; leadId?: string; date?: string }): Promise<SiteVisit[]> {
    return apiClient.get<SiteVisit[]>("/site-visits", { params }).then((r) => r.data);
  },

  create(payload: CreateSiteVisitPayload): Promise<SiteVisit> {
    return apiClient.post<SiteVisit>("/site-visits", payload).then((r) => r.data);
  },

  update(id: string, patch: { attended?: boolean; feedback?: SiteVisitFeedback | null; notes?: string }): Promise<SiteVisit> {
    return apiClient.patch<SiteVisit>(`/site-visits/${id}`, patch).then((r) => r.data);
  },
};
