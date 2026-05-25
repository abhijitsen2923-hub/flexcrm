import { Plus, RefreshCw, ShieldCheck } from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";

import {
  Badge,
  Button,
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
import { useAuth } from "../hooks/useAuth";
import { usePermissions } from "../hooks/usePermissions";
import { organizationsService } from "../services/organizations";
import { permissionsService } from "../services/permissions";
import { usersService } from "../services/users";
import type { LeadIndustry, Organization, PaginatedResponse, User, UserPermissions, UserRole } from "../types";
import { ROLES_BY_INDUSTRY } from "../types/crm";
import { extractErrorMessage } from "../utils/errors";
import { formatDate } from "../utils/format";
import { titleCase } from "../utils/options";


const emptyList: PaginatedResponse<User> = {
  items: [],
  pagination: { page: 1, page_size: 20, total: 0, total_pages: 1 }
};

// Full catalog of permission codes. Mirrors backend `PermissionCode` enum.
// Used by the drawer to render a fixed checkbox grid.
const ALL_PERMISSION_CODES: ReadonlyArray<string> = [
  "DASHBOARD_VIEW",
  "LEAD_VIEW", "LEAD_MANAGE", "LEAD_IMPORT", "LEAD_DOCS_MANAGE",
  "CUSTOMER_VIEW", "CUSTOMER_MANAGE",
  "DEAL_VIEW", "DEAL_MANAGE",
  "TASK_VIEW", "TASK_MANAGE",
  "ACTIVITY_VIEW", "ACTIVITY_MANAGE",
  "FINANCE_VIEW", "FINANCE_RECORD_PAYMENT", "FINANCE_REFUND",
  "HR_VIEW", "HR_MANAGE",
  "USER_VIEW", "USER_MANAGE",
  "ORG_MANAGE",
  "ANALYTICS_VIEW", "REPORTS_VIEW",
  "EXPORT_DATA",
];


interface CreateFormState {
  first_name: string;
  last_name: string;
  email: string;
  password: string;
  phone: string;
  role: UserRole;
  status: "active" | "invited";
}


function emptyForm(defaultRole: UserRole): CreateFormState {
  return {
    first_name: "",
    last_name: "",
    email: "",
    password: "",
    phone: "",
    role: defaultRole,
    status: "active",
  };
}


export default function UsersPage() {
  const { user: currentUser } = useAuth();
  const toast = useToast();
  const { has: hasPerm } = usePermissions();
  const canView = hasPerm("USER_VIEW");
  const canManage = hasPerm("USER_MANAGE");

  const [page, setPage] = useState(1);
  const [data, setData] = useState<PaginatedResponse<User>>(emptyList);
  const [loading, setLoading] = useState(false);

  // Org currency lookup is unrelated — but we need the org's business_type to
  // filter the role dropdown in the create modal.
  const [org, setOrg] = useState<Organization | null>(null);
  useEffect(() => {
    if (!canManage) return;
    let cancelled = false;
    void organizationsService.me().then((value) => {
      if (!cancelled) setOrg(value);
    }).catch(() => undefined);
    return () => { cancelled = true; };
  }, [canManage]);

  const orgIndustry: LeadIndustry = org?.business_type ?? "education";
  const assignableRoles: UserRole[] = ROLES_BY_INDUSTRY[orgIndustry];

  const query = useMemo(() => ({ page, page_size: 20 }), [page]);

  const refresh = useCallback(async () => {
    if (!canView) return;
    setLoading(true);
    try {
      const response = await usersService.list(query);
      setData(response);
    } catch (error) {
      toast.error("Failed to load users", extractErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }, [canView, query, toast]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // --- Create modal ------------------------------------------------------
  const [createOpen, setCreateOpen] = useState(false);
  const [form, setForm] = useState<CreateFormState>(() => emptyForm(assignableRoles[1] ?? "support"));
  const [createError, setCreateError] = useState<string | null>(null);
  const [createSubmitting, setCreateSubmitting] = useState(false);

  function openCreate() {
    // Default to the second role (skipping `owner`) so admins don't accidentally
    // promote every new hire to org owner.
    const defaultRole = assignableRoles.find((r) => r !== "owner") ?? assignableRoles[0];
    setForm(emptyForm(defaultRole));
    setCreateError(null);
    setCreateOpen(true);
  }

  async function handleCreateSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCreateSubmitting(true);
    setCreateError(null);
    try {
      await usersService.create({
        first_name: form.first_name.trim(),
        last_name: form.last_name.trim(),
        email: form.email.trim(),
        password: form.password,
        phone: form.phone.trim() || null,
        role: form.role,
        status: form.status,
      });
      toast.success("User created", `${form.first_name} ${form.last_name}`);
      setCreateOpen(false);
      await refresh();
    } catch (error) {
      setCreateError(extractErrorMessage(error));
    } finally {
      setCreateSubmitting(false);
    }
  }

  // --- Permissions drawer ------------------------------------------------
  const [drawerUser, setDrawerUser] = useState<User | null>(null);
  const [drawerPerms, setDrawerPerms] = useState<UserPermissions | null>(null);
  const [drawerLoading, setDrawerLoading] = useState(false);
  const [drawerSavingCode, setDrawerSavingCode] = useState<string | null>(null);

  async function openDrawer(user: User) {
    setDrawerUser(user);
    setDrawerLoading(true);
    setDrawerPerms(null);
    try {
      setDrawerPerms(await permissionsService.getForUser(user.id));
    } catch (error) {
      toast.error("Could not load permissions", extractErrorMessage(error));
    } finally {
      setDrawerLoading(false);
    }
  }

  function closeDrawer() {
    setDrawerUser(null);
    setDrawerPerms(null);
  }

  async function togglePermission(code: string, shouldGrant: boolean) {
    if (!drawerUser) return;
    setDrawerSavingCode(code);
    try {
      if (shouldGrant) {
        await permissionsService.grant(drawerUser.id, code);
      } else {
        await permissionsService.revoke(drawerUser.id, code);
      }
      setDrawerPerms(await permissionsService.getForUser(drawerUser.id));
      toast.success(shouldGrant ? "Permission granted" : "Permission revoked", code);
    } catch (error) {
      toast.error("Could not update permission", extractErrorMessage(error));
    } finally {
      setDrawerSavingCode(null);
    }
  }

  if (!canView) {
    return (
      <EmptyState
        title="Restricted area"
        description="You do not have permission to view the user directory. Ask an admin for USER_VIEW."
      />
    );
  }

  const columns: DataTableColumn<User>[] = [
    {
      key: "name",
      header: "Name",
      render: (user) => (
        <div>
          <div style={{ fontWeight: 600 }}>
            {user.first_name} {user.last_name}
          </div>
          <div className="text-xs muted">{user.email}</div>
        </div>
      )
    },
    {
      key: "role",
      header: "Role",
      render: (user) => <Badge tone="primary">{titleCase(user.role)}</Badge>
    },
    {
      key: "status",
      header: "Status",
      render: (user) => (
        <Badge tone={user.status === "active" ? "success" : "neutral"}>{titleCase(user.status)}</Badge>
      )
    },
    {
      key: "phone",
      header: "Phone",
      render: (user) => user.phone || <span className="muted">—</span>
    },
    {
      key: "created",
      header: "Created",
      render: (user) => <span className="text-sm">{formatDate(user.created_at)}</span>
    },
    {
      key: "actions",
      header: "",
      align: "right",
      render: (user) =>
        canManage && currentUser?.id !== user.id ? (
          <Button
            size="sm"
            variant="ghost"
            icon={<ShieldCheck size={14} />}
            onClick={() => void openDrawer(user)}
          >
            Permissions
          </Button>
        ) : (
          <span className="muted text-xs">—</span>
        )
    }
  ];

  const roleDefaults = new Set(drawerPerms?.role_defaults ?? []);
  const grantedCodes = new Set((drawerPerms?.granted ?? []).map((g) => g.permission_code));

  return (
    <>
      <div className="page-header">
        <div className="page-header__titles">
          <h1>Users</h1>
          <p>Directory of team members with access to this workspace.</p>
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
          {canManage && (
            <Button icon={<Plus size={14} />} onClick={openCreate}>
              New user
            </Button>
          )}
        </div>
      </div>

      <div className="card" style={{ padding: 0 }}>
        <div className="table-wrap" style={{ border: "none", borderRadius: 0, boxShadow: "none" }}>
          {loading && data.items.length === 0 ? (
            <LoadingBlock label="Loading users…" />
          ) : (
            <DataTable
              columns={columns}
              rows={data.items}
              rowKey={(user) => user.id}
              empty={<EmptyState title="No users yet" />}
            />
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

      {/* Create-user modal — role dropdown filtered by the org's vertical so an
          Education org never sees `visa_coordinator` and vice-versa. */}
      <Modal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title="New user"
        footer={
          <>
            <Button variant="secondary" onClick={() => setCreateOpen(false)} disabled={createSubmitting}>
              Cancel
            </Button>
            <Button type="submit" form="user-create-form" loading={createSubmitting} disabled={createSubmitting}>
              Create user
            </Button>
          </>
        }
      >
        <form id="user-create-form" className="form" onSubmit={handleCreateSubmit}>
          <div className="form-grid">
            <TextField
              id="user-first-name"
              label="First name"
              value={form.first_name}
              onChange={(event) => setForm({ ...form, first_name: event.target.value })}
              required
            />
            <TextField
              id="user-last-name"
              label="Last name"
              value={form.last_name}
              onChange={(event) => setForm({ ...form, last_name: event.target.value })}
              required
            />
          </div>
          <TextField
            id="user-email"
            label="Email"
            type="email"
            value={form.email}
            onChange={(event) => setForm({ ...form, email: event.target.value })}
            required
          />
          <TextField
            id="user-password"
            label="Initial password"
            type="password"
            value={form.password}
            onChange={(event) => setForm({ ...form, password: event.target.value })}
            required
            hint="At least 8 characters."
          />
          <TextField
            id="user-phone"
            label="Phone"
            value={form.phone}
            onChange={(event) => setForm({ ...form, phone: event.target.value })}
            placeholder="Optional"
          />
          <SelectField
            id="user-role"
            label="Role"
            value={form.role}
            onChange={(event) => setForm({ ...form, role: event.target.value as UserRole })}
            options={assignableRoles.map((role) => ({
              value: role,
              label: titleCase(role),
            }))}
            hint={`Roles available for your ${titleCase(orgIndustry)} workspace.`}
          />
          {createError && <div className="error-banner">{createError}</div>}
        </form>
      </Modal>

      {/* Permissions drawer — checkbox grid with role-default chips shown as
          disabled-checked, and explicit grants toggleable. */}
      <Modal
        open={Boolean(drawerUser)}
        onClose={closeDrawer}
        title={drawerUser ? `Permissions — ${drawerUser.first_name} ${drawerUser.last_name}` : ""}
        footer={<Button onClick={closeDrawer}>Done</Button>}
      >
        {drawerLoading ? (
          <LoadingBlock label="Loading permissions…" />
        ) : drawerPerms ? (
          <div className="stack" style={{ gap: "0.75rem" }}>
            <div className="muted text-sm">
              <strong>{drawerPerms.role_defaults.length}</strong> permission
              {drawerPerms.role_defaults.length === 1 ? "" : "s"} from role default ·{" "}
              <strong>{drawerPerms.granted.length}</strong> explicit grant
              {drawerPerms.granted.length === 1 ? "" : "s"} ·{" "}
              <strong>{drawerPerms.effective.length}</strong> effective.
            </div>
            <div className="text-xs muted">
              Role-default permissions are checked and locked — to remove a default, change the user's role.
              Grants override on top of defaults.
            </div>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))",
                gap: "0.5rem",
              }}
            >
              {ALL_PERMISSION_CODES.map((code) => {
                const isDefault = roleDefaults.has(code);
                const isGranted = grantedCodes.has(code);
                const isChecked = isDefault || isGranted;
                const disabled = isDefault || drawerSavingCode === code;
                return (
                  <label
                    key={code}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "0.5rem",
                      padding: "0.4rem 0.5rem",
                      border: "1px solid var(--color-border)",
                      borderRadius: 6,
                      background: isDefault ? "var(--color-bg-muted)" : "transparent",
                      cursor: disabled && !isDefault ? "wait" : isDefault ? "not-allowed" : "pointer",
                    }}
                    title={isDefault ? "Comes from the role default" : "Click to grant / revoke"}
                  >
                    <input
                      type="checkbox"
                      checked={isChecked}
                      disabled={disabled}
                      onChange={(event) => void togglePermission(code, event.target.checked)}
                    />
                    <span style={{ fontSize: "0.85rem" }}>{code}</span>
                  </label>
                );
              })}
            </div>
          </div>
        ) : null}
      </Modal>
    </>
  );
}
