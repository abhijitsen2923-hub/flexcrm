// "Assigned today / yesterday / on a day" — pure helpers for the leads list's assignment filter and the
// dashboard tile (unit-tested in tests/assignedDay.test.ts). "Assigned" = when the lead was given to its
// CURRENT owner (Lead.assigned_at); the day is the user's LOCAL calendar day. Self-contained (no runtime
// imports) so `node --test` can load it directly.

/** "" (off) | "today" | "yesterday" | a picked day "YYYY-MM-DD". */
export type AssignedDay = string;

const DAY_RE = /^\d{4}-\d{2}-\d{2}$/;

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

/** Local YYYY-MM-DD for a Date. */
export function localDay(date: Date): string {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

/** The calendar day an AssignedDay stands for (null when off / invalid). */
export function assignedDayDate(day: AssignedDay, now: Date = new Date()): string | null {
  if (day === "today") return localDay(now);
  if (day === "yesterday") {
    const d = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1);
    return localDay(d);
  }
  // Round-trip check: "2026-02-31" would otherwise roll over to 3 Mar.
  if (DAY_RE.test(day)) {
    const d = new Date(`${day}T00:00:00`);
    if (!Number.isNaN(d.getTime()) && localDay(d) === day) return day;
  }
  return null;
}

/** A day typed/picked in the date box is applied only once it's a whole, sensible date: no half-typed years
 * ("0002-10-04" while typing 2025), nothing before 2000 or after today. */
export function isPickableDay(day: string, now: Date = new Date()): boolean {
  const date = assignedDayDate(day, now);
  return date !== null && date >= "2000-01-01" && date <= localDay(now);
}

/** Query bounds for the leads API: local midnight of the day → local midnight of the next (half-open, the
 * same bounds as utils/dateRange.ts localDayRange gives the "Lead date" filter), or {} when off. */
export function assignedDayQuery(day: AssignedDay, now: Date = new Date()): { assigned_from?: string; assigned_to?: string } {
  const date = assignedDayDate(day, now);
  if (!date) return {};
  const start = new Date(`${date}T00:00:00`); // no zone suffix → LOCAL midnight
  const end = new Date(start);
  end.setDate(end.getDate() + 1);
  return { assigned_from: start.toISOString(), assigned_to: end.toISOString() };
}

/** "Today" / "Yesterday" / "Fri 10 Oct" (a picked day that happens to be today/yesterday reads that way too). */
export function assignedDayLabel(day: AssignedDay, now: Date = new Date()): string {
  const date = assignedDayDate(day, now);
  if (!date) return "";
  if (date === assignedDayDate("today", now)) return "Today";
  if (date === assignedDayDate("yesterday", now)) return "Yesterday";
  const d = new Date(`${date}T00:00:00`);
  return d.toLocaleDateString("en-IN", {
    weekday: "short",
    day: "numeric",
    month: "short",
    ...(d.getFullYear() !== now.getFullYear() ? { year: "numeric" } : {}),
  });
}

/** Phrase after "assigned": "today" / "yesterday" / "on Fri 10 Oct". */
export function assignedDayPhrase(day: AssignedDay, now: Date = new Date()): string {
  const label = assignedDayLabel(day, now);
  if (label === "Today" || label === "Yesterday") return label.toLowerCase();
  return label ? `on ${label}` : "";
}

/** `?assigned=` from a link (the dashboard tile): "today" | "yesterday" | "YYYY-MM-DD"; anything else → off. */
export function parseAssignedParam(value: string | null | undefined): AssignedDay {
  const v = (value ?? "").trim().toLowerCase();
  if (v === "today" || v === "yesterday") return v;
  return assignedDayDate(v) ? v : "";
}

export interface StageCount {
  code: string;
  name: string;
  count: number;
}

/** Leads per stage, in pipeline order (only stages that have leads); unknown stage codes go last. */
export function countByStage(
  leads: readonly { stage_code: string }[],
  stages: readonly { code: string; name: string; position: number }[]
): StageCount[] {
  const counts = new Map<string, number>();
  for (const lead of leads) counts.set(lead.stage_code, (counts.get(lead.stage_code) ?? 0) + 1);
  const known = [...stages]
    .sort((a, b) => a.position - b.position)
    .filter((s) => counts.has(s.code))
    .map((s) => ({ code: s.code, name: s.name, count: counts.get(s.code)! }));
  const knownCodes = new Set(known.map((s) => s.code));
  const unknown = [...counts.entries()]
    .filter(([code]) => !knownCodes.has(code))
    .map(([code, count]) => ({ code, name: code, count }));
  return [...known, ...unknown];
}
