import { Download, Pencil, Plus, RefreshCw, Search, Trash2 } from "lucide-react";
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
  TextareaField,
  useToast,
  type DataTableColumn
} from "../components";
import { useCustomers } from "../hooks/useCustomers";
import { usePermissions } from "../hooks/usePermissions";
import { useRealtimeEvent } from "../realtime";
import type { Customer, CustomerLifecycleStage, CustomerStatus } from "../types";
import { extractErrorMessage } from "../utils/errors";
import { formatDate } from "../utils/format";
import { customerStatusOptions, customerStatusTone, titleCase } from "../utils/options";


function lifecycleTone(stage: CustomerLifecycleStage): "success" | "info" | "warning" | "danger" | "neutral" {
  if (stage === "onboarding") return "info";
  if (stage === "active" || stage === "renewed") return "success";
  if (stage === "renewal_due") return "warning";
  if (stage === "at_risk" || stage === "churned") return "danger";
  return "neutral";
}


interface FormState {
  company_name: string;
  contact_name: string;
  email: string;
  phone: string;
  address: string;
  source: string;
  status: CustomerStatus;
}


const emptyForm: FormState = {
  company_name: "",
  contact_name: "",
  email: "",
  phone: "",
  address: "",
  source: "",
  status: "prospect"
};


export default function CustomersPage() {
  const [page, setPage] = useState(1);
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("");

  const query = useMemo(
    () => ({
      page,
      page_size: 20,
      search: search || undefined,
      status: statusFilter || undefined
    }),
    [page, search, statusFilter]
  );

  const { customers, pagination, loading, refresh, createCustomer, updateCustomer, deleteCustomer } =
    useCustomers(query);

  const { has: hasPerm } = usePermissions();
  const canManage = hasPerm("CUSTOMER_MANAGE");
  const canExport = hasPerm("EXPORT_DATA");
  const toast = useToast();

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Customer | null>(null);
  const [form, setForm] = useState<FormState>(emptyForm);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const [deleting, setDeleting] = useState<Customer | null>(null);
  const [deleteSubmitting, setDeleteSubmitting] = useState(false);

  useRealtimeEvent((event) => {
    if (event.event.startsWith("customer.")) {
      void refresh();
    }
  });

  function openCreate() {
    setEditing(null);
    setForm(emptyForm);
    setFormError(null);
    setFormOpen(true);
  }

  function openEdit(customer: Customer) {
    setEditing(customer);
    setForm({
      company_name: customer.company_name,
      contact_name: customer.contact_name,
      email: customer.email ?? "",
      phone: customer.phone ?? "",
      address: customer.address ?? "",
      source: customer.source ?? "",
      status: customer.status
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
        company_name: form.company_name.trim(),
        contact_name: form.contact_name.trim(),
        email: form.email.trim() || null,
        phone: form.phone.trim() || null,
        address: form.address.trim() || null,
        source: form.source.trim() || null,
        status: form.status
      };
      if (editing) {
        await updateCustomer(editing.id, payload);
        toast.success("Customer updated", payload.company_name);
      } else {
        await createCustomer(payload);
        toast.success("Customer created", payload.company_name);
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
      await deleteCustomer(deleting.id);
      toast.success("Customer deleted", deleting.company_name);
      setDeleting(null);
    } catch (deleteError) {
      toast.error("Delete failed", extractErrorMessage(deleteError));
    } finally {
      setDeleteSubmitting(false);
    }
  }

  function handleSearchSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPage(1);
    setSearch(searchInput.trim());
  }

  const columns: DataTableColumn<Customer>[] = [
    {
      key: "company",
      header: "Company",
      render: (customer) => (
        <div>
          <div style={{ fontWeight: 600 }}>{customer.company_name}</div>
          <div className="text-xs muted">{customer.contact_name}</div>
        </div>
      )
    },
    {
      key: "contact",
      header: "Contact",
      render: (customer) => (
        <div className="text-sm">
          {customer.email && <div>{customer.email}</div>}
          {customer.phone && <div className="muted text-xs">{customer.phone}</div>}
          {!customer.email && !customer.phone && <span className="muted">—</span>}
        </div>
      )
    },
    {
      key: "source",
      header: "Lead source",
      render: (customer) => customer.source || <span className="muted">—</span>
    },
    {
      key: "origin",
      header: "Origin",
      render: (customer) =>
        customer.source_lead ? (
          <span title={`Promoted from lead #${customer.source_lead.lead_number}`}>
            <Badge tone="success">Lead #{customer.source_lead.lead_number}</Badge>
          </span>
        ) : (
          <span className="muted text-xs">Manual</span>
        )
    },
    {
      key: "lifecycle",
      header: "Lifecycle",
      render: (customer) => (
        <Badge tone={lifecycleTone(customer.lifecycle_stage)}>{titleCase(customer.lifecycle_stage)}</Badge>
      )
    },
    {
      key: "ltv",
      header: "LTV",
      align: "right",
      render: (customer) => <span title="Sum of won deals + renewals">₹{Number(customer.ltv ?? 0).toLocaleString()}</span>
    },
    {
      key: "status",
      header: "Status",
      render: (customer) => (
        <Badge tone={customerStatusTone(customer.status)}>{titleCase(customer.status)}</Badge>
      )
    },
    {
      key: "created",
      header: "Created",
      render: (customer) => <span className="text-sm">{formatDate(customer.created_at)}</span>
    },
    {
      key: "actions",
      header: "",
      align: "right",
      render: (customer) =>
        canManage ? (
          <div className="row" style={{ justifyContent: "flex-end" }}>
            <Button variant="ghost" size="sm" icon={<Pencil size={14} />} onClick={() => openEdit(customer)}>
              Edit
            </Button>
            <Button
              variant="ghost"
              size="sm"
              icon={<Trash2 size={14} />}
              onClick={() => setDeleting(customer)}
            >
              Delete
            </Button>
          </div>
        ) : null
    }
  ];

  useEffect(() => {
    if (pagination.total_pages > 0 && page > pagination.total_pages) {
      setPage(pagination.total_pages);
    }
  }, [page, pagination.total_pages]);

  return (
    <>
      <div className="page-header">
        <div className="page-header__titles">
          <h1>Customer Management</h1>
          <p>Auto-created from leads on Sold, plus any customers added manually.</p>
        </div>
        <div className="page-header__actions">
          <Button
            variant="secondary"
            size="sm"
            icon={<RefreshCw size={14} />}
            onClick={() => void refresh()}
            loading={loading}
          >
            Refresh
          </Button>
          {canExport && (
            <Button
              variant="secondary"
              size="sm"
              icon={<Download size={14} />}
              onClick={() => window.location.assign("/api/v1/exports/customers.csv")}
            >
              Export CSV
            </Button>
          )}
          {canManage && (
            <Button icon={<Plus size={14} />} onClick={openCreate}>
              New customer
            </Button>
          )}
        </div>
      </div>

      <div className="card" style={{ padding: 0 }}>
        <div
          className="row row--between"
          style={{ padding: "1rem 1.25rem", borderBottom: "1px solid var(--color-border)" }}
        >
          <form onSubmit={handleSearchSubmit} className="search-input">
            <span className="search-input__icon">
              <Search size={14} />
            </span>
            <input
              className="input"
              placeholder="Search company, contact, email…"
              value={searchInput}
              onChange={(event) => setSearchInput(event.target.value)}
            />
          </form>
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
            {customerStatusOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
        <div className="table-wrap" style={{ border: "none", borderRadius: 0, boxShadow: "none" }}>
          {loading && customers.length === 0 ? (
            <LoadingBlock label="Loading customers…" />
          ) : (
            <DataTable
              columns={columns}
              rows={customers}
              rowKey={(customer) => customer.id}
              empty={<EmptyState title="No customers yet" description="Create your first customer to get started." />}
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
        title={editing ? "Edit customer" : "New customer"}
        footer={
          <>
            <Button variant="secondary" onClick={() => setFormOpen(false)} disabled={submitting}>
              Cancel
            </Button>
            <Button
              type="submit"
              form="customer-form"
              loading={submitting}
              disabled={submitting}
            >
              {editing ? "Save changes" : "Create customer"}
            </Button>
          </>
        }
      >
        <form id="customer-form" className="form" onSubmit={handleSubmit}>
          <div className="form-grid">
            <TextField
              id="customer-company"
              label="Company name"
              value={form.company_name}
              onChange={(event) => setForm({ ...form, company_name: event.target.value })}
              required
            />
            <TextField
              id="customer-contact"
              label="Contact name"
              value={form.contact_name}
              onChange={(event) => setForm({ ...form, contact_name: event.target.value })}
              required
            />
          </div>
          <div className="form-grid">
            <TextField
              id="customer-email"
              label="Email"
              type="email"
              value={form.email}
              onChange={(event) => setForm({ ...form, email: event.target.value })}
            />
            <TextField
              id="customer-phone"
              label="Phone"
              value={form.phone}
              onChange={(event) => setForm({ ...form, phone: event.target.value })}
            />
          </div>
          <div className="form-grid">
            <TextField
              id="customer-source"
              label="Source"
              value={form.source}
              onChange={(event) => setForm({ ...form, source: event.target.value })}
              placeholder="e.g. referral, website"
            />
            <SelectField
              id="customer-status"
              label="Status"
              value={form.status}
              onChange={(event) => setForm({ ...form, status: event.target.value as CustomerStatus })}
              options={customerStatusOptions}
            />
          </div>
          <TextareaField
            id="customer-address"
            label="Address"
            value={form.address}
            onChange={(event) => setForm({ ...form, address: event.target.value })}
            rows={3}
          />
          {formError && <div className="error-banner">{formError}</div>}
        </form>
      </Modal>

      <ConfirmDialog
        open={Boolean(deleting)}
        title="Delete customer?"
        description={
          deleting
            ? `“${deleting.company_name}” will be soft-deleted. Linked leads or deals stay in place.`
            : undefined
        }
        confirmLabel="Delete"
        destructive
        loading={deleteSubmitting}
        onCancel={() => setDeleting(null)}
        onConfirm={handleDelete}
      />
    </>
  );
}
