import type {
  CommissionLedgerEntry,
  Invoice,
  Payment,
  SalesOrder
} from "../types";
import { apiClient } from "./http";


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
  }
};
