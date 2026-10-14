import type { ReactNode } from "react";
import { Badge, Button, KpiCard, Stepper } from "../../components";
import type { Booking } from "../../types/realestate";
import { formatDate, formatInr } from "../../utils/format";
import {
  PURCHASE_STEPS,
  SOLD_STEP,
  effectiveStep,
  exactInr,
  isReadyToClose,
  nextAction,
  nextStageMove,
  paidBreakdown,
  paidHint,
  paidPercent,
  purchaseMoney,
  type LeadStageInfo,
  type PurchaseAction,
  type PurchasePerms,
} from "../../utils/purchaseProgress";
import { flatTypeLabel } from "../../utils/unitLabel";
import "./CustomerPurchaseCard.css";

const UNIT_TYPE_LABEL: Record<string, string> = {
  residential: "Residential",
  parking: "Parking",
  shop: "Shop",
  godown: "Godown",
};

const UNIT_STATUS_TONE: Record<string, "success" | "warning" | "primary" | "info" | "neutral"> = {
  available: "success",
  hold: "warning",
  booked: "primary",
  registered: "info",
  sold: "neutral",
};

// Plain words for the unit's status badge ("hold" alone reads like a typo to a buyer-facing team).
const UNIT_STATUS_LABEL: Record<string, string> = {
  available: "Available",
  hold: "On hold",
  booked: "Booked",
  registered: "Registered",
  sold: "Sold",
};

const BOOKING_STATUS_LABEL: Record<string, string> = {
  draft: "Not completed yet",
  confirmed: "Confirmed",
  cancelled: "Cancelled",
};

const strip = PURCHASE_STEPS.map((s) => s.label);

interface Props {
  booking: Booking;
  // The linked lead's stage (null: no linked lead, or one this user can't see) and that stage's name.
  lead: LeadStageInfo | null;
  leadNumber: number | null;
  stageName: string | null;
  perms: PurchasePerms;
  // LEAD_VIEW: the allotment letter / booking form endpoints need it.
  canViewDocs: boolean;
  // FINANCE_RECORD_PAYMENT: the payment plan window (record a payment, raise a demand).
  canManagePayments: boolean;
  busy: boolean; // the main action is loading (e.g. the booking wizard fetching the project's prices)
  onAction: (action: PurchaseAction) => void;
  onMove: (stageCode: string) => void;
  onPayments: () => void;
  onDocument: (docType: "booking_form" | "allotment_letter") => void;
}

/**
 * One purchase in the Customer drawer: what the flat costs and what's been paid, where the purchase stands
 * (Booked → Agreement / Payment → Registration → Possession → Sold / Closed), and the one next step. Read-only for
 * users who can't act — they still see the money and the progress.
 */
export function CustomerPurchaseCard({
  booking: b,
  lead,
  leadNumber,
  stageName,
  perms,
  canViewDocs,
  canManagePayments,
  busy,
  onAction,
  onMove,
  onPayments,
  onDocument,
}: Props) {
  const cancelled = b.status === "cancelled";
  const money = purchaseMoney(b);
  const step = effectiveStep(b, lead);
  const action = nextAction(b, lead, perms);
  const move = nextStageMove(b, lead, perms);
  // The main button may already be that move (e.g. "Mark sold") — don't offer it twice.
  const showMove = move && !(action?.kind === "move" && action.stageCode === move.code);
  const ready = step.kind === "step" && step.index === SOLD_STEP - 1 && isReadyToClose(b, money);
  const checklist = b.possessionChecklist ?? [];
  const ticked = checklist.filter(Boolean).length;
  const showPayments = canManagePayments && !cancelled && action?.kind !== "record_payment";

  return (
    <div className={`card purchase-card${cancelled ? " purchase-card--cancelled" : ""}`}>
      <div className="purchase-card__head">
        <div className="purchase-card__title">
          <strong>{b.unit ? `${b.unit.projectName} · ${b.unit.towerName}` : "Unit"}</strong>
          <div className="muted text-sm" style={{ marginTop: 2 }}>
            {b.unit
              ? `${flatTypeLabel(b.unit) || (UNIT_TYPE_LABEL[b.unit.unitType] ?? b.unit.unitType)} · Unit ${b.unit.unitNumber} · Floor ${b.unit.floor} · ${b.unit.area} ${b.unit.areaUnit}`
              : `Unit ${b.unitId.slice(0, 8)}`}
          </div>
        </div>
        <div className="purchase-card__badges">
          {cancelled && <Badge tone="danger">Cancelled</Badge>}
          {b.unit && (
            <Badge tone={UNIT_STATUS_TONE[b.unit.status] ?? "neutral"}>
              {UNIT_STATUS_LABEL[b.unit.status] ?? b.unit.status}
            </Badge>
          )}
        </div>
      </div>

      {cancelled ? (
        <p className="purchase-note">
          This booking was cancelled{b.cancellationReason ? ` (${b.cancellationReason})` : ""}. It is not counted in the
          customer's totals.
          {money.refunds > 0 ? ` Refunded ${formatInr(money.refunds)}.` : ""}
        </p>
      ) : (
        <div className="purchase-money">
          <MoneyTile
            label="List price"
            value={money.listPrice}
            hint="Unit's base price"
          />
          <MoneyTile
            label="Total flat value"
            value={money.total}
            hint={money.totalIsFinal ? "Booking price, all-in" : "List price — pricing not saved yet"}
          />
          <MoneyTile
            label="Paid till now"
            value={money.paid}
            hint={paidHint(money, formatInr)}
            title={`${paidBreakdown(money, exactInr)} = ${exactInr(money.paid)}`}
          />
          <MoneyTile
            label="Balance"
            value={money.balance}
            hint={money.total > 0 ? (money.balance === 0 ? "Fully paid" : `${paidPercent(money)}% paid`) : undefined}
          />
        </div>
      )}

      <div className="purchase-facts">
        <Fact label="Booking" value={BOOKING_STATUS_LABEL[b.status] ?? b.status} />
        <Fact label="Registration" value={b.scheduledDate ? formatDate(b.scheduledDate) : "—"} />
        {b.registrationNumber && <Fact label="Registration no." value={b.registrationNumber} />}
        {ticked > 0 && <Fact label="Possession checklist" value={`${ticked} of ${checklist.length} done`} />}
        {leadNumber !== null && stageName && <Fact label={`Lead #${leadNumber} stage`} value={stageName} />}
      </div>

      {!cancelled && (
        <div className="purchase-strip">
          {step.kind === "step" ? (
            <>
              <Stepper
                steps={strip}
                current={step.index}
                label="Purchase progress"
                // Sold / Closed is the last step: once there, every step before it is done.
                isDone={(i) => i < step.index}
              />
              {!lead && <p className="purchase-note purchase-note--small">Progress read from the booking.</p>}
            </>
          ) : step.kind === "lost" ? (
            <p className="purchase-note">
              <Badge tone="danger">Lead closed</Badge> {stageName ? `The lead is marked "${stageName}".` : ""}
            </p>
          ) : (
            <p className="purchase-note">
              The lead is at {stageName ? `"${stageName}"` : "an earlier stage"}. Move it to Booked / Token on the Leads
              page to follow this purchase here.
            </p>
          )}
        </div>
      )}

      {ready && (
        <div className="purchase-ready">
          <Badge tone="success">Ready to close</Badge>
          <span className="muted">Fully paid and handed over — a manager can mark it Sold.</span>
        </div>
      )}

      <div className="purchase-actions">
        {action && !action.allowed && (
          // Someone else does this step (e.g. a manager marks it sold) — say what's next instead of a dead button.
          <span className="muted text-sm purchase-actions__next">
            Next step: <strong>{action.label}</strong>
          </span>
        )}
        {action && action.allowed && (
          <Button size="sm" loading={busy} onClick={() => onAction(action)}>
            {action.label}
          </Button>
        )}
        {showMove && (
          <Button size="sm" variant="secondary" onClick={() => onMove(move.code)}>
            Move to {move.label}
          </Button>
        )}
        {showPayments && (
          <Button size="sm" variant="ghost" onClick={onPayments}>
            Payments
          </Button>
        )}
        {canViewDocs && (
          <>
            <Button size="sm" variant="ghost" onClick={() => onDocument("allotment_letter")}>
              Allotment Letter
            </Button>
            <Button size="sm" variant="ghost" onClick={() => onDocument("booking_form")}>
              Booking Form
            </Button>
          </>
        )}
      </div>
    </div>
  );
}

function MoneyTile({ label, value, hint, title }: { label: string; value: number | null; hint?: string; title?: string }) {
  return (
    // The tile shows the short lakh / crore figure; hovering gives the exact rupees.
    <div title={title ?? (value === null ? undefined : exactInr(value))}>
      <KpiCard label={label} value={value === null ? "—" : formatInr(value)} hint={hint || undefined} />
    </div>
  );
}

function Fact({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div>
      <div className="muted text-xs">{label}</div>
      <div style={{ fontWeight: 600 }}>{value}</div>
    </div>
  );
}
