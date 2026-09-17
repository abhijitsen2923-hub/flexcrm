import { useEffect, useMemo, useState } from "react";

import {
  Badge,
  Card,
  DataTable,
  EmptyState,
  KpiCard,
  LoadingBlock,
  SelectField,
  useToast,
  type DataTableColumn
} from "../../components";
import { financeService, type CollectionEntry } from "../../services/finance";
import { inventoryService } from "../../services/inventory";
import type { Project } from "../../types/realestate";
import { extractErrorMessage } from "../../utils/errors";
import { formatCurrency, formatDate } from "../../utils/format";

export default function CustomerReceivablesPage() {
  const toast = useToast();
  const [rows, setRows] = useState<CollectionEntry[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectFilter, setProjectFilter] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void inventoryService.listProjects().then(setProjects).catch(() => {});
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    financeService
      .listCollectionLedger(projectFilter ? { project_id: projectFilter } : {})
      .then((r) => { if (!cancelled) setRows(r); })
      // General businesses have no bookings — an error just leaves the list empty.
      .catch((e) => { if (!cancelled) toast.error("Failed to load receivables", extractErrorMessage(e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [projectFilter, toast]);

  const totals = useMemo(() => {
    const generated = rows.reduce((s, r) => s + Number(r.demand_amount), 0);
    const pending = rows.reduce((s, r) => s + Number(r.outstanding), 0);
    const overdue = rows.filter((r) => r.is_overdue).reduce((s, r) => s + Number(r.outstanding), 0);
    return { generated, pending, overdue, count: rows.length };
  }, [rows]);

  const columns: DataTableColumn<CollectionEntry>[] = [
    {
      key: "booking",
      header: "Booking / Unit",
      render: (r) => (
        <div>
          <strong>{r.project_name}</strong>
          <div className="muted text-xs">{r.unit_number}</div>
        </div>
      )
    },
    { key: "customer", header: "From (customer)", render: (r) => r.customer_name || "—" },
    { key: "inst", header: "Installment", render: (r) => r.installment_name },
    { key: "due", header: "Due", render: (r) => formatDate(r.due_date) },
    { key: "demand", header: "Demand", align: "right", render: (r) => formatCurrency(r.demand_amount, "INR") },
    { key: "paid", header: "Paid", align: "right", render: (r) => formatCurrency(r.paid_amount, "INR") },
    { key: "out", header: "Outstanding", align: "right", render: (r) => <strong>{formatCurrency(r.outstanding, "INR")}</strong> },
    { key: "status", header: "", render: (r) => (r.is_overdue ? <Badge tone="danger">Overdue</Badge> : <Badge tone="warning">Due</Badge>) }
  ];

  if (loading && rows.length === 0) return <LoadingBlock label="Loading receivables…" />;

  return (
    <>
      <div className="page-header">
        <div className="page-header__titles">
          <h1>Customer Receivables</h1>
          <p>Outstanding customer demands from booking payment schedules. Record collections from the booking.</p>
        </div>
      </div>

      <div className="kpi-grid">
        <KpiCard label="Demand generated" value={formatCurrency(totals.generated, "INR")} />
        <KpiCard label="Pending" value={formatCurrency(totals.pending, "INR")} />
        <KpiCard label="Overdue" value={formatCurrency(totals.overdue, "INR")} />
        <KpiCard label="Open demands" value={String(totals.count)} />
      </div>

      <Card>
        <div className="row" style={{ padding: "0.85rem 1rem", borderBottom: "1px solid var(--color-border)" }}>
          <div style={{ maxWidth: 280, width: "100%" }}>
            <SelectField
              id="rcv-project"
              label="Project"
              value={projectFilter}
              onChange={(e) => setProjectFilter(e.target.value)}
              options={[{ value: "", label: "All projects" }, ...projects.map((p) => ({ value: p.id, label: p.name }))]}
            />
          </div>
        </div>
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
