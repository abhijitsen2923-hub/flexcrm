import { apiClient } from "./http";

// The tenant's own campaign list (backend /campaigns). Each workspace has its own — nothing is shared or
// built in. Reading needs LEAD_VIEW; every change needs CAMPAIGN_MANAGE.

export type CampaignSource = "existing" | "manual" | "import" | "sheet" | "meta" | "integration";

export interface CampaignOption {
  id: string;
  name: string;
  is_active: boolean;
  needs_review: boolean;
}

export interface CampaignAlias {
  id: string;
  alias: string;
  kind: "merge" | "rename";
  created_at: string;
}

export interface CampaignRow {
  id: string;
  name: string;
  is_active: boolean;
  needs_review: boolean;
  source: CampaignSource;
  lead_count: number;
  aliases: CampaignAlias[];
  created_at: string;
  updated_at: string;
}

export interface CampaignSuggestion {
  keep_id: string;
  merge_id: string;
  reason: "spacing_punctuation" | "similar";
}

export interface CampaignOverview {
  items: CampaignRow[];
  suggestions: CampaignSuggestion[];
}

export interface CampaignMutationResult {
  campaign: CampaignRow | null;
  leads_updated: number;
}

export const campaignsService = {
  async list(includeInactive = false): Promise<CampaignOption[]> {
    const { data } = await apiClient.get<CampaignOption[]>("/campaigns", {
      params: includeInactive ? { include_inactive: true } : undefined
    });
    return data;
  },

  async overview(): Promise<CampaignOverview> {
    const { data } = await apiClient.get<CampaignOverview>("/campaigns/manage");
    return data;
  },

  async create(name: string): Promise<CampaignRow> {
    const { data } = await apiClient.post<CampaignRow>("/campaigns", { name });
    return data;
  },

  async rename(id: string, name: string): Promise<CampaignMutationResult> {
    const { data } = await apiClient.post<CampaignMutationResult>(`/campaigns/${id}/rename`, { name });
    return data;
  },

  async merge(sourceIds: string[], targetId: string): Promise<CampaignMutationResult> {
    const { data } = await apiClient.post<CampaignMutationResult>("/campaigns/merge", {
      source_ids: sourceIds,
      target_id: targetId
    });
    return data;
  },

  async clear(id: string): Promise<CampaignMutationResult> {
    const { data } = await apiClient.post<CampaignMutationResult>(`/campaigns/${id}/clear`);
    return data;
  },

  async setActive(id: string, isActive: boolean): Promise<CampaignRow> {
    const { data } = await apiClient.patch<CampaignRow>(`/campaigns/${id}`, { is_active: isActive });
    return data;
  },

  async markReviewed(id: string): Promise<CampaignRow> {
    const { data } = await apiClient.patch<CampaignRow>(`/campaigns/${id}`, { needs_review: false });
    return data;
  },

  async removeAlias(campaignId: string, aliasId: string): Promise<void> {
    await apiClient.delete(`/campaigns/${campaignId}/aliases/${aliasId}`);
  }
};
