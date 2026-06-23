import { RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";

import { Button, EmptyState, LoadingBlock, useToast } from "../components";
import { useAuth } from "../hooks/useAuth";
import { adminService } from "../services/admin";
import type { ModuleKey, Organization } from "../types";
import { MODULE_KEYS } from "../types/crm";
import { extractErrorMessage } from "../utils/errors";


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


export function PlatformAdminPage() {
  const { user } = useAuth();
  const toast = useToast();
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<Record<string, boolean>>({});

  if (!user?.is_platform_admin) {
    return <Navigate to="/" replace />;
  }

  const load = async () => {
    setLoading(true);
    try {
      const data = await adminService.listOrganizations();
      setOrgs(data);
    } catch (err) {
      toast.error("Failed to load organizations", extractErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const handleToggle = async (org: Organization, key: ModuleKey, enabled: boolean) => {
    const updated = { ...org.modules, [key]: enabled };
    // Optimistic update
    setOrgs((prev) =>
      prev.map((o) => (o.id === org.id ? { ...o, modules: updated } : o))
    );
    setSaving((prev) => ({ ...prev, [org.id]: true }));
    try {
      const fresh = await adminService.updateOrgModules(org.id, { [key]: enabled });
      setOrgs((prev) => prev.map((o) => (o.id === org.id ? fresh : o)));
    } catch (err) {
      // Revert on failure
      setOrgs((prev) =>
        prev.map((o) => (o.id === org.id ? { ...o, modules: org.modules } : o))
      );
      toast.error("Failed to update module access", extractErrorMessage(err));
    } finally {
      setSaving((prev) => ({ ...prev, [org.id]: false }));
    }
  };

  return (
    <>
      <div className="page-header">
        <div className="page-header__titles">
          <h1>Platform Admin</h1>
          <p>Manage module access for each company based on their subscription.</p>
        </div>
        <div className="page-header__actions">
          <Button variant="secondary" size="sm" icon={<RefreshCw size={14} />} onClick={load}>
            Refresh
          </Button>
        </div>
      </div>

      {loading ? (
        <LoadingBlock />
      ) : orgs.length === 0 ? (
        <EmptyState title="No organizations found" />
      ) : (
        <div className="card" style={{ overflowX: "auto" }}>
          <table className="table">
            <thead>
              <tr>
                <th>Company</th>
                <th>Plan</th>
                <th>Industry</th>
                {MODULE_KEYS.map((key) => (
                  <th key={key} style={{ textAlign: "center" }}>
                    {MODULE_LABELS[key]}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {orgs.map((org) => (
                <tr key={org.id}>
                  <td data-label="Company">
                    <strong>{org.name}</strong>
                    <div className="text-xs muted" style={{ marginTop: "0.1rem" }}>{org.id}</div>
                  </td>
                  <td data-label="Plan">
                    <span className="badge badge--neutral">{org.plan}</span>
                  </td>
                  <td data-label="Industry">{org.business_type}</td>
                  {MODULE_KEYS.map((key) => (
                    <td key={key} data-label={MODULE_LABELS[key]} style={{ textAlign: "center" }}>
                      <input
                        type="checkbox"
                        checked={org.modules?.[key] ?? false}
                        disabled={saving[org.id]}
                        onChange={(e) => void handleToggle(org, key, e.target.checked)}
                        aria-label={`${MODULE_LABELS[key]} for ${org.name}`}
                        style={{ width: 16, height: 16, cursor: "pointer" }}
                      />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
