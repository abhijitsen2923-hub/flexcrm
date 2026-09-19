import { useEffect, useMemo, useState } from "react";

import {
  Badge,
  Button,
  Card,
  DataTable,
  EmptyState,
  KpiCard,
  LoadingBlock,
  Modal,
  SelectField,
  TextField,
  useToast,
  type DataTableColumn
} from "../../components";
import { usePermissions } from "../../hooks/usePermissions";
import { financeService, type CollectionEntry, type DemandInput } from "../../services/finance";
import { inventoryService } from "../../services/inventory";
import type { Project } from "../../types/realestate";
import { extractErrorMessage } from "../../utils/errors";
import { formatCurrency, formatDate } from "../../utils/format";

// Add/edit form for a single customer demand (a PaymentSchedule row on a booking).
type DemandForm = {
  mode: "add" | "edit";
  bookingId: string;
  scheduleId?: string;
  installment_name: string;
  demand_amount: string;
  due_date: string;
  who: string; // customer · unit, for the modal subtitle
};

export default function CustomerReceivablesPage() {
  const toast = useToast();
  const { has } = usePermissions();
  const canManage = has("FINANCE_RECORD_PAYMENT");

  const [rows, setRows] = useState<CollectionEntry[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectFilter, setProjectFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshTick, setRefreshTick] = useState(0);
  const [form, setForm] = useState<DemandForm | null>(null);
  const [saving, setSaving] = useState(false);

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
  }, [projectFilter, refreshTick, toast]);

  const totals = useMemo(() => {
    const generated = rows.reduce((s, r) => s + Number(r.demand_amount), 0);
    const pending = rows.reduce((s, r) => s + Number(r.outstanding), 0);
    const overdue = rows.filter((r) => r.is_overdue).reduce((s, r) => s + Number(r.outstanding), 0);
    return { generated, pending, overdue, count: rows.length };
  }, [rows]);

  const whoLabel = (r: CollectionEntry) =>
    `${r.customer_name || "No customer"} · ${r.project_name} ${r.unit_number}`;

  function openEdit(r: CollectionEntry) {
    setForm({
      mode: "edit",
      bookingId: r.booking_id,
      scheduleId: r.payment_schedule_id,
      installment_name: r.installment_name,
      demand_amount: String(r.demand_amount),
      due_date: (r.due_date ?? "").slice(0, 10),
      who: whoLabel(r)
    });
  }

  function openAdd(r: CollectionEntry) {
    setForm({
      mode: "add",
      bookingId: r.booking_id,
      installment_name: "",
      demand_amount: "",
      due_date: "",
      who: whoLabel(r)
    });
  }

  async function saveForm() {
    if (!form) return;
    const amount = Number(form.demand_amount);
    if (!form.installment_name.trim() || !form.due_date || Number.isNaN(amount) || amount < 0) {
      toast.error("Incomplete demand", "Enter a milestone name, a due date and a valid amount.");
      return;
    }
    const body: DemandInput = {
      installment_name: form.installment_name.trim(),
      due_date: form.due_date,
      demand_amount: amount
    };
    setSaving(true);
    try {
      if (form.mode === "edit" && form.scheduleId) {
        await financeService.updateDemand(form.bookingId, form.scheduleId, body);
        toast.success("Demand updated");
      } else {
        await financeService.addDemand(form.bookingId, body);
        toast.success("Demand added");
      }
      setForm(null);
      setRefreshTick((t) => t + 1);
    } catch (e) {
      toast.error("Couldn't save the demand", extractErrorMessage(e));
    } finally {
      setSaving(false);
    }
  }

  async function removeRow(r: CollectionEntry) {
    if (Number(r.paid_amount) > 0) {
      toast.error("Payment recorded", "This demand has a payment against it and can't be deleted.");
      return;
    }
    if (!window.confirm(`Delete the "${r.installment_name}" demand for ${r.customer_name || "this customer"}?`)) {
      return;
    }
    try {
      await financeService.deleteDemand(r.booking_id, r.payment_schedule_id);
      toast.success("Demand deleted");
      setRefreshTick((t) => t + 1);
    } catch (e) {
      toast.error("Couldn't delete the demand", extractErrorMessage(e));
    }
  }

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

  if (canManage) {
    columns.push({
      key: "actions",
      header: "",
      align: "right",
      render: (r) => (
        <span className="row" style={{ gap: "0.4rem", justifyContent: "flex-end" }}>
          <Button size="sm" variant="ghost" onClick={() => openEdit(r)}>Edit</Button>
          <Button size="sm" variant="ghost" onClick={() => openAdd(r)}>Add</Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => void removeRow(r)}
            disabled={Number(r.paid_amount) > 0}
            title={Number(r.paid_amount) > 0 ? "Has a payment — can't delete" : "Delete this demand"}
          >
            Delete
          </Button>
        </span>
      )
    });
  }

  if (loading && rows.length === 0) return <LoadingBlock label="Loading receivables…" />;

  return (
    <>
      <div className="page-header">
        <div className="page-header__titles">
          <h1>Customer Receivables</h1>
          <p>Customer demands generated from each booking&rsquo;s payment schedule. Edit, add or remove a demand here; record collections from the booking.</p>
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
          rowKey={(r) => r.payment_schedule_id}
          empty={<EmptyState title="No receivables" description="Customer demands from bookings appear here." />}
        />
      </Card>

      <Modal
        open={!!form}
        title={form?.mode === "edit" ? "Edit demand" : "Add demand"}
        onClose={() => setForm(null)}
        footer={
          <>
            <Button variant="ghost" onClick={() => setForm(null)}>Cancel</Button>
            <Button onClick={() => void saveForm()} disabled={saving}>{saving ? "Saving…" : "Save"}</Button>
          </>
        }
      >
        {form && (
          <div className="form-grid">
            <p className="muted" style={{ marginTop: 0 }}>{form.who}</p>
            <TextField
              id="demand-name"
              label="Milestone / installment"
              value={form.installment_name}
              maxLength={120}
              placeholder="e.g. On Booking / Plinth / Possession"
              onChange={(e) => setForm({ ...form, installment_name: e.target.value })}
            />
            <TextField
              id="demand-amount"
              label="Demand amount (₹)"
              type="number"
              min={0}
              value={form.demand_amount}
              onChange={(e) => setForm({ ...form, demand_amount: e.target.value })}
            />
            <TextField
              id="demand-due"
              label="Due date"
              type="date"
              value={form.due_date}
              onChange={(e) => setForm({ ...form, due_date: e.target.value })}
            />
          </div>
        )}
      </Modal>
    </>
  );
}
