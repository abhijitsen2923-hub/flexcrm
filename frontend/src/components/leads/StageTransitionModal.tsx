import { useEffect, useMemo, useState, type FormEvent } from "react";

import { Badge, Button, Modal, SelectField, TextField, TextareaField } from "../../components";
import { usePipelines } from "../../context/PipelineContext";
import { useInventory } from "../../hooks/useInventory";
import { bookingsService } from "../../services/bookings";
import type { Lead, PipelineStage, User } from "../../types";
import type { Booking, PaymentMode } from "../../types/realestate";
import { extractErrorMessage } from "../../utils/errors";


const MIN_COMMENT_LENGTH = 10;
// Real-estate stage that schedules a site visit on the calendar.
const SITE_VISIT_STAGE = "site_visit_confirmed";
// Real-estate "Booked / Token" (position 7): capture the property + token and
// promote the lead to a Customer.
const BOOKED_STAGE = "booked";

const PAYMENT_MODES: { value: PaymentMode; label: string }[] = [
  { value: "upi", label: "UPI" },
  { value: "neft", label: "NEFT / RTGS" },
  { value: "cheque", label: "Cheque" },
  { value: "cash", label: "Cash" },
  { value: "card", label: "Card" },
  { value: "other", label: "Other" },
];

// Local YYYY-MM-DD for a <input type="date"> default (no timezone shift).
function todayDate(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}


interface StageTransitionModalProps {
  open: boolean;
  lead: Lead | null;
  targetStage: PipelineStage | null;
  // Team members assignable as the salesperson on the "Booked / Token" move.
  assignableUsers?: User[];
  onClose: () => void;
  onSubmit: (payload: {
    to_stage_code: string;
    comment: string;
    next_action_date: string | null;
    attachment_path: string | null;
    mentions: string[];
    site_visit?: { project_id: string; scheduled_at: string } | null;
    assigned_to_id?: string | null;
    booking?: {
      unit_id: string;
      token_amount: number;
      token_mode: PaymentMode;
      token_received_on: string;
    } | null;
  }) => Promise<void>;
}


export function StageTransitionModal({
  open,
  lead,
  targetStage,
  assignableUsers = [],
  onClose,
  onSubmit
}: StageTransitionModalProps) {
  const { getStage } = usePipelines();
  const { projects } = useInventory();
  const fromStage = lead ? getStage(lead.industry, lead.stage_code) : undefined;
  const isSiteVisitStage = targetStage?.code === SITE_VISIT_STAGE;
  const isBookedStage = targetStage?.code === BOOKED_STAGE;

  const [comment, setComment] = useState("");
  const [nextAction, setNextAction] = useState(""); // datetime-local (date + time)
  const [siteProjectId, setSiteProjectId] = useState("");
  const [siteDateTime, setSiteDateTime] = useState("");
  // "Booked / Token" capture.
  const [unitId, setUnitId] = useState("");
  const [tokenAmount, setTokenAmount] = useState("");
  const [tokenMode, setTokenMode] = useState<PaymentMode>("neft");
  const [tokenDate, setTokenDate] = useState("");
  const [salespersonId, setSalespersonId] = useState("");
  const [existingBooking, setExistingBooking] = useState<Booking | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset form whenever the modal opens onto a new transition.
  useEffect(() => {
    if (open) {
      setComment("");
      setNextAction("");
      setSiteProjectId("");
      setSiteDateTime("");
      setUnitId("");
      setTokenAmount("");
      setTokenMode("neft");
      setTokenDate(todayDate());
      setSalespersonId(lead?.assigned_to_id ?? "");
      setExistingBooking(null);
      setError(null);
    }
  }, [open, lead?.id, targetStage?.code, lead?.assigned_to_id]);

  // On a "Booked / Token" move, look up the lead's existing (non-cancelled)
  // booking so we record the token on it rather than showing a unit picker.
  useEffect(() => {
    if (!open || !isBookedStage || !lead) return;
    let cancelled = false;
    void bookingsService
      .list({ leadId: lead.id })
      .then((rows) => {
        if (cancelled) return;
        setExistingBooking(rows.find((b) => b.status !== "cancelled") ?? null);
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [open, isBookedStage, lead?.id]);

  // Available units across all projects, labelled "Project · Tower · Unit".
  const availableUnits = useMemo(
    () =>
      projects.flatMap((p) =>
        p.towers.flatMap((t) =>
          t.units
            .filter((u) => u.status === "available")
            .map((u) => ({ id: u.id, label: `${p.name} · ${t.name} · ${u.unitNumber}` }))
        )
      ),
    [projects]
  );

  const trimmedLength = useMemo(() => comment.trim().length, [comment]);
  const siteVisitReady = !isSiteVisitStage || Boolean(siteProjectId && siteDateTime);
  // Salesperson is only required when there ARE users to pick from. Booking roles
  // without USER_VIEW (e.g. crm_team) get an empty list — they book with the owner
  // defaulted server-side (their own id) rather than being blocked.
  const salespersonReady = assignableUsers.length === 0 || Boolean(salespersonId);
  const bookedReady =
    !isBookedStage ||
    Boolean((existingBooking || unitId) && Number(tokenAmount) > 0 && tokenMode && salespersonReady);
  const canSubmit = Boolean(
    lead && targetStage && trimmedLength >= MIN_COMMENT_LENGTH && siteVisitReady && bookedReady && !submitting
  );

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit || !targetStage) return;
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit({
        to_stage_code: targetStage.code,
        comment: comment.trim(),
        // datetime-local has no timezone — send it as an ISO instant.
        next_action_date: nextAction ? new Date(nextAction).toISOString() : null,
        attachment_path: null,
        mentions: [],
        site_visit:
          isSiteVisitStage && siteProjectId && siteDateTime
            ? { project_id: siteProjectId, scheduled_at: new Date(siteDateTime).toISOString() }
            : null,
        assigned_to_id: isBookedStage ? (salespersonId || null) : undefined,
        booking:
          isBookedStage && Number(tokenAmount) > 0
            ? {
                // A date field, not an instant — send YYYY-MM-DD as-is.
                unit_id: existingBooking ? existingBooking.unitId : unitId,
                token_amount: Number(tokenAmount),
                token_mode: tokenMode,
                token_received_on: tokenDate
              }
            : undefined
      });
      onClose();
    } catch (submitError) {
      setError(extractErrorMessage(submitError));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={submitting ? () => undefined : onClose}
      title={lead ? `Move lead #${lead.lead_number}` : "Move lead"}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button type="submit" form="stage-transition-form" disabled={!canSubmit} loading={submitting}>
            Save transition
          </Button>
        </>
      }
    >
      <form id="stage-transition-form" className="form" onSubmit={handleSubmit}>
        <div className="row" style={{ gap: "0.5rem", alignItems: "center", flexWrap: "wrap" }}>
          <Badge tone="neutral">{fromStage?.name ?? lead?.stage_code ?? "—"}</Badge>
          <span className="muted">→</span>
          <Badge tone={targetStage?.category === "closed_won" ? "success" : targetStage?.category === "closed_lost" ? "danger" : "warning"}>
            {targetStage?.name ?? "Select target stage"}
          </Badge>
        </div>

        <TextareaField
          id="transition-comment"
          label={`Comment (min ${MIN_COMMENT_LENGTH} characters)`}
          value={comment}
          onChange={(event) => setComment(event.target.value)}
          rows={4}
          required
          placeholder="e.g. Call back after 3 PM — interested in 2BHK, budget 80L"
          hint={
            trimmedLength < MIN_COMMENT_LENGTH
              ? `${MIN_COMMENT_LENGTH - trimmedLength} more characters required`
              : "This comment becomes part of the lead's permanent stage history."
          }
        />

        <TextField
          id="transition-next-action"
          label="Next action date & time (optional)"
          type="datetime-local"
          value={nextAction}
          onChange={(event) => setNextAction(event.target.value)}
          hint="Used to remind the assigned executive to follow up."
        />

        {isSiteVisitStage && (
          <div className="form-grid">
            <SelectField
              id="sv-project"
              label="Site (project)"
              value={siteProjectId}
              onChange={(event) => setSiteProjectId(event.target.value)}
              options={[
                { value: "", label: "Select a site…" },
                ...projects.map((p) => ({ value: p.id, label: p.name }))
              ]}
              hint="A site visit is booked on the calendar for this lead."
            />
            <TextField
              id="sv-datetime"
              label="Visit date & time"
              type="datetime-local"
              value={siteDateTime}
              onChange={(event) => setSiteDateTime(event.target.value)}
              required
            />
          </div>
        )}

        {isBookedStage && (
          <>
            <div className="muted text-sm">
              Records the token payment and promotes this lead to a Customer.
            </div>
            <div className="form-grid">
              {existingBooking ? (
                <TextField
                  id="bk-unit"
                  label="Property (booked unit)"
                  value={
                    existingBooking.unit
                      ? `${existingBooking.unit.projectName} · ${existingBooking.unit.towerName} · ${existingBooking.unit.unitNumber}`
                      : "This lead's existing booking"
                  }
                  readOnly
                  disabled
                  hint="Recording the token on this lead's existing booking."
                />
              ) : (
                <SelectField
                  id="bk-unit"
                  label="Property (unit)"
                  value={unitId}
                  onChange={(event) => setUnitId(event.target.value)}
                  options={[
                    { value: "", label: availableUnits.length ? "Select a unit…" : "No available units" },
                    ...availableUnits.map((u) => ({ value: u.id, label: u.label }))
                  ]}
                  hint="Booking this unit reserves it and creates a booking."
                />
              )}
              {assignableUsers.length > 0 ? (
                <SelectField
                  id="bk-salesperson"
                  label="Salesperson"
                  value={salespersonId}
                  onChange={(event) => setSalespersonId(event.target.value)}
                  options={[
                    { value: "", label: "Select salesperson…" },
                    ...assignableUsers.map((u) => ({ value: u.id, label: `${u.first_name} ${u.last_name}` }))
                  ]}
                  hint="Sets the lead's owner and the new customer's owner."
                />
              ) : (
                <TextField
                  id="bk-salesperson"
                  label="Salesperson"
                  value={
                    lead?.assigned_to ? `${lead.assigned_to.first_name} ${lead.assigned_to.last_name}` : "You"
                  }
                  readOnly
                  disabled
                  hint="Attributed to the lead's owner (you) for this booking."
                />
              )}
              <TextField
                id="bk-token"
                label="Token amount (₹)"
                type="number"
                min="1"
                value={tokenAmount}
                onChange={(event) => setTokenAmount(event.target.value)}
                required
              />
              <SelectField
                id="bk-mode"
                label="Payment method"
                value={tokenMode}
                onChange={(event) => setTokenMode(event.target.value as PaymentMode)}
                options={PAYMENT_MODES}
              />
              <TextField
                id="bk-date"
                label="Token received on"
                type="date"
                value={tokenDate}
                onChange={(event) => setTokenDate(event.target.value)}
                required
              />
            </div>
          </>
        )}

        {error && <div className="error-banner">{error}</div>}
      </form>
    </Modal>
  );
}
