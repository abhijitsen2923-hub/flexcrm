// Payment-plan wording and arithmetic for the booking's Payment plan window and the project's Payment plan panel.
// Pure, no React, no runtime imports (unit-tested in tests/paymentPlan.test.ts). Dates and money are formatted by
// the caller's formatters so these stay testable.
//
// The rules mirror the backend (backend/app/real_estate/payment_plan.py): a milestone's demand is its percent of
// the booking's price (box price + GST — not stamp duty or registration); an event milestone (stage complete,
// possession, registration) has no demand until it is marked reached or raised on one booking.
import type {
  MilestoneReached,
  PaymentScheduleEntry,
  PlanDueOn,
  PlanMilestone,
  PricingSnapshot,
} from "../types/realestate";

type DateFormatter = (iso: string) => string;
type MoneyFormatter = (amount: number) => string;
interface TowerName {
  id: string;
  name: string;
}

export const EVENT_DUE_ON: readonly PlanDueOn[] = ["on_stage", "on_possession", "on_registration"];

/** Stage complete / possession / registration — demanded when marked reached, not on a date. */
export function isEventMilestone(milestone: Pick<PlanMilestone, "due_on">): boolean {
  return EVENT_DUE_ON.includes(milestone.due_on);
}

/** 10 → "10%", 12.5 → "12.5%", 33.333 → "33.33%". */
export function formatPercent(value: number): string {
  const rounded = Math.round((Number(value) || 0) * 100) / 100;
  return `${rounded.toLocaleString("en-IN", { maximumFractionDigits: 2 })}%`;
}

/** When the milestone falls due, in plain words ("Within 30 days of booking"). */
export function dueOnText(milestone: Pick<PlanMilestone, "due_on" | "days" | "due_date">, formatDate: DateFormatter): string {
  switch (milestone.due_on) {
    case "on_booking":
      return "On booking";
    case "days_after_booking": {
      const days = milestone.days ?? 0;
      return `Within ${days} ${days === 1 ? "day" : "days"} of booking`;
    }
    case "on_date":
      return milestone.due_date ? `On ${formatDate(milestone.due_date)}` : "On a date";
    case "on_stage":
      return "When this stage is complete";
    case "on_possession":
      return "On possession";
    case "on_registration":
      return "On registration";
    default:
      return "";
  }
}

/** Sum of the plan's percentages (rounded to 2 decimals). */
export function planTotal(plan: Pick<PlanMilestone, "percent">[] | null | undefined): number {
  const sum = (plan ?? []).reduce((n, m) => n + (Number(m.percent) || 0), 0);
  return Math.round(sum * 100) / 100;
}

/** The booking's plan milestones that have no demand row yet (still to be raised), in plan order. */
export function pendingMilestones(
  plan: PlanMilestone[] | null | undefined,
  schedules: Pick<PaymentScheduleEntry, "milestoneKey">[]
): PlanMilestone[] {
  if (!plan || plan.length === 0) return [];
  const raised = new Set(schedules.map((s) => s.milestoneKey).filter((k): k is string => !!k));
  return plan.filter((m) => !raised.has(m.key));
}

function num(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

/**
 * What a plan percentage is taken of: box price + GST when the booking's pricing has them; else the total less
 * stamp duty and registration; else the unit's price (a booking whose pricing isn't saved yet).
 */
export function planBase(snapshot: Partial<PricingSnapshot> | null | undefined, unitBasePrice: number): number {
  const box = num(snapshot?.boxPrice);
  const gst = num(snapshot?.gstAmount);
  if (box !== null && gst !== null) return box + gst;
  const total = num(snapshot?.total);
  if (total !== null) return total - (num(snapshot?.stampDutyAmount) ?? 0) - (num(snapshot?.registrationAmount) ?? 0);
  return Number(unitBasePrice) || 0;
}

/** percent × base, rounded to paise (the server rounds the same way). */
export function milestoneAmount(percent: number, base: number): number {
  return Math.round((Number(percent) || 0) * (Number(base) || 0)) / 100;
}

/** The "reached" marks for one milestone: the whole-project mark first, then towers in the project's order. */
export function reachedFor(
  reached: MilestoneReached[] | null | undefined,
  key: string,
  towers: TowerName[]
): MilestoneReached[] {
  const order = new Map(towers.map((t, i) => [t.id, i]));
  return (reached ?? [])
    .filter((r) => r.key === key)
    .sort((a, b) => {
      if (a.towerId === null) return b.towerId === null ? 0 : -1;
      if (b.towerId === null) return 1;
      return (order.get(a.towerId) ?? Number.MAX_SAFE_INTEGER) - (order.get(b.towerId) ?? Number.MAX_SAFE_INTEGER);
    });
}

function towerName(id: string, towers: TowerName[]): string {
  return towers.find((t) => t.id === id)?.name ?? "a tower no longer listed";
}

/** "Tower A", "Tower A and Tower B", "Tower A, Tower B and Tower C". */
function joinNames(names: string[]): string {
  if (names.length <= 1) return names[0] ?? "";
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

/** Which bookings a mark covers, for sentences: "the whole project" or the named towers. */
export function scopeText(towerIds: string[] | null | undefined, towers: TowerName[]): string {
  if (!towerIds || towerIds.length === 0) return "the whole project";
  return joinNames(towerIds.map((id) => towerName(id, towers)));
}

/** "Reached on 12 Oct 2026 — all towers" / "Reached on 12 Oct 2026 — Tower A". */
export function reachedText(entry: MilestoneReached, towers: TowerName[], formatDate: DateFormatter): string {
  const where = entry.towerId === null ? "all towers" : towerName(entry.towerId, towers);
  return `Reached on ${formatDate(entry.reachedOn)} — ${where}`;
}

/** The sentence shown before marking a milestone reached. */
export function markConfirmText(milestone: Pick<PlanMilestone, "label" | "percent">, scope: string): string {
  return `This raises the ${milestone.label} demand (${formatPercent(milestone.percent)}) on every booking in ${scope} that hasn't had it.`;
}

export interface ToastText {
  title: string;
  description?: string;
}

function bookings(count: number): string {
  return `${count.toLocaleString("en-IN")} ${count === 1 ? "booking" : "bookings"}`;
}

/** Toast after marking reached: "Raised on 12 bookings · ₹54,00,000" (+ "3 already had it"). */
export function markResultText(
  result: { raised: number; alreadyRaised: number; amount: number },
  formatMoney: MoneyFormatter
): ToastText {
  const already = result.alreadyRaised > 0 ? `${bookings(result.alreadyRaised)} already had it` : undefined;
  if (result.raised > 0) {
    return { title: `Raised on ${bookings(result.raised)} · ${formatMoney(result.amount)}`, description: already };
  }
  return {
    title: "Marked reached",
    description: already
      ? `No new demands — ${already}.`
      : "No booking holds this milestone yet — bookings made from now on get it straight away.",
  };
}

/** The sentence shown before undoing a mark. */
export function undoConfirmText(milestone: Pick<PlanMilestone, "label">, entry: MilestoneReached, towers: TowerName[]): string {
  const where = entry.towerId === null ? "" : ` in ${towerName(entry.towerId, towers)}`;
  return `Removes the ${milestone.label} demands this raised${where} that have no payment or invoice yet.`;
}

function demands(count: number): string {
  return `${count.toLocaleString("en-IN")} ${count === 1 ? "demand" : "demands"}`;
}

/** Toast after undoing a mark: "Removed 9 demands" (+ "3 kept — they have a payment or invoice"). */
export function undoResultText(result: { removed: number; kept: number }): ToastText {
  const kept = result.kept > 0 ? `${demands(result.kept)} kept — they have a payment or invoice.` : undefined;
  if (result.removed > 0) return { title: `Removed ${demands(result.removed)}`, description: kept };
  return { title: "Mark removed", description: kept ?? "No demands needed removing." };
}

/**
 * An older project's dated demand schedule, shown as plan milestones (read-only) so the panel can list it.
 * Keys are made up for display only — they are never sent to the server.
 */
export function legacyScheduleAsPlan(
  rows: { label: string; percent: number | string; due_date: string }[] | null | undefined
): PlanMilestone[] {
  return (rows ?? []).map((row, i) => ({
    key: `legacy-${i}`,
    label: row.label,
    percent: Number(row.percent) || 0,
    due_on: "on_date",
    days: null,
    due_date: row.due_date ?? null,
  }));
}

/** Today as YYYY-MM-DD in the viewer's own time zone (an <input type="date"> default). */
export function localIsoDate(date: Date = new Date()): string {
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}
