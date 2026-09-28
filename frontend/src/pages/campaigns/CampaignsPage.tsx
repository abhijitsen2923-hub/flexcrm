import { Check, GitMerge, Pencil, Plus, Power, RefreshCw, Trash2, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";

import {
  Badge,
  Button,
  ConfirmDialog,
  DataTable,
  EmptyState,
  LoadingBlock,
  Modal,
  SelectField,
  TextField,
  useToast,
  type DataTableColumn
} from "../../components";
import { invalidate } from "../../hooks/resourceCache";
import { usePermissions } from "../../hooks/usePermissions";
import { useRealtimeRefresh } from "../../realtime";
import { campaignsService, type CampaignOverview, type CampaignRow } from "../../services/campaigns";
import {
  campaignKey,
  campaignSourceLabel,
  cleanCampaignName,
  findCampaignByKey,
  isCampaignListEvent,
  mergePreviewCount,
  renameConflictId,
  shouldUseLegacyCampaigns
} from "../../utils/campaigns";
import { extractErrorMessage } from "../../utils/errors";

type View = "all" | "review" | "inactive";

interface MergeState {
  sourceIds: string[];
  targetId: string;
}

const EMPTY: CampaignOverview = { items: [], suggestions: [] };

/**
 * The workspace's own campaign list (every tenant has its own). Campaign managers merge duplicates,
 * rename, remove junk and (de)activate; lead rows follow automatically and old spellings are remembered,
 * so CSV uploads / sheet rows / the New Lead form keep landing on the right campaign.
 */
export default function CampaignsPage() {
  const toast = useToast();
  const { has } = usePermissions();
  const canManage = has("CAMPAIGN_MANAGE");

  const [overview, setOverview] = useState<CampaignOverview>(EMPTY);
  const [loading, setLoading] = useState(false);
  const [notReady, setNotReady] = useState(false);
  const [view, setView] = useState<View>("all");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);

  const [createOpen, setCreateOpen] = useState(false);
  const [createName, setCreateName] = useState("");
  const [createError, setCreateError] = useState<string | null>(null);

  const [renaming, setRenaming] = useState<CampaignRow | null>(null);
  const [renameName, setRenameName] = useState("");
  const [renameError, setRenameError] = useState<string | null>(null);
  const [renameConflict, setRenameConflict] = useState<string | null>(null);

  const [merge, setMerge] = useState<MergeState | null>(null);
  const [clearing, setClearing] = useState<CampaignRow | null>(null);

  const load = useCallback(async () => {
    if (!canManage) return;
    setLoading(true);
    try {
      const data = await campaignsService.overview();
      setOverview(data);
      setNotReady(false);
      // Drop selections that no longer exist (merged / cleared elsewhere).
      setSelected((prev) => new Set([...prev].filter((id) => data.items.some((c) => c.id === id))));
    } catch (error) {
      if (shouldUseLegacyCampaigns(error)) setNotReady(true);
      else toast.error("Couldn't load campaigns", extractErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }, [canManage, toast]);

  useEffect(() => {
    void load();
  }, [load]);

  // Another manager's change, new/deleted leads (counts, names added by imports or sheets) — keep the list
  // current. Not on every lead edit: each reload re-syncs the list server-side.
  useRealtimeRefresh(
    (event) => isCampaignListEvent(event) || event.event === "lead.created" || event.event === "lead.deleted",
    () => void load(),
    5000
  );

  const byId = useMemo(() => new Map(overview.items.map((c) => [c.id, c])), [overview.items]);
  const counts = useMemo(
    () => ({
      all: overview.items.length,
      review: overview.items.filter((c) => c.needs_review).length,
      inactive: overview.items.filter((c) => !c.is_active).length
    }),
    [overview.items]
  );
  const rows = useMemo(() => {
    const term = campaignKey(search);
    return overview.items.filter((c) => {
      if (view === "review" && !c.needs_review) return false;
      if (view === "inactive" && c.is_active) return false;
      if (!term) return true;
      return campaignKey(c.name).includes(term) || c.aliases.some((a) => campaignKey(a.alias).includes(term));
    });
  }, [overview.items, view, search]);
  const suggestions = useMemo(
    () =>
      overview.suggestions.filter(
        (s) => byId.has(s.keep_id) && byId.has(s.merge_id) && !dismissed.has(`${s.keep_id}:${s.merge_id}`)
      ),
    [overview.suggestions, byId, dismissed]
  );

  // After any change: other screens' lead lists are stale too.
  async function afterChange(title: string, detail?: string) {
    toast.success(title, detail);
    invalidate("leads:");
    await load();
  }

  // ---- add ----------------------------------------------------------------------------------------
  function openCreate() {
    setCreateName("");
    setCreateError(null);
    setCreateOpen(true);
  }

  async function submitCreate(event: FormEvent) {
    event.preventDefault();
    const name = cleanCampaignName(createName);
    if (!name) return;
    setBusy(true);
    setCreateError(null);
    try {
      await campaignsService.create(name);
      setCreateOpen(false);
      await afterChange("Campaign added", name);
    } catch (error) {
      setCreateError(extractErrorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  // ---- rename -------------------------------------------------------------------------------------
  function openRename(row: CampaignRow) {
    setRenaming(row);
    setRenameName(row.name);
    setRenameError(null);
    setRenameConflict(null);
  }

  async function submitRename(event: FormEvent) {
    event.preventDefault();
    if (!renaming) return;
    const name = cleanCampaignName(renameName);
    if (!name || name === renaming.name) {
      setRenaming(null);
      return;
    }
    setBusy(true);
    setRenameError(null);
    setRenameConflict(null);
    try {
      const result = await campaignsService.rename(renaming.id, name);
      setRenaming(null);
      await afterChange("Campaign renamed", leadsChanged(result.leads_updated, name));
    } catch (error) {
      setRenameError(extractErrorMessage(error));
      const conflictId = renameConflictId(error);
      setRenameConflict(conflictId && byId.has(conflictId) && conflictId !== renaming.id ? conflictId : null);
    } finally {
      setBusy(false);
    }
  }

  // ---- merge --------------------------------------------------------------------------------------
  function openMerge(sourceIds: string[], targetId = "") {
    setMerge({ sourceIds, targetId });
  }

  async function submitMerge() {
    if (!merge || !merge.targetId) return;
    const target = byId.get(merge.targetId);
    // Only sources that still exist (another manager may have merged/removed one meanwhile — sending its
    // id again would fail as "stale" on every retry).
    const sourceIds = merge.sourceIds.filter((id) => byId.has(id));
    if (sourceIds.length === 0) {
      setMerge(null);
      return;
    }
    setBusy(true);
    try {
      const result = await campaignsService.merge(sourceIds, merge.targetId);
      setMerge(null);
      setSelected(new Set());
      await afterChange("Campaigns merged", leadsChanged(result.leads_updated, target?.name ?? ""));
    } catch (error) {
      toast.error("Merge failed", extractErrorMessage(error));
      await load();
    } finally {
      setBusy(false);
    }
  }

  // ---- flags / clear / old spellings ----------------------------------------------------------------
  async function run(action: () => Promise<unknown>, title: string, failure: string) {
    setBusy(true);
    try {
      await action();
      await afterChange(title);
    } catch (error) {
      toast.error(failure, extractErrorMessage(error));
      await load();
    } finally {
      setBusy(false);
    }
  }

  async function submitClear() {
    if (!clearing) return;
    const row = clearing;
    setBusy(true);
    try {
      const result = await campaignsService.clear(row.id);
      setClearing(null);
      await afterChange(
        "Campaign removed",
        result.leads_updated ? `${result.leads_updated} lead${result.leads_updated === 1 ? "" : "s"} now have no campaign.` : row.name
      );
    } catch (error) {
      toast.error("Couldn't remove the campaign", extractErrorMessage(error));
      setClearing(null);
      await load();
    } finally {
      setBusy(false);
    }
  }

  function toggleSelected(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  if (!canManage) {
    return (
      <>
        <div className="page-header">
          <div className="page-header__titles">
            <h1>Campaigns</h1>
          </div>
        </div>
        <EmptyState
          title="You don't have access to manage campaigns"
          description="Ask your workspace owner or a manager for the CAMPAIGN_MANAGE permission."
        />
      </>
    );
  }

  const columns: DataTableColumn<CampaignRow>[] = [
    {
      key: "select",
      header: "",
      width: "2.5rem",
      label: "Select",
      render: (row) => (
        <input
          type="checkbox"
          aria-label={`Select ${row.name}`}
          checked={selected.has(row.id)}
          onChange={() => toggleSelected(row.id)}
        />
      )
    },
    {
      key: "name",
      header: "Campaign",
      render: (row) => (
        <div style={{ minWidth: 0 }}>
          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "0.4rem", fontWeight: 600 }}>
            <span style={{ overflowWrap: "anywhere" }}>{row.name}</span>
            {row.needs_review && <Badge tone="warning">Needs review</Badge>}
            {!row.is_active && <Badge tone="neutral">Inactive</Badge>}
          </div>
          {row.aliases.length > 0 && (
            <div className="text-xs muted" style={{ marginTop: "0.3rem", display: "flex", flexWrap: "wrap", gap: "0.3rem", alignItems: "center" }}>
              <span>Also matches:</span>
              {row.aliases.map((alias) => (
                <span key={alias.id} className="active-filter" style={{ cursor: "default" }}>
                  {alias.alias}
                  <button
                    type="button"
                    className="btn btn--ghost btn--sm"
                    style={{ padding: 0, minHeight: 0 }}
                    title="Forget this old spelling"
                    aria-label={`Forget old spelling ${alias.alias}`}
                    disabled={busy}
                    onClick={() =>
                      void run(
                        () => campaignsService.removeAlias(row.id, alias.id),
                        "Old spelling removed",
                        "Couldn't remove the old spelling"
                      )
                    }
                  >
                    <X size={12} aria-hidden="true" />
                  </button>
                </span>
              ))}
            </div>
          )}
        </div>
      )
    },
    { key: "leads", header: "Leads", align: "right", width: "5rem", render: (row) => row.lead_count },
    { key: "source", header: "Added from", width: "10rem", render: (row) => <span className="muted">{campaignSourceLabel(row.source)}</span> },
    {
      key: "actions",
      header: "",
      label: "Actions",
      render: (row) => (
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.25rem", justifyContent: "flex-end" }}>
          <Button size="sm" variant="ghost" icon={<Pencil size={13} />} disabled={busy} onClick={() => openRename(row)}>
            Rename
          </Button>
          <Button
            size="sm"
            variant="ghost"
            icon={<GitMerge size={13} />}
            disabled={busy || overview.items.length < 2}
            onClick={() => openMerge([row.id])}
          >
            Merge into…
          </Button>
          {row.needs_review && (
            <Button
              size="sm"
              variant="ghost"
              icon={<Check size={13} />}
              disabled={busy}
              onClick={() => void run(() => campaignsService.markReviewed(row.id), "Marked as reviewed", "Couldn't update")}
            >
              Looks good
            </Button>
          )}
          <Button
            size="sm"
            variant="ghost"
            icon={<Power size={13} />}
            disabled={busy}
            title={row.is_active ? "Hide from the New Lead form (existing leads keep it)" : "Show in the New Lead form again"}
            onClick={() =>
              void run(
                () => campaignsService.setActive(row.id, !row.is_active),
                row.is_active ? "Campaign deactivated" : "Campaign activated",
                "Couldn't update"
              )
            }
          >
            {row.is_active ? "Deactivate" : "Activate"}
          </Button>
          <Button size="sm" variant="ghost" icon={<Trash2 size={13} />} disabled={busy} onClick={() => setClearing(row)}>
            Remove
          </Button>
        </div>
      )
    }
  ];

  const mergeSources = merge ? merge.sourceIds.map((id) => byId.get(id)).filter((c): c is CampaignRow => Boolean(c)) : [];
  const mergeTarget = merge?.targetId ? byId.get(merge.targetId) : undefined;
  const mergeCount = merge ? mergePreviewCount(overview.items, merge.sourceIds) : 0;
  const createExisting = findCampaignByKey(overview.items, createName);

  return (
    <>
      <div className="page-header">
        <div className="page-header__titles">
          <h1>Campaigns</h1>
          <p>Your workspace's campaign list. Merge duplicates, rename or remove junk — leads update automatically.</p>
        </div>
        <div className="page-header__actions">
          <Button variant="secondary" size="sm" icon={<RefreshCw size={14} />} onClick={() => void load()} loading={loading}>
            Refresh
          </Button>
          {!notReady && (
            <Button icon={<Plus size={14} />} onClick={openCreate}>
              New campaign
            </Button>
          )}
        </div>
      </div>

      {notReady ? (
        <EmptyState
          title="Campaigns are still being set up"
          description="This takes a minute after an update. Refresh shortly."
        />
      ) : (
        <>
          {suggestions.length > 0 && (
            <div className="card" style={{ padding: "1rem", marginBottom: "1rem" }}>
              <div style={{ fontWeight: 600 }}>Possible duplicates</div>
              <p className="text-sm muted" style={{ margin: "0.25rem 0 0.75rem" }}>
                These names look alike. Merge them only if they're really the same campaign.
              </p>
              <div className="stack" style={{ gap: "0.5rem" }}>
                {suggestions.slice(0, 20).map((s) => {
                  const keep = byId.get(s.keep_id)!;
                  const other = byId.get(s.merge_id)!;
                  return (
                    <div key={`${s.keep_id}:${s.merge_id}`} style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "0.5rem" }}>
                      <span style={{ flex: "1 1 16rem", minWidth: 0, overflowWrap: "anywhere" }}>
                        “{other.name}” ({other.lead_count}) looks like “{keep.name}” ({keep.lead_count})
                      </span>
                      <Button size="sm" variant="secondary" icon={<GitMerge size={13} />} disabled={busy} onClick={() => openMerge([other.id], keep.id)}>
                        Merge…
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setDismissed((prev) => new Set(prev).add(`${s.keep_id}:${s.merge_id}`))}
                      >
                        Not the same
                      </Button>
                    </div>
                  );
                })}
                {suggestions.length > 20 && <span className="text-xs muted">+{suggestions.length - 20} more</span>}
              </div>
            </div>
          )}

          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", alignItems: "center", marginBottom: "0.75rem" }}>
            {([
              ["all", `All (${counts.all})`],
              ["review", `Needs review (${counts.review})`],
              ["inactive", `Inactive (${counts.inactive})`]
            ] as const).map(([value, label]) => (
              <button
                key={value}
                type="button"
                className={`filter-chip${view === value ? " is-active" : ""}`}
                aria-pressed={view === value}
                onClick={() => setView(value)}
              >
                {label}
              </button>
            ))}
            <input
              className="input"
              style={{ flex: "1 1 12rem", maxWidth: "20rem" }}
              placeholder="Search campaigns"
              aria-label="Search campaigns"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
            {selected.size >= 1 && (
              <Button size="sm" icon={<GitMerge size={13} />} disabled={busy || overview.items.length < 2} onClick={() => openMerge([...selected])}>
                Merge {selected.size} selected…
              </Button>
            )}
          </div>

          <div className="card" style={{ padding: 0 }}>
            <div className="table-wrap" style={{ border: "none", borderRadius: 0, boxShadow: "none" }}>
              {loading && overview.items.length === 0 ? (
                <LoadingBlock label="Loading campaigns…" />
              ) : (
                <DataTable
                  columns={columns}
                  rows={rows}
                  rowKey={(row) => row.id}
                  empty={
                    <EmptyState
                      title={overview.items.length === 0 ? "No campaigns yet" : "Nothing here"}
                      description={
                        overview.items.length === 0
                          ? "Campaigns appear here as leads come in with one, or add your own."
                          : "No campaign matches this filter."
                      }
                    />
                  }
                />
              )}
            </div>
          </div>
        </>
      )}

      {/* Add */}
      <Modal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title="New campaign"
        footer={
          <>
            <Button variant="secondary" onClick={() => setCreateOpen(false)} disabled={busy}>Cancel</Button>
            <Button type="submit" form="campaign-create-form" loading={busy} disabled={!cleanCampaignName(createName) || Boolean(createExisting)}>
              Add
            </Button>
          </>
        }
      >
        <form id="campaign-create-form" onSubmit={(event) => void submitCreate(event)}>
          <TextField
            id="campaign-create-name"
            label="Name"
            value={createName}
            maxLength={120}
            autoFocus
            onChange={(event) => {
              setCreateName(event.target.value);
              setCreateError(null);
            }}
            hint={createExisting ? `Already in the list as “${createExisting.name}”.` : undefined}
            error={createError ?? undefined}
          />
        </form>
      </Modal>

      {/* Rename */}
      <Modal
        open={renaming !== null}
        onClose={() => setRenaming(null)}
        title={renaming ? `Rename “${renaming.name}”` : "Rename"}
        footer={
          <>
            <Button variant="secondary" onClick={() => setRenaming(null)} disabled={busy}>Cancel</Button>
            {renameConflict && renaming ? (
              <Button
                icon={<GitMerge size={14} />}
                onClick={() => {
                  const source = renaming.id;
                  setRenaming(null);
                  openMerge([source], renameConflict);
                }}
              >
                Merge instead…
              </Button>
            ) : (
              <Button type="submit" form="campaign-rename-form" loading={busy} disabled={!cleanCampaignName(renameName)}>
                Rename
              </Button>
            )}
          </>
        }
      >
        <form id="campaign-rename-form" onSubmit={(event) => void submitRename(event)}>
          <TextField
            id="campaign-rename-name"
            label="New name"
            value={renameName}
            maxLength={120}
            autoFocus
            onChange={(event) => {
              setRenameName(event.target.value);
              setRenameConflict(null);
              setRenameError(null);
            }}
            hint={renaming && renaming.lead_count > 0 ? `Its ${renaming.lead_count} lead${renaming.lead_count === 1 ? "" : "s"} will show the new name. The old name keeps working for imports and sheet rows.` : undefined}
            error={renameError ?? undefined}
          />
        </form>
      </Modal>

      {/* Merge */}
      <Modal
        open={merge !== null}
        onClose={() => setMerge(null)}
        title="Merge campaigns"
        footer={
          <>
            <Button variant="secondary" onClick={() => setMerge(null)} disabled={busy}>Cancel</Button>
            <Button icon={<GitMerge size={14} />} onClick={() => void submitMerge()} loading={busy} disabled={!mergeTarget || mergeSources.length === 0}>
              Merge
            </Button>
          </>
        }
      >
        {merge && (
          <div className="stack">
            <div>
              <div className="text-sm muted">Merging</div>
              <div style={{ fontWeight: 600, overflowWrap: "anywhere" }}>
                {mergeSources.map((c) => `“${c.name}” (${c.lead_count})`).join(", ")}
              </div>
            </div>
            <SelectField
              id="campaign-merge-target"
              label="Into"
              value={merge.targetId}
              onChange={(event) => setMerge({ ...merge, targetId: event.target.value })}
              options={[
                { value: "", label: "Choose a campaign…" },
                ...overview.items
                  .filter((c) => !merge.sourceIds.includes(c.id))
                  .map((c) => ({ value: c.id, label: c.is_active ? c.name : `${c.name} (inactive)` }))
              ]}
            />
            {mergeTarget && (
              <p className="text-sm">
                {mergeCount} lead{mergeCount === 1 ? "" : "s"} will change to “{mergeTarget.name}”. The merged names are
                remembered, so future imports, sheet rows and the New Lead form land on “{mergeTarget.name}” too. Lead
                titles aren't changed.
              </p>
            )}
          </div>
        )}
      </Modal>

      <ConfirmDialog
        open={clearing !== null}
        title={clearing ? `Remove “${clearing.name}”?` : "Remove campaign?"}
        description={
          clearing
            ? clearing.lead_count > 0
              ? `Its ${clearing.lead_count} lead${clearing.lead_count === 1 ? "" : "s"} will have no campaign. This can't be undone. To keep the leads grouped, merge it into another campaign instead.`
              : "It will be removed from the list. This can't be undone."
            : undefined
        }
        confirmLabel="Remove"
        destructive
        loading={busy}
        onCancel={() => setClearing(null)}
        onConfirm={() => void submitClear()}
      />
    </>
  );
}

function leadsChanged(count: number, name: string): string {
  if (!count) return name;
  return `${count} lead${count === 1 ? "" : "s"} now show “${name}”.`;
}
