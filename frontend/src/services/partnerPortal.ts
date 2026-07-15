import { apiClient } from "./http";
import type {
  BrokeragePayout,
  ChannelPartner,
  PartnerDashboard,
  PartnerLeadRow,
  PartnerLeadSubmit,
} from "../types/partner";

// Broker self-service. Every call is scoped server-side to the logged-in
// partner (require_broker + partner_for_user) — a broker can only see their own
// referrals and brokerage.
export const partnerPortalService = {
  me(): Promise<ChannelPartner> {
    return apiClient.get<ChannelPartner>("/partner/me").then((r) => r.data);
  },

  dashboard(): Promise<PartnerDashboard> {
    return apiClient.get<PartnerDashboard>("/partner/dashboard").then((r) => r.data);
  },

  leads(): Promise<PartnerLeadRow[]> {
    return apiClient.get<PartnerLeadRow[]>("/partner/leads").then((r) => r.data);
  },

  submitLead(payload: PartnerLeadSubmit): Promise<PartnerLeadRow> {
    return apiClient.post<PartnerLeadRow>("/partner/leads", payload).then((r) => r.data);
  },

  commissions(): Promise<BrokeragePayout[]> {
    return apiClient.get<BrokeragePayout[]>("/partner/commissions").then((r) => r.data);
  },
};
