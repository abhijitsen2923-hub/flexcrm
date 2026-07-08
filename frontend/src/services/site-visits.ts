import { apiClient } from "./http";
import type { SiteVisit, SiteVisitFeedback } from "../types/realestate";

export interface CreateSiteVisitPayload {
  leadId: string;
  projectId: string;
  scheduledAt: string;
  assignedToId?: string | null;
  notes?: string | null;
}

// The API is snake_case and returns enriched project/lead. Map at the boundary.
interface ApiSiteVisit {
  id: string;
  lead_id: string | null;
  project_id: string;
  scheduled_at: string;
  assigned_to_id: string | null;
  feedback: SiteVisitFeedback | null;
  attended: boolean | null;
  notes: string | null;
  created_at: string;
  project?: { id: string; name: string } | null;
  lead?: { id: string; lead_number: number; contact_name: string; contact_phone: string | null } | null;
}

function mapVisit(v: ApiSiteVisit): SiteVisit {
  return {
    id: v.id,
    leadId: v.lead_id ?? "",
    projectId: v.project_id,
    scheduledAt: v.scheduled_at,
    assignedToId: v.assigned_to_id,
    feedback: v.feedback,
    attended: v.attended,
    notes: v.notes,
    createdAt: v.created_at,
    project: v.project ? { id: v.project.id, name: v.project.name } : null,
    lead: v.lead
      ? {
          id: v.lead.id,
          leadNumber: v.lead.lead_number,
          contactName: v.lead.contact_name,
          contactPhone: v.lead.contact_phone ?? null,
        }
      : null,
  };
}

export const siteVisitsService = {
  list(params?: { projectId?: string; leadId?: string }): Promise<SiteVisit[]> {
    return apiClient
      .get<ApiSiteVisit[]>("/site-visits", {
        params: { project_id: params?.projectId, lead_id: params?.leadId },
      })
      .then((r) => r.data.map(mapVisit));
  },

  create(payload: CreateSiteVisitPayload): Promise<SiteVisit> {
    return apiClient
      .post<ApiSiteVisit>("/site-visits", {
        lead_id: payload.leadId,
        project_id: payload.projectId,
        scheduled_at: payload.scheduledAt,
        assigned_to_id: payload.assignedToId ?? null,
        notes: payload.notes ?? null,
      })
      .then((r) => mapVisit(r.data));
  },

  update(
    id: string,
    patch: { attended?: boolean; feedback?: SiteVisitFeedback | null; notes?: string }
  ): Promise<SiteVisit> {
    return apiClient.patch<ApiSiteVisit>(`/site-visits/${id}`, patch).then((r) => mapVisit(r.data));
  },
};
