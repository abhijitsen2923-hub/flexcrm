import { AlertTriangle, CheckCircle2, ChevronUp, Minus, X } from "lucide-react";
import { useEffect, useState } from "react";

import { leadImportJob, useLeadImportJob } from "../../hooks/useLeadImport";
import { importSummaryLine, type ImportJobState } from "../../utils/csvImport";
import { Button } from "../ui/Button";
import { Modal } from "../ui/Modal";
import { useToast } from "../ui/Toast";

// Summary tables show this many rows each (a huge list froze the dialog); the counts stay exact.
const RESULT_ROWS_SHOWN = 200;

type Outcome = "running" | "success" | "partial" | "nothing" | "failed";

function outcomeOf(job: ImportJobState): Outcome {
  if (job.status === "running") return "running";
  if (job.status === "failed") return "failed";
  if (job.stopped) return "partial";
  if (job.result && job.result.created === 0 && job.result.errors.length > 0) return "nothing";
  if (job.result && job.result.errors.length > 0) return "partial";
  return "success";
}

function titleOf(job: ImportJobState, outcome: Outcome): string {
  switch (outcome) {
    case "running":
      return "Importing leads…";
    case "failed":
      return "Import failed";
    case "nothing":
      return "Nothing was imported";
    case "partial":
      return job.stopped ? "Import stopped part-way" : "Import finished with errors";
    default:
      return "Import finished";
  }
}

/**
 * Background lead import status, on every page: a small card with live progress while a CSV import runs
 * (can be collapsed to a pill), then the outcome with "View details" (duplicates, row errors, a part-way
 * stop). The upload dialog closes as soon as a file is picked, so the user can keep working meanwhile.
 */
export function LeadImportStatus() {
  const job = useLeadImportJob();
  const toast = useToast();
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [announcement, setAnnouncement] = useState("");
  const outcome = outcomeOf(job);
  const visible = job.status !== "idle";

  // A new import always starts expanded.
  useEffect(() => {
    setCollapsed(false);
  }, [job.id]);

  // Screen readers: announce the start and the outcome only (not every progress tick).
  useEffect(() => {
    if (job.status === "running") setAnnouncement(`Import of ${job.fileName} started.`);
  }, [job.id, job.status, job.fileName]);

  // Once per finished import (the store remembers, so a remount doesn't repeat it): a toast + announcement.
  useEffect(() => {
    if (job.status !== "done" && job.status !== "failed") return;
    if (!leadImportJob.shouldAnnounce(job.id)) return;
    const summary = job.status === "failed" ? job.error ?? "" : job.result ? importSummaryLine(job.result) : "";
    const title = titleOf(job, outcome);
    setAnnouncement(`${title}. ${summary}`);
    if (outcome === "success") toast.success(title, summary);
    else if (outcome === "partial" && !job.stopped) toast.info(title, summary);
    else toast.error(title, job.stopped ? "See the import card for details." : summary);
  }, [job, outcome, toast]);

  // Leave room under the page content so the card never covers the last controls (e.g. pagination).
  useEffect(() => {
    const cls = !visible ? null : collapsed ? "has-import-pill" : "has-import-card";
    if (cls) document.body.classList.add(cls);
    return () => {
      if (cls) document.body.classList.remove(cls);
    };
  }, [visible, collapsed]);

  const progress = job.progress;
  const percent = progress && progress.total > 0 ? Math.round((progress.done / progress.total) * 100) : 0;
  const progressText =
    progress && progress.total > 0
      ? `${progress.done.toLocaleString()} of ${progress.total.toLocaleString()} rows`
      : "Reading the file…";
  const hasDetails = Boolean(
    job.result && (job.result.errors.length > 0 || job.result.duplicates.length > 0 || job.stopped)
  );
  const tone = outcome === "running" ? "running" : outcome === "success" ? "success" : "warning";
  const closeDetails = () => setDetailsOpen(false);

  return (
    <>
      {/* Always mounted, so screen readers reliably announce what's written into it. */}
      <div className="sr-only" role="status" aria-live="polite">{announcement}</div>

      {visible && collapsed && job.status === "running" && (
        <button
          type="button"
          className="import-status-pill"
          onClick={() => setCollapsed(false)}
          aria-label={`Importing leads, ${progressText}. Show import progress`}
        >
          <span className="spinner import-status__icon" aria-hidden="true" />
          <span>Importing… {percent}%</span>
          <ChevronUp size={14} aria-hidden="true" />
        </button>
      )}

      {visible && !(collapsed && job.status === "running") && (
        <section className={`import-status import-status--${tone}`} aria-label="Lead import">
          <div className="import-status__head">
            {outcome === "running" ? (
              <span className="spinner import-status__icon" aria-hidden="true" />
            ) : tone === "success" ? (
              <CheckCircle2 size={18} className="import-status__icon" aria-hidden="true" />
            ) : (
              <AlertTriangle size={18} className="import-status__icon" aria-hidden="true" />
            )}
            <div className="import-status__title">{titleOf(job, outcome)}</div>
            {outcome === "running" ? (
              <button
                type="button"
                className="import-status__close"
                aria-label="Hide import progress (the import keeps running)"
                title="Hide — the import keeps running"
                onClick={() => setCollapsed(true)}
              >
                <Minus size={16} aria-hidden="true" />
              </button>
            ) : (
              <button
                type="button"
                className="import-status__close"
                aria-label="Dismiss import status"
                onClick={() => leadImportJob.dismiss()}
              >
                <X size={16} aria-hidden="true" />
              </button>
            )}
          </div>
          <div className="import-status__file" title={job.fileName}>{job.fileName}</div>

          {outcome === "running" ? (
            <>
              <div
                className="import-status__bar"
                role="progressbar"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={percent}
                aria-label="Import progress"
              >
                <div className="import-status__bar-fill" style={{ width: `${percent}%` }} />
              </div>
              <div className="import-status__text">
                {progressText}
                {progress?.waiting ? " · server busy, continuing shortly" : ""}
              </div>
              <div className="import-status__hint">You can keep working — just don't close this tab.</div>
            </>
          ) : (
            <>
              <div className="import-status__text">
                {job.status === "failed" ? job.error : job.result ? importSummaryLine(job.result) : null}
                {job.stopped &&
                  ` — ${job.stopped.rowsBefore.toLocaleString()} of ${job.stopped.totalRows.toLocaleString()} rows processed.`}
              </div>
              {hasDetails && (
                <Button size="sm" variant="secondary" onClick={() => setDetailsOpen(true)}>
                  View details
                </Button>
              )}
            </>
          )}
        </section>
      )}

      <Modal
        open={detailsOpen && Boolean(job.result) && job.status !== "running"}
        onClose={closeDetails}
        title="Import summary"
        size="lg"
        footer={<Button onClick={closeDetails}>Close</Button>}
      >
        {job.result && (
          <div className="stack">
            {job.stopped && (
              <div className="notice-banner" role="alert" style={{ marginBottom: 0 }}>
                <strong>
                  The import stopped after {job.stopped.rowsBefore.toLocaleString()} of{" "}
                  {job.stopped.totalRows.toLocaleString()} rows.
                </strong>{" "}
                {job.stopped.reason} Upload the same file again with “Skip duplicate leads” on to add the rest —
                rows already imported are skipped.
                {!job.skipDuplicates &&
                  " Note: this import had “Skip duplicate leads” off; with it on, remaining rows that match existing leads are skipped instead of imported and flagged."}
              </div>
            )}
            <div>{importSummaryLine(job.result)}</div>

            {job.result.duplicates.length > 0 && (
              <>
                <div className="muted text-sm">
                  {job.result.duplicates.some((d) => d.skipped)
                    ? "These rows matched an existing lead and were skipped:"
                    : "These rows matched an existing lead and were imported (flagged with a red “!”):"}
                </div>
                <table className="table">
                  <thead>
                    <tr>
                      <th style={{ width: 56, textAlign: "left" }}>Row</th>
                      <th style={{ textAlign: "left" }}>Contact</th>
                      <th style={{ textAlign: "left" }}>Matches</th>
                      <th style={{ width: 90, textAlign: "left" }}>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {job.result.duplicates.slice(0, RESULT_ROWS_SHOWN).map((d, index) => (
                      <tr key={`dup-${d.row}-${index}`}>
                        <td>{d.row}</td>
                        <td>
                          {d.contact_name ?? "—"}
                          {(d.contact_email || d.contact_phone) && (
                            <div className="muted text-xs">
                              {[d.contact_email, d.contact_phone].filter(Boolean).join(" · ")}
                            </div>
                          )}
                        </td>
                        <td>{d.matched}</td>
                        <td>{d.skipped ? "Skipped" : "Imported"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {job.result.duplicates.length > RESULT_ROWS_SHOWN && (
                  <div className="muted text-xs">…and {job.result.duplicates.length - RESULT_ROWS_SHOWN} more.</div>
                )}
              </>
            )}

            {job.result.errors.length > 0 && (
              <>
                <div className="muted text-sm">
                  Fix these rows in your sheet and upload it again with “Skip duplicate leads” on — leads already
                  created are skipped, not duplicated.
                </div>
                <table className="table">
                  <thead>
                    <tr>
                      <th style={{ width: 56, textAlign: "left" }}>Row</th>
                      <th style={{ textAlign: "left" }}>Error</th>
                    </tr>
                  </thead>
                  <tbody>
                    {job.result.errors.slice(0, RESULT_ROWS_SHOWN).map((err, index) => (
                      <tr key={`err-${err.row}-${index}`}>
                        <td>{err.row}</td>
                        <td>{err.error}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {job.result.errors.length > RESULT_ROWS_SHOWN && (
                  <div className="muted text-xs">…and {job.result.errors.length - RESULT_ROWS_SHOWN} more.</div>
                )}
              </>
            )}
          </div>
        )}
      </Modal>
    </>
  );
}
