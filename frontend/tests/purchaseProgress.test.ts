// Unit tests for the Customer drawer's Purchases card (src/utils/purchaseProgress.ts): the money figures (no price
// saved, token only, token as a receipt counted once, receipts − refunds, cancelled left out), the stage → strip
// step mapping, the step read from the booking when no lead stage is known, the one next action per state, and
// which realtime events reload the drawer. Run: npm test
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  POSSESSION_CHECKLIST,
  effectiveStep,
  exactInr,
  instalmentTotals,
  isPossessionComplete,
  isReadyToClose,
  nextAction,
  nextStageMove,
  paidBreakdown,
  paidHint,
  paidPercent,
  purchaseEventMatters,
  purchaseMoney,
  purchaseStep,
  purchaseTotals,
  stepFromBooking,
  type PurchasePerms,
} from "../src/utils/purchaseProgress.ts";

interface TestBooking {
  status: string;
  tokenAmount: number | null;
  pricingSnapshot: { total?: number | null } | null;
  paymentReceipts: { amount: number; isToken?: boolean }[];
  refunds: { refundAmount: number }[];
  registrationNumber: string | null;
  possessionChecklist: boolean[] | null;
  unit?: { basePrice: number; status: string } | null;
}

const booking = (patch: Partial<TestBooking> = {}): TestBooking => ({
  status: "confirmed",
  tokenAmount: null,
  pricingSnapshot: null,
  paymentReceipts: [],
  refunds: [],
  registrationNumber: null,
  possessionChecklist: null,
  unit: { basePrice: 5_000_000, status: "booked" },
  ...patch,
});

const allTicked = POSSESSION_CHECKLIST.map(() => true);
const lakh = (n: number) => `${n / 100_000}L`;

const manager: PurchasePerms = { leadManage: true, recordPayment: true, canSetStage: () => true };
// A sales executive: may move to every active stage but not Sold (utils/stageAccess).
const salesExec: PurchasePerms = { leadManage: true, recordPayment: false, canSetStage: (code) => code !== "sold" };
// Accounts: records payments, can't touch leads.
const accounts: PurchasePerms = { leadManage: false, recordPayment: true, canSetStage: () => true };
const readOnly: PurchasePerms = { leadManage: false, recordPayment: false, canSetStage: () => false };
// A telecaller: has LEAD_MANAGE but may only set the early stages (utils/stageAccess).
const telecaller: PurchasePerms = {
  leadManage: true,
  recordPayment: false,
  canSetStage: (code) => ["call", "did_not_pickup", "follow_up", "not_interested", "disqualified"].includes(code),
};

const lead = (stage_code: string, category: string | null = null) => ({ stage_code, category });

// ------------------------------------------------------------------ money

test("no price saved yet: total is the list price, marked not final; balance is the list price less the token", () => {
  const m = purchaseMoney(booking({ status: "draft", tokenAmount: 100_000, unit: { basePrice: 5_000_000, status: "hold" } }));
  assert.equal(m.listPrice, 5_000_000);
  assert.equal(m.total, 5_000_000);
  assert.equal(m.totalIsFinal, false);
  assert.equal(m.tokenPaid, 100_000);
  assert.equal(m.paid, 100_000);
  assert.equal(m.balance, 4_900_000);
});

test("saved price wins over the list price", () => {
  const m = purchaseMoney(booking({ pricingSnapshot: { total: 6_250_000 } }));
  assert.equal(m.total, 6_250_000);
  assert.equal(m.totalIsFinal, true);
  assert.equal(m.listPrice, 5_000_000);
  assert.equal(m.balance, 6_250_000);
});

test("a saved price of 0 is still a saved price; a snapshot without a total is not", () => {
  assert.equal(purchaseMoney(booking({ pricingSnapshot: { total: 0 } })).totalIsFinal, true);
  const noTotal = purchaseMoney(booking({ pricingSnapshot: {} }));
  assert.equal(noTotal.totalIsFinal, false);
  assert.equal(noTotal.total, 5_000_000);
});

test("token only on the booking (older booking, no token receipt): counted once as paid", () => {
  const m = purchaseMoney(booking({ tokenAmount: 200_000 }));
  assert.deepEqual(
    { paid: m.paid, tokenPaid: m.tokenPaid, payments: m.payments, refunds: m.refunds },
    { paid: 200_000, tokenPaid: 200_000, payments: 0, refunds: 0 }
  );
});

test("token stored as a receipt is not counted twice with the booking's token field", () => {
  const m = purchaseMoney(
    booking({
      tokenAmount: 200_000,
      paymentReceipts: [
        { amount: 200_000, isToken: true },
        { amount: 500_000 },
      ],
    })
  );
  assert.equal(m.tokenPaid, 200_000);
  assert.equal(m.payments, 500_000);
  assert.equal(m.paid, 700_000);
  assert.equal(m.balance, 4_300_000);
});

test("token updated after a receipt existed: the receipt's amount is what was paid", () => {
  // The booking field and the token receipt are kept in step by the server; if they ever differ the receipt wins.
  const m = purchaseMoney(booking({ tokenAmount: 300_000, paymentReceipts: [{ amount: 250_000, isToken: true }] }));
  assert.equal(m.tokenPaid, 250_000);
  assert.equal(m.paid, 250_000);
});

test("paid = receipts − refunds; balance never goes below 0", () => {
  const m = purchaseMoney(
    booking({
      pricingSnapshot: { total: 1_000_000 },
      paymentReceipts: [{ amount: 100_000, isToken: true }, { amount: 900_000 }, { amount: 250_000 }],
      refunds: [{ refundAmount: 50_000 }],
    })
  );
  assert.equal(m.paid, 1_200_000);
  assert.equal(m.refunds, 50_000);
  assert.equal(m.balance, 0);
});

test("money sums don't drift by floating-point paise", () => {
  const m = purchaseMoney(booking({ pricingSnapshot: { total: 1 }, paymentReceipts: [{ amount: 0.1 }, { amount: 0.2 }] }));
  assert.equal(m.paid, 0.3);
  assert.equal(m.balance, 0.7);
});

test("missing unit: no list price, total 0 until a price is saved", () => {
  const m = purchaseMoney(booking({ unit: null }));
  assert.equal(m.listPrice, null);
  assert.equal(m.total, 0);
  assert.equal(m.balance, 0);
});

test("totals leave cancelled bookings out", () => {
  const totals = purchaseTotals([
    booking({ pricingSnapshot: { total: 6_000_000 }, paymentReceipts: [{ amount: 1_000_000 }] }),
    booking({ status: "draft", tokenAmount: 100_000 }),
    booking({ status: "cancelled", pricingSnapshot: { total: 9_000_000 }, paymentReceipts: [{ amount: 500_000 }] }),
  ]);
  assert.deepEqual(totals, { count: 2, total: 11_000_000, paid: 1_100_000, balance: 9_900_000 });
  assert.deepEqual(purchaseTotals([booking({ status: "cancelled" })]), { count: 0, total: 0, paid: 0, balance: 0 });
});

test("paid breakdown wording", () => {
  const m = purchaseMoney(
    booking({ paymentReceipts: [{ amount: 100_000, isToken: true }, { amount: 500_000 }], refunds: [{ refundAmount: 200_000 }] })
  );
  assert.equal(paidBreakdown(m, lakh), "Token 1L + payments 5L − refunds 2L");
  assert.equal(paidBreakdown(purchaseMoney(booking({ tokenAmount: 100_000 })), lakh), "Token 1L + payments 0L");
});

test("short paid hint and percent paid", () => {
  assert.equal(paidHint(purchaseMoney(booking()), lakh), "Nothing received yet");
  assert.equal(paidHint(purchaseMoney(booking({ tokenAmount: 100_000 })), lakh), "Token");
  assert.equal(
    paidHint(purchaseMoney(booking({ paymentReceipts: [{ amount: 100_000, isToken: true }, { amount: 400_000 }] })), lakh),
    "incl. token 1L"
  );
  assert.equal(paidHint(purchaseMoney(booking({ paymentReceipts: [{ amount: 400_000 }] })), lakh), "");
  assert.equal(
    paidHint(purchaseMoney(booking({ paymentReceipts: [{ amount: 400_000 }], refunds: [{ refundAmount: 100_000 }] })), lakh),
    "less refunds 1L"
  );
  assert.equal(paidPercent({ total: 1_000_000, paid: 999_999 }), 99);
  assert.equal(paidPercent({ total: 1_000_000, paid: 1_000_000 }), 100);
  assert.equal(paidPercent({ total: 1_000_000, paid: 2_000_000 }), 100);
  assert.equal(paidPercent({ total: 0, paid: 100 }), 0);
});

test("exact figure in Indian digit grouping", () => {
  assert.equal(exactInr(5_012_345), "₹50,12,345");
  assert.equal(exactInr(12_500_000.5), "₹1,25,00,000.5");
  assert.equal(exactInr(Number.NaN), "₹0");
});

test("instalment totals for the Payments tab", () => {
  assert.deepEqual(
    instalmentTotals([
      { demandAmount: 500_000, paidAmount: 500_000, outstanding: 0 },
      { demandAmount: 1_000_000, paidAmount: 250_000, outstanding: 750_000 },
    ]),
    { demand: 1_500_000, paid: 750_000, outstanding: 750_000 }
  );
  assert.deepEqual(instalmentTotals([]), { demand: 0, paid: 0, outstanding: 0 });
});

// ------------------------------------------------------------------ strip

test("stage → strip step", () => {
  assert.deepEqual(purchaseStep("booked"), { kind: "step", index: 0 });
  assert.deepEqual(purchaseStep("agreement_payment"), { kind: "step", index: 1 });
  assert.deepEqual(purchaseStep("registration"), { kind: "step", index: 2 });
  assert.deepEqual(purchaseStep("possession"), { kind: "step", index: 3 });
  assert.deepEqual(purchaseStep("sold", "closed_won"), { kind: "step", index: 4 });
});

test("stages before Booked / Token have no step; lost stages show as lost", () => {
  for (const code of ["new_enquiry", "call", "did_not_pickup", "follow_up", "site_visit_confirmed", "site_visit_done", "interested"]) {
    assert.deepEqual(purchaseStep(code), { kind: "before" }, code);
  }
  assert.deepEqual(purchaseStep("not_interested"), { kind: "lost" });
  assert.deepEqual(purchaseStep("disqualified", "closed_lost"), { kind: "lost" });
  // Any closed-lost stage (by category) is lost, even a code this file doesn't list.
  assert.deepEqual(purchaseStep("did_not_pick", "closed_lost"), { kind: "lost" });
  assert.deepEqual(purchaseStep("enrolled"), { kind: "unknown" });
  assert.deepEqual(purchaseStep(null), { kind: "unknown" });
});

test("possession complete only when every checklist item is ticked", () => {
  assert.equal(isPossessionComplete(allTicked), true);
  assert.equal(isPossessionComplete([...allTicked.slice(1), false]), false);
  assert.equal(isPossessionComplete(allTicked.slice(1)), false); // an older, shorter list
  assert.equal(isPossessionComplete(null), false);
});

test("step read from the booking when no lead stage is known", () => {
  assert.deepEqual(stepFromBooking(booking({ status: "draft", tokenAmount: 100_000 })), { kind: "step", index: 0 });
  // The token alone is not "a payment after the token".
  assert.deepEqual(stepFromBooking(booking({ paymentReceipts: [{ amount: 100_000, isToken: true }] })), { kind: "step", index: 0 });
  assert.deepEqual(
    stepFromBooking(booking({ paymentReceipts: [{ amount: 100_000, isToken: true }, { amount: 400_000 }] })),
    { kind: "step", index: 1 }
  );
  assert.deepEqual(stepFromBooking(booking({ registrationNumber: "SRO-1" })), { kind: "step", index: 2 });
  assert.deepEqual(stepFromBooking(booking({ unit: { basePrice: 1, status: "registered" } })), { kind: "step", index: 2 });
  assert.deepEqual(stepFromBooking(booking({ possessionChecklist: allTicked })), { kind: "step", index: 3 });
  assert.deepEqual(stepFromBooking(booking({ unit: { basePrice: 1, status: "sold" } })), { kind: "step", index: 4 });
});

test("the lead's stage wins over the booking; an unknown stage falls back to the booking", () => {
  const registered = booking({ registrationNumber: "SRO-1" });
  assert.deepEqual(effectiveStep(registered, lead("agreement_payment")), { kind: "step", index: 1 });
  assert.deepEqual(effectiveStep(registered, lead("not_interested", "closed_lost")), { kind: "lost" });
  assert.deepEqual(effectiveStep(registered, lead("interested")), { kind: "before" });
  assert.deepEqual(effectiveStep(registered, null), { kind: "step", index: 2 });
  assert.deepEqual(effectiveStep(registered, lead("enrolled")), { kind: "step", index: 2 });
});

// ------------------------------------------------------------------ next action

test("draft booking: Complete booking first, whatever the stage", () => {
  const draft = booking({ status: "draft", tokenAmount: 100_000 });
  assert.deepEqual(nextAction(draft, lead("booked"), manager), { kind: "complete_booking", label: "Complete booking", allowed: true });
  assert.equal(nextAction(draft, lead("agreement_payment"), accounts)?.allowed, false);
});

test("next action per stage", () => {
  const confirmed = booking();
  assert.deepEqual(nextAction(confirmed, lead("booked"), manager), { kind: "record_payment", label: "Record payment", allowed: true });
  assert.deepEqual(nextAction(confirmed, lead("agreement_payment"), manager), { kind: "register", label: "Mark registered", allowed: true });
  assert.deepEqual(nextAction(confirmed, lead("registration"), manager), {
    kind: "possession",
    label: "Possession checklist",
    allowed: true,
  });
  assert.deepEqual(nextAction(confirmed, lead("possession"), manager), {
    kind: "move",
    stageCode: "sold",
    label: "Mark sold",
    allowed: true,
  });
  assert.equal(nextAction(confirmed, lead("sold", "closed_won"), manager), null);
});

test("step work already done: the main button moves the lead on", () => {
  assert.deepEqual(nextAction(booking({ registrationNumber: "SRO-1" }), lead("agreement_payment"), manager), {
    kind: "move",
    stageCode: "registration",
    label: "Move to Registration",
    allowed: true,
  });
  assert.deepEqual(nextAction(booking({ possessionChecklist: allTicked }), lead("registration"), manager), {
    kind: "move",
    stageCode: "possession",
    label: "Move to Possession",
    allowed: true,
  });
});

test("nothing to offer: cancelled, lost, or not yet booked", () => {
  assert.equal(nextAction(booking({ status: "cancelled" }), lead("booked"), manager), null);
  assert.equal(nextAction(booking(), lead("not_interested", "closed_lost"), manager), null);
  assert.equal(nextAction(booking(), lead("interested"), manager), null);
});

test("who may do the next step", () => {
  const confirmed = booking();
  // Sold is managers only — a sales executive sees it as the next step but can't press it.
  assert.equal(nextAction(confirmed, lead("possession"), salesExec)?.allowed, false);
  assert.equal(nextAction(confirmed, lead("registration"), salesExec)?.allowed, true);
  // Recording money needs FINANCE_RECORD_PAYMENT.
  assert.equal(nextAction(confirmed, lead("booked"), salesExec)?.allowed, false);
  assert.equal(nextAction(confirmed, lead("booked"), accounts)?.allowed, true);
  assert.equal(nextAction(confirmed, lead("agreement_payment"), accounts)?.allowed, false);
  // A move needs a lead to move.
  assert.equal(nextAction(booking({ possessionChecklist: allTicked }), null, manager)?.allowed, false);
  assert.equal(nextAction(confirmed, lead("possession"), readOnly)?.allowed, false);
});

test("registering and the possession checklist need the right to set that stage, not just LEAD_MANAGE", () => {
  const confirmed = booking();
  // They move the lead to Registration / Possession, which a telecaller may not set.
  assert.deepEqual(nextAction(confirmed, lead("agreement_payment"), telecaller), {
    kind: "register",
    label: "Mark registered",
    allowed: false,
  });
  assert.deepEqual(nextAction(confirmed, lead("registration"), telecaller), {
    kind: "possession",
    label: "Possession checklist",
    allowed: false,
  });
  // Allowed for each stage on its own: may set Registration but not Possession.
  const upToRegistration: PurchasePerms = { ...telecaller, canSetStage: (code) => code === "registration" };
  assert.equal(nextAction(confirmed, lead("agreement_payment"), upToRegistration)?.allowed, true);
  assert.equal(nextAction(confirmed, lead("registration"), upToRegistration)?.allowed, false);
  // The booking-only strip (no lead) follows the same rule.
  assert.equal(nextAction(booking({ registrationNumber: "SRO-1" }), null, telecaller)?.allowed, false);
  assert.equal(nextAction(booking({ registrationNumber: "SRO-1" }), null, manager)?.allowed, true);
});

test("accounts (no lead stage) follow the booking: token only → Record payment", () => {
  assert.deepEqual(
    nextAction(booking({ paymentReceipts: [{ amount: 100_000, isToken: true }] }), null, accounts),
    { kind: "record_payment", label: "Record payment", allowed: true }
  );
});

test("Move to <next stage>", () => {
  assert.deepEqual(nextStageMove(booking(), lead("booked"), manager), { code: "agreement_payment", label: "Agreement / Payment" });
  assert.deepEqual(nextStageMove(booking(), lead("possession"), manager), { code: "sold", label: "Sold / Closed" });
  assert.equal(nextStageMove(booking(), lead("possession"), salesExec), null);
  assert.equal(nextStageMove(booking(), lead("sold", "closed_won"), manager), null);
  assert.equal(nextStageMove(booking(), lead("interested"), manager), null);
  assert.equal(nextStageMove(booking(), null, manager), null);
  assert.equal(nextStageMove(booking({ status: "cancelled" }), lead("booked"), manager), null);
  assert.equal(nextStageMove(booking(), lead("booked"), accounts), null);
});

test("ready to close: fully paid and every checklist item ticked", () => {
  const paidUp = { total: 1_000_000, paid: 1_000_000 };
  assert.equal(isReadyToClose(booking({ possessionChecklist: allTicked }), paidUp), true);
  assert.equal(isReadyToClose(booking({ possessionChecklist: allTicked }), { total: 1_000_000, paid: 999_999 }), false);
  assert.equal(isReadyToClose(booking(), paidUp), false);
  assert.equal(isReadyToClose(booking({ status: "cancelled", possessionChecklist: allTicked }), paidUp), false);
  assert.equal(isReadyToClose(booking({ possessionChecklist: allTicked }), { total: 0, paid: 0 }), false);
});

// ------------------------------------------------------------------ live refresh

test("realtime: only this customer's leads and units reload the drawer", () => {
  const leads = ["lead-1"];
  const units = ["unit-1"];
  assert.equal(purchaseEventMatters({ event: "lead.stage_changed", payload: { lead_id: "lead-1" } }, leads, units), true);
  assert.equal(purchaseEventMatters({ event: "lead.stage_changed", payload: { lead_id: "lead-2" } }, leads, units), false);
  // unit events carry unit_id at the top level of the envelope.
  const unitEvent = { event: "unit.status_changed", unit_id: "unit-1", status: "booked" };
  assert.equal(purchaseEventMatters(unitEvent, leads, units), true);
  assert.equal(purchaseEventMatters({ ...unitEvent, unit_id: "unit-9" }, leads, units), false);
  // No id to match (e.g. a merged bulk event) → reload to be safe.
  assert.equal(purchaseEventMatters({ event: "unit.status_changed" }, leads, units), true);
  assert.equal(purchaseEventMatters({ event: "customer.updated", payload: {} }, leads, units), false);
});
