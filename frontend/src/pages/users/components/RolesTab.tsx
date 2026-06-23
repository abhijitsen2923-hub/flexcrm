import { Edit2, Plus, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Badge, Button, EmptyState, LoadingBlock, useToast } from "../../../components";
import type { CustomRole } from "../../../services/customRoles";
import { customRolesService } from "../../../services/customRoles";
import { extractErrorMessage } from "../../../utils/errors";
import { CustomRoleEditorModal } from "./CustomRoleEditorModal";

interface Props {
  canManage: boolean;
}

export function RolesTab({ canManage }: Props) {
  const toast = useToast();
  const [roles, setRoles] = useState<CustomRole[]>([]);
  const [loading, setLoading] = useState(false);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editingRole, setEditingRole] = useState<CustomRole | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setRoles(await customRolesService.list());
    } catch (error) {
      toast.error("Failed to load custom roles", extractErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => { void refresh(); }, [refresh]);

  async function handleDelete(role: CustomRole) {
    if (role.assigned_user_count > 0) {
      toast.error("Cannot delete", `${role.assigned_user_count} user(s) still assigned.`);
      return;
    }
    try {
      await customRolesService.delete(role.id);
      toast.success("Role deleted", role.name);
      await refresh();
    } catch (error) {
      toast.error("Delete failed", extractErrorMessage(error));
    }
  }

  function openCreate() {
    setEditingRole(null);
    setEditorOpen(true);
  }

  function openEdit(role: CustomRole) {
    setEditingRole(role);
    setEditorOpen(true);
  }

  return (
    <>
      <div className="page-header" style={{ marginBottom: "1rem" }}>
        <div className="page-header__titles">
          <h2 style={{ fontSize: "1.1rem" }}>Custom roles</h2>
          <p className="muted text-sm">Define named permission templates for your organisation.</p>
        </div>
        {canManage && (
          <div className="page-header__actions">
            <Button icon={<Plus size={14} />} onClick={openCreate}>New role</Button>
          </div>
        )}
      </div>

      {loading ? (
        <LoadingBlock label="Loading roles…" />
      ) : roles.length === 0 ? (
        <EmptyState
          title="No custom roles yet"
          description={canManage ? 'Click "New role" to create a permission template.' : "No custom roles have been defined."}
        />
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: "1rem" }}>
          {roles.map((role) => (
            <div key={role.id} className="card" style={{ padding: "1rem" }}>
              <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "0.5rem" }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 600, display: "flex", alignItems: "center", gap: "0.5rem" }}>
                    {role.name}
                    {!role.is_active && <Badge tone="neutral">Inactive</Badge>}
                  </div>
                  {role.description && (
                    <div className="text-sm muted" style={{ marginTop: "0.25rem" }}>{role.description}</div>
                  )}
                  <div className="text-xs muted" style={{ marginTop: "0.5rem" }}>
                    {role.permissions.length} permission{role.permissions.length === 1 ? "" : "s"} ·{" "}
                    {role.assigned_user_count} user{role.assigned_user_count === 1 ? "" : "s"} assigned
                  </div>
                </div>
                {canManage && (
                  <div style={{ display: "flex", gap: "0.25rem", flexShrink: 0 }}>
                    <Button size="sm" variant="ghost" icon={<Edit2 size={13} />} onClick={() => openEdit(role)} />
                    <Button
                      size="sm"
                      variant="ghost"
                      icon={<Trash2 size={13} />}
                      onClick={() => void handleDelete(role)}
                      disabled={role.assigned_user_count > 0}
                      title={role.assigned_user_count > 0 ? "Reassign users before deleting" : "Delete role"}
                    />
                  </div>
                )}
              </div>
              <div style={{ marginTop: "0.75rem", display: "flex", flexWrap: "wrap", gap: "0.25rem" }}>
                {role.permissions.slice(0, 6).map((perm) => (
                  <span
                    key={perm}
                    style={{
                      fontSize: "0.7rem",
                      padding: "0.1rem 0.4rem",
                      background: "var(--color-bg-muted)",
                      borderRadius: 4,
                      border: "1px solid var(--color-border)",
                    }}
                  >
                    {perm}
                  </span>
                ))}
                {role.permissions.length > 6 && (
                  <span className="text-xs muted">+{role.permissions.length - 6} more</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      <CustomRoleEditorModal
        open={editorOpen}
        onClose={() => setEditorOpen(false)}
        onSaved={() => void refresh()}
        editing={editingRole}
      />
    </>
  );
}
