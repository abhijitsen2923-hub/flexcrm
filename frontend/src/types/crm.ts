import type { PaginatedResponse } from "./common";


export type UserRole =
  // Cross-vertical (Phase 8)
  | "owner"
  | "support"
  | "analyst"
  // Education-only
  | "academic_admin"
  | "counselor"
  | "fee_admin"
  // Travel-only
  | "ops_manager"
  | "travel_agent"
  | "visa_coordinator"
  // Real-estate-only
  | "sales_manager"
  | "sales_executive"
  | "telecaller"
  | "accounts"
  | "crm_team"
  | "receptionist"
  | "broker"
  // Customer portal — end-buyer accounts, no staff access.
  | "customer"
  // Custom — org-defined role template; permissions sourced from CustomRole table.
  | "custom"
  // Legacy — kept so old user records still type-check; not assignable from UI.
  | "admin"
  | "manager"
  | "sales";

export type PermissionCode =
  | "DASHBOARD_VIEW"
  | "LEAD_VIEW" | "LEAD_MANAGE" | "LEAD_IMPORT" | "LEAD_DOCS_MANAGE"
  | "CUSTOMER_VIEW" | "CUSTOMER_MANAGE"
  | "DEAL_VIEW" | "DEAL_MANAGE"
  | "TASK_VIEW" | "TASK_MANAGE"
  | "ACTIVITY_VIEW" | "ACTIVITY_MANAGE"
  | "FINANCE_VIEW" | "FINANCE_RECORD_PAYMENT" | "FINANCE_REFUND"
  | "HR_VIEW" | "HR_MANAGE"
  | "USER_VIEW" | "USER_MANAGE"
  | "ORG_MANAGE"
  | "ANALYTICS_VIEW" | "REPORTS_VIEW"
  | "EXPORT_DATA";

// Which roles each vertical may assign. Mirrors ROLE_INDUSTRIES in
// `backend/app/core/permissions.py`. Used by the admin user-create modal to
// filter the role dropdown by the current org's business_type.
export const ROLES_BY_INDUSTRY: Record<LeadIndustry, UserRole[]> = {
  education: ["owner", "academic_admin", "counselor", "fee_admin", "support", "analyst"],
  travel: ["owner", "ops_manager", "travel_agent", "visa_coordinator", "support", "analyst"],
  real_estate: ["owner", "sales_manager", "sales_executive", "telecaller", "receptionist", "accounts", "crm_team", "broker", "support", "analyst"],
};
export type UserStatus = "active" | "inactive" | "invited" | "suspended";
export type CustomerStatus = "active" | "inactive" | "prospect" | "churned";
export type CustomerLifecycleStage =
  | "onboarding"
  | "active"
  | "at_risk"
  | "renewal_due"
  | "renewed"
  | "churned";
export type LeadIndustry = "education" | "travel" | "real_estate";
export type PipelineStageCategory = "active" | "closed_won" | "closed_lost";
export type InvoiceStatus = "draft" | "issued" | "paid" | "refunded" | "void";
export type PaymentStatus = "pending" | "received" | "refunded";
export type CommissionDirection = "accrued" | "payable" | "paid" | "reversed";
export type DealStage = "discovery" | "proposal" | "negotiation" | "closed_won" | "closed_lost";
export type DealStatus = "open" | "won" | "lost" | "on_hold";
export type TaskPriority = "low" | "medium" | "high" | "urgent";
export type TaskStatus = "pending" | "in_progress" | "completed" | "cancelled";
export type ActivityType = "note" | "call" | "email" | "meeting" | "task" | "status_change";

export type ModuleKey =
  | "deals" | "tasks" | "activities" | "finance" | "hr"
  | "inventory" | "bookings" | "site_visits" | "projects";
export const MODULE_KEYS: ModuleKey[] = [
  "deals", "tasks", "activities", "finance", "hr",
  "inventory", "bookings", "site_visits", "projects",
];

export interface UserSummary {
  id: string;
  first_name: string;
  last_name: string;
  email: string;
  role: UserRole;
  status: UserStatus;
  business_type: LeadIndustry | null;
  organization_id: string | null;
  is_platform_admin: boolean;
  // Phase 8 — effective permissions (role defaults ∪ explicit grants).
  // Populated on /me, login, refresh. Empty array on list-endpoint payloads.
  permissions: string[];
  // Populated when role === "custom" so the UI can display the template name.
  custom_role_id?: string | null;
  custom_role_name?: string | null;
}

export interface GrantedPermission {
  id: string;
  user_id: string;
  permission_code: string;
  granted_by_id: string | null;
  created_at: string;
}

export interface UserPermissions {
  user_id: string;
  role_defaults: string[];
  granted: GrantedPermission[];
  effective: string[];
}

export interface Organization {
  id: string;
  name: string;
  business_type: LeadIndustry;
  plan: string;
  features: Record<string, unknown> | null;
  allowed_currencies: string[];
  modules: Record<ModuleKey, boolean>;
  is_active: boolean;
  is_deleted: boolean;
  created_at: string;
  updated_at: string;
}

export interface User extends UserSummary {
  phone: string | null;
  created_at: string;
  updated_at: string;
}

export interface CustomerSourceLead {
  id: string;
  lead_number: number;
  title: string;
}

export interface Customer {
  id: string;
  company_name: string;
  contact_name: string;
  email: string | null;
  phone: string | null;
  address: string | null;
  source: string | null;
  status: CustomerStatus;
  lifecycle_stage: CustomerLifecycleStage;
  customer_number: number | null;
  onboarding_started_at: string | null;
  renewal_due_at: string | null;
  ltv: string;
  sale_value: string | null;
  churn_reason: string | null;
  original_owner_id: string | null;
  current_owner_id: string | null;
  current_owner?: { id: string; first_name: string; last_name: string; email: string } | null;
  source_lead_id: string | null;
  source_lead: CustomerSourceLead | null;
  created_by_id: string | null;
  updated_by_id: string | null;
  created_at: string;
  updated_at: string;
}


export interface SalesOrderAssist {
  id: string;
  user_id: string;
  percent: number;
  reason: string | null;
}

export interface SalesOrder {
  id: string;
  order_number: string;
  lead_id: string | null;
  customer_id: string;
  primary_owner_id: string | null;
  title: string;
  deal_value: string;
  currency: string;
  payment_status: PaymentStatus;
  closed_at: string;
  created_at: string;
  assists: SalesOrderAssist[];
}

export interface Invoice {
  id: string;
  invoice_number: string;
  sales_order_id: string;
  amount: string;
  due_date: string | null;
  status: InvoiceStatus;
  created_at: string;
}

export interface Payment {
  id: string;
  invoice_id: string;
  amount: string;
  received_at: string;
  method: string | null;
  txn_ref: string | null;
}

export interface CommissionLedgerEntry {
  id: string;
  user_id: string;
  sales_order_id: string | null;
  direction: CommissionDirection;
  amount: string;
  note: string | null;
  recorded_at: string;
}

export interface ScorecardRow {
  user_id: string;
  user_name: string;
  deals_closed: number;
  revenue: string;
  collections: string;
  conversion_rate: string;
  score: string;
  grade: string;
}

export interface TeamScorecard {
  snapshot_date: string;
  rows: ScorecardRow[];
}

export interface PipelineStage {
  id: string;
  industry: LeadIndustry;
  position: number;
  code: string;
  name: string;
  category: PipelineStageCategory;
  comment_required: boolean;
}

export interface StageTransition {
  id: string;
  lead_id: string;
  from_stage_code: string | null;
  to_stage_code: string;
  comment: string;
  next_action_date: string | null;
  attachment_path: string | null;
  performed_by_id: string | null;
  performed_at: string;
  mentions: string[] | null;
  performed_by?: UserSummary | null;
}

export interface LeadCallLog {
  id: string;
  lead_id: string;
  user_id: string;
  call_type: "first_call" | "follow_up" | "dnp";
  notes: string | null;
  created_at: string;
  user?: UserSummary | null;
}

export interface Lead {
  id: string;
  customer_id: string | null;
  industry: LeadIndustry;
  stage_code: string;
  lead_number: number;
  title: string;
  contact_name: string;
  contact_email: string | null;
  contact_phone: string | null;
  contact_phone_alt: string | null;
  company_name: string | null;
  value: string;
  currency: string;
  probability: number;
  expected_close_date: string | null;
  source: string | null;
  interest: string | null;
  last_comment_preview: string | null;
  last_comment_at: string | null;
  assigned_to_id: string | null;
  // Channel partner (broker) who referred this lead, if any.
  partner_id: string | null;
  // Real-estate specific (null for other verticals). Numeric fields arrive as
  // strings over JSON, same as `value`.
  property_type: string | null;
  budget_min: string | null;
  budget_max: string | null;
  preferred_location: string | null;
  possession_preference: string | null;
  created_by_id: string | null;
  updated_by_id: string | null;
  created_at: string;
  updated_at: string;
  customer?: Pick<Customer, "id" | "company_name" | "contact_name" | "email" | "status"> | null;
  assigned_to?: UserSummary | null;
  partner?: { id: string; company_name: string; contact_name: string } | null;
  // Set by the list endpoint when another active lead shares this lead's email
  // or phone. Drives the "!" duplicate marker in the UI.
  is_duplicate?: boolean;
}

export interface Deal {
  id: string;
  customer_id: string;
  title: string;
  amount: string;
  stage: DealStage;
  expected_close: string | null;
  status: DealStatus;
  created_by_id: string | null;
  updated_by_id: string | null;
  created_at: string;
  updated_at: string;
  customer?: Pick<Customer, "id" | "company_name" | "contact_name" | "status">;
}

export interface Task {
  id: string;
  title: string;
  description: string | null;
  assigned_to_id: string | null;
  due_date: string | null;
  priority: TaskPriority;
  status: TaskStatus;
  created_by_id: string | null;
  updated_by_id: string | null;
  created_at: string;
  updated_at: string;
  assigned_to?: UserSummary | null;
}

export interface Activity {
  id: string;
  customer_id: string;
  type: ActivityType;
  note: string;
  created_by_id: string | null;
  updated_by_id: string | null;
  created_at: string;
  updated_at: string;
  customer?: Pick<Customer, "id" | "company_name" | "contact_name" | "status">;
}

export interface ChartPoint {
  label: string;
  value: number | string;
}

export interface DashboardSummary {
  total_customers: number;
  active_leads: number;
  open_deals_value: string;
  overdue_tasks: number;
  recent_activity_count: number;
}

export interface DashboardCharts {
  revenue_trend: ChartPoint[];
  lead_stage_breakdown: ChartPoint[];
  task_status_breakdown: ChartPoint[];
}

export interface RecentActivityItem {
  id: string;
  customer_id: string;
  customer_name: string;
  type: string;
  note: string;
  created_at: string;
}

export interface RecentActivities {
  items: RecentActivityItem[];
}

export interface AnalyticsRevenue {
  total_closed_revenue: string;
  open_pipeline_value: string;
  monthly_revenue: ChartPoint[];
}

export interface AnalyticsLeads {
  total_leads: number;
  won_leads: number;
  stage_breakdown: ChartPoint[];
  source_breakdown: ChartPoint[];
}

export interface AnalyticsConversion {
  lead_to_win_rate: number;
  deal_win_rate: number;
  average_probability: number;
}

export type CustomerListResponse = PaginatedResponse<Customer>;
export type LeadListResponse = PaginatedResponse<Lead>;
export type DealListResponse = PaginatedResponse<Deal>;
export type TaskListResponse = PaginatedResponse<Task>;
export type ActivityListResponse = PaginatedResponse<Activity>;
