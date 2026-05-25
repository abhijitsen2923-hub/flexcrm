import { Pencil, Plus, RefreshCw, Trash2 } from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";

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
import { useTasks } from "../hooks/useTasks";
import { useRealtimeEvent } from "../realtime";
import type { Task, TaskPriority, TaskStatus } from "../types";
import { extractErrorMessage } from "../utils/errors";
import { formatDateTime } from "../utils/format";
import {
  taskPriorityOptions,
  taskPriorityTone,
  taskStatusOptions,
  taskStatusTone,
  titleCase
} from "../utils/options";


interface FormState {
  title: string;
  description: string;
  due_date: string;
  priority: TaskPriority;
  status: TaskStatus;
}


const emptyForm: FormState = {
  title: "",
  description: "",
  due_date: "",
  priority: "medium",
  status: "pending"
};


function toDateTimeLocal(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const pad = (value: number) => value.toString().padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}


export default function TasksPage() {
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [priorityFilter, setPriorityFilter] = useState<string>("");

  const query = useMemo(
    () => ({
      page,
      page_size: 20,
      status: statusFilter || undefined,
      priority: priorityFilter || undefined
    }),
    [page, statusFilter, priorityFilter]
  );

  const { tasks, pagination, loading, refresh, createTask, updateTask, deleteTask } = useTasks(query);
  const toast = useToast();

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Task | null>(null);
  const [form, setForm] = useState<FormState>(emptyForm);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<Task | null>(null);
  const [deleteSubmitting, setDeleteSubmitting] = useState(false);

  useRealtimeEvent((event) => {
    if (event.event.startsWith("task.")) {
      void refresh();
    }
  });

  function openCreate() {
    setEditing(null);
    setForm(emptyForm);
    setFormError(null);
    setFormOpen(true);
  }

  function openEdit(task: Task) {
    setEditing(task);
    setForm({
      title: task.title,
      description: task.description ?? "",
      due_date: toDateTimeLocal(task.due_date),
      priority: task.priority,
      status: task.status
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
        title: form.title.trim(),
        description: form.description.trim() || null,
        due_date: form.due_date ? new Date(form.due_date).toISOString() : null,
        priority: form.priority,
        status: form.status
      };
      if (editing) {
        await updateTask(editing.id, payload);
        toast.success("Task updated", payload.title);
      } else {
        await createTask(payload);
        toast.success("Task created", payload.title);
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
      await deleteTask(deleting.id);
      toast.success("Task deleted", deleting.title);
      setDeleting(null);
    } catch (deleteError) {
      toast.error("Delete failed", extractErrorMessage(deleteError));
    } finally {
      setDeleteSubmitting(false);
    }
  }

  const columns: DataTableColumn<Task>[] = [
    {
      key: "title",
      header: "Title",
      render: (task) => (
        <div>
          <div style={{ fontWeight: 600 }}>{task.title}</div>
          {task.description && (
            <div className="text-xs muted" style={{ marginTop: "0.15rem" }}>
              {task.description.length > 80 ? `${task.description.slice(0, 80)}…` : task.description}
            </div>
          )}
        </div>
      )
    },
    {
      key: "priority",
      header: "Priority",
      render: (task) => <Badge tone={taskPriorityTone(task.priority)}>{titleCase(task.priority)}</Badge>
    },
    {
      key: "status",
      header: "Status",
      render: (task) => <Badge tone={taskStatusTone(task.status)}>{titleCase(task.status)}</Badge>
    },
    {
      key: "due",
      header: "Due",
      render: (task) => <span className="text-sm">{formatDateTime(task.due_date)}</span>
    },
    {
      key: "actions",
      header: "",
      align: "right",
      render: (task) => (
        <div className="row" style={{ justifyContent: "flex-end" }}>
          <Button variant="ghost" size="sm" icon={<Pencil size={14} />} onClick={() => openEdit(task)}>
            Edit
          </Button>
          <Button variant="ghost" size="sm" icon={<Trash2 size={14} />} onClick={() => setDeleting(task)}>
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
          <h1>Tasks</h1>
          <p>Operational to-dos, follow-ups, and overdue items.</p>
        </div>
        <div className="page-header__actions">
          <Button variant="secondary" size="sm" icon={<RefreshCw size={14} />} onClick={() => void refresh()} loading={loading}>
            Refresh
          </Button>
          <Button icon={<Plus size={14} />} onClick={openCreate}>
            New task
          </Button>
        </div>
      </div>

      <div className="card" style={{ padding: 0 }}>
        <div className="row" style={{ padding: "1rem 1.25rem", borderBottom: "1px solid var(--color-border)", gap: "0.5rem" }}>
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
            {taskStatusOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          <select
            className="select"
            value={priorityFilter}
            onChange={(event) => {
              setPriorityFilter(event.target.value);
              setPage(1);
            }}
            aria-label="Filter by priority"
          >
            <option value="">All priorities</option>
            {taskPriorityOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
        <div className="table-wrap" style={{ border: "none", borderRadius: 0, boxShadow: "none" }}>
          {loading && tasks.length === 0 ? (
            <LoadingBlock label="Loading tasks…" />
          ) : (
            <DataTable
              columns={columns}
              rows={tasks}
              rowKey={(task) => task.id}
              empty={<EmptyState title="No tasks yet" description="Add a task to start tracking follow-ups." />}
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
        title={editing ? "Edit task" : "New task"}
        footer={
          <>
            <Button variant="secondary" onClick={() => setFormOpen(false)} disabled={submitting}>
              Cancel
            </Button>
            <Button type="submit" form="task-form" loading={submitting} disabled={submitting}>
              {editing ? "Save changes" : "Create task"}
            </Button>
          </>
        }
      >
        <form id="task-form" className="form" onSubmit={handleSubmit}>
          <TextField
            id="task-title"
            label="Title"
            value={form.title}
            onChange={(event) => setForm({ ...form, title: event.target.value })}
            required
          />
          <TextareaField
            id="task-description"
            label="Description"
            value={form.description}
            onChange={(event) => setForm({ ...form, description: event.target.value })}
            rows={3}
          />
          <div className="form-grid">
            <TextField
              id="task-due"
              label="Due date"
              type="datetime-local"
              value={form.due_date}
              onChange={(event) => setForm({ ...form, due_date: event.target.value })}
            />
            <SelectField
              id="task-priority"
              label="Priority"
              value={form.priority}
              onChange={(event) => setForm({ ...form, priority: event.target.value as TaskPriority })}
              options={taskPriorityOptions}
            />
          </div>
          <SelectField
            id="task-status"
            label="Status"
            value={form.status}
            onChange={(event) => setForm({ ...form, status: event.target.value as TaskStatus })}
            options={taskStatusOptions}
          />
          {formError && <div className="error-banner">{formError}</div>}
        </form>
      </Modal>

      <ConfirmDialog
        open={Boolean(deleting)}
        title="Delete task?"
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
