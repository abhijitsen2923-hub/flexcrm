import { Pencil, Plus, RefreshCw, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState, type FormEvent } from "react";

import {
  Badge,
  Button,
  ConfirmDialog,
  DataTable,
  EmptyState,
  LoadingBlock,
  Modal,
  Pagination,
  SelectField,
  TextField,
  useToast,
  type DataTableColumn
} from "../components";
import { useDeals } from "../hooks/useDeals";
import { useRealtimeRefresh } from "../realtime";
import { customersService } from "../services/customers";
import type { Customer, Deal, DealStage, DealStatus } from "../types";
import { extractErrorMessage } from "../utils/errors";
import { formatCurrency, formatDate } from "../utils/format";
import {
  dealStageOptions,
  dealStageTone,
  dealStatusOptions,
  dealStatusTone,
  titleCase
} from "../utils/options";


interface FormState {
  customer_id: string;
  title: string;
  amount: string;
  stage: DealStage;
  expected_close: string;
  status: DealStatus;
}


const emptyForm: FormState = {
  customer_id: "",
  title: "",
  amount: "0",
  stage: "discovery",
  expected_close: "",
  status: "open"
};


export default function DealsPage() {
  const [page, setPage] = useState(1);
  const [stageFilter, setStageFilter] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("");

  const query = useMemo(
    () => ({
      page,
      page_size: 20,
      stage: stageFilter || undefined,
      status: statusFilter || undefined
    }),
    [page, stageFilter, statusFilter]
  );

  const { deals, pagination, loading, refresh, createDeal, updateDeal, deleteDeal } = useDeals(query);
  const toast = useToast();

  const [customers, setCustomers] = useState<Customer[]>([]);
  useEffect(() => {
    customersService
      .list({ page: 1, page_size: 100 })
      .then((response) => setCustomers(response.items))
      .catch(() => undefined);
  }, []);

  const customerOptions = useMemo(
    () => customers.map((customer) => ({ value: customer.id, label: customer.company_name })),
    [customers]
  );

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Deal | null>(null);
  const [form, setForm] = useState<FormState>(emptyForm);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<Deal | null>(null);
  const [deleteSubmitting, setDeleteSubmitting] = useState(false);

  useRealtimeRefresh(
    (event) => event.event.startsWith("deal."),
    () => {
      void refresh();
    },
  );

  function openCreate() {
    setEditing(null);
    setForm({ ...emptyForm, customer_id: customers[0]?.id ?? "" });
    setFormError(null);
    setFormOpen(true);
  }

  function openEdit(deal: Deal) {
    setEditing(deal);
    setForm({
      customer_id: deal.customer_id,
      title: deal.title,
      amount: deal.amount,
      stage: deal.stage,
      expected_close: deal.expected_close ?? "",
      status: deal.status
    });
    setFormError(null);
    setFormOpen(true);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setFormError(null);
    try {
      const payload = {
        customer_id: form.customer_id,
        title: form.title.trim(),
        amount: form.amount || "0",
        stage: form.stage,
        expected_close: form.expected_close || null,
        status: form.status
      };
      if (editing) {
        await updateDeal(editing.id, payload);
        toast.success("Deal updated", payload.title);
      } else {
        await createDeal(payload);
        toast.success("Deal created", payload.title);
      }
      setFormOpen(false);
    } catch (submitError) {
      setFormError(extractErrorMessage(submitError));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete() {
    if (!deleting) return;
    setDeleteSubmitting(true);
    try {
      await deleteDeal(deleting.id);
      toast.success("Deal deleted", deleting.title);
      setDeleting(null);
    } catch (deleteError) {
      toast.error("Delete failed", extractErrorMessage(deleteError));
    } finally {
      setDeleteSubmitting(false);
    }
  }

  const columns: DataTableColumn<Deal>[] = [
    {
      key: "title",
      header: "Title",
      render: (deal) => (
        <div>
          <div style={{ fontWeight: 600 }}>{deal.title}</div>
          <div className="text-xs muted">{deal.customer?.company_name ?? "—"}</div>
        </div>
      )
    },
    {
      key: "amount",
      header: "Amount",
      align: "right",
      render: (deal) => formatCurrency(deal.amount)
    },
    {
      key: "stage",
      header: "Stage",
      render: (deal) => <Badge tone={dealStageTone(deal.stage)}>{titleCase(deal.stage)}</Badge>
    },
    {
      key: "status",
      header: "Status",
      render: (deal) => <Badge tone={dealStatusTone(deal.status)}>{titleCase(deal.status)}</Badge>
    },
    {
      key: "close",
      header: "Expected close",
      render: (deal) => <span className="text-sm">{formatDate(deal.expected_close)}</span>
    },
    {
      key: "actions",
      header: "",
      align: "right",
      render: (deal) => (
        <div className="row" style={{ justifyContent: "flex-end" }}>
          <Button variant="ghost" size="sm" icon={<Pencil size={14} />} onClick={() => openEdit(deal)}>
            Edit
          </Button>
          <Button variant="ghost" size="sm" icon={<Trash2 size={14} />} onClick={() => setDeleting(deal)}>
            Delete
          </Button>
        </div>
      )
    }
  ];

  return (
    <>
      <div className="page-header">
        <div className="page-header__titles">
          <h1>Deals</h1>
          <p>Pipeline of in-flight and closed deals.</p>
        </div>
        <div className="page-header__actions">
          <Button variant="secondary" size="sm" icon={<RefreshCw size={14} />} onClick={() => void refresh()} loading={loading}>
            Refresh
          </Button>
          <Button icon={<Plus size={14} />} onClick={openCreate} disabled={customers.length === 0}>
            New deal
          </Button>
        </div>
      </div>

      <div className="card" style={{ padding: 0 }}>
        <div className="row" style={{ padding: "1rem 1.25rem", borderBottom: "1px solid var(--color-border)", gap: "0.5rem" }}>
          <select
            className="select"
            value={stageFilter}
            onChange={(event) => {
              setStageFilter(event.target.value);
              setPage(1);
            }}
            aria-label="Filter by stage"
          >
            <option value="">All stages</option>
            {dealStageOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          <select
            className="select"
            value={statusFilter}
            onChange={(event) => {
              setStatusFilter(event.target.value);
              setPage(1);
            }}
            aria-label="Filter by status"
          >
            <option value="">All statuses</option>
            {dealStatusOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
        <div className="table-wrap" style={{ border: "none", borderRadius: 0, boxShadow: "none" }}>
          {loading && deals.length === 0 ? (
            <LoadingBlock label="Loading deals…" />
          ) : (
            <DataTable
              columns={columns}
              rows={deals}
              rowKey={(deal) => deal.id}
              empty={<EmptyState title="No deals yet" description="Create a deal to start tracking revenue." />}
            />
          )}
        </div>
        <Pagination
          page={pagination.page}
          pageSize={pagination.page_size}
          total={pagination.total}
          totalPages={pagination.total_pages}
          onPageChange={setPage}
        />
      </div>

      <Modal
        open={formOpen}
        onClose={() => setFormOpen(false)}
        title={editing ? "Edit deal" : "New deal"}
        footer={
          <>
            <Button variant="secondary" onClick={() => setFormOpen(false)} disabled={submitting}>
              Cancel
            </Button>
            <Button type="submit" form="deal-form" loading={submitting} disabled={submitting}>
              {editing ? "Save changes" : "Create deal"}
            </Button>
          </>
        }
      >
        <form id="deal-form" className="form" onSubmit={handleSubmit}>
          <SelectField
            id="deal-customer"
            label="Customer"
            value={form.customer_id}
            onChange={(event) => setForm({ ...form, customer_id: event.target.value })}
            options={customerOptions}
            required
            placeholder={customerOptions.length === 0 ? "No customers available" : "Select a customer"}
          />
          <TextField
            id="deal-title"
            label="Title"
            value={form.title}
            onChange={(event) => setForm({ ...form, title: event.target.value })}
            required
          />
          <div className="form-grid">
            <TextField
              id="deal-amount"
              label="Amount"
              type="number"
              min={0}
              step="0.01"
              value={form.amount}
              onChange={(event) => setForm({ ...form, amount: event.target.value })}
            />
            <TextField
              id="deal-close-date"
              label="Expected close"
              type="date"
              value={form.expected_close}
              onChange={(event) => setForm({ ...form, expected_close: event.target.value })}
            />
          </div>
          <div className="form-grid">
            <SelectField
              id="deal-stage"
              label="Stage"
              value={form.stage}
              onChange={(event) => setForm({ ...form, stage: event.target.value as DealStage })}
              options={dealStageOptions}
            />
            <SelectField
              id="deal-status"
              label="Status"
              value={form.status}
              onChange={(event) => setForm({ ...form, status: event.target.value as DealStatus })}
              options={dealStatusOptions}
            />
          </div>
          {formError && <div className="error-banner">{formError}</div>}
        </form>
      </Modal>

      <ConfirmDialog
        open={Boolean(deleting)}
        title="Delete deal?"
        description={deleting ? `"${deleting.title}" will be soft-deleted.` : undefined}
        confirmLabel="Delete"
        destructive
        loading={deleteSubmitting}
        onCancel={() => setDeleting(null)}
        onConfirm={handleDelete}
      />
    </>
  );
}
