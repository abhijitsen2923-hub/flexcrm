import type {
  CommissionLedgerEntry,
  Invoice,
  Payment,
  SalesOrder
} from "../types";
import type {
  Expense,
  ExpenseStatus,
  ExpenseWritePayload,
  FinanceCategory,
  FinanceCategoryKind,
  FinanceDocument,
  CustomerContract,
  CustomerContractListItem,
  CustomerDemand,
  DemandReceipt,
  PayrollEmployee,
  PayrollRunResult,
  Budget,
  BudgetWritePayload,
  FinanceSettings,
  FinanceSummary,
  ManualIncome,
  ManualIncomeWritePayload,
  Vendor,
  VendorBill,
  VendorBillStatus,
  VendorBillWritePayload,
  VendorPayment
} from "../types/finance";
import { apiClient } from "./http";


function qs(params: Record<string, string | number | boolean | undefined | null>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : "";
}


export interface MonthlyReportRow {
  user_id: string | null;
  user_name: string;
  deals_closed: number;
  revenue: string;
  collections: string;
}

export interface MonthlyReport {
  month: string;
  rows: MonthlyReportRow[];
}

export interface CollectionEntry {
  booking_id: string;
  booking_number: string;
  unit_number: string;
  project_name: string;
  installment_name: string;
  due_date: string;
  demand_amount: number;
  paid_amount: number;
  outstanding: number;
  is_overdue: boolean;
}

export const financeService = {
  async listSalesOrders(): Promise<SalesOrder[]> {
    const { data } = await apiClient.get<SalesOrder[]>("/finance/sales-orders");
    return data;
  },
  async listInvoices(salesOrderId?: string): Promise<Invoice[]> {
    const params = salesOrderId ? `?sales_order_id=${salesOrderId}` : "";
    const { data } = await apiClient.get<Invoice[]>(`/finance/invoices${params}`);
    return data;
  },
  async recordPayment(invoiceId: string, payload: { amount: string | number; method?: string; txn_ref?: string }): Promise<Payment> {
    const { data } = await apiClient.post<Payment>(`/finance/invoices/${invoiceId}/payments`, payload);
    return data;
  },
  async issueRefund(paymentId: string, payload: { amount: string | number; reason?: string }) {
    const { data } = await apiClient.post(`/finance/payments/${paymentId}/refund`, payload);
    return data;
  },
  async listLedger(userId?: string): Promise<CommissionLedgerEntry[]> {
    const params = userId ? `?user_id=${userId}` : "";
    const { data } = await apiClient.get<CommissionLedgerEntry[]>(`/finance/commission-ledger${params}`);
    return data;
  },
  async monthlyReport(month: string): Promise<MonthlyReport> {
    const { data } = await apiClient.get<MonthlyReport>(`/finance/reports/monthly?month=${month}`);
    return data;
  },
  async listCollectionLedger(): Promise<CollectionEntry[]> {
    const { data } = await apiClient.get<CollectionEntry[]>("/bookings/collection-ledger");
    return data;
  },

  // ---- Settings ----
  async getSettings(): Promise<FinanceSettings> {
    const { data } = await apiClient.get<FinanceSettings>("/finance/settings");
    return data;
  },
  async updateSettings(payload: Partial<FinanceSettings>): Promise<FinanceSettings> {
    const { data } = await apiClient.patch<FinanceSettings>("/finance/settings", payload);
    return data;
  },

  // ---- Categories ----
  async listCategories(kind?: FinanceCategoryKind, includeInactive = false): Promise<FinanceCategory[]> {
    const { data } = await apiClient.get<FinanceCategory[]>(
      `/finance/categories${qs({ kind, include_inactive: includeInactive || undefined })}`
    );
    return data;
  },
  async createCategory(payload: { name: string; kind?: FinanceCategoryKind; group_label?: string | null }): Promise<FinanceCategory> {
    const { data } = await apiClient.post<FinanceCategory>("/finance/categories", payload);
    return data;
  },
  async updateCategory(id: string, payload: { name?: string; group_label?: string | null; is_active?: boolean }): Promise<FinanceCategory> {
    const { data } = await apiClient.patch<FinanceCategory>(`/finance/categories/${id}`, payload);
    return data;
  },

  // ---- Vendors ----
  async listVendors(params: { is_active?: boolean; q?: string } = {}): Promise<Vendor[]> {
    const { data } = await apiClient.get<Vendor[]>(`/finance/vendors${qs(params)}`);
    return data;
  },
  async getVendor(id: string): Promise<Vendor> {
    const { data } = await apiClient.get<Vendor>(`/finance/vendors/${id}`);
    return data;
  },
  async createVendor(payload: Partial<Vendor>): Promise<Vendor> {
    const { data } = await apiClient.post<Vendor>("/finance/vendors", payload);
    return data;
  },
  async updateVendor(id: string, payload: Partial<Vendor>): Promise<Vendor> {
    const { data } = await apiClient.patch<Vendor>(`/finance/vendors/${id}`, payload);
    return data;
  },
  async deleteVendor(id: string): Promise<void> {
    await apiClient.delete(`/finance/vendors/${id}`);
  },

  // ---- Expenses ----
  async listExpenses(params: { status?: ExpenseStatus; category_id?: string; vendor_id?: string; date_from?: string; date_to?: string } = {}): Promise<Expense[]> {
    const { data } = await apiClient.get<Expense[]>(`/finance/expenses${qs(params)}`);
    return data;
  },
  async createExpense(payload: ExpenseWritePayload & { submit?: boolean }): Promise<Expense> {
    const { data } = await apiClient.post<Expense>("/finance/expenses", payload);
    return data;
  },
  async updateExpense(id: string, payload: ExpenseWritePayload): Promise<Expense> {
    const { data } = await apiClient.patch<Expense>(`/finance/expenses/${id}`, payload);
    return data;
  },
  async submitExpense(id: string): Promise<Expense> {
    const { data } = await apiClient.post<Expense>(`/finance/expenses/${id}/submit`);
    return data;
  },
  async approveExpense(id: string): Promise<Expense> {
    const { data } = await apiClient.post<Expense>(`/finance/expenses/${id}/approve`);
    return data;
  },
  async rejectExpense(id: string, reason: string): Promise<Expense> {
    const { data } = await apiClient.post<Expense>(`/finance/expenses/${id}/reject`, { reason });
    return data;
  },
  async markExpensePaid(id: string, payload: { paid_at?: string | null; payment_mode?: string | null } = {}): Promise<Expense> {
    const { data } = await apiClient.post<Expense>(`/finance/expenses/${id}/mark-paid`, payload);
    return data;
  },
  async deleteExpense(id: string): Promise<void> {
    await apiClient.delete(`/finance/expenses/${id}`);
  },

  // ---- Vendor bills + payments ----
  async listVendorBills(params: { vendor_id?: string; status?: VendorBillStatus } = {}): Promise<VendorBill[]> {
    const { data } = await apiClient.get<VendorBill[]>(`/finance/vendor-bills${qs(params)}`);
    return data;
  },
  async getVendorBill(id: string): Promise<VendorBill> {
    const { data } = await apiClient.get<VendorBill>(`/finance/vendor-bills/${id}`);
    return data;
  },
  async createVendorBill(payload: VendorBillWritePayload): Promise<VendorBill> {
    const { data } = await apiClient.post<VendorBill>("/finance/vendor-bills", payload);
    return data;
  },
  async updateVendorBill(id: string, payload: VendorBillWritePayload): Promise<VendorBill> {
    const { data } = await apiClient.patch<VendorBill>(`/finance/vendor-bills/${id}`, payload);
    return data;
  },
  async cancelVendorBill(id: string): Promise<VendorBill> {
    const { data } = await apiClient.post<VendorBill>(`/finance/vendor-bills/${id}/cancel`);
    return data;
  },
  async recordVendorPayment(id: string, payload: { amount: number; paid_on: string; method?: string; txn_ref?: string; note?: string }): Promise<VendorPayment> {
    const { data } = await apiClient.post<VendorPayment>(`/finance/vendor-bills/${id}/payments`, payload);
    return data;
  },

  // ---- Documents ----
  async uploadDocument(form: FormData): Promise<FinanceDocument> {
    const { data } = await apiClient.post<FinanceDocument>("/finance/documents", form, {
      headers: { "Content-Type": "multipart/form-data" }
    });
    return data;
  },
  async listDocuments(ownerType: string, ownerId: string): Promise<FinanceDocument[]> {
    const { data } = await apiClient.get<FinanceDocument[]>(
      `/finance/documents${qs({ owner_type: ownerType, owner_id: ownerId })}`
    );
    return data;
  },
  async downloadDocument(id: string): Promise<string> {
    const { data } = await apiClient.get<{ url: string }>(`/finance/documents/${id}/download`);
    return data.url;
  },

  // Fetch a generated PDF (auth header via apiClient) as a blob and save it.
  async downloadPdf(path: string, filename: string): Promise<void> {
    const res = await apiClient.get(path, { responseType: "blob" });
    const url = window.URL.createObjectURL(res.data as Blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  },

  // ---- Manual income (Phase 2) ----
  async listIncome(params: { category_id?: string; date_from?: string; date_to?: string } = {}): Promise<ManualIncome[]> {
    const { data } = await apiClient.get<ManualIncome[]>(`/finance/income${qs(params)}`);
    return data;
  },
  async createIncome(payload: ManualIncomeWritePayload): Promise<ManualIncome> {
    const { data } = await apiClient.post<ManualIncome>("/finance/income", payload);
    return data;
  },
  async updateIncome(id: string, payload: ManualIncomeWritePayload): Promise<ManualIncome> {
    const { data } = await apiClient.patch<ManualIncome>(`/finance/income/${id}`, payload);
    return data;
  },
  async deleteIncome(id: string): Promise<void> {
    await apiClient.delete(`/finance/income/${id}`);
  },

  // ---- Dashboard summary (Phase 2) ----
  async getSummary(): Promise<FinanceSummary> {
    const { data } = await apiClient.get<FinanceSummary>("/finance/summary");
    return data;
  },

  // ---- Per-customer demand ledger (Phase 3a) ----
  async listContracts(customerId?: string): Promise<CustomerContractListItem[]> {
    const { data } = await apiClient.get<CustomerContractListItem[]>(`/finance/contracts${qs({ customer_id: customerId })}`);
    return data;
  },
  async getContract(id: string): Promise<CustomerContract> {
    const { data } = await apiClient.get<CustomerContract>(`/finance/contracts/${id}`);
    return data;
  },
  async createContract(payload: { customer_id: string; title: string; contract_value: number; currency?: string; notes?: string | null }): Promise<CustomerContract> {
    const { data } = await apiClient.post<CustomerContract>("/finance/contracts", payload);
    return data;
  },
  async updateContract(id: string, payload: { title?: string; contract_value?: number; notes?: string | null; status?: string }): Promise<CustomerContract> {
    const { data } = await apiClient.patch<CustomerContract>(`/finance/contracts/${id}`, payload);
    return data;
  },
  async raiseDemand(contractId: string, payload: { description?: string | null; amount: number; due_date?: string | null }): Promise<CustomerDemand> {
    const { data } = await apiClient.post<CustomerDemand>(`/finance/contracts/${contractId}/demands`, payload);
    return data;
  },
  async updateDemand(id: string, payload: { description?: string | null; amount?: number; due_date?: string | null }): Promise<CustomerDemand> {
    const { data } = await apiClient.patch<CustomerDemand>(`/finance/demands/${id}`, payload);
    return data;
  },
  async cancelDemand(id: string): Promise<CustomerDemand> {
    const { data } = await apiClient.post<CustomerDemand>(`/finance/demands/${id}/cancel`);
    return data;
  },
  async recordDemandReceipt(demandId: string, payload: { amount: number; received_on: string; method?: string; txn_ref?: string; note?: string }): Promise<DemandReceipt> {
    const { data } = await apiClient.post<DemandReceipt>(`/finance/demands/${demandId}/receipts`, payload);
    return data;
  },

  // ---- Payroll (Phase 3) ----
  async listPayrollEmployees(): Promise<PayrollEmployee[]> {
    const { data } = await apiClient.get<PayrollEmployee[]>("/finance/payroll/employees");
    return data;
  },
  async setEmployeeSalary(userId: string, monthlySalary: number): Promise<PayrollEmployee> {
    const { data } = await apiClient.patch<PayrollEmployee>(`/finance/payroll/employees/${userId}`, { monthly_salary: monthlySalary });
    return data;
  },
  async runPayroll(month: string, employeeIds?: string[]): Promise<PayrollRunResult> {
    const { data } = await apiClient.post<PayrollRunResult>("/finance/payroll/run", { month, employee_ids: employeeIds });
    return data;
  },

  // ---- Budgets (Phase 3) ----
  async listBudgets(periodKey?: string): Promise<Budget[]> {
    const { data } = await apiClient.get<Budget[]>("/finance/budgets", {
      params: periodKey ? { period_key: periodKey } : undefined
    });
    return data;
  },
  async createBudget(payload: BudgetWritePayload): Promise<Budget> {
    const { data } = await apiClient.post<Budget>("/finance/budgets", payload);
    return data;
  },
  async updateBudget(id: string, payload: Partial<BudgetWritePayload>): Promise<Budget> {
    const { data } = await apiClient.patch<Budget>(`/finance/budgets/${id}`, payload);
    return data;
  },
  async deleteBudget(id: string): Promise<void> {
    await apiClient.delete(`/finance/budgets/${id}`);
  }
};
