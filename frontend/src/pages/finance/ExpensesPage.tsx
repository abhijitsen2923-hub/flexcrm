import { useEffect, useMemo, useState } from "react";

import {
  Badge,
  Button,
  Card,
  DataTable,
  EmptyState,
  FileUploadField,
  KpiCard,
  Modal,
  SelectField,
  SkeletonTable,
  TextField,
  TextareaField,
  useToast,
  type DataTableColumn
} from "../../components";
import { usePermissions } from "../../hooks/usePermissions";
import { financeService } from "../../services/finance";
import type {
  Expense,
  ExpenseStatus,
  FinanceCategory,
  FinanceDocument,
  GstInput,
  Vendor
} from "../../types/finance";
import { extractErrorMessage } from "../../utils/errors";
import { formatCurrency, formatDate } from "../../utils/format";
import { EMPTY_GST, GstFields } from "./components/GstFields";

const STATUS_TONE: Record<ExpenseStatus, "success" | "warning" | "danger" | "info" | "neutral"> = {
  draft: "neutral",
  submitted: "warning",
  approved: "info",
  rejected: "danger",
  paid: "success"
};

const STATUS_OPTIONS = [
  { value: "", label: "All statuses" },
  { value: "draft", label: "Draft" },
  { value: "submitted", label: "Submitted" },
  { value: "approved", label: "Approved" },
  { value: "rejected", label: "Rejected" },
  { value: "paid", label: "Paid" }
];

interface FormState {
  title: string;
  category_id: string;
  vendor_id: string;
  expense_date: string;
  department: string;
  payment_mode: string;
  notes: string;
  gst: GstInput;
  submit: boolean;
}

const EMPTY_FORM: FormState = {
  title: "",
  category_id: "",
  vendor_id: "",
  expense_date: new Date().toISOString().slice(0, 10),
  department: "",
  payment_mode: "",
  notes: "",
  gst: { ...EMPTY_GST },
  submit: false
};

function inCurrentMonth(iso: string): boolean {
  const d = new Date(iso);
  const now = new Date();
  return d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth();
}

export default function ExpensesPage() {
  const toast = useToast();
  const { has } = usePermissions();
  const canSubmit = has("FINANCE_EXPENSE_SUBMIT");
  const canApprove = has("FINANCE_EXPENSE_APPROVE");
  const canPay = has("FINANCE_RECORD_PAYMENT");

  const [expenses, setExpenses] = useState<Expense[]>([]);
  const [categories, setCategories] = useState<FinanceCategory[]>([]);
  const [vendors, setVendors] = useState<Vendor[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [categoryFilter, setCategoryFilter] = useState<string>("");

  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Expense | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [busyAction, setBusyAction] = useState(false);
  const [docs, setDocs] = useState<FinanceDocument[]>([]);

  const categoryName = useMemo(() => new Map(categories.map((c) => [c.id, c.name])), [categories]);
  const vendorName = useMemo(() => new Map(vendors.map((v) => [v.id, v.name])), [vendors]);

  async function loadExpenses() {
    const params: { status?: ExpenseStatus; category_id?: string } = {};
    if (statusFilter) params.status = statusFilter as ExpenseStatus;
    if (categoryFilter) params.category_id = categoryFilter;
    setExpenses(await financeService.listExpenses(params));
  }

  async function refreshAll() {
    setLoading(true);
    try {
      // Fire the expense list in parallel with the lookups — the list is what
      // the user is waiting for, so it must not queue behind categories/vendors.
      await Promise.all([
        loadExpenses(),
        financeService.listCategories("expense").then(setCategories),
        financeService.listVendors({ is_active: true }).then(setVendors)
      ]);
    } catch (e) {
      toast.error("Failed to load expenses", extractErrorMessage(e));
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    void refreshAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    void loadExpenses().catch((e) => toast.error("Filter failed", extractErrorMessage(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter, categoryFilter]);

  function openCreate() {
    setEditing(null);
    setForm({ ...EMPTY_FORM, gst: { ...EMPTY_GST } });
    setDocs([]);
    setModalOpen(true);
  }

  async function openExpense(x: Expense) {
    setEditing(x);
    setForm({
      title: x.title,
      category_id: x.category_id,
      vendor_id: x.vendor_id ?? "",
      expense_date: x.expense_date,
      department: x.department ?? "",
      payment_mode: x.payment_mode ?? "",
      notes: x.notes ?? "",
      gst: {
        amount_entered: Number(x.amount_entered),
        gst_applicable: x.gst_applicable,
        gst_treatment: x.gst_treatment ?? "intra_state",
        gst_inclusive: x.gst_inclusive,
        gst_rate: x.gst_rate === null ? null : Number(x.gst_rate),
        tds_amount: Number(x.tds_amount)
      },
      submit: false
    });
    setDocs([]);
    setModalOpen(true);
    try {
      setDocs(await financeService.listDocuments("expense", x.id));
    } catch {
      /* non-critical */
    }
  }

  const editable = !editing || editing.status === "draft" || editing.status === "rejected";

  function buildPayload() {
    return {
      ...form.gst,
      title: form.title,
      notes: form.notes || null,
      category_id: form.category_id,
      vendor_id: form.vendor_id || null,
      expense_date: form.expense_date,
      department: form.department || null,
      payment_mode: form.payment_mode || null
    };
  }

  async function save() {
    if (!form.title.trim() || !form.category_id) {
      toast.error("Title and category are required");
      return;
    }
    setSaving(true);
    try {
      if (editing) {
        await financeService.updateExpense(editing.id, buildPayload());
        toast.success("Expense updated");
      } else {
        await financeService.createExpense({ ...buildPayload(), submit: form.submit });
        toast.success(form.submit ? "Expense submitted" : "Expense saved as draft");
      }
      setModalOpen(false);
      await loadExpenses();
    } catch (e) {
      toast.error("Save failed", extractErrorMessage(e));
    } finally {
      setSaving(false);
    }
  }

  async function runAction(fn: () => Promise<unknown>, okMsg: string) {
    setBusyAction(true);
    try {
      await fn();
      toast.success(okMsg);
      setModalOpen(false);
      await loadExpenses();
    } catch (e) {
      toast.error("Action failed", extractErrorMessage(e));
    } finally {
      setBusyAction(false);
    }
  }

  async function uploadDoc(file: File) {
    if (!editing) return;
    const fd = new FormData();
    fd.append("file", file);
    fd.append("owner_type", "expense");
    fd.append("owner_id", editing.id);
    fd.append("doc_type", "bill");
    try {
      await financeService.uploadDocument(fd);
      setDocs(await financeService.listDocuments("expense", editing.id));
      toast.success("Attachment uploaded");
    } catch (e) {
      toast.error("Upload failed", extractErrorMessage(e));
    }
  }

  async function openDoc(doc: FinanceDocument) {
    try {
      const url = await financeService.downloadDocument(doc.id);
      window.open(url, "_blank", "noopener");
    } catch (e) {
      toast.error("Could not open document", extractErrorMessage(e));
    }
  }

  async function downloadVoucher() {
    if (!editing) return;
    try {
      await financeService.downloadPdf(`/finance/expenses/${editing.id}/voucher.pdf`, `expense-${editing.expense_number}.pdf`);
    } catch (e) {
      toast.error("Could not generate voucher", extractErrorMessage(e));
    }
  }

  const kpis = useMemo(() => {
    const monthTotal = expenses
      .filter((x) => inCurrentMonth(x.expense_date))
      .reduce((s, x) => s + Number(x.net_payable), 0);
    const pending = expenses.filter((x) => x.status === "submitted").length;
    const paidTotal = expenses
      .filter((x) => x.status === "paid" && inCurrentMonth(x.expense_date))
      .reduce((s, x) => s + Number(x.net_payable), 0);
    return { monthTotal, pending, paidTotal };
  }, [expenses]);

  const columns: DataTableColumn<Expense>[] = [
    {
      key: "expense",
      header: "Expense",
      render: (x) => (
        <div>
          <strong>{x.title}</strong>
          <div className="muted text-xs">
            {x.expense_number} · {categoryName.get(x.category_id) ?? "—"}
            {x.vendor_id ? ` · ${vendorName.get(x.vendor_id) ?? ""}` : ""}
          </div>
        </div>
      )
    },
    { key: "date", header: "Date", render: (x) => formatDate(x.expense_date) },
    { key: "amount", header: "Net payable", align: "right", render: (x) => <strong>{formatCurrency(x.net_payable, "INR")}</strong> },
    { key: "status", header: "Status", render: (x) => <Badge tone={STATUS_TONE[x.status]}>{x.status}</Badge> }
  ];

  const categoryOptions = categories.map((c) => ({ value: c.id, label: c.name }));
  const vendorOptions = [{ value: "", label: "— none —" }, ...vendors.map((v) => ({ value: v.id, label: v.name }))];

  return (
    <>
      <div className="page-header">
        <div className="page-header__titles">
          <h1>Expenses</h1>
          <p>Record, approve and pay business expenses.</p>
        </div>
        {canSubmit && <Button onClick={openCreate}>Add Expense</Button>}
      </div>

      <div className="kpi-grid">
        <KpiCard label="This month" value={formatCurrency(kpis.monthTotal, "INR")} />
        <KpiCard label="Pending approval" value={String(kpis.pending)} />
        <KpiCard label="Paid this month" value={formatCurrency(kpis.paidTotal, "INR")} />
      </div>

      <Card>
        <div className="row" style={{ gap: "0.6rem", marginBottom: "0.75rem", flexWrap: "wrap" }}>
          <SelectField id="f-status" label="" aria-label="Filter by status" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} options={STATUS_OPTIONS} />
          <SelectField
            id="f-cat"
            label=""
            aria-label="Filter by category"
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
            options={[{ value: "", label: "All categories" }, ...categoryOptions]}
          />
        </div>
        {loading && expenses.length === 0 ? (
          <SkeletonTable cols={5} rows={8} />
        ) : (
          <DataTable
            columns={columns}
            rows={expenses}
            rowKey={(x) => x.id}
            onRowClick={(x) => void openExpense(x)}
            empty={<EmptyState title="No expenses" description="Add an expense to get started." />}
          />
        )}
      </Card>

      <Modal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        size="lg"
        title={editing ? `${editing.expense_number} · ${editing.title}` : "Add Expense"}
        footer={
          <div className="row row--between" style={{ width: "100%", flexWrap: "wrap", gap: "0.5rem" }}>
            <div className="row" style={{ gap: "0.4rem", flexWrap: "wrap" }}>
              {editing && canApprove && editing.status === "submitted" && (
                <>
                  <Button size="sm" loading={busyAction} onClick={() => void runAction(() => financeService.approveExpense(editing!.id), "Approved")}>Approve</Button>
                  <Button size="sm" variant="danger" loading={busyAction} onClick={() => void runAction(() => financeService.rejectExpense(editing!.id, window.prompt("Reason for rejection?") || "Rejected"), "Rejected")}>Reject</Button>
                </>
              )}
              {editing && canPay && editing.status === "approved" && (
                <Button size="sm" loading={busyAction} onClick={() => void runAction(() => financeService.markExpensePaid(editing!.id, {}), "Marked paid")}>Mark paid</Button>
              )}
              {editing && canSubmit && (editing.status === "draft" || editing.status === "rejected") && (
                <>
                  <Button size="sm" loading={busyAction} onClick={() => void runAction(() => financeService.submitExpense(editing!.id), "Submitted")}>Submit</Button>
                  <Button size="sm" variant="ghost" loading={busyAction} onClick={() => void runAction(() => financeService.deleteExpense(editing!.id), "Deleted")}>Delete</Button>
                </>
              )}
            </div>
            <div className="row" style={{ gap: "0.4rem" }}>
              <Button variant="secondary" onClick={() => setModalOpen(false)}>Close</Button>
              {editable && canSubmit && <Button loading={saving} onClick={() => void save()}>{editing ? "Save" : "Save draft"}</Button>}
            </div>
          </div>
        }
      >
        <div className="form">
          {editing && <Badge tone={STATUS_TONE[editing.status]}>{editing.status}</Badge>}
          {editing?.rejected_reason && <div className="error-banner">Rejected: {editing.rejected_reason}</div>}

          <TextField id="e-title" label="Title" value={form.title} disabled={!editable} onChange={(e) => setForm({ ...form, title: e.target.value })} required />
          <div className="form-grid">
            <SelectField id="e-cat" label="Category" value={form.category_id} disabled={!editable} onChange={(e) => setForm({ ...form, category_id: e.target.value })} options={categoryOptions} placeholder="Select a category…" />
            <SelectField id="e-vendor" label="Vendor (optional)" value={form.vendor_id} disabled={!editable} onChange={(e) => setForm({ ...form, vendor_id: e.target.value })} options={vendorOptions} />
            <TextField id="e-date" label="Expense date" type="date" value={form.expense_date} disabled={!editable} onChange={(e) => setForm({ ...form, expense_date: e.target.value })} required />
            <TextField id="e-dept" label="Department (optional)" value={form.department} disabled={!editable} onChange={(e) => setForm({ ...form, department: e.target.value })} />
            <TextField id="e-mode" label="Payment mode (optional)" value={form.payment_mode} disabled={!editable} onChange={(e) => setForm({ ...form, payment_mode: e.target.value })} />
          </div>

          {editable ? (
            <GstFields value={form.gst} onChange={(gst) => setForm({ ...form, gst })} />
          ) : (
            <div className="muted text-sm">
              Amount {formatCurrency(editing?.amount_entered, "INR")} · GST{" "}
              {formatCurrency(Number(editing?.cgst_amount ?? 0) + Number(editing?.sgst_amount ?? 0) + Number(editing?.igst_amount ?? 0), "INR")} ·
              Net payable <strong>{formatCurrency(editing?.net_payable, "INR")}</strong>
            </div>
          )}

          <TextareaField id="e-notes" label="Notes" rows={2} value={form.notes} disabled={!editable} onChange={(e) => setForm({ ...form, notes: e.target.value })} />

          {!editing && canSubmit && (
            <label className="row" style={{ gap: "0.5rem", alignItems: "center" }}>
              <input type="checkbox" checked={form.submit} onChange={(e) => setForm({ ...form, submit: e.target.checked })} />
              <span>Submit for approval immediately</span>
            </label>
          )}

          {editing && (
            <div>
              <Button size="sm" variant="secondary" onClick={() => void downloadVoucher()}>Download voucher (PDF)</Button>
            </div>
          )}

          {editing && (
            <div className="stack" style={{ gap: "0.4rem" }}>
              <div className="muted text-xs" style={{ textTransform: "uppercase", letterSpacing: ".04em" }}>Attachments</div>
              {docs.length > 0 ? (
                <div className="stack" style={{ gap: "0.25rem" }}>
                  {docs.map((d) => (
                    <button key={d.id} type="button" className="link text-sm" style={{ textAlign: "left" }} onClick={() => void openDoc(d)}>
                      {d.file_name || d.doc_type || "Attachment"}
                    </button>
                  ))}
                </div>
              ) : (
                <span className="muted text-sm">No attachments yet.</span>
              )}
              {canSubmit && <FileUploadField buttonLabel="Attach bill / receipt" onFileSelected={uploadDoc} />}
            </div>
          )}
        </div>
      </Modal>
    </>
  );
}
