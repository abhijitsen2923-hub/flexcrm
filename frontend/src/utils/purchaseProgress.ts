// The Customer drawer's Purchases card: the money on each booking (list price, total flat value, paid till now,
// balance), where the purchase stands on the Booked → Agreement / Payment → Registration → Possession →
// Sold / Closed strip, and the one next step to offer. Pure, no React, no runtime imports (unit-tested in
// tests/purchaseProgress.test.ts). Money is formatted by the caller's formatter so these stay testable.
//
// The rules mirror the backend: the total is the booking's saved price (pricing_snapshot.total) else the unit's
// list price (router.py _booking_total); the token is a payment receipt marked is_token (token_receipts.py), and
// the automatic forward moves (lead_sync.py) follow the same events the fallback strip reads below.

type MoneyFormatter = (amount: number) => string;

/** The five steps of a purchase after the token, in order — each is a real-estate lead stage. */
export const PURCHASE_STEPS = [
  { code: "booked", label: "Booked" },
  { code: "agreement_payment", label: "Agreement / Payment" },
  { code: "registration", label: "Registration" },
  { code: "possession", label: "Possession" },
  { code: "sold", label: "Sold / Closed" },
] as const;

export const SOLD_STEP = PURCHASE_STEPS.length - 1;

// Real-estate stages before "Booked / Token" (backend pipeline_seed.py positions 1-7), and the two closed-lost ones.
const BEFORE_BOOKED = new Set([
  "new_enquiry",
  "call",
  "did_not_pickup",
  "follow_up",
  "site_visit_confirmed",
  "site_visit_done",
  "interested",
]);
const LOST = new Set(["not_interested", "disqualified"]);

/**
 * The handover checklist ticked on the Possession page. Saved per booking as true/false in this order; every
 * item ticked means possession is complete. The backend's automatic move to Possession counts these items, so
 * keep its constant in step with this list's length.
 */
export const POSSESSION_CHECKLIST = [
  "Demand note issued",
  "Final payment received",
  "Registration stamp duty paid",
  "Sub-registrar appointment scheduled",
  "Possession letter issued",
  "Key handover done",
  "Society paperwork filed",
] as const;

/** True when every item of the possession checklist is ticked (a shorter, older list is not complete). */
export function isPossessionComplete(checklist: readonly boolean[] | null | undefined): boolean {
  return !!checklist && checklist.length >= POSSESSION_CHECKLIST.length && checklist.every(Boolean);
}

// ------------------------------------------------------------------ money

/** What the money figures need from a booking (a `Booking` fits). */
export interface MoneyInput {
  tokenAmount: number | null;
  pricingSnapshot: { total?: number | null } | null;
  paymentReceipts: readonly { amount: number; isToken?: boolean }[];
  refunds: readonly { refundAmount: number }[];
  unit?: { basePrice: number } | null;
}

export interface PurchaseMoney {
  listPrice: number | null; // the unit's base price (null when the unit didn't load)
  total: number; // the booking's saved price, else the list price
  totalIsFinal: boolean; // false = no price saved yet, so `total` is only the list price
  paid: number; // token + other payments − refunds
  tokenPaid: number;
  payments: number; // receipts other than the token
  refunds: number;
  balance: number; // max(0, total − paid)
}

const num = (value: unknown): number => {
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : 0;
};
// Paise-safe sums: 0.1 + 0.2 must not show as ₹0.30000000000000004.
const round2 = (n: number): number => Math.round(n * 100) / 100;

export function purchaseMoney(booking: MoneyInput): PurchaseMoney {
  const listPrice = booking.unit ? num(booking.unit.basePrice) : null;
  const saved = booking.pricingSnapshot?.total;
  const totalIsFinal = saved !== null && saved !== undefined && Number.isFinite(Number(saved));
  const total = totalIsFinal ? num(saved) : listPrice ?? 0;

  let tokenReceipts = 0;
  let payments = 0;
  let hasTokenReceipt = false;
  for (const receipt of booking.paymentReceipts) {
    if (receipt.isToken) {
      hasTokenReceipt = true;
      tokenReceipts += num(receipt.amount);
    } else {
      payments += num(receipt.amount);
    }
  }
  // A token recorded before tokens became receipts (and that the one-time catch-up left alone) lives only on the
  // booking — count it once. When a token receipt exists, the booking's token field is the same money.
  const tokenPaid = hasTokenReceipt ? tokenReceipts : num(booking.tokenAmount);
  const refunds = booking.refunds.reduce((sum, r) => sum + num(r.refundAmount), 0);
  const paid = round2(tokenPaid + payments - refunds);
  return {
    listPrice,
    total: round2(total),
    totalIsFinal,
    paid,
    tokenPaid: round2(tokenPaid),
    payments: round2(payments),
    refunds: round2(refunds),
    balance: round2(Math.max(0, total - paid)),
  };
}

export interface PurchaseTotals {
  count: number; // bookings that are not cancelled
  total: number;
  paid: number;
  balance: number;
}

/** Sum of the money over a customer's bookings. Cancelled bookings are left out (their money was refunded). */
export function purchaseTotals(bookings: readonly (MoneyInput & { status: string })[]): PurchaseTotals {
  return bookings
    .filter((b) => b.status !== "cancelled")
    .reduce<PurchaseTotals>(
      (sum, b) => {
        const m = purchaseMoney(b);
        return {
          count: sum.count + 1,
          total: round2(sum.total + m.total),
          paid: round2(sum.paid + m.paid),
          balance: round2(sum.balance + m.balance),
        };
      },
      { count: 0, total: 0, paid: 0, balance: 0 }
    );
}

/** "Token ₹1.00L + payments ₹5.00L" (and "− refunds ₹X" when something was refunded) — what makes up Paid. */
export function paidBreakdown(money: PurchaseMoney, fmt: MoneyFormatter): string {
  const parts = `Token ${fmt(money.tokenPaid)} + payments ${fmt(money.payments)}`;
  return money.refunds > 0 ? `${parts} − refunds ${fmt(money.refunds)}` : parts;
}

/** The short line under "Paid till now": what it includes, in a few words (the full breakdown is the tooltip). */
export function paidHint(money: PurchaseMoney, fmt: MoneyFormatter): string {
  if (money.paid <= 0 && money.refunds <= 0) return "Nothing received yet";
  const parts: string[] = [];
  if (money.tokenPaid > 0) parts.push(money.payments > 0 ? `incl. token ${fmt(money.tokenPaid)}` : "Token");
  if (money.refunds > 0) parts.push(`less refunds ${fmt(money.refunds)}`);
  return parts.join(" · ");
}

/** Share of the total received, rounded down so "100% paid" only shows once it truly is (0 when no total). */
export function paidPercent(money: Pick<PurchaseMoney, "total" | "paid">): number {
  if (money.total <= 0) return 0;
  return Math.max(0, Math.min(100, Math.floor((money.paid / money.total) * 100)));
}

/** The exact figure in Indian digit grouping — "₹50,12,345" — for a tooltip next to the short "₹50.12L". */
export function exactInr(amount: number): string {
  return `₹${num(amount).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}

// ------------------------------------------------------------------ progress strip

export type PurchaseStepState =
  | { kind: "step"; index: number } // 0..4 on PURCHASE_STEPS
  | { kind: "before" } // the lead is still before Booked / Token
  | { kind: "lost" } // the lead was closed as lost (Not Interested / Disqualified)
  | { kind: "unknown" }; // no stage to go on (no lead, or not a real-estate stage)

/** Where a lead's stage sits on the strip. `category` (the stage's pipeline category) catches any lost stage. */
export function purchaseStep(stageCode: string | null | undefined, category?: string | null): PurchaseStepState {
  if (!stageCode) return { kind: "unknown" };
  const index = PURCHASE_STEPS.findIndex((s) => s.code === stageCode);
  if (index >= 0) return { kind: "step", index };
  if (category === "closed_lost" || LOST.has(stageCode)) return { kind: "lost" };
  if (BEFORE_BOOKED.has(stageCode)) return { kind: "before" };
  return { kind: "unknown" };
}

/** What the strip needs from a booking when the lead's stage isn't known (a `Booking` fits). */
export interface ProgressInput {
  status: string;
  registrationNumber: string | null;
  possessionChecklist: readonly boolean[] | null;
  paymentReceipts: readonly { isToken?: boolean }[];
  unit?: { status: string } | null;
}

/** Registered at the sub-registrar: a deed number saved, or the unit marked registered / sold. */
export function isRegistered(booking: Pick<ProgressInput, "registrationNumber" | "unit">): boolean {
  const unitStatus = booking.unit?.status;
  return !!booking.registrationNumber || unitStatus === "registered" || unitStatus === "sold";
}

/**
 * The step read from the booking itself — for a booking with no linked lead, or a user who can't see leads
 * (accounts). Follows the same events that move a lead forward automatically: a payment after the token →
 * Agreement / Payment, registration → Registration, the full checklist → Possession; Sold only once the unit is sold.
 */
export function stepFromBooking(booking: ProgressInput): PurchaseStepState {
  if (booking.unit?.status === "sold") return { kind: "step", index: SOLD_STEP };
  if (isPossessionComplete(booking.possessionChecklist)) return { kind: "step", index: 3 };
  if (isRegistered(booking)) return { kind: "step", index: 2 };
  if (booking.status === "confirmed" && booking.paymentReceipts.some((r) => !r.isToken)) return { kind: "step", index: 1 };
  return { kind: "step", index: 0 };
}

/** The linked lead's stage, plus its pipeline category when known. */
export interface LeadStageInfo {
  stage_code: string;
  category?: string | null;
}

/** The strip position: the lead's stage when there is one on the strip, else what the booking shows. */
export function effectiveStep(booking: ProgressInput, lead: LeadStageInfo | null): PurchaseStepState {
  if (lead) {
    const fromLead = purchaseStep(lead.stage_code, lead.category);
    if (fromLead.kind !== "unknown") return fromLead;
  }
  return stepFromBooking(booking);
}

// ------------------------------------------------------------------ next step

export interface PurchasePerms {
  leadManage: boolean; // LEAD_MANAGE — booking wizard, registration, checklist, stage moves
  recordPayment: boolean; // FINANCE_RECORD_PAYMENT
  canSetStage: (stageCode: string) => boolean; // utils/stageAccess canSetStage for the user's role
}

export type PurchaseActionKind = "complete_booking" | "record_payment" | "register" | "possession" | "move";

export interface PurchaseAction {
  kind: PurchaseActionKind;
  label: string;
  allowed: boolean; // false = this user can't do it; show it as "Next step" text only
  stageCode?: string; // "move": the stage the lead moves to
}

function moveTo(index: number, lead: LeadStageInfo | null, perms: PurchasePerms): PurchaseAction {
  const step = PURCHASE_STEPS[index];
  return {
    kind: "move",
    stageCode: step.code,
    label: index === SOLD_STEP ? "Mark sold" : `Move to ${step.label}`,
    // A move goes through the lead's stage-change dialog, so it needs a lead this user can see and move.
    allowed: !!lead && perms.leadManage && perms.canSetStage(step.code),
  };
}

/**
 * The one main button for a booking: finish a draft booking first, then the work of the step the purchase is at
 * (record a payment → mark registered → possession checklist → mark sold). When that step's work is already done
 * (e.g. registered but the lead still says Agreement / Payment), the button is the move to the next stage.
 * null = nothing to do (cancelled, sold, lost, or the lead hasn't reached Booked / Token).
 */
export function nextAction(
  booking: ProgressInput,
  lead: LeadStageInfo | null,
  perms: PurchasePerms
): PurchaseAction | null {
  if (booking.status === "cancelled") return null;
  if (booking.status === "draft") return { kind: "complete_booking", label: "Complete booking", allowed: perms.leadManage };
  const step = effectiveStep(booking, lead);
  if (step.kind !== "step") return null;
  switch (step.index) {
    case 0:
      return { kind: "record_payment", label: "Record payment", allowed: perms.recordPayment };
    // Registering and finishing the checklist move the lead to that stage, so (like the server, which skips the
    // move for someone who can't set the stage) they're offered only to users allowed to set it.
    case 1:
      return isRegistered(booking)
        ? moveTo(2, lead, perms)
        : { kind: "register", label: "Mark registered", allowed: perms.leadManage && perms.canSetStage("registration") };
    case 2:
      return isPossessionComplete(booking.possessionChecklist)
        ? moveTo(3, lead, perms)
        : {
            kind: "possession",
            label: "Possession checklist",
            allowed: perms.leadManage && perms.canSetStage("possession"),
          };
    case 3:
      return moveTo(SOLD_STEP, lead, perms);
    default:
      return null;
  }
}

/** "Move to <next stage>" next to the main button: the lead's next strip stage, when this user may set it. */
export function nextStageMove(
  booking: Pick<ProgressInput, "status">,
  lead: LeadStageInfo | null,
  perms: PurchasePerms
): { code: string; label: string } | null {
  if (!lead || booking.status === "cancelled" || !perms.leadManage) return null;
  const step = purchaseStep(lead.stage_code, lead.category);
  if (step.kind !== "step" || step.index >= SOLD_STEP) return null;
  const next = PURCHASE_STEPS[step.index + 1];
  return perms.canSetStage(next.code) ? { code: next.code, label: next.label } : null;
}

/** Fully paid and handed over — the purchase can be closed as Sold (always a manual step by a manager). */
export function isReadyToClose(
  booking: Pick<ProgressInput, "status" | "possessionChecklist">,
  money: Pick<PurchaseMoney, "total" | "paid">
): boolean {
  return (
    booking.status !== "cancelled" &&
    money.total > 0 &&
    money.paid >= money.total &&
    isPossessionComplete(booking.possessionChecklist)
  );
}

// ------------------------------------------------------------------ live refresh

/**
 * Should a realtime event reload the open Customer drawer? Only a stage change of one of its bookings' leads or a
 * status change of one of its units. An event without an id (e.g. one merged from a bulk write) reloads to be safe.
 * The server sends `{ id, event, payload }` for lead events and puts `unit_id` at the top level for unit events.
 */
export function purchaseEventMatters(
  event: { event: string; payload?: unknown },
  leadIds: readonly string[],
  unitIds: readonly string[]
): boolean {
  const top = event as unknown as Record<string, unknown>;
  const payload = (event.payload && typeof event.payload === "object" ? event.payload : {}) as Record<string, unknown>;
  const pick = (key: string): string | null => {
    const value = top[key] ?? payload[key];
    return typeof value === "string" ? value : null;
  };
  if (event.event === "lead.stage_changed") {
    const leadId = pick("lead_id");
    return leadId === null || leadIds.includes(leadId);
  }
  if (event.event === "unit.status_changed") {
    const unitId = pick("unit_id");
    return unitId === null || unitIds.includes(unitId);
  }
  return false;
}

// ------------------------------------------------------------------ payments tab

/** Demanded / paid / outstanding over instalment rows (the Payments tab's totals line). */
export function instalmentTotals(
  rows: readonly { demandAmount: number; paidAmount: number; outstanding: number }[]
): { demand: number; paid: number; outstanding: number } {
  return rows.reduce(
    (sum, r) => ({
      demand: round2(sum.demand + num(r.demandAmount)),
      paid: round2(sum.paid + num(r.paidAmount)),
      outstanding: round2(sum.outstanding + num(r.outstanding)),
    }),
    { demand: 0, paid: 0, outstanding: 0 }
  );
}
