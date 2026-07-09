import { apiClient } from "./http";
import type { SiteVisit, SiteVisitFeedback, SiteVisitStatus } from "../types/realestate";

export interface CreateSiteVisitPayload {
  leadId?: string | null;
  projectId: string;
  scheduledAt: string;
  assignedToId?: string | null;
  notes?: string | null;
}

export interface UpdateSiteVisitPayload {
  attended?: boolean;
  feedback?: SiteVisitFeedback | null;
  notes?: string;
  scheduledAt?: string;
  assignedToId?: string | null;
  status?: SiteVisitStatus;
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
  status?: SiteVisitStatus;
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
    status: v.status ?? "scheduled",
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
        lead_id: payload.leadId ?? null,
        project_id: payload.projectId,
        scheduled_at: payload.scheduledAt,
        assigned_to_id: payload.assignedToId ?? null,
        notes: payload.notes ?? null,
      })
      .then((r) => mapVisit(r.data));
  },

  update(id: string, patch: UpdateSiteVisitPayload): Promise<SiteVisit> {
    // Map the camelCase reschedule/reassign fields to the API's snake_case.
    const body: Record<string, unknown> = {};
    if (patch.attended !== undefined) body.attended = patch.attended;
    if (patch.feedback !== undefined) body.feedback = patch.feedback;
    if (patch.notes !== undefined) body.notes = patch.notes;
    if (patch.scheduledAt !== undefined) body.scheduled_at = patch.scheduledAt;
    if (patch.assignedToId !== undefined) body.assigned_to_id = patch.assignedToId;
    if (patch.status !== undefined) body.status = patch.status;
    return apiClient.patch<ApiSiteVisit>(`/site-visits/${id}`, body).then((r) => mapVisit(r.data));
  },
};
