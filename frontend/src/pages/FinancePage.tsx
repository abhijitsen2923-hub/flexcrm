import { Download, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import {
  Badge,
  Button,
  Card,
  DataTable,
  EmptyState,
  LoadingBlock,
  useToast,
  type DataTableColumn
} from "../components";
import { FEATURES } from "../config/features";
import { usePermissions } from "../hooks/usePermissions";
import { useRealtimeEvent } from "../realtime";
import {
  financeService,
  type CollectionEntry,
  type MonthlyReport
} from "../services/finance";
import type { CommissionLedgerEntry, Invoice, SalesOrder } from "../types";
import { extractErrorMessage } from "../utils/errors";
import { formatCurrency, formatDateTime, formatInr } from "../utils/format";


type TabKey = "orders" | "invoices" | "commissions" | "monthly" | "collection";


function ymNow(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}


export default function FinancePage() {
  const [tab, setTab] = useState<TabKey>("orders");
  const [orders, setOrders] = useState<SalesOrder[]>([]);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [ledger, setLedger] = useState<CommissionLedgerEntry[]>([]);
  const [collection, setCollection] = useState<CollectionEntry[]>([]);
  const [report, setReport] = useState<MonthlyReport | null>(null);
  const [reportMonth, setReportMonth] = useState(ymNow());
  const [loading, setLoading] = useState(false);
  const toast = useToast();
  const { has: hasPerm } = usePermissions();
  const canRecordPayment = hasPerm("FINANCE_RECORD_PAYMENT");
  const canExport = hasPerm("EXPORT_DATA");
  const canSeeReports = hasPerm("REPORTS_VIEW");

  // If the monthly tab gets hidden mid-session (e.g. permission revoked),
  // switch the user to a tab they can still see.
  useEffect(() => {
    if (tab === "monthly" && !canSeeReports) {
      setTab("orders");
    }
  }, [tab, canSeeReports]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [o, inv, led, col] = await Promise.all([
        financeService.listSalesOrders(),
        financeService.listInvoices(),
        financeService.listLedger(),
        FEATURES.bookings ? financeService.listCollectionLedger() : Promise.resolve([])
      ]);
      setOrders(o);
      setInvoices(inv);
      setLedger(led);
      setCollection(col);
    } catch (error) {
      toast.error("Could not load finance data", extractErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    void load();
  }, [load]);

  useRealtimeEvent((event) => {
    if (
      event.event.startsWith("sales_order.") ||
      event.event.startsWith("payment.") ||
      event.event.startsWith("refund.")
    ) {
      void load();
    }
  });

  async function fetchReport() {
    try {
      setReport(await financeService.monthlyReport(reportMonth));
    } catch (error) {
      toast.error("Report failed", extractErrorMessage(error));
    }
  }

  async function recordPayment(invoice: Invoice) {
    try {
      await financeService.recordPayment(invoice.id, { amount: invoice.amount });
      toast.success("Payment recorded", `Invoice ${invoice.invoice_number}`);
      await load();
    } catch (error) {
      toast.error("Could not record payment", extractErrorMessage(error));
    }
  }

  const orderColumns: DataTableColumn<SalesOrder>[] = [
    { key: "order", header: "Order", render: (row) => <strong>{row.order_number}</strong> },
    { key: "title", header: "Title", render: (row) => row.title },
    {
      key: "value",
      header: "Value",
      align: "right",
      render: (row) => formatCurrency(row.deal_value, row.currency || "INR")
    },
    {
      key: "payment",
      header: "Payment",
      render: (row) => <Badge tone={row.payment_status === "received" ? "success" : "warning"}>{row.payment_status}</Badge>
    },
    { key: "closed", header: "Closed at", render: (row) => formatDateTime(row.closed_at) }
  ];

  const invoiceColumns: DataTableColumn<Invoice>[] = [
    { key: "number", header: "Invoice", render: (row) => <strong>{row.invoice_number}</strong> },
    { key: "amount", header: "Amount", align: "right", render: (row) => formatCurrency(row.amount) },
    {
      key: "status",
      header: "Status",
      render: (row) => (
        <Badge tone={row.status === "paid" ? "success" : row.status === "refunded" ? "danger" : "warning"}>
          {row.status}
        </Badge>
      )
    },
    {
      key: "actions",
      header: "",
      align: "right",
      render: (row) =>
        row.status === "issued" && canRecordPayment ? (
          <Button size="sm" variant="ghost" onClick={() => void recordPayment(row)}>
            Record payment
          </Button>
        ) : (
          <span className="muted text-xs">—</span>
        )
    }
  ];

  const ledgerColumns: DataTableColumn<CommissionLedgerEntry>[] = [
    { key: "recorded", header: "When", render: (row) => formatDateTime(row.recorded_at) },
    { key: "user", header: "User", render: (row) => row.user_id.slice(0, 8) + "…" },
    {
      key: "direction",
      header: "Direction",
      render: (row) => (
        <Badge tone={row.direction === "reversed" ? "danger" : row.direction === "payable" ? "info" : "neutral"}>
          {row.direction}
        </Badge>
      )
    },
    { key: "amount", header: "Amount", align: "right", render: (row) => formatCurrency(row.amount) },
    { key: "note", header: "Note", render: (row) => row.note ?? "—" }
  ];

  return (
    <>
      <div className="page-header">
        <div className="page-header__titles">
          <h1>Finance</h1>
          <p>Sales orders, invoices, payments, and commissions — all auto-created on Sold.</p>
        </div>
        <div className="page-header__actions">
          <Button variant="secondary" size="sm" icon={<RefreshCw size={14} />} onClick={() => void load()} loading={loading}>
            Refresh
          </Button>
          {canExport && (
            <Button
              variant="secondary"
              size="sm"
              icon={<Download size={14} />}
              onClick={() => window.location.assign("/api/v1/exports/sales-orders.csv")}
            >
              Export CSV
            </Button>
          )}
        </div>
      </div>

      <div className="drawer__tabs" style={{ marginBottom: "1rem" }}>
        {(["orders", "invoices", "commissions", "collection", "monthly"] as TabKey[])
          .filter((key) => {
            if (key === "monthly") return canSeeReports;
            if (key === "collection") return FEATURES.bookings;
            return true;
          })
          .map((key) => (
            <button
              key={key}
              type="button"
              className={`tab ${tab === key ? "tab--active" : ""}`}
              onClick={() => setTab(key)}
            >
              {key === "orders"
                ? "Sales Orders"
                : key === "invoices"
                  ? "Invoices"
                  : key === "commissions"
                    ? "Commission Ledger"
                    : key === "collection"
                      ? "Collection Ledger"
                      : "Monthly Report"}
            </button>
          ))}
      </div>

      {tab === "orders" && (
        <div className="card" style={{ padding: 0 }}>
          <div className="table-wrap" style={{ border: "none", boxShadow: "none" }}>
            {loading && orders.length === 0 ? (
              <LoadingBlock label="Loading sales orders…" />
            ) : (
              <DataTable
                columns={orderColumns}
                rows={orders}
                rowKey={(row) => row.id}
                empty={<EmptyState title="No sales orders yet" description="They appear automatically when a lead reaches Sold." />}
              />
            )}
          </div>
        </div>
      )}

      {tab === "invoices" && (
        <div className="card" style={{ padding: 0 }}>
          <div className="table-wrap" style={{ border: "none", boxShadow: "none" }}>
            <DataTable
              columns={invoiceColumns}
              rows={invoices}
              rowKey={(row) => row.id}
              empty={<EmptyState title="No invoices yet" />}
            />
          </div>
        </div>
      )}

      {tab === "commissions" && (
        <div className="card" style={{ padding: 0 }}>
          <div className="table-wrap" style={{ border: "none", boxShadow: "none" }}>
            <DataTable
              columns={ledgerColumns}
              rows={ledger}
              rowKey={(row) => row.id}
              empty={<EmptyState title="Ledger is empty" />}
            />
          </div>
        </div>
      )}

      {tab === "collection" && (
        <div className="card" style={{ padding: 0 }}>
          <div className="table-wrap" style={{ border: "none", boxShadow: "none" }}>
            <DataTable
              columns={[
                {
                  key: "booking",
                  header: "Booking",
                  render: (row) => <strong>{row.booking_number || row.booking_id.slice(0, 8)}</strong>
                },
                { key: "project", header: "Project", render: (row) => row.project_name },
                { key: "unit", header: "Unit", render: (row) => row.unit_number },
                { key: "installment", header: "Installment", render: (row) => row.installment_name },
                {
                  key: "due",
                  header: "Due date",
                  render: (row) => (
                    <span style={row.is_overdue ? { color: "var(--color-danger)", fontWeight: 600 } : {}}>
                      {new Date(row.due_date).toLocaleDateString()}
                    </span>
                  )
                },
                {
                  key: "demand",
                  header: "Demand",
                  align: "right",
                  render: (row) => formatInr(row.demand_amount)
                },
                {
                  key: "paid",
                  header: "Paid",
                  align: "right",
                  render: (row) => (
                    <span style={{ color: "var(--status-available)" }}>{formatInr(row.paid_amount)}</span>
                  )
                },
                {
                  key: "outstanding",
                  header: "Outstanding",
                  align: "right",
                  render: (row) => (
                    <span style={row.outstanding > 0 ? { color: "var(--color-danger)", fontWeight: 600 } : {}}>
                      {formatInr(row.outstanding)}
                    </span>
                  )
                },
                {
                  key: "status",
                  header: "Status",
                  render: (row) =>
                    row.is_overdue ? (
                      <Badge tone="danger">Overdue</Badge>
                    ) : row.outstanding === 0 ? (
                      <Badge tone="success">Cleared</Badge>
                    ) : (
                      <Badge tone="warning">Pending</Badge>
                    )
                }
              ] as DataTableColumn<CollectionEntry>[]}
              rows={collection}
              rowKey={(row) => `${row.booking_id}-${row.installment_name}`}
              empty={<EmptyState title="No collection entries" description="Payment schedules from bookings appear here." />}
            />
          </div>
        </div>
      )}

      {tab === "monthly" && (
        <Card>
          <div className="row" style={{ alignItems: "flex-end", gap: "0.75rem" }}>
            <div className="field">
              <label className="field__label">Month</label>
              <input
                className="input"
                type="month"
                value={reportMonth}
                onChange={(event) => setReportMonth(event.target.value)}
              />
            </div>
            <Button onClick={() => void fetchReport()}>Run report</Button>
          </div>
          {report && (
            <div style={{ marginTop: "1rem" }}>
              <h3>{report.month}</h3>
              <DataTable
                columns={[
                  { key: "user", header: "Owner", render: (row) => row.user_name },
                  { key: "deals", header: "Deals closed", align: "right", render: (row) => row.deals_closed },
                  { key: "revenue", header: "Revenue", align: "right", render: (row) => formatCurrency(row.revenue) },
                  { key: "collections", header: "Collections", align: "right", render: (row) => formatCurrency(row.collections) }
                ]}
                rows={report.rows}
                rowKey={(row) => `${row.user_id ?? "anon"}-${row.user_name}`}
                empty={<EmptyState title="No revenue in this month" />}
              />
            </div>
          )}
        </Card>
      )}
    </>
  );
}
