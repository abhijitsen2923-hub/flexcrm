import { ArrowRight, Sparkles, X } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { Badge, Button, LoadingBlock, EmptyState } from "../../components";
import { usePipelines } from "../../context/PipelineContext";
import { useAuth } from "../../hooks/useAuth";
import { leadsService } from "../../services/leads";
import type { Lead, LeadCallLog, PipelineStage, StageTransition } from "../../types";
import { formatCurrency, formatDate, formatDateTime, formatRelative } from "../../utils/format";
import { industryInterestLabel, pipelineCategoryTone, titleCase } from "../../utils/options";


type TabKey = "overview" | "history" | "activity";


interface LeadDrawerProps {
  open: boolean;
  lead: Lead | null;
  onClose: () => void;
  onTransitionRequest: (lead: Lead, target: PipelineStage) => void;
  refreshKey?: number;
}


export function LeadDrawer({ open, lead, onClose, onTransitionRequest, refreshKey }: LeadDrawerProps) {
  const { byIndustry, getStage } = usePipelines();
  const { user } = useAuth();
  const [tab, setTab] = useState<TabKey>("overview");
  const [history, setHistory] = useState<StageTransition[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState(false);
  const [calls, setCalls] = useState<LeadCallLog[]>([]);
  const [callBusy, setCallBusy] = useState(false);

  // Escape key + lock body scroll while drawer is open.
  useEffect(() => {
    if (!open) return;
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", handler);
      document.body.style.overflow = previousOverflow;
    };
  }, [open, onClose]);

  useEffect(() => {
    if (!open || !lead) {
      setHistory([]);
      return;
    }
    let cancelled = false;
    setHistoryLoading(true);
    setHistoryError(false);
    void (async () => {
      try {
        const rows = await leadsService.transitions(lead.id);
        if (!cancelled) setHistory(rows);
      } catch {
        if (!cancelled) setHistoryError(true);
      } finally {
        if (!cancelled) setHistoryLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, lead?.id, refreshKey]);

  useEffect(() => {
    if (!open || !lead) {
      setCalls([]);
      return;
    }
    let cancelled = false;
    void leadsService.calls(lead.id).then((rows) => { if (!cancelled) setCalls(rows); }).catch(() => {});
    return () => { cancelled = true; };
  }, [open, lead?.id, refreshKey]);

  async function handleLogCall(callType: "first_call" | "follow_up") {
    if (!lead) return;
    setCallBusy(true);
    try {
      await leadsService.logCall(lead.id, callType);
      setCalls(await leadsService.calls(lead.id));
    } catch {
      /* non-critical */
    } finally {
      setCallBusy(false);
    }
  }

  if (!open || !lead) return null;

  const stages = byIndustry[lead.industry];
  const currentStage = getStage(lead.industry, lead.stage_code);
  const interestLabel = industryInterestLabel(lead.industry);
  const myFirstCall = calls.find((c) => c.user_id === user?.id && c.call_type === "first_call");
  const followUpCount = calls.filter((c) => c.call_type === "follow_up").length;

  return createPortal(
    // No backdrop-tap close: the drawer holds editable content (comments,
    // transitions) — close only via the ✕ button.
    <div className="modal-backdrop" role="dialog" aria-modal="true">
      <div className="drawer">
        <header className="drawer__header">
          <div>
            <div className="muted text-xs">Lead #{lead.lead_number}</div>
            <h2 style={{ marginTop: "0.25rem" }}>{lead.title}</h2>
            <div className="row" style={{ gap: "0.5rem", marginTop: "0.5rem", alignItems: "center" }}>
              <Badge tone="info">{titleCase(lead.industry)}</Badge>
              <Badge tone={currentStage ? pipelineCategoryTone(currentStage.category) : "neutral"}>
                {currentStage?.name ?? lead.stage_code}
              </Badge>
              <span className="muted text-sm">
                Owner: {lead.assigned_to ? `${lead.assigned_to.first_name} ${lead.assigned_to.last_name}` : "Unassigned"}
              </span>
            </div>
          </div>
          <button type="button" className="btn btn--ghost btn--icon" onClick={onClose} aria-label="Close drawer">
            <X size={18} />
          </button>
        </header>

        <div className="drawer__tabs">
          {(["overview", "history", "activity"] as TabKey[]).map((key) => (
            <button
              key={key}
              type="button"
              className={`tab ${tab === key ? "tab--active" : ""}`}
              onClick={() => setTab(key)}
            >
              {key === "overview" ? "Overview" : key === "history" ? "Stage History" : "Activity"}
            </button>
          ))}
        </div>

        <div className="drawer__body">
          {tab === "overview" && (
            <div className="stack">
              <div className="card" style={{ padding: "0.75rem 1rem" }}>
                <div className="muted text-xs" style={{ textTransform: "uppercase", letterSpacing: ".04em", marginBottom: "0.5rem" }}>
                  Call tracking
                </div>
                <div className="row" style={{ gap: "0.5rem", flexWrap: "wrap", alignItems: "center" }}>
                  {myFirstCall ? (
                    <Badge tone="success">First call done · {formatDateTime(myFirstCall.created_at)}</Badge>
                  ) : (
                    <Button size="sm" loading={callBusy} onClick={() => void handleLogCall("first_call")}>
                      First Call Done
                    </Button>
                  )}
                  <Button size="sm" variant="secondary" loading={callBusy} onClick={() => void handleLogCall("follow_up")}>
                    Follow-up Call Done
                  </Button>
                  {followUpCount > 0 && (
                    <span className="muted text-sm">{followUpCount} follow-up call{followUpCount === 1 ? "" : "s"}</span>
                  )}
                </div>
                {calls.length > 0 && (
                  <div className="stack" style={{ gap: "0.2rem", marginTop: "0.6rem" }}>
                    {calls.slice().reverse().slice(0, 5).map((c) => (
                      <div key={c.id} className="text-xs muted">
                        {c.call_type === "first_call" ? "First call" : "Follow-up"}
                        {" · "}{c.user ? `${c.user.first_name} ${c.user.last_name}` : "—"}
                        {" · "}{formatDateTime(c.created_at)}
                      </div>
                    ))}
                  </div>
                )}
              </div>
              <DetailRow label="Contact" value={lead.contact_name || "—"} />
              <DetailRow label="Email" value={lead.contact_email ?? "—"} />
              <DetailRow label="Phone" value={lead.contact_phone ?? "—"} />
              <DetailRow label="Company" value={lead.company_name ?? "—"} />
              <DetailRow label="Industry" value={titleCase(lead.industry)} />
              <DetailRow label={interestLabel} value={lead.interest ?? "—"} />
              <DetailRow label="Source" value={lead.source ?? "—"} />
              <DetailRow label="Value" value={formatCurrency(lead.value, lead.currency || "INR")} />
              <DetailRow label="Probability" value={`${lead.probability}%`} />
              <DetailRow label="Expected close" value={formatDate(lead.expected_close_date)} />
              <DetailRow
                label="Customer"
                value={
                  lead.customer_id ? (
                    <span>
                      <Badge tone="success">Promoted</Badge>{" "}
                      <a className="link" href="/customers">
                        {lead.customer?.company_name ?? "View in Customer Management"}
                      </a>
                    </span>
                  ) : (
                    <span className="muted">Not yet promoted — reaches the Customers list on Sold.</span>
                  )
                }
              />
              <DetailRow
                label="Last comment"
                value={
                  lead.last_comment_preview ? (
                    <span title={lead.last_comment_preview}>
                      {lead.last_comment_preview} <span className="muted">— {formatRelative(lead.last_comment_at)}</span>
                    </span>
                  ) : "—"
                }
              />

              <div className="card" style={{ padding: "0.75rem 1rem" }}>
                <div className="row row--between" style={{ alignItems: "center", marginBottom: "0.5rem" }}>
                  <strong>Move this lead</strong>
                  <span className="muted text-sm">Each move opens a comment box (min 10 chars).</span>
                </div>
                <div className="row" style={{ flexWrap: "wrap", gap: "0.4rem" }}>
                  {stages.map((stage) => {
                    const isCurrent = stage.code === lead.stage_code;
                    return (
                      <button
                        key={stage.id}
                        type="button"
                        className={`btn btn--sm ${isCurrent ? "btn--secondary" : "btn--ghost"}`}
                        disabled={isCurrent}
                        onClick={() => onTransitionRequest(lead, stage)}
                      >
                        {stage.position}. {stage.name}
                        {isCurrent && <Sparkles size={12} style={{ marginLeft: "0.35rem" }} />}
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
          )}

          {tab === "history" && (
            <div className="stack">
              {historyLoading && history.length === 0 ? (
                <LoadingBlock label="Loading history…" />
              ) : historyError ? (
                <EmptyState title="Couldn't load stage history" description="Please reopen the lead or try again." />
              ) : history.length === 0 ? (
                <EmptyState title="No transitions yet" description="Move this lead to start a history trail." />
              ) : (
                <ol className="timeline">
                  {history.map((entry) => {
                    const from = entry.from_stage_code ? getStage(lead.industry, entry.from_stage_code) : null;
                    const to = getStage(lead.industry, entry.to_stage_code);
                    return (
                      <li key={entry.id} className="timeline__item">
                        <div className="timeline__head">
                          <Badge tone="neutral">{from ? from.name : "System"}</Badge>
                          <ArrowRight size={12} className="muted" />
                          <Badge tone={to ? pipelineCategoryTone(to.category) : "neutral"}>
                            {to?.name ?? entry.to_stage_code}
                          </Badge>
                          <span className="muted text-sm" style={{ marginLeft: "auto" }}>
                            {formatDateTime(entry.performed_at)}
                          </span>
                        </div>
                        <p className="timeline__comment">{entry.comment}</p>
                        <div className="timeline__meta">
                          {entry.performed_by && (
                            <span className="muted text-sm">
                              by {entry.performed_by.first_name} {entry.performed_by.last_name}
                            </span>
                          )}
                          {entry.next_action_date && (
                            <span className="muted text-sm">
                              · next action {formatDateTime(entry.next_action_date)}
                            </span>
                          )}
                          {entry.attachment_path && (
                            <a className="link text-sm" href={entry.attachment_path} target="_blank" rel="noreferrer">
                              · attachment
                            </a>
                          )}
                        </div>
                      </li>
                    );
                  })}
                </ol>
              )}
            </div>
          )}

          {tab === "activity" && (
            <EmptyState
              title="Linked to customer"
              description="Activities are tracked at the customer level. Open the customer to see calls, emails, and notes."
            />
          )}
        </div>

        <footer className="drawer__footer">
          <Button variant="secondary" onClick={onClose}>
            Close
          </Button>
        </footer>
      </div>
    </div>,
    document.body
  );
}


function DetailRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="detail-row">
      <span className="detail-row__label">{label}</span>
      <span className="detail-row__value">{value}</span>
    </div>
  );
}
