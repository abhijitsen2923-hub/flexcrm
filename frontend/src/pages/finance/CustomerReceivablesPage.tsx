import { useEffect, useMemo, useState } from "react";

import {
  Badge,
  Card,
  DataTable,
  EmptyState,
  KpiCard,
  LoadingBlock,
  useToast,
  type DataTableColumn
} from "../../components";
import { financeService, type CollectionEntry } from "../../services/finance";
import { extractErrorMessage } from "../../utils/errors";
import { formatCurrency, formatDate } from "../../utils/format";

export default function CustomerReceivablesPage() {
  const toast = useToast();
  const [rows, setRows] = useState<CollectionEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void (async () => {
      try {
        setRows(await financeService.listCollectionLedger());
      } catch (e) {
        // General businesses have no bookings — treat as empty rather than an error.
        toast.error("Failed to load receivables", extractErrorMessage(e));
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const totals = useMemo(() => {
    const outstanding = rows.reduce((s, r) => s + Number(r.outstanding), 0);
    const overdue = rows.filter((r) => r.is_overdue).reduce((s, r) => s + Number(r.outstanding), 0);
    return { outstanding, overdue, count: rows.length };
  }, [rows]);

  const columns: DataTableColumn<CollectionEntry>[] = [
    {
      key: "booking",
      header: "Booking / Unit",
      render: (r) => (
        <div>
          <strong>{r.project_name}</strong>
          <div className="muted text-xs">{r.unit_number} · {r.booking_number}</div>
        </div>
      )
    },
    { key: "inst", header: "Installment", render: (r) => r.installment_name },
    { key: "due", header: "Due", render: (r) => formatDate(r.due_date) },
    { key: "demand", header: "Demand", align: "right", render: (r) => formatCurrency(r.demand_amount, "INR") },
    { key: "paid", header: "Paid", align: "right", render: (r) => formatCurrency(r.paid_amount, "INR") },
    { key: "out", header: "Outstanding", align: "right", render: (r) => <strong>{formatCurrency(r.outstanding, "INR")}</strong> },
    { key: "status", header: "", render: (r) => (r.is_overdue ? <Badge tone="danger">Overdue</Badge> : <Badge tone="warning">Due</Badge>) }
  ];

  if (loading) return <LoadingBlock label="Loading receivables…" />;

  return (
    <>
      <div className="page-header">
        <div className="page-header__titles">
          <h1>Customer Receivables</h1>
          <p>Outstanding customer demands from booking payment schedules. Record collections from the booking.</p>
        </div>
      </div>

      <div className="kpi-grid">
        <KpiCard label="Total outstanding" value={formatCurrency(totals.outstanding, "INR")} />
        <KpiCard label="Overdue" value={formatCurrency(totals.overdue, "INR")} />
        <KpiCard label="Open demands" value={String(totals.count)} />
      </div>

      <Card>
        <DataTable
          columns={columns}
          rows={rows}
          rowKey={(r) => `${r.booking_id}-${r.installment_name}-${r.due_date}`}
          empty={<EmptyState title="No receivables" description="Customer demands from bookings appear here." />}
        />
      </Card>
    </>
  );
}
