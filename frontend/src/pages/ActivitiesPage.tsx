import { Plus, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";

import {
  Badge,
  Button,
  EmptyState,
  LoadingBlock,
  Modal,
  Pagination,
  SelectField,
  TextareaField,
  useToast
} from "../components";
import { useRealtimeEvent } from "../realtime";
import { activitiesService } from "../services/activities";
import { customersService } from "../services/customers";
import type {
  Activity,
  ActivityListResponse,
  ActivityType,
  Customer
} from "../types";
import { extractErrorMessage } from "../utils/errors";
import { formatRelative } from "../utils/format";
import { activityTypeOptions, titleCase } from "../utils/options";


const emptyList: ActivityListResponse = {
  items: [],
  pagination: { page: 1, page_size: 20, total: 0, total_pages: 1 }
};


interface FormState {
  customer_id: string;
  type: ActivityType;
  note: string;
}


const emptyForm: FormState = {
  customer_id: "",
  type: "note",
  note: ""
};


export default function ActivitiesPage() {
  const [page, setPage] = useState(1);
  const [typeFilter, setTypeFilter] = useState<string>("");
  const [data, setData] = useState<ActivityListResponse>(emptyList);
  const [loading, setLoading] = useState(false);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const toast = useToast();

  const query = useMemo(
    () => ({ page, page_size: 20, type: typeFilter || undefined }),
    [page, typeFilter]
  );

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const response = await activitiesService.list(query);
      setData(response);
    } catch (error) {
      toast.error("Failed to load activities", extractErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }, [query, toast]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    customersService
      .list({ page: 1, page_size: 100 })
      .then((response) => setCustomers(response.items))
      .catch(() => undefined);
  }, []);

  useRealtimeEvent((event) => {
    if (event.event.startsWith("activity.") || event.event.startsWith("customer.")) {
      void refresh();
    }
  });

  const customerOptions = useMemo(
    () => customers.map((customer) => ({ value: customer.id, label: customer.company_name })),
    [customers]
  );

  const [formOpen, setFormOpen] = useState(false);
  const [form, setForm] = useState<FormState>(emptyForm);
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function openCreate() {
    setForm({ ...emptyForm, customer_id: customers[0]?.id ?? "" });
    setFormError(null);
    setFormOpen(true);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setFormError(null);
    try {
      await activitiesService.create({
        customer_id: form.customer_id,
        type: form.type,
        note: form.note.trim()
      });
      toast.success("Activity logged");
      setFormOpen(false);
      await refresh();
    } catch (error) {
      setFormError(extractErrorMessage(error));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <div className="page-header">
        <div className="page-header__titles">
          <h1>Activities</h1>
          <p>Notes, calls, meetings, and other touchpoints.</p>
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
          <Button icon={<Plus size={14} />} onClick={openCreate} disabled={customers.length === 0}>
            Log activity
          </Button>
        </div>
      </div>

      <div className="card" style={{ padding: 0 }}>
        <div className="row" style={{ padding: "1rem 1.25rem", borderBottom: "1px solid var(--color-border)" }}>
          <select
            className="select"
            value={typeFilter}
            onChange={(event) => {
              setTypeFilter(event.target.value);
              setPage(1);
            }}
            aria-label="Filter by type"
          >
            <option value="">All types</option>
            {activityTypeOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        <div style={{ padding: "1rem 1.25rem" }}>
          {loading && data.items.length === 0 ? (
            <LoadingBlock label="Loading activities…" />
          ) : data.items.length === 0 ? (
            <EmptyState title="No activities yet" description="Log your first interaction with a customer." />
          ) : (
            <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: "0.75rem" }}>
              {data.items.map((activity: Activity) => (
                <li
                  key={activity.id}
                  style={{ border: "1px solid var(--color-border)", borderRadius: "0.5rem", padding: "0.75rem 1rem", background: "var(--color-surface)" }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.5rem" }}>
                    <strong style={{ fontSize: "0.9rem" }}>
                      {activity.customer?.company_name ?? "(unknown customer)"}
                    </strong>
                    <Badge tone="info">{titleCase(activity.type)}</Badge>
                  </div>
                  <div className="text-sm" style={{ marginTop: "0.35rem", color: "var(--color-text)" }}>
                    {activity.note}
                  </div>
                  <div className="text-xs muted" style={{ marginTop: "0.25rem" }}>
                    {formatRelative(activity.created_at)}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        <Pagination
          page={data.pagination.page}
          pageSize={data.pagination.page_size}
          total={data.pagination.total}
          totalPages={data.pagination.total_pages}
          onPageChange={setPage}
        />
      </div>

      <Modal
        open={formOpen}
        onClose={() => setFormOpen(false)}
        title="Log activity"
        footer={
          <>
            <Button variant="secondary" onClick={() => setFormOpen(false)} disabled={submitting}>
              Cancel
            </Button>
            <Button type="submit" form="activity-form" loading={submitting} disabled={submitting}>
              Save activity
            </Button>
          </>
        }
      >
        <form id="activity-form" className="form" onSubmit={handleSubmit}>
          <SelectField
            id="activity-customer"
            label="Customer"
            value={form.customer_id}
            onChange={(event) => setForm({ ...form, customer_id: event.target.value })}
            options={customerOptions}
            required
            placeholder={customerOptions.length === 0 ? "No customers available" : "Select a customer"}
          />
          <SelectField
            id="activity-type"
            label="Type"
            value={form.type}
            onChange={(event) => setForm({ ...form, type: event.target.value as ActivityType })}
            options={activityTypeOptions}
          />
          <TextareaField
            id="activity-note"
            label="Note"
            value={form.note}
            onChange={(event) => setForm({ ...form, note: event.target.value })}
            required
            rows={4}
          />
          {formError && <div className="error-banner">{formError}</div>}
        </form>
      </Modal>
    </>
  );
}
