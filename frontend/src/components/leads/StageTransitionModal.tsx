import { useEffect, useMemo, useState, type FormEvent } from "react";

import {
  Badge,
  Button,
  FieldWrapper,
  Modal,
  SelectField,
  TextField,
  TextareaField
} from "../../components";
import { usePipelines } from "../../context/PipelineContext";
import { useInventory } from "../../hooks/useInventory";
import { usersService } from "../../services/users";
import type { Lead, PipelineStage, UserSummary } from "../../types";
import { extractErrorMessage } from "../../utils/errors";


const MIN_COMMENT_LENGTH = 10;
// Real-estate stage that schedules a site visit on the calendar.
const SITE_VISIT_STAGE = "site_visit_scheduled";


interface StageTransitionModalProps {
  open: boolean;
  lead: Lead | null;
  targetStage: PipelineStage | null;
  onClose: () => void;
  onSubmit: (payload: {
    to_stage_code: string;
    comment: string;
    next_action_date: string | null;
    attachment_path: string | null;
    mentions: string[];
    site_visit?: { project_id: string; scheduled_at: string } | null;
  }) => Promise<void>;
}


export function StageTransitionModal({
  open,
  lead,
  targetStage,
  onClose,
  onSubmit
}: StageTransitionModalProps) {
  const { getStage } = usePipelines();
  const { projects } = useInventory();
  const fromStage = lead ? getStage(lead.industry, lead.stage_code) : undefined;
  const isSiteVisitStage = targetStage?.code === SITE_VISIT_STAGE;

  const [comment, setComment] = useState("");
  const [nextActionDate, setNextActionDate] = useState("");
  const [attachmentPath, setAttachmentPath] = useState("");
  const [siteProjectId, setSiteProjectId] = useState("");
  const [siteDateTime, setSiteDateTime] = useState("");
  const [mentions, setMentions] = useState<UserSummary[]>([]);
  const [mentionQuery, setMentionQuery] = useState("");
  const [mentionCandidates, setMentionCandidates] = useState<UserSummary[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset form whenever the modal opens onto a new transition.
  useEffect(() => {
    if (open) {
      setComment("");
      setNextActionDate("");
      setAttachmentPath("");
      setSiteProjectId("");
      setSiteDateTime("");
      setMentions([]);
      setMentionQuery("");
      setMentionCandidates([]);
      setError(null);
    }
  }, [open, lead?.id, targetStage?.code]);

  useEffect(() => {
    if (!open || mentionQuery.trim().length < 1) {
      setMentionCandidates([]);
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const response = await usersService.list({ page: 1, page_size: 5, search: mentionQuery });
        if (!cancelled) {
          setMentionCandidates(
            response.items.filter((user) => !mentions.some((m) => m.id === user.id))
          );
        }
      } catch {
        if (!cancelled) setMentionCandidates([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, mentionQuery, mentions]);

  const trimmedLength = useMemo(() => comment.trim().length, [comment]);
  const siteVisitReady = !isSiteVisitStage || Boolean(siteProjectId && siteDateTime);
  const canSubmit = Boolean(
    lead && targetStage && trimmedLength >= MIN_COMMENT_LENGTH && siteVisitReady && !submitting
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
        next_action_date: nextActionDate || null,
        attachment_path: attachmentPath.trim() || null,
        mentions: mentions.map((u) => u.id),
        site_visit:
          isSiteVisitStage && siteProjectId && siteDateTime
            ? { project_id: siteProjectId, scheduled_at: new Date(siteDateTime).toISOString() }
            : null
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
          hint={
            trimmedLength < MIN_COMMENT_LENGTH
              ? `${MIN_COMMENT_LENGTH - trimmedLength} more characters required`
              : "Looks good — this comment becomes part of the lead's permanent stage history."
          }
        />

        <div className="form-grid">
          <TextField
            id="transition-next-action"
            label="Next action date (optional)"
            type="date"
            value={nextActionDate}
            onChange={(event) => setNextActionDate(event.target.value)}
          />
          <TextField
            id="transition-attachment"
            label="Attachment path / URL (optional)"
            placeholder="https://… or relative path"
            value={attachmentPath}
            onChange={(event) => setAttachmentPath(event.target.value)}
          />
        </div>

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

        <FieldWrapper label="Mention teammates (optional)" htmlFor="transition-mention-search">
          <input
            id="transition-mention-search"
            className="input"
            placeholder="Type a name to search…"
            value={mentionQuery}
            onChange={(event) => setMentionQuery(event.target.value)}
          />
          {mentionCandidates.length > 0 && (
            <div className="mention-list">
              {mentionCandidates.map((candidate) => (
                <button
                  key={candidate.id}
                  type="button"
                  className="btn btn--ghost btn--sm"
                  onClick={() => {
                    setMentions((prev) => [...prev, candidate]);
                    setMentionQuery("");
                    setMentionCandidates([]);
                  }}
                >
                  @{candidate.first_name} {candidate.last_name}
                </button>
              ))}
            </div>
          )}
          {mentions.length > 0 && (
            <div className="row" style={{ gap: "0.35rem", flexWrap: "wrap", marginTop: "0.5rem" }}>
              {mentions.map((user) => (
                <button
                  key={user.id}
                  type="button"
                  className="badge badge--info"
                  onClick={() => setMentions((prev) => prev.filter((m) => m.id !== user.id))}
                  style={{ cursor: "pointer", border: "none" }}
                >
                  @{user.first_name} {user.last_name} ×
                </button>
              ))}
            </div>
          )}
        </FieldWrapper>

        {error && <div className="error-banner">{error}</div>}
      </form>
    </Modal>
  );
}
