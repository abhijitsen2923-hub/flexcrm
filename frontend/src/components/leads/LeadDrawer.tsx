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
import { canSetStage } from "../../utils/stageAccess";
import { LeadBookingsTab } from "./LeadBookingsTab";


// Mirror the stage-transition comment floor so a DNP is captured "like Call".
const MIN_DNP_COMMENT = 10;

type TabKey = "overview" | "bookings" | "history" | "activity";

const TAB_LABELS: Record<TabKey, string> = {
  overview: "Overview",
  bookings: "Booking & Payments",
  history: "Stage History",
  activity: "Activity",
};


interface LeadDrawerProps {
  open: boolean;
  lead: Lead | null;
  onClose: () => void;
  onTransitionRequest: (lead: Lead, target: PipelineStage) => void;
  // Fired after an in-drawer action mutates the lead (e.g. a DNP schedules the
  // next action) so the parent can refresh its list / "due" filter / badge —
  // stage moves already refresh via onTransitionRequest → transition flow.
  onLogged?: () => void;
  refreshKey?: number;
}


export function LeadDrawer({ open, lead, onClose, onTransitionRequest, onLogged, refreshKey }: LeadDrawerProps) {
  const { byIndustry, getStage } = usePipelines();
  const { user } = useAuth();
  const [tab, setTab] = useState<TabKey>("overview");
  const [history, setHistory] = useState<StageTransition[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState(false);
  const [calls, setCalls] = useState<LeadCallLog[]>([]);
  // "Did Not Pick" inline form — logs a DNP with a comment + a scheduled next call.
  const [dnpOpen, setDnpOpen] = useState(false);
  const [dnpComment, setDnpComment] = useState("");
  const [dnpDate, setDnpDate] = useState("");
  const [dnpBusy, setDnpBusy] = useState(false);

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

  // Reset the DNP form when switching leads.
  useEffect(() => {
    setDnpOpen(false);
    setDnpComment("");
    setDnpDate("");
  }, [lead?.id]);

  async function submitDnp() {
    if (!lead || dnpComment.trim().length < MIN_DNP_COMMENT) return;
    setDnpBusy(true);
    try {
      await leadsService.logCall(
        lead.id,
        "dnp",
        dnpComment.trim(),
        dnpDate ? new Date(dnpDate).toISOString() : null
      );
      setCalls(await leadsService.calls(lead.id));
      setDnpOpen(false);
      setDnpComment("");
      setDnpDate("");
      // The DNP just moved the lead's next_action_date + last comment — let the
      // parent list / date-filter / "due" badge reflect it without a manual refresh.
      onLogged?.();
    } catch {
      /* non-critical */
    } finally {
      setDnpBusy(false);
    }
  }

  if (!open || !lead) return null;

  const stages = byIndustry[lead.industry];
  const currentStage = getStage(lead.industry, lead.stage_code);
  const interestLabel = industryInterestLabel(lead.industry);
  const isRealEstate = lead.industry === "real_estate";
  const tabs: TabKey[] = isRealEstate
    ? ["overview", "bookings", "history", "activity"]
    : ["overview", "history", "activity"];
  const activeTab: TabKey = tab === "bookings" && !isRealEstate ? "overview" : tab;

  // Real-estate leads carry a budget range (budget_min/max), not a single value —
  // show the range instead of `value` (which defaults to 0 for RE). Mirrors the
  // null-handling of the leads-list "Value / Budget" column.
  const cur = lead.currency || "INR";
  const budgetMin = lead.budget_min != null ? formatCurrency(lead.budget_min, cur) : null;
  const budgetMax = lead.budget_max != null ? formatCurrency(lead.budget_max, cur) : null;
  const budgetText =
    budgetMin && budgetMax ? `${budgetMin} – ${budgetMax}`
    : budgetMin ? `From ${budgetMin}`
    : budgetMax ? `Up to ${budgetMax}`
    : "—";

  return createPortal(
    // No backdrop-tap close: the drawer holds editable content (comments,
    // transitions) — close only via the ✕ button.
    <div className="modal-backdrop" role="dialog" aria-modal="true">
      <div className="drawer">
        <header className="drawer__header">
          <div>
            <div className="muted text-xs">Lead #{lead.lead_number}</div>
            <h2 style={{ marginTop: "0.25rem" }}>{lead.contact_name || lead.title}</h2>
            {lead.contact_name && lead.title && (
              <div className="muted text-sm">{lead.title}</div>
            )}
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
          {tabs.map((key) => (
            <button
              key={key}
              type="button"
              className={`tab ${activeTab === key ? "tab--active" : ""}`}
              onClick={() => setTab(key)}
            >
              {TAB_LABELS[key]}
            </button>
          ))}
        </div>

        <div className="drawer__body">
          {activeTab === "bookings" && isRealEstate && (
            <LeadBookingsTab leadId={lead.id} customerId={lead.customer_id} refreshKey={refreshKey} />
          )}
          {activeTab === "overview" && (
            <div className="stack">
              <DetailRow label="Contact" value={lead.contact_name || "—"} />
              <DetailRow label="Email" value={lead.contact_email ?? "—"} />
              <DetailRow label="Phone" value={lead.contact_phone ?? "—"} />
              <DetailRow label="Company" value={lead.company_name ?? "—"} />
              <DetailRow label="Industry" value={titleCase(lead.industry)} />
              <DetailRow label={interestLabel} value={lead.interest ?? "—"} />
              <DetailRow label="Source" value={lead.source ?? "—"} />
              {isRealEstate ? (
                <DetailRow label="Budget" value={budgetText} />
              ) : (
                <DetailRow label="Value" value={formatCurrency(lead.value, lead.currency || "INR")} />
              )}
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
                  {stages
                    .filter((stage) => stage.code === lead.stage_code || canSetStage(user?.role, stage.code))
                    .map((stage) => {
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
                  <button
                    type="button"
                    className="btn btn--sm btn--ghost"
                    onClick={() => setDnpOpen((v) => !v)}
                    title="Log a Did-Not-Pick and schedule the next call"
                  >
                    Did Not Pick
                  </button>
                </div>

                {dnpOpen && (
                  <div className="stack" style={{ gap: "0.5rem", marginTop: "0.6rem", padding: "0.6rem 0.75rem", background: "var(--color-surface-muted)", borderRadius: "var(--radius-sm)" }}>
                    <textarea
                      className="input"
                      rows={2}
                      placeholder={`What happened? (min ${MIN_DNP_COMMENT} chars)`}
                      value={dnpComment}
                      onChange={(e) => setDnpComment(e.target.value)}
                    />
                    <label className="stack" style={{ gap: 2 }}>
                      <span className="muted text-xs">Next call date &amp; time (optional)</span>
                      <input className="input" type="datetime-local" value={dnpDate} onChange={(e) => setDnpDate(e.target.value)} />
                    </label>
                    <div className="row" style={{ justifyContent: "flex-end", gap: "0.4rem" }}>
                      <Button size="sm" variant="secondary" onClick={() => setDnpOpen(false)} disabled={dnpBusy}>Cancel</Button>
                      <Button size="sm" loading={dnpBusy} disabled={dnpComment.trim().length < MIN_DNP_COMMENT} onClick={() => void submitDnp()}>
                        Log DNP
                      </Button>
                    </div>
                  </div>
                )}

                {calls.length > 0 && (
                  <div style={{ marginTop: "0.75rem" }}>
                    <div className="muted text-xs" style={{ textTransform: "uppercase", letterSpacing: ".04em", marginBottom: "0.35rem" }}>
                      Call log
                    </div>
                    <div className="stack" style={{ gap: "0.25rem" }}>
                      {calls.slice().reverse().slice(0, 6).map((c) => (
                        <div key={c.id} className="text-xs muted">
                          {c.call_type === "first_call" ? "First call" : c.call_type === "dnp" ? "Did not pick" : "Follow-up"}
                          {" · "}{c.user ? `${c.user.first_name} ${c.user.last_name}` : "—"}
                          {" · "}{formatDateTime(c.created_at)}
                          {c.next_action_date ? ` · next call ${formatDateTime(c.next_action_date)}` : ""}
                          {c.notes ? ` — ${c.notes}` : ""}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {activeTab === "history" && (
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

          {activeTab === "activity" && (
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
