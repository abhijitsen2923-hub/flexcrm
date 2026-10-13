// Unit tests for the payment-plan helpers (src/utils/paymentPlan.ts): due-on wording, pending milestones, the
// "% of price" base (mirrors backend plan_base), reached marks and the mark / undo messages. Run: npm test
import assert from "node:assert/strict";
import { test } from "node:test";

import type { MilestoneReached, PlanMilestone } from "../src/types/realestate.ts";
import {
  dueOnText,
  formatPercent,
  isEventMilestone,
  legacyScheduleAsPlan,
  localIsoDate,
  markConfirmText,
  markResultText,
  milestoneAmount,
  pendingMilestones,
  planBase,
  planTotal,
  reachedFor,
  reachedText,
  scopeText,
  undoConfirmText,
  undoResultText,
} from "../src/utils/paymentPlan.ts";

const fmtDate = (iso: string) => `<${iso}>`;
const fmtInr = (n: number) => `₹${n}`;

function milestone(overrides: Partial<PlanMilestone> = {}): PlanMilestone {
  return { key: "m1", label: "Booking amount", percent: 10, due_on: "on_booking", days: null, due_date: null, ...overrides };
}

const SAMPLE_PLAN: PlanMilestone[] = [
  milestone({ key: "bk", label: "Booking", percent: 10, due_on: "on_booking" }),
  milestone({ key: "ag", label: "Agreement", percent: 20, due_on: "days_after_booking", days: 30 }),
  milestone({ key: "fd", label: "Foundation complete", percent: 15, due_on: "on_stage" }),
  milestone({ key: "st", label: "Structure complete", percent: 20, due_on: "on_stage" }),
  milestone({ key: "ps", label: "Possession", percent: 25, due_on: "on_possession" }),
  milestone({ key: "rg", label: "Registration", percent: 10, due_on: "on_registration" }),
];

const TOWERS = [
  { id: "t-a", name: "Tower A" },
  { id: "t-b", name: "Tower B" },
  { id: "t-c", name: "Tower C" },
];

test("event milestones are the stage / possession / registration ones", () => {
  assert.deepEqual(
    SAMPLE_PLAN.filter(isEventMilestone).map((m) => m.key),
    ["fd", "st", "ps", "rg"]
  );
  assert.equal(isEventMilestone({ due_on: "on_date" }), false);
});

test("dueOnText says when each milestone falls due", () => {
  assert.equal(dueOnText(milestone({ due_on: "on_booking" }), fmtDate), "On booking");
  assert.equal(dueOnText(milestone({ due_on: "days_after_booking", days: 30 }), fmtDate), "Within 30 days of booking");
  assert.equal(dueOnText(milestone({ due_on: "days_after_booking", days: 1 }), fmtDate), "Within 1 day of booking");
  assert.equal(dueOnText(milestone({ due_on: "on_date", due_date: "2026-12-01" }), fmtDate), "On <2026-12-01>");
  assert.equal(dueOnText(milestone({ due_on: "on_date", due_date: null }), fmtDate), "On a date");
  assert.equal(dueOnText(milestone({ due_on: "on_stage" }), fmtDate), "When this stage is complete");
  assert.equal(dueOnText(milestone({ due_on: "on_possession" }), fmtDate), "On possession");
  assert.equal(dueOnText(milestone({ due_on: "on_registration" }), fmtDate), "On registration");
});

test("formatPercent and planTotal", () => {
  assert.equal(formatPercent(10), "10%");
  assert.equal(formatPercent(12.5), "12.5%");
  assert.equal(formatPercent(33.333), "33.33%");
  assert.equal(planTotal(SAMPLE_PLAN), 100);
  assert.equal(planTotal([milestone({ percent: 33.33 }), milestone({ percent: 33.33 }), milestone({ percent: 33.34 })]), 100);
  assert.equal(planTotal(null), 0);
});

test("pending = plan milestones with no demand row carrying their key, in plan order", () => {
  const rows = [
    { milestoneKey: "bk" },
    { milestoneKey: "ag" },
    { milestoneKey: null }, // a manual row added by hand
  ];
  assert.deepEqual(
    pendingMilestones(SAMPLE_PLAN, rows).map((m) => m.key),
    ["fd", "st", "ps", "rg"]
  );
  // A deleted date row becomes pending again.
  assert.deepEqual(pendingMilestones(SAMPLE_PLAN, [{ milestoneKey: "ag" }]).map((m) => m.key)[0], "bk");
  assert.deepEqual(pendingMilestones(null, rows), []);
  assert.deepEqual(pendingMilestones([], rows), []);
});

test("planBase: box price + GST, else total less stamp duty and registration, else the unit price", () => {
  assert.equal(planBase({ boxPrice: 5_000_000, gstAmount: 250_000, total: 5_600_000, stampDutyAmount: 350_000 }, 4_000_000), 5_250_000);
  // Older snapshot without boxPrice.
  assert.equal(planBase({ total: 5_600_000, stampDutyAmount: 250_000, registrationAmount: 50_000 }, 4_000_000), 5_300_000);
  assert.equal(planBase({ total: 5_600_000 }, 4_000_000), 5_600_000);
  // Pricing not saved yet.
  assert.equal(planBase(null, 4_000_000), 4_000_000);
  assert.equal(planBase(undefined, 0), 0);
});

test("milestoneAmount is percent × base, to the paisa", () => {
  assert.equal(milestoneAmount(10, 5_250_000), 525_000);
  assert.equal(milestoneAmount(12.5, 1_000_001), 125_000.13);
  assert.equal(milestoneAmount(0, 5_000_000), 0);
});

test("reached marks: whole project first, then towers in the project's order; other keys ignored", () => {
  const reached: MilestoneReached[] = [
    { key: "fd", towerId: "t-c", reachedOn: "2026-10-05" },
    { key: "st", towerId: null, reachedOn: "2026-11-01" },
    { key: "fd", towerId: "t-a", reachedOn: "2026-10-01" },
    { key: "fd", towerId: null, reachedOn: "2026-10-12" },
  ];
  assert.deepEqual(
    reachedFor(reached, "fd", TOWERS).map((r) => r.towerId),
    [null, "t-a", "t-c"]
  );
  assert.deepEqual(reachedFor(null, "fd", TOWERS), []);
});

test("reachedText names the scope", () => {
  assert.equal(
    reachedText({ key: "fd", towerId: null, reachedOn: "2026-10-12" }, TOWERS, fmtDate),
    "Reached on <2026-10-12> — all towers"
  );
  assert.equal(
    reachedText({ key: "fd", towerId: "t-b", reachedOn: "2026-10-12" }, TOWERS, fmtDate),
    "Reached on <2026-10-12> — Tower B"
  );
  assert.equal(
    reachedText({ key: "fd", towerId: "gone", reachedOn: "2026-10-12" }, TOWERS, fmtDate),
    "Reached on <2026-10-12> — a tower no longer listed"
  );
});

test("scopeText and the mark confirmation sentence", () => {
  assert.equal(scopeText(null, TOWERS), "the whole project");
  assert.equal(scopeText([], TOWERS), "the whole project");
  assert.equal(scopeText(["t-a"], TOWERS), "Tower A");
  assert.equal(scopeText(["t-a", "t-c"], TOWERS), "Tower A and Tower C");
  assert.equal(scopeText(["t-a", "t-b", "t-c"], TOWERS), "Tower A, Tower B and Tower C");
  assert.equal(
    markConfirmText(SAMPLE_PLAN[2], "Tower A"),
    "This raises the Foundation complete demand (15%) on every booking in Tower A that hasn't had it."
  );
});

test("mark result toast", () => {
  assert.deepEqual(markResultText({ raised: 12, alreadyRaised: 0, amount: 5_400_000 }, fmtInr), {
    title: "Raised on 12 bookings · ₹5400000",
    description: undefined,
  });
  assert.deepEqual(markResultText({ raised: 1, alreadyRaised: 3, amount: 450_000 }, fmtInr), {
    title: "Raised on 1 booking · ₹450000",
    description: "3 bookings already had it",
  });
  assert.deepEqual(markResultText({ raised: 0, alreadyRaised: 1, amount: 0 }, fmtInr), {
    title: "Marked reached",
    description: "No new demands — 1 booking already had it.",
  });
  assert.equal(markResultText({ raised: 0, alreadyRaised: 0, amount: 0 }, fmtInr).title, "Marked reached");
  assert.match(markResultText({ raised: 0, alreadyRaised: 0, amount: 0 }, fmtInr).description ?? "", /from now on/);
});

test("undo confirmation and result", () => {
  assert.equal(
    undoConfirmText(SAMPLE_PLAN[2], { key: "fd", towerId: null, reachedOn: "2026-10-12" }, TOWERS),
    "Removes the Foundation complete demands this raised that have no payment or invoice yet."
  );
  assert.equal(
    undoConfirmText(SAMPLE_PLAN[2], { key: "fd", towerId: "t-b", reachedOn: "2026-10-12" }, TOWERS),
    "Removes the Foundation complete demands this raised in Tower B that have no payment or invoice yet."
  );
  assert.deepEqual(undoResultText({ removed: 9, kept: 0 }), { title: "Removed 9 demands", description: undefined });
  assert.deepEqual(undoResultText({ removed: 1, kept: 2 }), {
    title: "Removed 1 demand",
    description: "2 demands kept — they have a payment or invoice.",
  });
  assert.deepEqual(undoResultText({ removed: 0, kept: 0 }), { title: "Mark removed", description: "No demands needed removing." });
});

test("an older project's dated demand schedule reads as on-date milestones", () => {
  const plan = legacyScheduleAsPlan([
    { label: "Booking", percent: "10", due_date: "2026-11-01" },
    { label: "Slab", percent: 90, due_date: "2027-03-01" },
  ]);
  assert.deepEqual(plan.map((m) => [m.label, m.percent, m.due_on, m.due_date]), [
    ["Booking", 10, "on_date", "2026-11-01"],
    ["Slab", 90, "on_date", "2027-03-01"],
  ]);
  assert.equal(new Set(plan.map((m) => m.key)).size, 2);
  assert.deepEqual(legacyScheduleAsPlan(null), []);
});

test("localIsoDate uses the local calendar date", () => {
  assert.equal(localIsoDate(new Date(2026, 0, 5, 23, 59)), "2026-01-05");
  assert.equal(localIsoDate(new Date(2026, 9, 13, 0, 1)), "2026-10-13");
});
