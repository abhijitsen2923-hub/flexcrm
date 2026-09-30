// Lead intent (High / Medium / Low) — pure helpers, no React (unit-tested in tests/leadIntent.test.ts).
// The "fixed from Booked onward" rule mirrors the backend (backend/app/core/lead_intent.py).
import type { LeadIntent, LeadIntentSource, PipelineStage } from "../types/crm";

export interface IntentOption {
  key: LeadIntent;
  label: string;
  hint: string;
}

// Left → right on the slider.
export const INTENT_OPTIONS: readonly IntentOption[] = [
  { key: "low", label: "Low", hint: "Just exploring" },
  { key: "medium", label: "Medium", hint: "Considering" },
  { key: "high", label: "High", hint: "Ready to buy" },
];

export const INTENT_LABEL: Record<LeadIntent, string> = { high: "High", medium: "Medium", low: "Low" };

// Leads-list filter token for "no intent yet".
export const NOT_RATED = "none";
export type IntentFilterToken = LeadIntent | typeof NOT_RATED;
// Canonical order of filter tokens (chips, applied chip, query string).
export const INTENT_FILTER_ORDER: readonly IntentFilterToken[] = ["high", "medium", "low", NOT_RATED];

// Real-estate "Booked / Token" position in the seeded pipeline — used only if the stage list isn't loaded.
const REAL_ESTATE_BOOKED_POSITION = 8;

export function isLeadIntent(value: unknown): value is LeadIntent {
  return value === "high" || value === "medium" || value === "low";
}

/**
 * True when a lead at `stage` keeps its intent as is: a closed stage (won or lost), or a real-estate stage at
 * or after "Booked / Token". A move there doesn't ask for intent and the lead details show it read-only.
 * `industryStages` = that industry's pipeline (finds Booked's position); unknown stage → not locked.
 */
export function isIntentLocked(
  stage: Pick<PipelineStage, "industry" | "position" | "category"> | undefined | null,
  industryStages: readonly Pick<PipelineStage, "code" | "position">[] = []
): boolean {
  if (!stage) return false;
  if (stage.category === "closed_won" || stage.category === "closed_lost") return true;
  if (stage.industry !== "real_estate") return false;
  const booked = industryStages.find((s) => s.code === "booked")?.position ?? REAL_ESTATE_BOOKED_POSITION;
  return stage.position >= booked;
}

/** Slider position 0..2 for an intent; -1 = not set (no handle shown). */
export function intentIndex(intent: LeadIntent | null | undefined): number {
  return intent ? INTENT_OPTIONS.findIndex((o) => o.key === intent) : -1;
}

/** The intent at a point along the bar (0 = left end, 1 = right end) — snaps to the nearest of the three. */
export function intentAtRatio(ratio: number): LeadIntent {
  const clamped = Math.min(1, Math.max(0, Number.isFinite(ratio) ? ratio : 0));
  return INTENT_OPTIONS[Math.round(clamped * (INTENT_OPTIONS.length - 1))].key;
}

/** Arrow-key step: from "not set", any arrow lands on Medium; otherwise one step, clamped at the ends. */
export function stepIntent(intent: LeadIntent | null | undefined, delta: 1 | -1): LeadIntent {
  const index = intentIndex(intent);
  if (index < 0) return "medium";
  return INTENT_OPTIONS[Math.min(INTENT_OPTIONS.length - 1, Math.max(0, index + delta))].key;
}

// ---- Leads-list filter ----------------------------------------------------------------------------------------

/** "high,none" → {"high","none"}; unknown tokens dropped; case / spaces ignored. */
export function parseIntentFilter(value: string | null | undefined): Set<IntentFilterToken> {
  const tokens = new Set<IntentFilterToken>();
  for (const raw of (value ?? "").split(",")) {
    const token = raw.trim().toLowerCase();
    if ((INTENT_FILTER_ORDER as readonly string[]).includes(token)) tokens.add(token as IntentFilterToken);
  }
  return tokens;
}

/** {"none","high"} → "high,none" (canonical order); empty → "". */
export function serializeIntentFilter(tokens: ReadonlySet<IntentFilterToken>): string {
  return INTENT_FILTER_ORDER.filter((t) => tokens.has(t)).join(",");
}

/** Add or remove one token. */
export function toggleIntentFilter(value: string, token: IntentFilterToken): string {
  const tokens = parseIntentFilter(value);
  if (tokens.has(token)) tokens.delete(token);
  else tokens.add(token);
  return serializeIntentFilter(tokens);
}

/** Applied-filter chip text: "High, Not rated". */
export function intentFilterLabel(value: string): string {
  return INTENT_FILTER_ORDER.filter((t) => parseIntentFilter(value).has(t))
    .map((t) => (t === NOT_RATED ? "Not rated" : INTENT_LABEL[t]))
    .join(", ");
}

/** How a change happened, for the history line. */
export function intentSourceLabel(source: LeadIntentSource): string {
  switch (source) {
    case "quick_set":
      return "changed in lead details";
    case "bulk":
      return "set on a bulk move";
    case "created":
      return "set when the lead was added";
    case "import":
      return "set by CSV upload";
    default:
      return "set on a stage change";
  }
}
