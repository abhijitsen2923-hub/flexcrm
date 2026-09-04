import { useEffect, useMemo, useState } from "react";

import {
  Button,
  Card,
  DataTable,
  EmptyState,
  LoadingBlock,
  Modal,
  SelectField,
  TextField,
  TextareaField,
  useToast,
  type DataTableColumn
} from "../../components";
import { usePermissions } from "../../hooks/usePermissions";
import { financeService } from "../../services/finance";
import type { FinanceCategory, GstInput, ManualIncome } from "../../types/finance";
import { extractErrorMessage } from "../../utils/errors";
import { formatCurrency, formatDate } from "../../utils/format";
import { EMPTY_GST, GstFields } from "./components/GstFields";

const EMPTY_FORM = {
  title: "",
  category_id: "",
  source: "",
  income_date: new Date().toISOString().slice(0, 10),
  payment_mode: "",
  notes: ""
};

export default function IncomePage() {
  const toast = useToast();
  const { has } = usePermissions();
  const canManage = has("FINANCE_RECORD_PAYMENT");

  const [income, setIncome] = useState<ManualIncome[]>([]);
  const [categories, setCategories] = useState<FinanceCategory[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<ManualIncome | null>(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [gst, setGst] = useState<GstInput>({ ...EMPTY_GST });
  const [saving, setSaving] = useState(false);

  const categoryName = useMemo(() => new Map(categories.map((c) => [c.id, c.name])), [categories]);

  async function refresh() {
    setLoading(true);
    try {
      const [inc, cats] = await Promise.all([
        financeService.listIncome(),
        financeService.listCategories("income")
      ]);
      setIncome(inc);
      setCategories(cats);
    } catch (e) {
      toast.error("Failed to load income", extractErrorMessage(e));
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    void refresh();
  }, []);

  function openCreate() {
    setEditing(null);
    setForm({ ...EMPTY_FORM, income_date: new Date().toISOString().slice(0, 10) });
    setGst({ ...EMPTY_GST });
    setModalOpen(true);
  }
  function openEdit(x: ManualIncome) {
    setEditing(x);
    setForm({
      title: x.title,
      category_id: x.category_id,
      source: x.source ?? "",
      income_date: x.income_date,
      payment_mode: x.payment_mode ?? "",
      notes: x.notes ?? ""
    });
    setGst({
      amount_entered: Number(x.amount_entered),
      gst_applicable: x.gst_applicable,
      gst_treatment: x.gst_treatment ?? "intra_state",
      gst_inclusive: x.gst_inclusive,
      gst_rate: x.gst_rate === null ? null : Number(x.gst_rate),
      tds_amount: Number(x.tds_amount)
    });
    setModalOpen(true);
  }

  async function save() {
    if (!form.title.trim() || !form.category_id) {
      toast.error("Title and category are required");
      return;
    }
    setSaving(true);
    try {
      const payload = {
        ...gst,
        title: form.title,
        category_id: form.category_id,
        source: form.source || null,
        income_date: form.income_date,
        payment_mode: form.payment_mode || null,
        notes: form.notes || null
      };
      if (editing) await financeService.updateIncome(editing.id, payload);
      else await financeService.createIncome(payload);
      toast.success(editing ? "Income updated" : "Income recorded");
      setModalOpen(false);
      await refresh();
    } catch (e) {
      toast.error("Save failed", extractErrorMessage(e));
    } finally {
      setSaving(false);
    }
  }

  async function remove(x: ManualIncome) {
    if (!window.confirm(`Delete income ${x.income_number}?`)) return;
    try {
      await financeService.deleteIncome(x.id);
      toast.success("Deleted");
      await refresh();
    } catch (e) {
      toast.error("Delete failed", extractErrorMessage(e));
    }
  }

  const total = useMemo(() => income.reduce((s, x) => s + Number(x.total_amount), 0), [income]);

  const columns: DataTableColumn<ManualIncome>[] = [
    {
      key: "inc",
      header: "Income",
      render: (x) => (
        <div>
          <strong>{x.title}</strong>
          <div className="muted text-xs">
            {x.income_number} · {categoryName.get(x.category_id) ?? "—"}
            {x.source ? ` · ${x.source}` : ""}
          </div>
        </div>
      )
    },
    { key: "date", header: "Date", render: (x) => formatDate(x.income_date) },
    { key: "amount", header: "Amount", align: "right", render: (x) => <strong>{formatCurrency(x.total_amount, "INR")}</strong> },
    {
      key: "actions",
      header: "",
      align: "right",
      render: (x) =>
        canManage ? (
          <span className="row" style={{ gap: "0.4rem", justifyContent: "flex-end" }}>
            <Button size="sm" variant="ghost" onClick={() => openEdit(x)}>Edit</Button>
            <Button size="sm" variant="ghost" onClick={() => void remove(x)}>Delete</Button>
          </span>
        ) : null
    }
  ];

  if (loading && income.length === 0) return <LoadingBlock label="Loading income…" />;

  const categoryOptions = categories.map((c) => ({ value: c.id, label: c.name }));

  return (
    <>
      <div className="page-header">
        <div className="page-header__titles">
          <h1>Income</h1>
          <p>Non-sale income — interest, rent, misc. Booking/sale revenue appears under Revenue and the Dashboard.</p>
        </div>
        {canManage && <Button onClick={openCreate}>Add Income</Button>}
      </div>

      <Card>
        <div className="muted text-sm" style={{ marginBottom: "0.5rem" }}>
          Total recorded: <strong>{formatCurrency(total, "INR")}</strong>
        </div>
        <DataTable
          columns={columns}
          rows={income}
          rowKey={(x) => x.id}
          empty={<EmptyState title="No income recorded" description="Add interest, rent or other non-sale income." />}
        />
      </Card>

      <Modal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        size="lg"
        title={editing ? `Edit ${editing.income_number}` : "Add Income"}
        footer={
          <>
            <Button variant="secondary" onClick={() => setModalOpen(false)}>Cancel</Button>
            <Button loading={saving} onClick={() => void save()}>Save</Button>
          </>
        }
      >
        <div className="form">
          <TextField id="i-title" label="Title" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required />
          <div className="form-grid">
            <SelectField id="i-cat" label="Category" value={form.category_id} onChange={(e) => setForm({ ...form, category_id: e.target.value })} options={categoryOptions} placeholder="Select a category…" />
            <TextField id="i-source" label="Source (optional)" value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value })} />
            <TextField id="i-date" label="Income date" type="date" value={form.income_date} onChange={(e) => setForm({ ...form, income_date: e.target.value })} required />
            <TextField id="i-mode" label="Payment mode (optional)" value={form.payment_mode} onChange={(e) => setForm({ ...form, payment_mode: e.target.value })} />
          </div>
          <GstFields value={gst} onChange={setGst} />
          <TextareaField id="i-notes" label="Notes" rows={2} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
        </div>
      </Modal>
    </>
  );
}
