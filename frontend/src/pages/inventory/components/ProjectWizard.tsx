// Add / Edit Project — a 7-step wizard in one modal. Nothing is saved until "Save project" on the last step:
// Create is one call (project + towers + parking + plan); Edit saves the project's fields first (new units are
// priced from them), then adds whatever inventory is missing. The cover image uploads after either.
import { useEffect, useMemo, useRef, useState } from "react";
import { Check, ChevronLeft, ChevronRight } from "lucide-react";
import { Button, ConfirmDialog, Modal, Stepper, useToast } from "../../../components";
import { inventoryService } from "../../../services/inventory";
import type { Project } from "../../../types/realestate";
import { extractErrorMessage } from "../../../utils/errors";
import { describeCreated, isParkingBlock, parkingCountsByType } from "../../../utils/projectInventory";
import {
  NO_EXISTING_PARKING,
  STEP_INFO,
  STEP_PARKING,
  STEP_PLAN,
  STEP_PREVIEW,
  STEP_PRICING,
  STEP_REVIEW,
  STEP_TOWERS,
  WIZARD_STEPS,
  buildCreatePayload,
  buildEditPayloads,
  buildPreviewRequest,
  coverFileError,
  firstInvalidStep,
  initialWizardState,
  isStepOk,
  validateStep,
  type ExistingParking,
  type WizardState,
} from "../../../utils/projectWizard";
import { InfoStep, ParkingStep, PlanStep, PricingStep } from "./ProjectWizardSteps";
import { TowersStep } from "./ProjectWizardTowers";
import { PreviewStep, ReviewStep, type PreviewState } from "./ProjectWizardReview";
import "./ProjectWizard.css";

interface ProjectWizardProps {
  project: Project | null; // null = Add project
  onClose: () => void;
  onSaved: () => void | Promise<void>;
  // Edit saved the project's fields but not its inventory — the list should show what did save.
  onPartlySaved?: () => void;
}

/** The project's cover: the newest image labelled "Cover", else its first image. */
function currentCoverUrl(project: Project | null): string | null {
  if (!project) return null;
  const images = project.media.filter((m) => m.type === "image");
  const covers = images.filter((m) => (m.label ?? "").trim().toLowerCase() === "cover");
  return (covers[covers.length - 1] ?? images[0])?.url ?? null;
}

export function ProjectWizard({ project, onClose, onSaved, onPartlySaved }: ProjectWizardProps) {
  const toast = useToast();
  const editing = project !== null;
  const existingParking: ExistingParking = useMemo(
    () => (project ? parkingCountsByType(project.towers) : NO_EXISTING_PARKING),
    [project]
  );
  const ctx = useMemo(() => ({ editing, existingParking }), [editing, existingParking]);

  const [state, setState] = useState<WizardState>(() => initialWizardState(project, existingParking));
  const [dirty, setDirty] = useState(false);
  const [step, setStep] = useState(STEP_INFO);
  const [visited, setVisited] = useState<Set<number>>(() => new Set([STEP_INFO]));
  // Steps whose problems are on show (after the user tried to move on from them).
  const [shown, setShown] = useState<Set<number>>(() => new Set());
  const [coverFile, setCoverFile] = useState<File | null>(null);
  const [coverUrl, setCoverUrl] = useState<string | null>(null);
  const [coverError, setCoverError] = useState<string | null>(null);
  const [preview, setPreview] = useState<PreviewState>({ status: "idle" });
  const [retry, setRetry] = useState(0);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const bodyRef = useRef<HTMLDivElement>(null);
  const previewSeq = useRef(0);

  const checks = useMemo(() => WIZARD_STEPS.map((_, i) => validateStep(i, state, ctx)), [state, ctx]);

  function update(change: (s: WizardState) => WizardState) {
    setState(change);
    setDirty(true);
  }

  // The picked cover's thumbnail (revoked when it changes or the wizard closes).
  useEffect(() => {
    if (!coverFile) {
      setCoverUrl(null);
      return;
    }
    const url = URL.createObjectURL(coverFile);
    setCoverUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [coverFile]);

  function pickCover(file: File | null) {
    if (file) {
      const problem = coverFileError(file);
      if (problem) {
        setCoverError(problem);
        return;
      }
    }
    setCoverError(null);
    setCoverFile(file);
    setDirty(true);
  }

  // Preview (steps 6 and 7): ask the server — the same planning code as Save — whenever the page differs from the
  // last answer.
  const previewRequest = useMemo(
    () => (step === STEP_PREVIEW || step === STEP_REVIEW ? buildPreviewRequest(state, project) : null),
    [step, state, project]
  );
  const previewKey = previewRequest ? JSON.stringify(previewRequest) : null;
  useEffect(() => {
    if (!previewRequest || !previewKey) return;
    if (preview.status !== "idle" && preview.status !== "error" && preview.key === previewKey) return;
    const seq = ++previewSeq.current;
    setPreview({ status: "loading", key: previewKey });
    const call =
      previewRequest.kind === "create"
        ? inventoryService.previewNewProject(previewRequest.payload)
        : inventoryService.previewProjectInventory(project!.id, previewRequest.payload);
    call
      .then((data) => {
        if (seq === previewSeq.current) setPreview({ status: "ok", key: previewKey, data });
      })
      .catch((err) => {
        if (seq === previewSeq.current) setPreview({ status: "error", key: previewKey, message: extractErrorMessage(err) });
      });
    // Re-run only when the step, the page's request or a retry changes — not on every preview state change.
  }, [step, previewKey, retry]);
  const currentPreview: PreviewState = preview.status !== "idle" && preview.key === previewKey ? preview : { status: "idle" };

  function show(target: number) {
    setStep(target);
    setVisited((prev) => new Set(prev).add(target));
    bodyRef.current?.closest(".modal__body")?.scrollTo({ top: 0 });
  }

  /** Back is always free; forward only through steps without problems (else land on the first one, explained). */
  function goTo(target: number) {
    if (target <= step) {
      show(target);
      return;
    }
    const bad = firstInvalidStep(state, ctx, target);
    if (bad !== null) {
      setShown((prev) => new Set(prev).add(bad));
      show(bad);
      return;
    }
    show(target);
  }

  function requestClose() {
    if (saving) return;
    if (dirty) setConfirmDiscard(true);
    else onClose();
  }

  async function save() {
    const bad = firstInvalidStep(state, ctx);
    if (bad !== null) {
      setShown((prev) => new Set(prev).add(bad));
      show(bad);
      return;
    }
    // The preview runs the same checks as Save: if it was refused (e.g. too many units in one save), Save would be
    // too — and on Edit only after the project's details had already been saved. Stop here instead.
    if (currentPreview.status === "error") {
      setSaveError(`Fix this first: ${currentPreview.message}`);
      return;
    }
    if (currentPreview.status === "loading") {
      setSaveError("Wait for the preview to finish, then save.");
      return;
    }
    setSaving(true);
    setSaveError(null);
    let projectId = project?.id ?? null;
    let detailsSaved = false;
    const name = state.info.name.trim();
    try {
      if (!project) {
        // One atomic call: the project, its towers and their units, parking and the plan.
        const created = await inventoryService.createProjectFull(buildCreatePayload(state));
        projectId = created.id;
        const built = {
          towers: created.towers.filter((t) => !isParkingBlock(t.name)).length,
          units: created.totalUnits,
          parking: created.totalParking,
        };
        const anyBuilt = built.towers + built.units + built.parking > 0;
        toast.success("Project created", anyBuilt ? `${name} · ${describeCreated(built)}` : name);
      } else {
        // The project's fields first — the server prices new units and parking spots from them.
        const { update: details, sync } = buildEditPayloads(state, project);
        await inventoryService.updateProject(project.id, details);
        detailsSaved = true;
        const result = await inventoryService.syncProjectInventory(project.id, sync);
        const added = result.created.towers + result.created.units + result.created.parking;
        toast.success("Project updated", added ? `${name} · ${describeCreated(result.created)}` : name);
        if (result.notes.length) toast.info("Existing units kept", result.notes.join(" "));
      }
    } catch (err) {
      const message = extractErrorMessage(err);
      setSaveError(
        detailsSaved
          ? `The project's details were saved, but its towers and parking weren't: ${message}`
          : message
      );
      if (detailsSaved) onPartlySaved?.();
      setSaving(false);
      return;
    }
    if (coverFile && projectId) {
      // Separate from the save on purpose: a failed upload never undoes the project.
      try {
        await inventoryService.uploadProjectMedia(projectId, coverFile, "image", "Cover");
      } catch (err) {
        toast.warning(
          "Cover image not uploaded",
          `${extractErrorMessage(err)} The project is saved — add the image from its Media Repository.`
        );
      }
    }
    setSaving(false);
    await onSaved();
  }

  const stepCheck = (i: number) => (shown.has(i) ? checks[i] : null);
  const isDone = (i: number) => visited.has(i) && i !== step && (i === STEP_PREVIEW || (i < STEP_PREVIEW && isStepOk(checks[i])));
  const stepProps = { state, update, project };

  return (
    <>
      <Modal
        open
        size="xl"
        title={editing ? `Edit project — ${project!.name}` : "Add project"}
        onClose={requestClose}
        footer={
          <div className="pw-footer">
            <span className="pw-footer__step muted text-sm">
              Step {step + 1} of {WIZARD_STEPS.length}
            </span>
            <div className="pw-footer__actions">
              {step > STEP_INFO && (
                <Button variant="secondary" icon={<ChevronLeft size={16} />} onClick={() => goTo(step - 1)} disabled={saving}>
                  Back
                </Button>
              )}
              <Button variant="ghost" className="pw-hide-phone" onClick={requestClose} disabled={saving}>
                Cancel
              </Button>
              {step < STEP_REVIEW ? (
                <Button className="pw-next" onClick={() => goTo(step + 1)}>
                  Next <ChevronRight size={16} />
                </Button>
              ) : (
                <Button className="pw-next" icon={<Check size={16} />} loading={saving} onClick={() => void save()}>
                  Save project
                </Button>
              )}
            </div>
          </div>
        }
      >
        <div className="pw" ref={bodyRef}>
          <div className="pw-stepper-bar">
            <Stepper steps={WIZARD_STEPS} current={step} isDone={isDone} onSelect={goTo} label="Project setup steps" />
          </div>

          {step === STEP_INFO && (
            <InfoStep
              {...stepProps}
              check={stepCheck(STEP_INFO)}
              cover={{
                file: coverFile,
                previewUrl: coverUrl,
                existingUrl: currentCoverUrl(project),
                error: coverError,
                onPick: pickCover,
              }}
            />
          )}
          {step === STEP_TOWERS && <TowersStep {...stepProps} check={stepCheck(STEP_TOWERS)} />}
          {step === STEP_PRICING && <PricingStep {...stepProps} check={stepCheck(STEP_PRICING)} />}
          {step === STEP_PARKING && <ParkingStep {...stepProps} check={stepCheck(STEP_PARKING)} existing={existingParking} />}
          {step === STEP_PLAN && <PlanStep {...stepProps} check={stepCheck(STEP_PLAN)} />}
          {step === STEP_PREVIEW && <PreviewStep preview={currentPreview} onRetry={() => setRetry((n) => n + 1)} editing={editing} towers={state.towers} />}
          {step === STEP_REVIEW && (
            <ReviewStep
              state={state}
              project={project}
              existingParking={existingParking}
              preview={currentPreview}
              coverFileName={coverFile?.name ?? null}
              saveError={saveError}
              goTo={goTo}
            />
          )}
        </div>
      </Modal>

      <ConfirmDialog
        open={confirmDiscard}
        title="Discard your changes?"
        description="Nothing on these steps has been saved yet."
        confirmLabel="Discard"
        cancelLabel="Keep editing"
        destructive
        onCancel={() => setConfirmDiscard(false)}
        onConfirm={() => {
          setConfirmDiscard(false);
          onClose();
        }}
      />
    </>
  );
}
