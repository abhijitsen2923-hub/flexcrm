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
  TextareaField,
  useToast,
  type DataTableColumn
} from "../../components";
import { usePermissions } from "../../hooks/usePermissions";
import { financeService } from "../../services/finance";
import type { Budget, FinanceCategory } from "../../types/finance";
import { extractErrorMessage } from "../../utils/errors";
import { formatCurrency } from "../../utils/format";

const thisMonth = () => new Date().toISOString().slice(0, 7);

type Form = {
  name: string;
  period_key: string;
  category_id: string;
  department: string;
  amount: string;
  notes: string;
};

const emptyForm = (period: string): Form => ({
  name: "",
  period_key: period,
  category_id: "",
  department: "",
  amount: "",
  notes: ""
});

function usageTone(pct: number): "success" | "warning" | "danger" {
  if (pct > 100) return "danger";
  if (pct >= 80) return "warning";
  return "success";
}

export default function BudgetsPage() {
  const toast = useToast();
  const { has } = usePermissions();
  const canManage = has("FINANCE_SETTINGS_MANAGE");

  const [period, setPeriod] = useState(thisMonth());
  const [budgets, setBudgets] = useState<Budget[]>([]);
  const [categories, setCategories] = useState<FinanceCategory[]>([]);
  const [loading, setLoading] = useState(true);

  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Budget | null>(null);
  const [form, setForm] = useState<Form>(emptyForm(thisMonth()));
  const [saving, setSaving] = useState(false);

  const categoryOptions = useMemo(
    () => categories.filter((c) => c.is_active).map((c) => ({ value: c.id, label: c.name })),
    [categories]
  );

  async function refresh(periodKey: string) {
    setLoading(true);
    try {
      const [list, cats] = await Promise.all([
        financeService.listBudgets(periodKey),
        categories.length ? Promise.resolve(categories) : financeService.listCategories("expense")
      ]);
      setBudgets(list);
      if (!categories.length) setCategories(cats);
    } catch (e) {
      toast.error("Failed to load budgets", extractErrorMessage(e));
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    void refresh(period);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [period]);

  function openCreate() {
    setEditing(null);
    setForm(emptyForm(period));
    setModalOpen(true);
  }

  function openEdit(b: Budget) {
    setEditing(b);
    setForm({
      name: b.name,
      period_key: b.period_key,
      category_id: b.category_id ?? "",
      department: b.department ?? "",
      amount: String(Number(b.amount)),
      notes: b.notes ?? ""
    });
    setModalOpen(true);
  }

  async function save() {
    if (!form.name.trim() || !form.amount) {
      toast.error("Name and amount are required");
      return;
    }
    setSaving(true);
    const payload = {
      name: form.name.trim(),
      period_key: form.period_key,
      category_id: form.category_id || null,
      department: form.department.trim() || null,
      amount: Number(form.amount),
      notes: form.notes.trim() || null
    };
    try {
      if (editing) {
        await financeService.updateBudget(editing.id, payload);
        toast.success("Budget updated");
      } else {
        await financeService.createBudget(payload);
        toast.success("Budget created");
      }
      setModalOpen(false);
      // If saved into a different month, jump the filter there (useEffect
      // reloads); otherwise refresh the current month in place.
      if (form.period_key !== period) {
        setPeriod(form.period_key);
      } else {
        await refresh(period);
      }
    } catch (e) {
      toast.error("Save failed", extractErrorMessage(e));
    } finally {
      setSaving(false);
    }
  }

  async function remove(b: Budget) {
    if (!window.confirm(`Delete budget "${b.name}"?`)) return;
    try {
      await financeService.deleteBudget(b.id);
      toast.success("Budget deleted");
      await refresh(period);
    } catch (e) {
      toast.error("Delete failed", extractErrorMessage(e));
    }
  }

  const totals = useMemo(() => {
    const budget = budgets.reduce((s, b) => s + Number(b.amount), 0);
    const actual = budgets.reduce((s, b) => s + Number(b.actual), 0);
    return { budget, actual, remaining: budget - actual };
  }, [budgets]);

  const columns: DataTableColumn<Budget>[] = [
    {
      key: "name",
      header: "Budget",
      render: (b) => (
        <div>
          <strong>{b.name}</strong>
          <div className="muted text-xs">
            {b.category_name ?? "All categories"}
            {b.department ? ` · ${b.department}` : ""}
          </div>
        </div>
      )
    },
    { key: "amount", header: "Budgeted", align: "right", render: (b) => formatCurrency(b.amount, "INR") },
    { key: "actual", header: "Actual", align: "right", render: (b) => formatCurrency(b.actual, "INR") },
    {
      key: "variance",
      header: "Remaining",
      align: "right",
      render: (b) => (
        <strong style={{ color: Number(b.variance) < 0 ? "var(--danger, #dc2626)" : undefined }}>
          {formatCurrency(b.variance, "INR")}
        </strong>
      )
    },
    {
      key: "used",
      header: "Used",
      render: (b) => (
        <div style={{ minWidth: 120 }}>
          <div className="row" style={{ justifyContent: "space-between", marginBottom: 2 }}>
            <Badge tone={usageTone(b.used_pct)}>{b.used_pct}%</Badge>
          </div>
          <div style={{ height: 6, borderRadius: 3, background: "var(--surface-2, #e5e7eb)", overflow: "hidden" }}>
            <div
              style={{
                height: "100%",
                width: `${Math.min(100, b.used_pct)}%`,
                background:
                  usageTone(b.used_pct) === "danger"
                    ? "#dc2626"
                    : usageTone(b.used_pct) === "warning"
                    ? "#d97706"
                    : "#16a34a"
              }}
            />
          </div>
        </div>
      )
    },
  ];

  if (canManage) {
    columns.push({
      key: "actions",
      header: "",
      align: "right",
      render: (b: Budget) => (
        <span className="row" style={{ gap: "0.4rem", justifyContent: "flex-end" }}>
          <Button size="sm" variant="ghost" onClick={() => openEdit(b)}>Edit</Button>
          <Button size="sm" variant="ghost" onClick={() => void remove(b)}>Delete</Button>
        </span>
      )
    });
  }

  if (loading && budgets.length === 0) return <LoadingBlock label="Loading budgets…" />;

  return (
    <>
      <div className="page-header">
        <div className="page-header__titles">
          <h1>Budgets</h1>
          <p>Set a monthly spending target per category or department; actuals track live against expenses.</p>
        </div>
        {canManage && <Button onClick={openCreate}>New Budget</Button>}
      </div>

      <div className="row" style={{ gap: "0.5rem", alignItems: "flex-end", marginBottom: "1rem" }}>
        <TextField id="b-period" label="Month" type="month" value={period} onChange={(e) => setPeriod(e.target.value)} />
      </div>

      <div className="kpi-grid">
        <KpiCard label="Budgeted" value={formatCurrency(totals.budget, "INR")} />
        <KpiCard label="Actual spend" value={formatCurrency(totals.actual, "INR")} />
        <KpiCard label="Remaining" value={formatCurrency(totals.remaining, "INR")} />
      </div>

      <Card>
        <DataTable
          columns={columns}
          rows={budgets}
          rowKey={(b) => b.id}
          empty={
            <EmptyState
              title="No budgets for this month"
              description={canManage ? "Create a budget to start tracking spend against a target." : "No budgets have been set for this month."}
            />
          }
        />
      </Card>

      <Modal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        title={editing ? "Edit Budget" : "New Budget"}
        footer={
          <>
            <Button variant="secondary" onClick={() => setModalOpen(false)}>Cancel</Button>
            <Button loading={saving} onClick={() => void save()}>{editing ? "Save" : "Create"}</Button>
          </>
        }
      >
        <div className="form">
          <TextField id="f-name" label="Budget name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
          <div className="form-grid">
            <TextField id="f-period" label="Month" type="month" value={form.period_key} onChange={(e) => setForm({ ...form, period_key: e.target.value })} required />
            <TextField id="f-amount" label="Amount (₹)" type="number" min="0" step="0.01" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} required />
          </div>
          <SelectField
            id="f-category"
            label="Category (optional)"
            value={form.category_id}
            onChange={(e) => setForm({ ...form, category_id: e.target.value })}
            options={categoryOptions}
            placeholder="All categories"
          />
          <TextField id="f-dept" label="Department (optional)" value={form.department} onChange={(e) => setForm({ ...form, department: e.target.value })} />
          <TextareaField id="f-notes" label="Notes" rows={2} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
          {form.category_id ? (
            <p className="muted text-sm">Actual spend counts only expenses in this category for the selected month.</p>
          ) : (
            <p className="muted text-sm">With no category, actual spend counts all expenses for the selected month.</p>
          )}
        </div>
      </Modal>
    </>
  );
}
