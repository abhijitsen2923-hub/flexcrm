// Pure helpers for the lead drawer's Stage History tab: merge stage moves and owner changes into ONE
// timeline, and label owner changes. No React / DOM, so they're unit-testable with `node --test`.
import type { HistoryActor, LeadAssignmentEvent, StageTransition } from "../../types";

export type TimelineEntry =
  | { kind: "stage"; key: string; at: string; transition: StageTransition }
  | { kind: "owner"; key: string; at: string; event: LeadAssignmentEvent };

const SOURCE_LABELS: Record<string, string> = {
  created: "Assigned when created",
  import: "Assigned on upload",
  reassign: "Reassigned",
  bulk_reassign: "Bulk reassigned",
  booking: "Salesperson set at booking",
};

export function assignmentSourceLabel(source: string): string {
  return SOURCE_LABELS[source] ?? "Owner changed";
}

/** "First Last", skipping missing parts; `fallback` when there's no usable name (e.g. unassigned). */
export function actorName(
  actor: Pick<HistoryActor, "first_name" | "last_name"> | null | undefined,
  fallback: string
): string {
  const name = [actor?.first_name, actor?.last_name]
    .map((part) => (part ?? "").trim())
    .filter(Boolean)
    .join(" ");
  return name || fallback;
}

function toTime(iso: string): number {
  const t = Date.parse(iso);
  return Number.isNaN(t) ? 0 : t;
}

/**
 * Stage moves + owner changes, newest first. On an identical timestamp (creating a lead with an owner
 * writes both in one transaction) the owner change sorts above the stage entry, so "Lead created" stays
 * at the bottom; otherwise each source keeps its own (newest-first) order.
 */
export function buildLeadTimeline(
  transitions: readonly StageTransition[],
  events: readonly LeadAssignmentEvent[]
): TimelineEntry[] {
  const entries: TimelineEntry[] = [
    ...transitions.map((t) => ({ kind: "stage" as const, key: `stage-${t.id}`, at: t.performed_at, transition: t })),
    ...events.map((e) => ({ kind: "owner" as const, key: `owner-${e.id}`, at: e.performed_at, event: e })),
  ];
  return entries
    .map((entry, index) => ({ entry, index }))
    .sort((a, b) => {
      const byTime = toTime(b.entry.at) - toTime(a.entry.at);
      if (byTime !== 0) return byTime;
      if (a.entry.kind !== b.entry.kind) return a.entry.kind === "owner" ? -1 : 1;
      return a.index - b.index;
    })
    .map(({ entry }) => entry);
}
