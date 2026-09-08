import { ChevronDown, Phone } from "lucide-react";

import type { Lead, PipelineStage } from "../../types";
import { telHref } from "../../utils/contactLinks";
import { pipelineCategoryTone } from "../../utils/options";


function initialsFor(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
}


interface LeadRowProps {
  lead: Lead;
  /** Resolved stage for this lead's (industry, stage_code), if known. */
  stage: PipelineStage | null | undefined;
  /** Whether this lead's next action is past-due (drives the overdue dot). */
  overdue: boolean;
  /** Tap the row body → open the lead detail drawer. */
  onOpen: () => void;
  /** Tap the stage chip → open the stage picker. Null when the user can't move stages. */
  onStageTap: (() => void) | null;
}


/**
 * A compact, single lead row for the phone list (per the approved mobile
 * preview). One primary line (name) + a secondary line (full phone · #id), a
 * colour-coded stage chip on the right, and a one-tap call button. Details
 * live on the detail drawer — this row is for scanning and quick actions.
 */
export function LeadRow({ lead, stage, overdue, onOpen, onStageTap }: LeadRowProps) {
  const name = lead.contact_name || lead.customer?.contact_name || lead.title || "Unnamed lead";
  const phone = lead.contact_phone || lead.contact_phone_alt || "";
  const tone = stage ? pipelineCategoryTone(stage.category) : "neutral";
  const stageLabel = stage ? stage.name : lead.stage_code;
  const tel = telHref(phone);

  return (
    <div className="lead-row">
      <button type="button" className="lead-row__main" onClick={onOpen} aria-label={`Open lead ${name}`}>
        <span className={`lead-row__avatar${overdue ? " lead-row__avatar--overdue" : ""}`} aria-hidden="true">
          {initialsFor(name)}
        </span>
        <span className="lead-row__text">
          <span className="lead-row__name">
            {lead.is_duplicate && (
              <span className="lead-row__dup" title="Possible duplicate — shares an email or phone">!</span>
            )}
            {name}
          </span>
          <span className="lead-row__meta">
            {phone ? (
              <span className="lead-row__phone">{phone}</span>
            ) : (
              <span className="muted">No phone</span>
            )}
            <span className="lead-row__sep">·</span>
            <span className="muted">#{lead.lead_number}</span>
            {overdue && <span className="lead-row__overdue">Overdue</span>}
          </span>
        </span>
      </button>
      {onStageTap ? (
        <button
          type="button"
          className={`lead-row__stage lead-row__stage--${tone}`}
          onClick={onStageTap}
          aria-label={`Change stage (currently ${stageLabel})`}
        >
          <span className="lead-row__stage-label">{stageLabel}</span>
          <ChevronDown size={13} aria-hidden="true" />
        </button>
      ) : (
        <span className={`lead-row__stage lead-row__stage--${tone} lead-row__stage--static`}>
          <span className="lead-row__stage-label">{stageLabel}</span>
        </span>
      )}
      {tel && (
        <a
          className="lead-row__call"
          href={tel}
          onClick={(event) => event.stopPropagation()}
          aria-label={`Call ${name}`}
          title={`Call ${phone}`}
        >
          <Phone size={16} aria-hidden="true" />
        </a>
      )}
    </div>
  );
}
