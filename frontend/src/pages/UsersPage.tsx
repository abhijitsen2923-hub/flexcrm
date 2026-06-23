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
import type { CustomRole } from "../services/customRoles";
import { customRolesService } from "../services/customRoles";
import type { LeadIndustry, Organization, PaginatedResponse, User, UserPermissions, UserRole } from "../types";
import { ROLES_BY_INDUSTRY } from "../types/crm";
import { extractErrorMessage } from "../utils/errors";
import { formatDate } from "../utils/format";
import { titleCase } from "../utils/options";
import { RolesTab } from "./users/components/RolesTab";


const emptyList: PaginatedResponse<User> = {
  items: [],
  pagination: { page: 1, page_size: 20, total: 0, total_pages: 1 }
};

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

// Sentinel prefix for custom role option values in the select dropdown.
const CUSTOM_ROLE_PREFIX = "custom:";

interface CreateFormState {
  first_name: string;
  last_name: string;
  email: string;
  password: string;
  phone: string;
  // Either a UserRole string, or "custom:<uuid>" for custom roles.
  roleValue: string;
  status: "active" | "invited";
}

function emptyForm(defaultRoleValue: string): CreateFormState {
  return {
    first_name: "",
    last_name: "",
    email: "",
    password: "",
    phone: "",
    roleValue: defaultRoleValue,
    status: "active",
  };
}

function roleLabel(user: User): string {
  if (user.role === "custom") return user.custom_role_name ? `Custom: ${user.custom_role_name}` : "Custom";
  return titleCase(user.role);
}


export default function UsersPage() {
  const { user: currentUser } = useAuth();
  const toast = useToast();
  const { has: hasPerm } = usePermissions();
  const canView = hasPerm("USER_VIEW");
  const canManage = hasPerm("USER_MANAGE");

  const [activeTab, setActiveTab] = useState<"users" | "roles">("users");

  const [page, setPage] = useState(1);
  const [data, setData] = useState<PaginatedResponse<User>>(emptyList);
  const [loading, setLoading] = useState(false);

  const [org, setOrg] = useState<Organization | null>(null);
  const [customRoles, setCustomRoles] = useState<CustomRole[]>([]);

  useEffect(() => {
    if (!canManage) return;
    let cancelled = false;
    void Promise.all([
      organizationsService.me(),
      customRolesService.list(),
    ]).then(([orgData, roles]) => {
      if (!cancelled) {
        setOrg(orgData);
        setCustomRoles(roles.filter((r) => r.is_active));
      }
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
      setData(await usersService.list(query));
    } catch (error) {
      toast.error("Failed to load users", extractErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }, [canView, query, toast]);

  useEffect(() => { void refresh(); }, [refresh]);

  // --- Create modal ------------------------------------------------------
  const [createOpen, setCreateOpen] = useState(false);
  const [form, setForm] = useState<CreateFormState>(() => emptyForm(assignableRoles[1] ?? "support"));
  const [createError, setCreateError] = useState<string | null>(null);
  const [createSubmitting, setCreateSubmitting] = useState(false);

  function openCreate() {
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
      const isCustom = form.roleValue.startsWith(CUSTOM_ROLE_PREFIX);
      const role = isCustom ? "custom" : form.roleValue;
      const custom_role_id = isCustom ? form.roleValue.slice(CUSTOM_ROLE_PREFIX.length) : undefined;

      await usersService.create({
        first_name: form.first_name.trim(),
        last_name: form.last_name.trim(),
        email: form.email.trim(),
        password: form.password,
        phone: form.phone.trim() || null,
        role: role as UserRole,
        status: form.status,
        custom_role_id,
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

  function closeDrawer() { setDrawerUser(null); setDrawerPerms(null); }

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
          <div style={{ fontWeight: 600 }}>{user.first_name} {user.last_name}</div>
          <div className="text-xs muted">{user.email}</div>
        </div>
      )
    },
    {
      key: "role",
      header: "Role",
      render: (user) => (
        <Badge tone={user.role === "custom" ? "neutral" : "primary"}>
          {roleLabel(user)}
        </Badge>
      )
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

  // Role dropdown options: predefined roles + separator + active custom roles.
  const roleOptions = [
    ...assignableRoles.map((r) => ({ value: r, label: titleCase(r) })),
    ...(customRoles.length > 0
      ? [
          { value: "__separator__", label: "── Custom roles ──" },
          ...customRoles.map((r) => ({
            value: `${CUSTOM_ROLE_PREFIX}${r.id}`,
            label: `Custom: ${r.name}`,
          })),
        ]
      : []),
  ];

  return (
    <>
      <div className="page-header">
        <div className="page-header__titles">
          <h1>Users &amp; Roles</h1>
          <p>Manage team members and define custom permission templates.</p>
        </div>
        {activeTab === "users" && (
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
              <Button icon={<Plus size={14} />} onClick={openCreate}>New user</Button>
            )}
          </div>
        )}
      </div>

      {/* Tab bar */}
      <div style={{ display: "flex", gap: "0.25rem", marginBottom: "1.25rem", borderBottom: "1px solid var(--color-border)" }}>
        {(["users", "roles"] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            style={{
              padding: "0.5rem 1rem",
              border: "none",
              background: "transparent",
              fontWeight: activeTab === tab ? 600 : 400,
              color: activeTab === tab ? "var(--color-primary)" : "var(--color-text-muted)",
              borderBottom: activeTab === tab ? "2px solid var(--color-primary)" : "2px solid transparent",
              cursor: "pointer",
              marginBottom: "-1px",
            }}
          >
            {titleCase(tab)}
          </button>
        ))}
      </div>

      {activeTab === "roles" ? (
        <RolesTab canManage={canManage} />
      ) : (
        <>
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

          {/* Create-user modal */}
          <Modal
            open={createOpen}
            onClose={() => setCreateOpen(false)}
            title="New user"
            footer={
              <>
                <Button variant="secondary" onClick={() => setCreateOpen(false)} disabled={createSubmitting}>Cancel</Button>
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
                  onChange={(e) => setForm({ ...form, first_name: e.target.value })}
                  required
                />
                <TextField
                  id="user-last-name"
                  label="Last name"
                  value={form.last_name}
                  onChange={(e) => setForm({ ...form, last_name: e.target.value })}
                  required
                />
              </div>
              <TextField
                id="user-email"
                label="Email"
                type="email"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                required
              />
              <TextField
                id="user-password"
                label="Initial password"
                type="password"
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
                required
                hint="At least 8 characters."
              />
              <TextField
                id="user-phone"
                label="Phone"
                value={form.phone}
                onChange={(e) => setForm({ ...form, phone: e.target.value })}
                placeholder="Optional"
              />
              <SelectField
                id="user-role"
                label="Role"
                value={form.roleValue}
                onChange={(e) => setForm({ ...form, roleValue: e.target.value })}
                options={roleOptions.filter((o) => o.value !== "__separator__").map((o) => ({
                  value: o.value,
                  label: o.label,
                }))}
                hint={`Predefined + custom roles for your ${titleCase(orgIndustry)} workspace.`}
              />
              {createError && <div className="error-banner">{createError}</div>}
            </form>
          </Modal>

          {/* Permissions drawer */}
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
                {drawerUser?.role === "custom" && drawerUser.custom_role_name && (
                  <div className="text-sm" style={{ padding: "0.4rem 0.6rem", background: "var(--color-bg-muted)", borderRadius: 6 }}>
                    Role template: <strong>{drawerUser.custom_role_name}</strong>
                  </div>
                )}
                <div className="muted text-sm">
                  <strong>{drawerPerms.role_defaults.length}</strong> from role ·{" "}
                  <strong>{drawerPerms.granted.length}</strong> explicit grant{drawerPerms.granted.length === 1 ? "" : "s"} ·{" "}
                  <strong>{drawerPerms.effective.length}</strong> effective.
                </div>
                <div className="text-xs muted">
                  Role permissions are checked and locked. Grants add on top.
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
                        title={isDefault ? "Comes from the role template" : "Click to grant / revoke"}
                      >
                        <input
                          type="checkbox"
                          checked={isChecked}
                          disabled={disabled}
                          onChange={(e) => void togglePermission(code, e.target.checked)}
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
      )}
    </>
  );
}
