import { useMemo, useState } from "react";
import { Button, ConfirmDialog, Modal, TextField, useToast } from "../../../components";
import { usePermissions } from "../../../hooks/usePermissions";
import { inventoryService } from "../../../services/inventory";
import type { MilestoneReached, PlanMilestone, Project } from "../../../types/realestate";
import { extractErrorMessage } from "../../../utils/errors";
import { formatDate, formatInr } from "../../../utils/format";
import {
  dueOnText,
  formatPercent,
  isEventMilestone,
  legacyScheduleAsPlan,
  localIsoDate,
  markConfirmText,
  markResultText,
  planTotal,
  reachedFor,
  reachedText,
  scopeText,
  undoConfirmText,
  undoResultText,
} from "../../../utils/paymentPlan";
import { isParkingBlock } from "../../../utils/projectInventory";
import "./ProjectPaymentPlanPanel.css";

interface Props {
  project: Project;
  onChanged: (project: Project) => void;
}

/**
 * The project's payment plan on the project detail screen: its milestones in order, and for stage / possession /
 * registration milestones whether they've been reached. Marking one reached raises its demand on every booking
 * that holds it (whole project or chosen towers); Undo takes back the demands that have no payment or invoice.
 */
export function ProjectPaymentPlanPanel({ project, onChanged }: Props) {
  const toast = useToast();
  const { has } = usePermissions();
  const canMark = has("FINANCE_RECORD_PAYMENT");

  const plan = project.paymentPlan ?? [];
  // A project set up before payment plans keeps its dated demand schedule — list it (read-only).
  const legacy = plan.length === 0 ? legacyScheduleAsPlan(project.demandSchedule) : [];
  const rows = plan.length > 0 ? plan : legacy;
  // Real towers only — the project's "Parking" block holds no bookings with a plan.
  const towers = useMemo(
    () => project.towers.filter((t) => !isParkingBlock(t.name)).map((t) => ({ id: t.id, name: t.name })),
    [project.towers]
  );

  // "Mark reached" dialog.
  const [markFor, setMarkFor] = useState<PlanMilestone | null>(null);
  const [markDate, setMarkDate] = useState(localIsoDate());
  const [markAll, setMarkAll] = useState(true);
  const [markTowerIds, setMarkTowerIds] = useState<string[]>([]);
  const [marking, setMarking] = useState(false);
  // "Undo" confirmation.
  const [undoFor, setUndoFor] = useState<{ milestone: PlanMilestone; entry: MilestoneReached } | null>(null);
  const [undoing, setUndoing] = useState(false);

  // The reply carries the bare project (no towers / units / media), so keep everything the detail screen shows
  // and take only the payment-plan fields from it.
  function applyProject(updated: Project) {
    onChanged({
      ...project,
      paymentPlan: updated.paymentPlan,
      milestonesReached: updated.milestonesReached,
      demandSchedule: updated.demandSchedule,
      updatedAt: updated.updatedAt,
    });
  }

  function openMark(milestone: PlanMilestone) {
    setMarkFor(milestone);
    setMarkDate(localIsoDate());
    setMarkAll(true);
    setMarkTowerIds([]);
  }

  const pickTowers = towers.length > 1 && !markAll;
  const markScope = scopeText(pickTowers ? markTowerIds : null, towers);

  async function submitMark() {
    if (!markFor) return;
    if (!markDate) {
      toast.error("Pick the date it was reached");
      return;
    }
    if (pickTowers && markTowerIds.length === 0) {
      toast.error("Pick at least one tower", "Or choose All towers.");
      return;
    }
    setMarking(true);
    try {
      const result = await inventoryService.markMilestoneReached(project.id, markFor.key, {
        reached_on: markDate,
        tower_ids: pickTowers ? markTowerIds : null,
      });
      applyProject(result.project);
      const { title, description } = markResultText(result, formatInr);
      toast.success(title, description);
      setMarkFor(null);
    } catch (e) {
      toast.error("Could not mark it reached", extractErrorMessage(e));
    } finally {
      setMarking(false);
    }
  }

  async function confirmUndo() {
    if (!undoFor) return;
    setUndoing(true);
    try {
      const result = await inventoryService.undoMilestoneReached(project.id, undoFor.milestone.key, undoFor.entry.towerId);
      applyProject(result.project);
      const { title, description } = undoResultText(result);
      toast.success(title, description);
      setUndoFor(null);
    } catch (e) {
      toast.error("Could not undo", extractErrorMessage(e));
    } finally {
      setUndoing(false);
    }
  }

  if (rows.length === 0) {
    return <p className="project-plan__empty">No payment plan yet — Edit project → Payment plan.</p>;
  }

  return (
    <div className="project-plan">
      {plan.length === 0 && (
        <p className="project-plan__note">
          Set up before payment plans — each booking gets these dated demands. Edit project → Payment plan to change it.
        </p>
      )}

      <ol className="project-plan__list">
        {rows.map((milestone, i) => {
          const isEvent = plan.length > 0 && isEventMilestone(milestone);
          const marks = isEvent ? reachedFor(project.milestonesReached, milestone.key, towers) : [];
          return (
            <li key={milestone.key} className="project-plan__row">
              <span className="project-plan__num" aria-hidden="true">{i + 1}</span>
              <div className="project-plan__main">
                <div className="project-plan__head">
                  <strong className="project-plan__name">{milestone.label}</strong>
                  <span className="project-plan__pct">{formatPercent(milestone.percent)}</span>
                </div>
                <div className="project-plan__due">{dueOnText(milestone, formatDate)}</div>
                {isEvent && (
                  <div className="project-plan__marks">
                    {marks.length === 0 ? (
                      <span className="project-plan__pending">Not reached yet</span>
                    ) : (
                      marks.map((entry) => (
                        <div key={entry.towerId ?? "all"} className="project-plan__mark">
                          <span>{reachedText(entry, towers, formatDate)}</span>
                          {canMark && (
                            <Button size="sm" variant="ghost" onClick={() => setUndoFor({ milestone, entry })}>
                              Undo
                            </Button>
                          )}
                        </div>
                      ))
                    )}
                  </div>
                )}
              </div>
              {isEvent && canMark && (
                <div className="project-plan__action">
                  <Button size="sm" variant="secondary" onClick={() => openMark(milestone)}>
                    Mark reached
                  </Button>
                </div>
              )}
            </li>
          );
        })}
      </ol>

      <div className="project-plan__foot">
        <strong>
          {rows.length} {rows.length === 1 ? "milestone" : "milestones"} · {formatPercent(planTotal(rows))}
        </strong>
        {plan.length > 0 && (
          <span>
            % of the booking's price (box price + GST). Stage, possession and registration milestones are demanded
            when they're marked reached here.
          </span>
        )}
      </div>

      {markFor && (
        <Modal
          open
          title={`Mark “${markFor.label}” reached`}
          onClose={() => !marking && setMarkFor(null)}
          footer={
            <>
              <Button variant="secondary" onClick={() => setMarkFor(null)} disabled={marking}>
                Cancel
              </Button>
              <Button loading={marking} onClick={() => void submitMark()}>
                Mark reached
              </Button>
            </>
          }
        >
          <div className="stack" style={{ gap: "0.75rem" }}>
            <TextField
              id="plan-reached-on"
              label="Reached on"
              type="date"
              value={markDate}
              onChange={(e) => setMarkDate(e.target.value)}
              hint="The demand falls due on this date (or on the booking date, for bookings made later)."
              required
            />
            {towers.length > 1 && (
              <fieldset className="project-plan__scope">
                <legend className="field__label">Towers</legend>
                <label className="project-plan__choice">
                  <input type="radio" name="plan-scope" checked={markAll} onChange={() => setMarkAll(true)} />
                  <span>All towers</span>
                </label>
                <label className="project-plan__choice">
                  <input type="radio" name="plan-scope" checked={!markAll} onChange={() => setMarkAll(false)} />
                  <span>Only some towers</span>
                </label>
                {!markAll && (
                  <div className="project-plan__towers">
                    {towers.map((tower) => (
                      <label key={tower.id} className="project-plan__choice">
                        <input
                          type="checkbox"
                          checked={markTowerIds.includes(tower.id)}
                          onChange={(e) =>
                            setMarkTowerIds((prev) =>
                              e.target.checked ? [...prev, tower.id] : prev.filter((id) => id !== tower.id)
                            )
                          }
                        />
                        <span>{tower.name}</span>
                      </label>
                    ))}
                  </div>
                )}
              </fieldset>
            )}
            <p className="project-plan__confirm">
              {pickTowers && markTowerIds.length === 0
                ? "Pick the towers whose bookings get this demand."
                : markConfirmText(markFor, markScope)}
            </p>
          </div>
        </Modal>
      )}

      <ConfirmDialog
        open={undoFor !== null}
        title={undoFor ? `Undo “${undoFor.milestone.label}” reached?` : ""}
        description={undoFor ? undoConfirmText(undoFor.milestone, undoFor.entry, towers) : ""}
        confirmLabel="Undo"
        destructive
        loading={undoing}
        onCancel={() => !undoing && setUndoFor(null)}
        onConfirm={() => void confirmUndo()}
      />
    </div>
  );
}
