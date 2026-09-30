import { useEffect, useMemo, useState, type FormEvent } from "react";

import { Badge, Button, Modal, TextareaField, TextField } from "../../components";
import type { LeadIntent } from "../../types";
import { extractErrorMessage } from "../../utils/errors";
import { IntentSlider } from "./IntentSlider";

const MIN_COMMENT_LENGTH = 10;

interface BulkStageModalProps {
  open: boolean;
  count: number;            // how many leads will move
  stageName: string;        // human label of the target stage
  // Whether the move asks for intent (not for a closed target stage, where intent is fixed).
  intentAsked: boolean;
  onClose: () => void;
  // One shared comment (+ optional next action, + the intent when asked) applied to every selected lead.
  onSubmit: (comment: string, nextActionDate: string | null, intent: LeadIntent | null) => Promise<void>;
}

/**
 * Compact confirm dialog for a BULK stage move. Stage transitions require a
 * mandatory comment (≥10 chars, same as the single-lead modal), so the batch
 * carries one shared comment. Per-lead capture (booking/site-visit) is NOT
 * offered here — those stages are excluded from the bulk picker.
 */
export function BulkStageModal({ open, count, stageName, intentAsked, onClose, onSubmit }: BulkStageModalProps) {
  // Never pre-selected — one intent for every selected lead, picked each time.
  const [intent, setIntent] = useState<LeadIntent | null>(null);
  const [showIntentError, setShowIntentError] = useState(false);
  const [comment, setComment] = useState("");
  const [nextAction, setNextAction] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setIntent(null);
      setShowIntentError(false);
      setComment("");
      setNextAction("");
      setError(null);
    }
  }, [open]);

  const trimmedLength = useMemo(() => comment.trim().length, [comment]);
  const canSubmit = trimmedLength >= MIN_COMMENT_LENGTH && !submitting;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) return;
    if (intentAsked && !intent) {
      setShowIntentError(true);
      document.getElementById("bulk-stage-intent")?.scrollIntoView({ behavior: "smooth", block: "center" });
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit(
        comment.trim(),
        nextAction ? new Date(nextAction).toISOString() : null,
        intentAsked ? intent : null
      );
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
      title={`Move ${count} lead${count === 1 ? "" : "s"}`}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button type="submit" form="bulk-stage-form" disabled={!canSubmit} loading={submitting}>
            Move {count} lead{count === 1 ? "" : "s"}
          </Button>
        </>
      }
    >
      <form id="bulk-stage-form" className="form" onSubmit={handleSubmit}>
        <div className="transition-move-bar">
          <div className="transition-move-bar__stages">
            <span className="muted">Moving to</span>
            <Badge tone="warning">{stageName}</Badge>
          </div>
          {intentAsked && (
            <IntentSlider
              id="bulk-stage-intent"
              value={intent}
              onChange={(next) => {
                setIntent(next);
                setShowIntentError(false);
              }}
              required
              hint="Set on every selected lead"
              error={showIntentError && !intent ? "Pick an intent — Low, Medium or High" : undefined}
            />
          )}
        </div>
        <p className="muted text-sm">
          Bulk moves only go forward — leads already past this stage, or closed (Sold or lost), are skipped
          (change those one at a time).
        </p>

        <TextareaField
          id="bulk-stage-comment"
          label={`Comment (min ${MIN_COMMENT_LENGTH} characters)`}
          value={comment}
          onChange={(event) => setComment(event.target.value)}
          rows={4}
          required
          placeholder="e.g. Qualified batch from the July property expo — following up this week"
          hint={
            trimmedLength < MIN_COMMENT_LENGTH
              ? `${MIN_COMMENT_LENGTH - trimmedLength} more characters required`
              : "Added to every selected lead's stage history."
          }
        />

        <TextField
          id="bulk-stage-next-action"
          label="Next action date & time (optional)"
          type="datetime-local"
          value={nextAction}
          onChange={(event) => setNextAction(event.target.value)}
          hint="Applied to all selected leads to schedule a follow-up."
        />

        {error && <div className="error-banner">{error}</div>}
      </form>
    </Modal>
  );
}
