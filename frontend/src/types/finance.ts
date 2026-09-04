// Finance vertical — Phase 1 types (expenses / vendors / vendor bills). Imported
// directly (not via the types barrel), mirroring types/realestate.ts.

export type ExpenseStatus = "draft" | "submitted" | "approved" | "rejected" | "paid";
export type VendorBillStatus = "open" | "partially_paid" | "paid" | "cancelled";
export type FinanceBusinessMode = "general" | "re_builder" | "re_broker" | "hybrid";
export type GstTreatment = "intra_state" | "inter_state";
export type FinanceCategoryKind = "expense" | "income";

export interface FinanceSettings {
  gst_registered: boolean;
  gstin: string | null;
  home_state_code: string | null;
  default_place_of_supply_state: string | null;
  expense_approval_threshold: string;
  finance_business_mode: FinanceBusinessMode;
}

export interface FinanceCategory {
  id: string;
  name: string;
  kind: FinanceCategoryKind;
  group_label: string | null;
  source: string;
  is_active: boolean;
  sort_order: number | null;
}

export interface Vendor {
  id: string;
  name: string;
  contact_name: string | null;
  phone: string | null;
  email: string | null;
  gstin: string | null;
  pan: string | null;
  state_code: string | null;
  address: string | null;
  bank_account: string | null;
  ifsc: string | null;
  upi: string | null;
  notes: string | null;
  is_active: boolean;
  created_at: string;
}

// Monetary fields arrive as strings (Decimal) from the API.
interface GstSnapshot {
  gst_applicable: boolean;
  gst_treatment: GstTreatment | null;
  gst_inclusive: boolean;
  gst_rate: string | null;
  amount_entered: string;
  taxable_amount: string;
  cgst_amount: string;
  sgst_amount: string;
  igst_amount: string;
  tds_amount: string;
  total_amount: string;
  net_payable: string;
}

export interface Expense extends GstSnapshot {
  id: string;
  expense_number: string;
  title: string;
  notes: string | null;
  category_id: string;
  vendor_id: string | null;
  bill_id: string | null;
  project_id: string | null;
  department: string | null;
  expense_date: string;
  payment_mode: string | null;
  status: ExpenseStatus;
  submitted_by_id: string | null;
  submitted_at: string | null;
  approved_by_id: string | null;
  approved_at: string | null;
  rejected_reason: string | null;
  paid_at: string | null;
  created_at: string;
}

export interface VendorPayment {
  id: string;
  payment_number: string;
  bill_id: string;
  vendor_id: string | null;
  amount: string;
  paid_on: string;
  method: string | null;
  txn_ref: string | null;
  note: string | null;
  created_at: string;
}

export interface VendorBill extends GstSnapshot {
  id: string;
  bill_number: string;
  vendor_id: string;
  vendor_invoice_no: string | null;
  category_id: string | null;
  project_id: string | null;
  bill_date: string | null;
  due_date: string | null;
  description: string | null;
  status: VendorBillStatus;
  amount_paid: string;
  paid_on: string | null;
  created_at: string;
  payments: VendorPayment[];
}

export interface FinanceDocument {
  id: string;
  owner_type: string;
  owner_id: string;
  doc_type: string | null;
  file_name: string | null;
  content_type: string | null;
  created_at: string;
}

// ---- Write payloads ----

export interface GstInput {
  amount_entered: number;
  gst_applicable: boolean;
  gst_treatment: GstTreatment | null;
  gst_inclusive: boolean;
  gst_rate: number | null;
  tds_amount: number;
}

export interface ExpenseWritePayload extends GstInput {
  title: string;
  notes?: string | null;
  category_id: string;
  vendor_id?: string | null;
  bill_id?: string | null;
  project_id?: string | null;
  department?: string | null;
  expense_date: string;
  payment_mode?: string | null;
}

export interface VendorBillWritePayload extends GstInput {
  vendor_id: string;
  vendor_invoice_no?: string | null;
  category_id?: string | null;
  project_id?: string | null;
  bill_date?: string | null;
  due_date?: string | null;
  description?: string | null;
}

// ---- Manual income + dashboard summary (Phase 2) ----

export interface ManualIncome extends GstSnapshot {
  id: string;
  income_number: string;
  title: string;
  category_id: string;
  source: string | null;
  project_id: string | null;
  income_date: string;
  payment_mode: string | null;
  notes: string | null;
  created_at: string;
}

export interface ManualIncomeWritePayload extends GstInput {
  title: string;
  category_id: string;
  source?: string | null;
  project_id?: string | null;
  income_date: string;
  payment_mode?: string | null;
  notes?: string | null;
}

export interface FinanceBreakdownRow {
  label: string;
  value: string;
}

export interface FinanceSummary {
  income_total: string;
  manual_income_total: string;
  sales_revenue_total: string;
  expense_total: string;
  expense_paid: string;
  expense_pending_approval: number;
  vendor_payable_outstanding: string;
  output_gst: string;
  input_gst: string;
  net_gst: string;
  net_position: string;
  expense_by_category: FinanceBreakdownRow[];
  income_by_category: FinanceBreakdownRow[];
}

// ---- Per-customer demand ledger (Phase 3a) ----

export interface DemandReceipt {
  id: string;
  receipt_number: string;
  demand_id: string;
  amount: string;
  received_on: string;
  method: string | null;
  txn_ref: string | null;
  note: string | null;
  created_at: string;
}

export interface CustomerDemand {
  id: string;
  demand_number: string;
  contract_id: string;
  description: string | null;
  amount: string;
  due_date: string | null;
  status: string;
  amount_received: string;
  outstanding: string;
  created_at: string;
  receipts: DemandReceipt[];
}

export interface CustomerContract {
  id: string;
  customer_id: string;
  title: string;
  contract_value: string;
  currency: string;
  notes: string | null;
  status: string;
  created_at: string;
  total_demanded: string;
  total_received: string;
  balance: string;
  demands: CustomerDemand[];
}

export interface CustomerContractListItem {
  id: string;
  customer_id: string;
  title: string;
  contract_value: string;
  currency: string;
  status: string;
  total_demanded: string;
  total_received: string;
  balance: string;
  created_at: string;
}

// ---- Payroll (Phase 3) ----

export interface PayrollEmployee {
  user_id: string;
  name: string;
  role: string | null;
  monthly_salary: string;
}

export interface PayrollRunResult {
  month: string;
  created: number;
  skipped: number;
  total_amount: string;
}

export interface Budget {
  id: string;
  name: string;
  period_key: string; // YYYY-MM
  category_id: string | null;
  category_name: string | null;
  department: string | null;
  amount: string;
  actual: string;
  variance: string;
  used_pct: number;
  notes: string | null;
}

export interface BudgetWritePayload {
  name: string;
  period_key: string;
  category_id?: string | null;
  department?: string | null;
  amount: number;
  notes?: string | null;
}
