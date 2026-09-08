import { useState } from "react";

import type { Lead, PipelineStage, UserRole } from "../../types";
import { pipelineCategoryTone } from "../../utils/options";
import { canSetStage } from "../../utils/stageAccess";
import { EmptyState } from "../ui/EmptyState";
import { Modal } from "../ui/Modal";
import { SkeletonCircle, SkeletonRect } from "../ui/SkeletonBlock";
import { LeadRow } from "./LeadRow";


/** Local midnight today, for the overdue comparison (dates are YYYY-MM-DD). */
function isOverdue(nextActionDate: string | null | undefined): boolean {
  if (!nextActionDate) return false;
  const due = new Date(nextActionDate);
  if (Number.isNaN(due.getTime())) return false;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  due.setHours(0, 0, 0, 0);
  return due.getTime() < today.getTime();
}


interface LeadRowListProps {
  leads: ReadonlyArray<Lead>;
  loading: boolean;
  /** Resolve a lead's stage: (industry, stage_code) → the stage, if known. */
  getStage: (industry: Lead["industry"], code: string) => PipelineStage | null | undefined;
  /** All stages for an industry (drives the stage picker). */
  byIndustry: Record<string, PipelineStage[]>;
  /** LEAD_MANAGE — gates whether the stage chip is tappable. */
  canManage: boolean;
  /** Current user role — filters which stages the picker offers. */
  userRole: UserRole | undefined;
  /** Tap the row body → open the lead detail drawer. */
  onOpenLead: (lead: Lead) => void;
  /** Pick a target stage → hand off to the existing transition flow (comment modal). */
  onChangeStage: (lead: Lead, target: PipelineStage) => void;
}


/**
 * The phone-only leads list: a scannable stack of compact rows. Tapping a row
 * opens the detail drawer; tapping the stage chip opens a bottom-sheet stage
 * picker that hands off to the existing StageTransitionModal (mandatory
 * comment on every move). Desktop keeps the DataTable/Kanban — this renders
 * only under the phone breakpoint.
 */
export function LeadRowList({
  leads,
  loading,
  getStage,
  byIndustry,
  canManage,
  userRole,
  onOpenLead,
  onChangeStage,
}: LeadRowListProps) {
  // Which lead's stage picker is open (null = closed).
  const [stagePickerLead, setStagePickerLead] = useState<Lead | null>(null);

  if (loading && leads.length === 0) {
    return (
      <div className="lead-rows" aria-busy="true">
        {Array.from({ length: 8 }).map((_, i) => (
          <div className="lead-row lead-row--skeleton" key={i}>
            <SkeletonCircle size="2rem" />
            <div style={{ flex: 1, display: "grid", gap: "0.4rem" }}>
              <SkeletonRect width="55%" height="0.85rem" />
              <SkeletonRect width="35%" height="0.7rem" />
            </div>
            <SkeletonRect width="4.5rem" height="1.5rem" radius="999px" />
          </div>
        ))}
      </div>
    );
  }

  if (leads.length === 0) {
    return (
      <EmptyState title="No leads yet" description="Create your first lead to start tracking deals." />
    );
  }

  const pickerStages = stagePickerLead ? byIndustry[stagePickerLead.industry] ?? [] : [];
  const pickerName = stagePickerLead
    ? stagePickerLead.contact_name || stagePickerLead.customer?.contact_name || stagePickerLead.title
    : "";

  return (
    <>
      <div className="lead-rows" role="list">
        {leads.map((lead) => (
          <LeadRow
            key={lead.id}
            lead={lead}
            stage={getStage(lead.industry, lead.stage_code)}
            overdue={isOverdue(lead.next_action_date)}
            onOpen={() => onOpenLead(lead)}
            onStageTap={canManage ? () => setStagePickerLead(lead) : null}
          />
        ))}
      </div>

      <Modal
        open={Boolean(stagePickerLead)}
        onClose={() => setStagePickerLead(null)}
        title={pickerName ? `Move ${pickerName}` : "Move stage"}
      >
        <div className="stage-picker">
          {pickerStages
            .filter((s) => s.code === stagePickerLead?.stage_code || canSetStage(userRole, s.code))
            .map((s) => {
              const current = s.code === stagePickerLead?.stage_code;
              const tone = pipelineCategoryTone(s.category);
              return (
                <button
                  key={s.id}
                  type="button"
                  className={`stage-picker__item${current ? " stage-picker__item--current" : ""}`}
                  disabled={current}
                  onClick={() => {
                    const lead = stagePickerLead;
                    setStagePickerLead(null);
                    if (lead) onChangeStage(lead, s);
                  }}
                >
                  <span className={`stage-picker__dot stage-picker__dot--${tone}`} aria-hidden="true" />
                  <span className="stage-picker__name">
                    {s.position}. {s.name}
                  </span>
                  {current && <span className="stage-picker__current">Current</span>}
                </button>
              );
            })}
        </div>
      </Modal>
    </>
  );
}
