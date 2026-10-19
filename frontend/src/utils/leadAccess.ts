// A custom role's "Data access": which leads its users see — chosen campaigns, chosen sources, and/or only the
// leads assigned to them (backend: app/services/lead_scope.py). A lead must match every limit that is set; a lead
// with no campaign (or no source) is outside a campaign (or source) limit.

/** How a role's access comes back from the API (`CustomRoleRead.lead_access`). null = not limited on that one. */
export interface RoleLeadAccess {
  own_leads_only: boolean;
  campaigns: { id: string; name: string }[] | null;
  sources: string[] | null;
}

/** The signed-in user's limits (`/auth/profile` → `lead_access`; absent = sees every lead). */
export interface UserLeadAccess {
  own_leads_only: boolean;
  campaigns: string[] | null;
  sources: string[] | null;
}

/** What the role editor sends. */
export interface LeadAccessPayload {
  own_leads_only: boolean;
  campaign_ids: string[] | null;
  sources: string[] | null;
}

export type AccessMode = "all" | "chosen";

/** The role editor's form state. */
export interface LeadAccessDraft {
  ownOnly: boolean;
  campaignMode: AccessMode;
  campaignIds: string[];
  sourceMode: AccessMode;
  sources: string[];
}

/** Permissions a limited role can't hold (they act on every lead or could lift the limits). Mirrors the backend's
 *  LEAD_LIMITED_EXCLUDED. */
export const LIMITED_EXCLUDED_PERMISSIONS: ReadonlyArray<string> = ["USER_MANAGE", "ORG_MANAGE", "CAMPAIGN_MANAGE"];

export function draftFromRole(access: RoleLeadAccess | null | undefined): LeadAccessDraft {
  return {
    ownOnly: Boolean(access?.own_leads_only),
    campaignMode: access?.campaigns ? "chosen" : "all",
    campaignIds: (access?.campaigns ?? []).map((c) => c.id),
    sourceMode: access?.sources ? "chosen" : "all",
    sources: [...(access?.sources ?? [])],
  };
}

export function draftIsLimited(draft: LeadAccessDraft): boolean {
  return draft.ownOnly || draft.campaignMode === "chosen" || draft.sourceMode === "chosen";
}

/** Why the draft can't be saved yet, or null. */
export function draftProblem(draft: LeadAccessDraft): string | null {
  if (draft.campaignMode === "chosen" && draft.campaignIds.length === 0) {
    return "Choose at least one campaign, or allow all campaigns.";
  }
  if (draft.sourceMode === "chosen" && draft.sources.length === 0) {
    return "Choose at least one source, or allow all sources.";
  }
  return null;
}

export function draftToPayload(draft: LeadAccessDraft): LeadAccessPayload {
  return {
    own_leads_only: draft.ownOnly,
    campaign_ids: draft.campaignMode === "chosen" ? [...new Set(draft.campaignIds)] : null,
    sources: draft.sourceMode === "chosen" ? dedupeLabels(draft.sources) : null,
  };
}

/** Add or remove one value (case-insensitive for labels). */
export function toggleValue(values: string[], value: string, on: boolean, caseInsensitive = false): string[] {
  const same = (a: string) => (caseInsensitive ? a.toLowerCase() === value.toLowerCase() : a === value);
  const rest = values.filter((v) => !same(v));
  return on ? [...rest, value] : rest;
}

function dedupeLabels(values: string[]): string[] {
  const seen = new Map<string, string>();
  for (const raw of values) {
    const label = raw.split(/\s+/).filter(Boolean).join(" ");
    if (label && !seen.has(label.toLowerCase())) seen.set(label.toLowerCase(), label);
  }
  return [...seen.values()];
}

function listPhrase(values: string[], max = 3): string {
  if (values.length <= max) return values.join(", ");
  return `${values.slice(0, max).join(", ")} +${values.length - max} more`;
}

/** One line for a role card / the user's own banner: "All leads" or "Campaigns: A, B · Sources: Website · Only their
 *  own leads". */
export function describeLeadAccess(access: RoleLeadAccess | UserLeadAccess | null | undefined, own = "their"): string {
  if (!access) return "All leads";
  const parts: string[] = [];
  if (access.campaigns) {
    const names = access.campaigns.map((c) => (typeof c === "string" ? c : c.name));
    parts.push(names.length ? `Campaigns: ${listPhrase(names)}` : "Campaigns: none (removed)");
  }
  if (access.sources) parts.push(`Sources: ${listPhrase(access.sources)}`);
  if (access.own_leads_only) parts.push(`Only ${own} own leads`);
  return parts.length ? parts.join(" · ") : "All leads";
}

export interface Option {
  value: string;
  label: string;
}

/** Source choices for a limited user (New Lead form, Source filter): only their allowed sources, spelled like the
 *  standard list when it has them; no "Other…". Everyone else gets the full list unchanged. */
export function sourceOptionsFor(base: Option[], access: UserLeadAccess | null | undefined): Option[] {
  if (!access?.sources) return base;
  const byKey = new Map(base.map((o) => [o.value.toLowerCase(), o]));
  return dedupeLabels(access.sources).map((s) => byKey.get(s.toLowerCase()) ?? { value: s, label: s });
}

/** The campaign a limited user's New Lead form starts with: their only campaign, when they have exactly one. */
export function defaultCampaignFor(access: UserLeadAccess | null | undefined): string {
  return access?.campaigns && access.campaigns.length === 1 ? access.campaigns[0] : "";
}

/** The source a limited user's New Lead form starts with: their only source, when they have exactly one. */
export function defaultSourceFor(base: Option[], access: UserLeadAccess | null | undefined): string {
  const options = access?.sources ? sourceOptionsFor(base, access) : [];
  return options.length === 1 ? options[0].value : "";
}
