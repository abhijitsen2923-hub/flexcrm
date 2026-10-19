import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Button, Modal, TextField, useToast } from "../../../components";
import type {
  CustomRole,
  CreateCustomRolePayload,
  LeadAccessOptions,
  UpdateCustomRolePayload,
} from "../../../services/customRoles";
import { customRolesService } from "../../../services/customRoles";
import { extractErrorMessage } from "../../../utils/errors";
import {
  LIMITED_EXCLUDED_PERMISSIONS,
  draftFromRole,
  draftIsLimited,
  draftProblem,
  draftToPayload,
  toggleValue,
  type AccessMode,
  type LeadAccessDraft,
} from "../../../utils/leadAccess";
import { ALL_PERMISSION_CODES, HIDDEN_PERMISSION_CODES } from "../../../utils/permissionCodes";

// Long lists get a filter box.
const FILTER_FROM = 12;

interface Props {
  open: boolean;
  onClose: () => void;
  onSaved: () => void;
  editing?: CustomRole | null;
}

function ModeChips({
  label,
  mode,
  onChange,
  allLabel,
  chosenLabel,
}: {
  label: string;
  mode: AccessMode;
  onChange: (mode: AccessMode) => void;
  allLabel: string;
  chosenLabel: string;
}) {
  return (
    <div className="role-access__row" role="radiogroup" aria-label={label}>
      <span className="role-access__label">{label}</span>
      {(["all", "chosen"] as const).map((value) => (
        <button
          key={value}
          type="button"
          role="radio"
          aria-checked={mode === value}
          className={`filter-chip${mode === value ? " is-active" : ""}`}
          onClick={() => onChange(value)}
        >
          {value === "all" ? allLabel : chosenLabel}
        </button>
      ))}
    </div>
  );
}

function ChoiceList({
  items,
  selected,
  onToggle,
  emptyText,
  filterLabel,
}: {
  items: { value: string; label: string }[];
  selected: (value: string) => boolean;
  onToggle: (value: string, on: boolean) => void;
  emptyText: string;
  filterLabel: string;
}) {
  const [filter, setFilter] = useState("");
  const shown = useMemo(() => {
    const term = filter.trim().toLowerCase();
    return term ? items.filter((i) => i.label.toLowerCase().includes(term)) : items;
  }, [items, filter]);
  if (items.length === 0) return <div className="text-sm muted">{emptyText}</div>;
  return (
    <div className="role-access__choices">
      {items.length >= FILTER_FROM && (
        <input
          className="input"
          type="search"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Filter…"
          aria-label={filterLabel}
        />
      )}
      <div className="filter-stage-list role-access__list">
        {shown.map((item) => (
          <label key={item.value} className="filter-stage-list__item">
            <input type="checkbox" checked={selected(item.value)} onChange={(e) => onToggle(item.value, e.target.checked)} />
            <span>{item.label}</span>
          </label>
        ))}
        {shown.length === 0 && <span className="text-sm muted">No match.</span>}
      </div>
    </div>
  );
}

export function CustomRoleEditorModal({ open, onClose, onSaved, editing }: Props) {
  const toast = useToast();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [selectedPerms, setSelectedPerms] = useState<Set<string>>(new Set());
  const [access, setAccess] = useState<LeadAccessDraft>(() => draftFromRole(null));
  const [options, setOptions] = useState<LeadAccessOptions | null>(null);
  const [optionsError, setOptionsError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setName(editing?.name ?? "");
      setDescription(editing?.description ?? "");
      setSelectedPerms(new Set(editing?.permissions ?? []));
      setAccess(draftFromRole(editing?.lead_access));
      setError(null);
    }
  }, [open, editing]);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setOptionsError(null);
    customRolesService
      .leadAccessOptions()
      .then((data) => { if (!cancelled) setOptions(data); })
      .catch((err) => { if (!cancelled) setOptionsError(extractErrorMessage(err)); });
    return () => { cancelled = true; };
  }, [open]);

  const limited = draftIsLimited(access);
  const excluded = useMemo(() => new Set(limited ? LIMITED_EXCLUDED_PERMISSIONS : []), [limited]);

  // The role's own choices stay listed even if they're no longer offered (e.g. a source no lead uses any more).
  const campaignItems = useMemo(() => {
    const byId = new Map((options?.campaigns ?? []).map((c) => [c.id, c.name]));
    for (const c of editing?.lead_access?.campaigns ?? []) if (!byId.has(c.id)) byId.set(c.id, c.name);
    return [...byId.entries()].map(([value, label]) => ({ value, label })).sort((a, b) => a.label.localeCompare(b.label));
  }, [options, editing]);
  const sourceItems = useMemo(() => {
    const byKey = new Map((options?.sources ?? []).map((s) => [s.toLowerCase(), s]));
    for (const s of access.sources) if (!byKey.has(s.toLowerCase())) byKey.set(s.toLowerCase(), s);
    return [...byKey.values()].sort((a, b) => a.localeCompare(b)).map((s) => ({ value: s, label: s }));
  }, [options, access.sources]);

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
    const problem = draftProblem(access);
    if (problem) { setError(problem); return; }
    setSubmitting(true);
    setError(null);
    try {
      // A limited role can't hold user / workspace / campaign management — they're left out (shown switched off).
      const permissions = Array.from(selectedPerms).filter((code) => !excluded.has(code)) as CreateCustomRolePayload["permissions"];
      const lead_access = draftToPayload(access);
      if (editing) {
        const payload: UpdateCustomRolePayload = { name: name.trim(), description: description.trim() || null, permissions, lead_access };
        await customRolesService.update(editing.id, payload);
        toast.success("Role updated", name.trim());
      } else {
        await customRolesService.create({ name: name.trim(), description: description.trim() || null, permissions, lead_access });
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

        <fieldset className="role-access">
          <legend className="label">Data access</legend>
          <p className="text-xs muted role-access__intro">
            Which leads people with this role see — and the customers, bookings, site visits and payments that come
            from those leads. New leads they add must be inside these limits too.
          </p>
          <label className="role-access__own">
            <input
              type="checkbox"
              checked={access.ownOnly}
              onChange={(e) => setAccess({ ...access, ownOnly: e.target.checked })}
            />
            <span>Only leads assigned to them</span>
          </label>

          <ModeChips
            label="Campaigns"
            mode={access.campaignMode}
            onChange={(campaignMode) => setAccess({ ...access, campaignMode })}
            allLabel="All campaigns"
            chosenLabel="Chosen campaigns"
          />
          {access.campaignMode === "chosen" && (
            <ChoiceList
              items={campaignItems}
              selected={(id) => access.campaignIds.includes(id)}
              onToggle={(id, on) => setAccess({ ...access, campaignIds: toggleValue(access.campaignIds, id, on) })}
              emptyText={options ? "No campaigns yet — add them on the Campaigns screen." : "Loading campaigns…"}
              filterLabel="Filter campaigns"
            />
          )}

          <ModeChips
            label="Sources"
            mode={access.sourceMode}
            onChange={(sourceMode) => setAccess({ ...access, sourceMode })}
            allLabel="All sources"
            chosenLabel="Chosen sources"
          />
          {access.sourceMode === "chosen" && (
            <ChoiceList
              items={sourceItems}
              selected={(s) => access.sources.some((v) => v.toLowerCase() === s.toLowerCase())}
              onToggle={(s, on) => setAccess({ ...access, sources: toggleValue(access.sources, s, on, true) })}
              emptyText={options ? "No sources yet." : "Loading sources…"}
              filterLabel="Filter sources"
            />
          )}

          {optionsError && <div className="text-sm" style={{ color: "var(--color-danger)" }}>Couldn't load the lists: {optionsError}</div>}
          {(access.campaignMode === "chosen" || access.sourceMode === "chosen") && (
            <p className="text-xs muted">
              A lead must match every limit you set. Leads with no campaign (or no source) are hidden when you limit
              campaigns (or sources).
            </p>
          )}
          {limited && (
            <p className="text-xs muted">
              A role that sees only some leads can't manage users, the workspace or the campaign list.
            </p>
          )}
        </fieldset>

        <div>
          <div className="label" style={{ marginBottom: "0.5rem" }}>
            Permissions
            <span className="text-xs muted" style={{ marginLeft: "0.5rem" }}>
              {[...selectedPerms].filter((c) => !excluded.has(c)).length} selected
            </span>
          </div>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))",
              gap: "0.5rem",
            }}
          >
            {[
              ...ALL_PERMISSION_CODES,
              ...HIDDEN_PERMISSION_CODES.filter((c) => ((editing?.permissions ?? []) as readonly string[]).includes(c)),
            ].map((code) => {
              const blocked = excluded.has(code);
              const checked = selectedPerms.has(code) && !blocked;
              return (
                <label
                  key={code}
                  title={blocked ? "Not available for a role that sees only some leads" : undefined}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "0.5rem",
                    padding: "0.4rem 0.5rem",
                    border: "1px solid var(--color-border)",
                    borderRadius: 6,
                    background: checked ? "var(--color-primary-soft, #eff6ff)" : "transparent",
                    cursor: blocked ? "not-allowed" : "pointer",
                    opacity: blocked ? 0.55 : 1,
                  }}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    disabled={blocked}
                    onChange={() => togglePerm(code)}
                  />
                  <span style={{ fontSize: "0.85rem" }}>{code}</span>
                </label>
              );
            })}
          </div>
        </div>
        {error && <div className="error-banner">{error}</div>}
      </form>
    </Modal>
  );
}
