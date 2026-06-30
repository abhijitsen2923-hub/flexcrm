import { RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";

import { Button, ConfirmDialog, EmptyState, LoadingBlock, useToast } from "../components";
import { useAuth } from "../hooks/useAuth";
import { adminService } from "../services/admin";
import type { ModuleKey, Organization } from "../types";
import { extractErrorMessage } from "../utils/errors";

type Industry = Organization["business_type"];

function StatusBadge({ org }: { org: Organization }) {
  const [label, color] = org.is_deleted
    ? ["Archived", "#6b7280"]
    : org.is_active
      ? ["Active", "#15803d"]
      : ["Disabled", "#b45309"];
  return (
    <span
      className="badge"
      style={{ background: `${color}1a`, color, border: `1px solid ${color}40` }}
    >
      {label}
    </span>
  );
}

const MODULE_LABELS: Record<ModuleKey, string> = {
  deals: "Deals",
  tasks: "Tasks",
  activities: "Activities",
  finance: "Finance",
  hr: "HR",
  inventory: "Inventory",
  bookings: "Bookings",
  site_visits: "Site Visits",
  projects: "Projects",
};

const CORE_MODULES: ModuleKey[] = ["deals", "tasks", "activities"];
const OPS_MODULES: ModuleKey[] = ["finance", "hr"];
const RE_MODULES: ModuleKey[] = ["inventory", "bookings", "site_visits", "projects"];

const INDUSTRY_LABEL: Record<Industry, string> = {
  education: "Education",
  travel: "Travel",
  real_estate: "Real Estate",
};

function defaultsForIndustry(industry: Industry): Record<ModuleKey, boolean> {
  const isRE = industry === "real_estate";
  return {
    deals: true,
    tasks: true,
    activities: true,
    finance: false,
    hr: false,
    inventory: isRE,
    bookings: isRE,
    site_visits: isRE,
    projects: isRE,
  };
}

function ModuleRow({
  label,
  checked,
  disabled,
  onChange,
}: {
  label: string;
  checked: boolean;
  disabled: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        padding: "0.25rem 0",
        cursor: disabled ? "not-allowed" : "pointer",
        userSelect: "none",
      }}
    >
      <span style={{ fontSize: "0.875rem" }}>{label}</span>
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        style={{ width: 16, height: 16, cursor: disabled ? "not-allowed" : "pointer", flexShrink: 0 }}
      />
    </label>
  );
}

function ModuleGroup({
  title,
  keys,
  org,
  disabled,
  onToggle,
}: {
  title: string;
  keys: ModuleKey[];
  org: Organization;
  disabled: boolean;
  onToggle: (key: ModuleKey, val: boolean) => void;
}) {
  return (
    <div style={{ marginBottom: "0.875rem" }}>
      <div
        className="text-xs muted"
        style={{ textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 600, marginBottom: "0.25rem" }}
      >
        {title}
      </div>
      {keys.map((key) => (
        <ModuleRow
          key={key}
          label={MODULE_LABELS[key]}
          checked={org.modules?.[key] ?? false}
          disabled={disabled}
          onChange={(val) => onToggle(key, val)}
        />
      ))}
    </div>
  );
}

export function PlatformAdminPage() {
  const { user } = useAuth();
  const toast = useToast();
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<Record<string, boolean>>({});
  const [includeArchived, setIncludeArchived] = useState(false);
  const [confirmOrg, setConfirmOrg] = useState<Organization | null>(null);

  if (!user?.is_platform_admin) {
    return <Navigate to="/" replace />;
  }

  const load = async (archived: boolean) => {
    setLoading(true);
    try {
      const data = await adminService.listOrganizations(archived);
      setOrgs(data);
    } catch (err) {
      toast.error("Failed to load organizations", extractErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load(includeArchived);
  }, [includeArchived]);

  const handleSetActive = async (org: Organization, isActive: boolean) => {
    setSaving((prev) => ({ ...prev, [org.id]: true }));
    try {
      const fresh = await adminService.setOrgActive(org.id, isActive);
      setOrgs((prev) => prev.map((o) => (o.id === org.id ? fresh : o)));
      toast.success(
        isActive ? "Client enabled" : "Client disabled",
        `${org.name} ${isActive ? "can sign in again" : "is now suspended"}`,
      );
    } catch (err) {
      toast.error(isActive ? "Enable failed" : "Disable failed", extractErrorMessage(err));
    } finally {
      setSaving((prev) => ({ ...prev, [org.id]: false }));
    }
  };

  const handleRestore = async (org: Organization) => {
    setSaving((prev) => ({ ...prev, [org.id]: true }));
    try {
      const fresh = await adminService.restoreOrganization(org.id);
      setOrgs((prev) => prev.map((o) => (o.id === org.id ? fresh : o)));
      toast.success("Client restored", `${org.name} is active again`);
    } catch (err) {
      toast.error("Restore failed", extractErrorMessage(err));
    } finally {
      setSaving((prev) => ({ ...prev, [org.id]: false }));
    }
  };

  const handleArchiveConfirmed = async () => {
    const org = confirmOrg;
    if (!org) return;
    setSaving((prev) => ({ ...prev, [org.id]: true }));
    try {
      const fresh = await adminService.archiveOrganization(org.id);
      // In the default view archived orgs are hidden; remove it. When showing
      // archived, keep it in place so the Restore action is available.
      setOrgs((prev) =>
        includeArchived
          ? prev.map((o) => (o.id === org.id ? fresh : o))
          : prev.filter((o) => o.id !== org.id),
      );
      toast.success("Client deleted", `${org.name} was archived and can be restored.`);
    } catch (err) {
      toast.error("Delete failed", extractErrorMessage(err));
    } finally {
      setSaving((prev) => ({ ...prev, [org.id]: false }));
      setConfirmOrg(null);
    }
  };

  const handleToggle = async (org: Organization, key: ModuleKey, enabled: boolean) => {
    const updated = { ...org.modules, [key]: enabled };
    setOrgs((prev) => prev.map((o) => (o.id === org.id ? { ...o, modules: updated } : o)));
    setSaving((prev) => ({ ...prev, [org.id]: true }));
    try {
      const fresh = await adminService.updateOrgModules(org.id, { [key]: enabled });
      setOrgs((prev) => prev.map((o) => (o.id === org.id ? fresh : o)));
    } catch (err) {
      setOrgs((prev) => prev.map((o) => (o.id === org.id ? { ...o, modules: org.modules } : o)));
      toast.error("Failed to update module access", extractErrorMessage(err));
    } finally {
      setSaving((prev) => ({ ...prev, [org.id]: false }));
    }
  };

  const handleApplyDefaults = async (org: Organization) => {
    const defaults = defaultsForIndustry(org.business_type);
    setOrgs((prev) => prev.map((o) => (o.id === org.id ? { ...o, modules: defaults } : o)));
    setSaving((prev) => ({ ...prev, [org.id]: true }));
    try {
      const fresh = await adminService.updateOrgModules(org.id, defaults);
      setOrgs((prev) => prev.map((o) => (o.id === org.id ? fresh : o)));
      toast.success("Defaults applied", `${org.name} updated for ${INDUSTRY_LABEL[org.business_type] ?? org.business_type}`);
    } catch (err) {
      setOrgs((prev) => prev.map((o) => (o.id === org.id ? org : o)));
      toast.error("Failed to apply defaults", extractErrorMessage(err));
    } finally {
      setSaving((prev) => ({ ...prev, [org.id]: false }));
    }
  };

  return (
    <>
      <div className="page-header">
        <div className="page-header__titles">
          <h1>Platform Admin</h1>
          <p>Control which modules each organisation can access.</p>
        </div>
        <div className="page-header__actions" style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <label style={{ display: "flex", alignItems: "center", gap: "0.375rem", fontSize: "0.875rem", cursor: "pointer" }}>
            <input
              type="checkbox"
              checked={includeArchived}
              onChange={(e) => setIncludeArchived(e.target.checked)}
            />
            Show archived
          </label>
          <Button variant="secondary" size="sm" icon={<RefreshCw size={14} />} onClick={() => void load(includeArchived)}>
            Refresh
          </Button>
        </div>
      </div>

      {loading ? (
        <LoadingBlock />
      ) : orgs.length === 0 ? (
        <EmptyState title="No organizations found" />
      ) : (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))",
            gap: "1rem",
          }}
        >
          {orgs.map((org) => {
            const busy = !!saving[org.id];
            const locked = org.is_deleted || !org.is_active;
            return (
              <div key={org.id} className="card" style={{ opacity: org.is_deleted ? 0.6 : 1 }}>
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "flex-start",
                    gap: "0.5rem",
                    marginBottom: "1rem",
                  }}
                >
                  <div>
                    <div style={{ fontWeight: 600, marginBottom: "0.3rem" }}>{org.name}</div>
                    <div style={{ display: "flex", gap: "0.375rem", flexWrap: "wrap" }}>
                      <StatusBadge org={org} />
                      <span className="badge badge--neutral">
                        {INDUSTRY_LABEL[org.business_type] ?? org.business_type}
                      </span>
                      <span className="badge badge--neutral">{org.plan}</span>
                    </div>
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: "0.375rem", alignItems: "stretch" }}>
                    {org.is_deleted ? (
                      <Button variant="primary" size="sm" disabled={busy} onClick={() => void handleRestore(org)}>
                        Restore
                      </Button>
                    ) : (
                      <>
                        <Button variant="secondary" size="sm" disabled={busy} onClick={() => void handleApplyDefaults(org)}>
                          Apply defaults
                        </Button>
                        {org.is_active ? (
                          <Button variant="secondary" size="sm" disabled={busy} onClick={() => void handleSetActive(org, false)}>
                            Disable
                          </Button>
                        ) : (
                          <Button variant="primary" size="sm" disabled={busy} onClick={() => void handleSetActive(org, true)}>
                            Enable
                          </Button>
                        )}
                        <Button variant="danger" size="sm" disabled={busy} onClick={() => setConfirmOrg(org)}>
                          Delete
                        </Button>
                      </>
                    )}
                  </div>
                </div>

                <ModuleGroup
                  title="Core CRM"
                  keys={CORE_MODULES}
                  org={org}
                  disabled={busy || locked}
                  onToggle={(key, val) => void handleToggle(org, key, val)}
                />
                <ModuleGroup
                  title="Business Operations"
                  keys={OPS_MODULES}
                  org={org}
                  disabled={busy || locked}
                  onToggle={(key, val) => void handleToggle(org, key, val)}
                />
                {org.business_type === "real_estate" && (
                  <ModuleGroup
                    title="Real Estate"
                    keys={RE_MODULES}
                    org={org}
                    disabled={busy || locked}
                    onToggle={(key, val) => void handleToggle(org, key, val)}
                  />
                )}
              </div>
            );
          })}
        </div>
      )}

      <ConfirmDialog
        open={confirmOrg !== null}
        title="Delete client"
        description={
          confirmOrg
            ? `Delete "${confirmOrg.name}"? Its users lose access immediately. The data is archived and can be restored later from "Show archived".`
            : ""
        }
        confirmLabel="Delete"
        cancelLabel="Cancel"
        destructive
        loading={confirmOrg ? !!saving[confirmOrg.id] : false}
        onCancel={() => setConfirmOrg(null)}
        onConfirm={() => void handleArchiveConfirmed()}
      />
    </>
  );
}
