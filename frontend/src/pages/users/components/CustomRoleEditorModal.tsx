import { useEffect, useState, type FormEvent } from "react";
import { Button, Modal, SelectField, TextField, useToast } from "../../../components";
import type { CustomRole, CreateCustomRolePayload, UpdateCustomRolePayload } from "../../../services/customRoles";
import { customRolesService } from "../../../services/customRoles";
import { extractErrorMessage } from "../../../utils/errors";

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

interface Props {
  open: boolean;
  onClose: () => void;
  onSaved: () => void;
  editing?: CustomRole | null;
}

export function CustomRoleEditorModal({ open, onClose, onSaved, editing }: Props) {
  const toast = useToast();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [selectedPerms, setSelectedPerms] = useState<Set<string>>(new Set());
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setName(editing?.name ?? "");
      setDescription(editing?.description ?? "");
      setSelectedPerms(new Set(editing?.permissions ?? []));
      setError(null);
    }
  }, [open, editing]);

  function togglePerm(code: string) {
    setSelectedPerms((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code); else next.add(code);
      return next;
    });
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) { setError("Name is required."); return; }
    setSubmitting(true);
    setError(null);
    try {
      const permissions = Array.from(selectedPerms) as CreateCustomRolePayload["permissions"];
      if (editing) {
        const payload: UpdateCustomRolePayload = { name: name.trim(), description: description.trim() || null, permissions };
        await customRolesService.update(editing.id, payload);
        toast.success("Role updated", name.trim());
      } else {
        await customRolesService.create({ name: name.trim(), description: description.trim() || null, permissions });
        toast.success("Role created", name.trim());
      }
      onSaved();
      onClose();
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={editing ? `Edit role — ${editing.name}` : "New custom role"}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={submitting}>Cancel</Button>
          <Button type="submit" form="role-editor-form" loading={submitting} disabled={submitting}>
            {editing ? "Save changes" : "Create role"}
          </Button>
        </>
      }
    >
      <form id="role-editor-form" className="form" onSubmit={handleSubmit}>
        <TextField
          id="role-name"
          label="Role name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Pre-Sales Associate"
          required
        />
        <TextField
          id="role-description"
          label="Description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Optional — describe when to use this role"
        />
        <div>
          <div className="label" style={{ marginBottom: "0.5rem" }}>
            Permissions
            <span className="text-xs muted" style={{ marginLeft: "0.5rem" }}>
              {selectedPerms.size} selected
            </span>
          </div>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))",
              gap: "0.5rem",
            }}
          >
            {ALL_PERMISSION_CODES.map((code) => (
              <label
                key={code}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "0.5rem",
                  padding: "0.4rem 0.5rem",
                  border: "1px solid var(--color-border)",
                  borderRadius: 6,
                  background: selectedPerms.has(code) ? "var(--color-primary-soft, #eff6ff)" : "transparent",
                  cursor: "pointer",
                }}
              >
                <input
                  type="checkbox"
                  checked={selectedPerms.has(code)}
                  onChange={() => togglePerm(code)}
                />
                <span style={{ fontSize: "0.85rem" }}>{code}</span>
              </label>
            ))}
          </div>
        </div>
        {error && <div className="error-banner">{error}</div>}
      </form>
    </Modal>
  );
}
