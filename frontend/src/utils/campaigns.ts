// Pure helpers for the tenant's campaign list — no React, no network (unit-tested in tests/campaigns.test.ts).
// The identity rule mirrors the backend (app/core/campaign_names.py): case and extra spaces don't matter.
import type { CampaignOption, CampaignRow, CampaignSource } from "../services/campaigns";

export const CAMPAIGN_NAME_MAX_LEN = 120;

// Select value for "type a new campaign" — deliberately NOT "Other", which a tenant may use as a real name.
export const NEW_CAMPAIGN_VALUE = "__new_campaign__";

export interface SelectOption {
  value: string;
  label: string;
}

/** Trim + collapse whitespace runs + clamp (as the backend stores it). Blank → "". */
export function cleanCampaignName(raw: string | null | undefined): string {
  return (raw ?? "").split(/\s+/).filter(Boolean).join(" ").slice(0, CAMPAIGN_NAME_MAX_LEN).trim();
}

/** Identity key: two names are the same campaign when their keys are equal. */
export function campaignKey(raw: string | null | undefined): string {
  return cleanCampaignName(raw).toLowerCase();
}

export function findCampaignByKey<T extends { name: string }>(
  campaigns: ReadonlyArray<T>,
  raw: string | null | undefined
): T | undefined {
  const key = campaignKey(raw);
  return key ? campaigns.find((c) => campaignKey(c.name) === key) : undefined;
}

const byName = (a: string, b: string) => a.localeCompare(b, undefined, { sensitivity: "base" });

/**
 * New Lead form options: "None", the tenant's ACTIVE campaigns, and — for campaign managers, or in legacy
 * mode (backend without campaign lists) — a "type a new one" entry. A value that isn't in the list (e.g.
 * still selected after a refresh) stays selectable so the controlled <select> can't silently reset.
 */
export function buildCampaignFormOptions(
  campaigns: ReadonlyArray<CampaignOption>,
  { allowNew, legacyNames = [], current = "" }: { allowNew: boolean; legacyNames?: ReadonlyArray<string>; current?: string }
): SelectOption[] {
  const seen = new Set<string>();
  const names: string[] = [];
  for (const name of [...campaigns.filter((c) => c.is_active).map((c) => c.name), ...legacyNames]) {
    const key = campaignKey(name);
    if (key && !seen.has(key)) {
      seen.add(key);
      names.push(cleanCampaignName(name));
    }
  }
  if (current && current !== NEW_CAMPAIGN_VALUE && !seen.has(campaignKey(current))) {
    names.push(current);
  }
  names.sort(byName);
  const options: SelectOption[] = [{ value: "", label: "None" }, ...names.map((n) => ({ value: n, label: n }))];
  // Also kept while it's the current value (e.g. chosen in legacy mode, then the list came back) — otherwise
  // the select shows "None" while the form still holds the sentinel and the user can't switch away.
  if (allowNew || current === NEW_CAMPAIGN_VALUE) options.push({ value: NEW_CAMPAIGN_VALUE, label: "+ New campaign…" });
  return options;
}

/**
 * Leads-list Campaign filter: the campaigns actually on the leads this user can see (`inUse` — the backend
 * scopes it to a rep's own leads, so a rep doesn't discover campaigns used only on others' leads), one
 * entry per campaign, labelled from the workspace list (inactive marked), plus always the current selection.
 */
export function buildCampaignFilterOptions(
  campaigns: ReadonlyArray<CampaignOption>,
  inUse: ReadonlyArray<string>,
  selected: string
): SelectOption[] {
  const byKey = new Map<string, SelectOption>();
  for (const value of inUse) {
    const key = campaignKey(value);
    if (!key || byKey.has(key)) continue;
    const known = findCampaignByKey(campaigns, value);
    const name = known?.name ?? cleanCampaignName(value);
    byKey.set(key, { value: known ? known.name : value, label: known && !known.is_active ? `${name} (inactive)` : name });
  }
  const options = [...byKey.values()].sort((a, b) => byName(a.label, b.label));
  if (selected && !options.some((o) => o.value === selected)) options.push({ value: selected, label: selected });
  return options;
}

/**
 * Realtime events that change the workspace campaign list itself: campaign.* (add / rename / (de)activate
 * without leads), a manager's merge/rename/clear that moved leads, or a sheet relabel (may add names).
 */
export function isCampaignListEvent(event: { event: string; payload: unknown }): boolean {
  if (event.event.startsWith("campaign.")) return true;
  if (event.event !== "lead.updated") return false;
  const reason = (event.payload as { reason?: unknown } | null)?.reason;
  return typeof reason === "string" && (reason.startsWith("campaign_") || reason === "sheet_relabel");
}

/** How many leads a merge will move onto the target (the sources' counts). */
export function mergePreviewCount(rows: ReadonlyArray<Pick<CampaignRow, "id" | "lead_count">>, sourceIds: ReadonlyArray<string>): number {
  const wanted = new Set(sourceIds);
  return rows.reduce((sum, row) => (wanted.has(row.id) ? sum + row.lead_count : sum), 0);
}

interface ErrorLike {
  response?: { status?: number; data?: { error?: { detail?: unknown; extra?: Record<string, unknown> } } };
}

function errorParts(error: unknown): { status?: number; detail?: unknown; extra: Record<string, unknown> } {
  const response = (error as ErrorLike | null)?.response;
  return {
    status: response?.status,
    detail: response?.data?.error?.detail,
    extra: response?.data?.error?.extra ?? {}
  };
}

/**
 * This backend has no campaign list (an older version mid-deploy → 404, or the tenant migration still
 * running → 409 not_ready): fall back to the old free-text behaviour, which that backend accepts, so
 * creating leads never breaks. Anything else (5xx, network, 401/403) comes from a backend that DOES
 * enforce the list — keep the last list rather than offer free text it would reject.
 */
export function shouldUseLegacyCampaigns(error: unknown): boolean {
  const { status, extra } = errorParts(error);
  if (status === 404) return true;
  return status === 409 && extra.reason === "not_ready";
}

/**
 * The backend's message when a lead write was refused over its campaign (unknown / inactive), else null.
 * The detail comes in FastAPI's field-error list shape (so older clients show it too); a plain string is
 * accepted as well.
 */
export function campaignRejectionMessage(error: unknown): string | null {
  const { status, detail, extra } = errorParts(error);
  if (status !== 422) return null;
  if (extra.reason !== "unknown_campaign" && extra.reason !== "inactive_campaign") return null;
  const first = Array.isArray(detail) ? (detail[0] as { msg?: unknown } | undefined) : undefined;
  const message = typeof detail === "string" ? detail : typeof first?.msg === "string" ? first.msg : "";
  return message.trim() ? message : null;
}

/** On a rename 409 ("that name exists / is an old spelling of another campaign"): the other campaign's id. */
export function renameConflictId(error: unknown): string | null {
  const { status, extra } = errorParts(error);
  if (status !== 409) return null;
  if (extra.reason !== "name_exists" && extra.reason !== "alias_of_other") return null;
  return typeof extra.conflict_campaign_id === "string" ? extra.conflict_campaign_id : null;
}

const SOURCE_LABELS: Record<CampaignSource, string> = {
  existing: "Existing leads",
  manual: "Added by a manager",
  import: "CSV upload",
  sheet: "Google Sheet",
  meta: "Meta lead ads",
  integration: "Integration"
};

export function campaignSourceLabel(source: string): string {
  return SOURCE_LABELS[source as CampaignSource] ?? source;
}
