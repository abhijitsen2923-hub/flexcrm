// Channel-partner (broker) types. Snake_case to match the API payloads directly
// (same convention as the core CRM types in crm.ts) — no boundary mapping.

export type BrokerageType = "percent" | "flat";
export type PayoutStatus = "accrued" | "paid" | "reversed";

export interface ChannelPartner {
  id: string;
  user_id: string | null;
  company_name: string;
  contact_name: string;
  phone: string | null;
  email: string | null;
  rera_number: string | null;
  pan: string | null;
  brokerage_type: BrokerageType;
  brokerage_rate: string;
  payout_bank_account: string | null;
  payout_ifsc: string | null;
  payout_upi: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ChannelPartnerStats {
  leads_total: number;
  leads_active: number;
  leads_sold: number;
  conversion_rate: number; // 0..1
  brokerage_accrued: string;
  brokerage_paid: string;
  brokerage_outstanding: string;
}

export interface ChannelPartnerListItem extends ChannelPartner {
  stats: ChannelPartnerStats;
}

export interface BrokeragePayout {
  id: string;
  partner_id: string;
  lead_id: string | null;
  sales_order_id: string | null;
  deal_value: string | null;
  rate_type: string;
  rate_snapshot: string;
  amount: string;
  status: PayoutStatus;
  note: string | null;
  paid_on: string | null;
  created_at: string;
}

export interface PartnerStageCount {
  stage_code: string;
  label: string;
  count: number;
}

export interface PartnerLeadRow {
  id: string;
  lead_number: number;
  title: string;
  contact_name: string;
  stage_code: string;
  property_type: string | null;
  preferred_location: string | null;
  budget_min: string | null;
  budget_max: string | null;
  created_at: string;
}

export interface PartnerDashboard {
  partner: ChannelPartner;
  stats: ChannelPartnerStats;
  stage_breakdown: PartnerStageCount[];
  recent_payouts: BrokeragePayout[];
}

// --- request payloads ---

export interface ChannelPartnerCreate {
  company_name: string;
  contact_name: string;
  phone?: string | null;
  email?: string | null;
  rera_number?: string | null;
  pan?: string | null;
  brokerage_type: BrokerageType;
  brokerage_rate: number;
  payout_bank_account?: string | null;
  payout_ifsc?: string | null;
  payout_upi?: string | null;
  is_active?: boolean;
  user_id?: string | null;
}

export type ChannelPartnerUpdate = Partial<ChannelPartnerCreate>;

export interface PartnerLeadSubmit {
  title?: string | null;
  contact_name: string;
  contact_email: string;
  contact_phone: string;
  property_type?: string | null;
  preferred_location?: string | null;
  budget_min?: number | null;
  budget_max?: number | null;
  interest?: string | null;
  notes?: string | null;
}
