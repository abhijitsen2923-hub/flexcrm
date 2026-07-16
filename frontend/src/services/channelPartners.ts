import { apiClient } from "./http";
import type { Lead } from "../types";
import type {
  BrokeragePayout,
  ChannelPartner,
  ChannelPartnerCreate,
  ChannelPartnerFull,
  ChannelPartnerListItem,
  ChannelPartnerUpdate,
  PayoutStatus,
} from "../types/partner";

// Staff-facing channel-partner management (roster, overview, payouts). Broker
// self-service lives in `partnerPortal.ts`. Payloads are snake_case already, so
// no boundary mapping is needed.
export interface PartnerOption {
  id: string;
  company_name: string;
  contact_name: string;
}

export const channelPartnersService = {
  list(): Promise<ChannelPartnerListItem[]> {
    return apiClient.get<ChannelPartnerListItem[]>("/channel-partners").then((r) => r.data);
  },

  // Lightweight picker for the New Lead form (any LEAD_MANAGE holder).
  options(): Promise<PartnerOption[]> {
    return apiClient.get<PartnerOption[]>("/channel-partners/options").then((r) => r.data);
  },

  get(id: string): Promise<ChannelPartnerListItem> {
    return apiClient.get<ChannelPartnerListItem>(`/channel-partners/${id}`).then((r) => r.data);
  },

  // Full record incl. PAN + payout details (USER_MANAGE) — for the edit form.
  getFull(id: string): Promise<ChannelPartnerFull> {
    return apiClient.get<ChannelPartnerFull>(`/channel-partners/${id}/full`).then((r) => r.data);
  },

  create(payload: ChannelPartnerCreate): Promise<ChannelPartner> {
    return apiClient.post<ChannelPartner>("/channel-partners", payload).then((r) => r.data);
  },

  update(id: string, payload: ChannelPartnerUpdate): Promise<ChannelPartner> {
    return apiClient.patch<ChannelPartner>(`/channel-partners/${id}`, payload).then((r) => r.data);
  },

  leads(id: string): Promise<Lead[]> {
    return apiClient.get<Lead[]>(`/channel-partners/${id}/leads`).then((r) => r.data);
  },

  payouts(id: string): Promise<BrokeragePayout[]> {
    return apiClient.get<BrokeragePayout[]>(`/channel-partners/${id}/payouts`).then((r) => r.data);
  },

  updatePayout(
    payoutId: string,
    body: { status: PayoutStatus; paid_on?: string | null; note?: string | null }
  ): Promise<BrokeragePayout> {
    return apiClient
      .patch<BrokeragePayout>(`/channel-partners/payouts/${payoutId}`, body)
      .then((r) => r.data);
  },
};
