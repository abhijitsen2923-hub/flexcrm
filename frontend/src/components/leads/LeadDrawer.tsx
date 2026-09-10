import { ArrowRight, Mail, MessageCircle, Phone, Sparkles, X } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { Badge, Button, LoadingBlock, EmptyState, useToast } from "../../components";
import { usePipelines } from "../../context/PipelineContext";
import { useAuth } from "../../hooks/useAuth";
import { usePermissions } from "../../hooks/usePermissions";
import { leadsService } from "../../services/leads";
import { siteVisitsService } from "../../services/site-visits";
import type { Lead, LeadCallLog, PipelineStage, StageTransition } from "../../types";
import type { SiteVisit } from "../../types/realestate";
import { mailtoHref, telHref, whatsAppHref } from "../../utils/contactLinks";
import { extractErrorMessage } from "../../utils/errors";
import { formatCurrency, formatDate, formatDateTime, formatRelative } from "../../utils/format";
import { industryInterestLabel, pipelineCategoryTone, titleCase } from "../../utils/options";
import { canSetStage } from "../../utils/stageAccess";
import { LeadBookingsTab } from "./LeadBookingsTab";


// Mirror the stage-transition comment floor so a DNP is captured "like Call".
const MIN_DNP_COMMENT = 10;

/** ISO instant → `YYYY-MM-DDTHH:mm` in local time, to seed a datetime-local input. */
function toLocalInput(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

type TabKey = "overview" | "bookings" | "siteVisits" | "history" | "activity";

const TAB_LABELS: Record<TabKey, string> = {
  overview: "Overview",
  bookings: "Booking & Payments",
  siteVisits: "Site Visits",
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
  const { has } = usePermissions();
  const toast = useToast();
  const canManageVisits = has("LEAD_MANAGE");
  const [tab, setTab] = useState<TabKey>("overview");
  const [history, setHistory] = useState<StageTransition[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState(false);
  const [calls, setCalls] = useState<LeadCallLog[]>([]);
  const [visits, setVisits] = useState<SiteVisit[]>([]);
  const [visitsLoading, setVisitsLoading] = useState(false);
  // Inline reschedule for a single site visit (id being edited + its new time).
  const [rescheduleVisitId, setRescheduleVisitId] = useState<string | null>(null);
  const [rescheduleAt, setRescheduleAt] = useState("");
  const [visitBusy, setVisitBusy] = useState(false);
  // "Did Not Pick" inline form — logs a DNP with a comment + a scheduled next call.
  const [dnpOpen, setDnpOpen] = useState(false);
  const [dnpComment, setDnpComment] = useState("");
  const [dnpDate, setDnpDate] = useState("");
  const [dnpBusy, setDnpBusy] = useState(false);
  // "Log follow-up" inline form (shown only in the Follow-up stage) — records a
  // repeated follow-up call; each one stacks in the call log as Follow-up #N.
  const [fuOpen, setFuOpen] = useState(false);
  const [fuComment, setFuComment] = useState("");
  const [fuDate, setFuDate] = useState("");
  const [fuBusy, setFuBusy] = useState(false);

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

  // Site visits (real-estate only) — a lead can have many; list them all.
  useEffect(() => {
    if (!open || !lead || lead.industry !== "real_estate") {
      setVisits([]);
      return;
    }
    let cancelled = false;
    setVisitsLoading(true);
    void siteVisitsService
      .list({ leadId: lead.id })
      .then((rows) => { if (!cancelled) setVisits(rows); })
      .catch(() => { if (!cancelled) setVisits([]); })
      .finally(() => { if (!cancelled) setVisitsLoading(false); });
    return () => { cancelled = true; };
  }, [open, lead?.id, refreshKey]);

  // Reset the DNP + follow-up forms when switching leads.
  useEffect(() => {
    setDnpOpen(false);
    setDnpComment("");
    setDnpDate("");
    setFuOpen(false);
    setFuComment("");
    setFuDate("");
    setRescheduleVisitId(null);
    setRescheduleAt("");
  }, [lead?.id]);

  async function refreshVisits() {
    if (!lead) return;
    try {
      setVisits(await siteVisitsService.list({ leadId: lead.id }));
    } catch {
      /* non-critical */
    }
  }

  async function saveReschedule(visitId: string) {
    if (!rescheduleAt) return;
    setVisitBusy(true);
    try {
      // Convert the local datetime-local value to a real UTC instant.
      await siteVisitsService.update(visitId, { scheduledAt: new Date(rescheduleAt).toISOString() });
      await refreshVisits();
      setRescheduleVisitId(null);
      setRescheduleAt("");
      toast.success("Visit rescheduled");
      onLogged?.();
    } catch (err) {
      toast.error("Reschedule failed", extractErrorMessage(err));
    } finally {
      setVisitBusy(false);
    }
  }

  async function cancelVisit(visitId: string) {
    setVisitBusy(true);
    try {
      await siteVisitsService.update(visitId, { status: "cancelled" });
      await refreshVisits();
      toast.success("Visit cancelled");
    } catch (err) {
      toast.error("Cancel failed", extractErrorMessage(err));
    } finally {
      setVisitBusy(false);
    }
  }

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

  async function submitFollowUp() {
    if (!lead || fuComment.trim().length < MIN_DNP_COMMENT) return;
    setFuBusy(true);
    try {
      await leadsService.logCall(
        lead.id,
        "follow_up",
        fuComment.trim(),
        fuDate ? new Date(fuDate).toISOString() : null
      );
      setCalls(await leadsService.calls(lead.id));
      setFuOpen(false);
      setFuComment("");
      setFuDate("");
      // A follow-up (optionally) reschedules next_action_date + updates the last
      // comment — refresh the parent list / "due" filter like the DNP path does.
      onLogged?.();
    } catch {
      /* non-critical */
    } finally {
      setFuBusy(false);
    }
  }

  if (!open || !lead) return null;

  const stages = byIndustry[lead.industry];
  const currentStage = getStage(lead.industry, lead.stage_code);
  const interestLabel = industryInterestLabel(lead.industry);
  const isRealEstate = lead.industry === "real_estate";
  const tabs: TabKey[] = isRealEstate
    ? ["overview", "bookings", "siteVisits", "history", "activity"]
    : ["overview", "history", "activity"];
  const activeTab: TabKey =
    (tab === "bookings" || tab === "siteVisits") && !isRealEstate ? "overview" : tab;

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
          {activeTab === "siteVisits" && isRealEstate && (
            <div className="stack">
              {visitsLoading && visits.length === 0 ? (
                <LoadingBlock label="Loading site visits…" />
              ) : visits.length === 0 ? (
                <EmptyState
                  title="No site visits"
                  description="Move this lead to “Site Visit Confirmed” to book one or more visits."
                />
              ) : (
                visits.map((v) => {
                  const cancelled = v.status === "cancelled";
                  const isRescheduling = rescheduleVisitId === v.id;
                  return (
                    <div key={v.id} className="card" style={{ padding: "0.75rem 1rem", opacity: cancelled ? 0.6 : 1 }}>
                      <div className="row row--between">
                        <strong style={cancelled ? { textDecoration: "line-through" } : undefined}>
                          {v.project?.name ?? "Site"}
                        </strong>
                        <span className="muted text-sm">{formatDateTime(v.scheduledAt)}</span>
                      </div>
                      <div className="muted text-sm" style={{ marginTop: 4 }}>
                        {cancelled
                          ? "Cancelled"
                          : v.attended === null
                            ? "Not recorded"
                            : v.attended
                              ? "Attended"
                              : "Absent"}
                        {v.feedback ? ` · ${v.feedback}` : ""}
                      </div>

                      {canManageVisits && !cancelled && (
                        <div style={{ marginTop: "0.6rem" }}>
                          {isRescheduling ? (
                            <div className="stack" style={{ gap: "0.4rem" }}>
                              <input
                                className="input"
                                type="datetime-local"
                                value={rescheduleAt}
                                onChange={(e) => setRescheduleAt(e.target.value)}
                                aria-label="New visit date & time"
                              />
                              <div className="row" style={{ justifyContent: "flex-end", gap: "0.4rem" }}>
                                <Button size="sm" variant="secondary" disabled={visitBusy} onClick={() => { setRescheduleVisitId(null); setRescheduleAt(""); }}>
                                  Cancel
                                </Button>
                                <Button size="sm" loading={visitBusy} disabled={!rescheduleAt} onClick={() => void saveReschedule(v.id)}>
                                  Save time
                                </Button>
                              </div>
                            </div>
                          ) : (
                            <div className="row" style={{ gap: "0.4rem" }}>
                              <Button
                                size="sm"
                                variant="ghost"
                                onClick={() => { setRescheduleVisitId(v.id); setRescheduleAt(toLocalInput(v.scheduledAt)); }}
                              >
                                Reschedule
                              </Button>
                              <Button size="sm" variant="ghost" disabled={visitBusy} onClick={() => void cancelVisit(v.id)}>
                                Cancel visit
                              </Button>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          )}
          {activeTab === "overview" && (
            <div className="stack">
              <ContactActions
                name={lead.contact_name || lead.title}
                phone={lead.contact_phone}
                altPhone={lead.contact_phone_alt}
                email={lead.contact_email}
              />
              <DetailRow label="Contact" value={lead.contact_name || "—"} />
              <DetailRow label="Email" value={lead.contact_email ?? "—"} />
              <DetailRow label="Phone" value={lead.contact_phone ?? "—"} />
              {lead.contact_phone_alt && <DetailRow label="Alt phone" value={lead.contact_phone_alt} />}
              <DetailRow label="Company" value={lead.company_name ?? "—"} />
              <DetailRow label="Industry" value={titleCase(lead.industry)} />
              <DetailRow label={interestLabel} value={lead.interest ?? "—"} />
              <DetailRow label="Source" value={lead.source ?? "—"} />
              {lead.external_id && <DetailRow label="Source ID" value={lead.external_id} />}
              <DetailRow label="Location" value={lead.preferred_location ?? "—"} />
              {isRealEstate && lead.possession_preference && (
                <DetailRow label="Possession" value={lead.possession_preference} />
              )}
              {isRealEstate ? (
                <DetailRow label="Budget" value={budgetText} />
              ) : (
                <DetailRow label="Value" value={formatCurrency(lead.value, lead.currency || "INR")} />
              )}
              <DetailRow label="Probability" value={`${lead.probability}%`} />
              <DetailRow label="Expected close" value={formatDate(lead.expected_close_date)} />
              <DetailRow label="Created" value={formatDateTime(lead.created_at)} />
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
              {lead.notes && (
                <DetailRow
                  label="Notes"
                  value={<span style={{ whiteSpace: "pre-wrap" }}>{lead.notes}</span>}
                />
              )}

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
                  {lead.stage_code === "follow_up" && (
                    <button
                      type="button"
                      className="btn btn--sm btn--ghost"
                      onClick={() => setFuOpen((v) => !v)}
                      title="Log another follow-up and (optionally) schedule the next one"
                    >
                      Log follow-up
                    </button>
                  )}
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

                {fuOpen && (
                  <div className="stack" style={{ gap: "0.5rem", marginTop: "0.6rem", padding: "0.6rem 0.75rem", background: "var(--color-surface-muted)", borderRadius: "var(--radius-sm)" }}>
                    <textarea
                      className="input"
                      rows={2}
                      placeholder={`How did the follow-up go? (min ${MIN_DNP_COMMENT} chars)`}
                      value={fuComment}
                      onChange={(e) => setFuComment(e.target.value)}
                    />
                    <label className="stack" style={{ gap: 2 }}>
                      <span className="muted text-xs">Next follow-up date &amp; time (optional)</span>
                      <input className="input" type="datetime-local" value={fuDate} onChange={(e) => setFuDate(e.target.value)} />
                    </label>
                    <div className="row" style={{ justifyContent: "flex-end", gap: "0.4rem" }}>
                      <Button size="sm" variant="secondary" onClick={() => setFuOpen(false)} disabled={fuBusy}>Cancel</Button>
                      <Button size="sm" loading={fuBusy} disabled={fuComment.trim().length < MIN_DNP_COMMENT} onClick={() => void submitFollowUp()}>
                        Log follow-up
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
                      {(() => {
                        // Number follow-ups chronologically (#1, #2, …) — `calls`
                        // arrives oldest-first from the backend.
                        const fuOrdinal = new Map<string, number>();
                        let n = 0;
                        for (const c of calls) {
                          if (c.call_type === "follow_up") { n += 1; fuOrdinal.set(c.id, n); }
                        }
                        return calls.slice().reverse().slice(0, 6).map((c) => (
                          <div key={c.id} className="text-xs muted">
                            {c.call_type === "first_call"
                              ? "First call"
                              : c.call_type === "dnp"
                                ? "Did not pick"
                                : `Follow-up #${fuOrdinal.get(c.id) ?? ""}`}
                            {" · "}{c.user ? `${c.user.first_name} ${c.user.last_name}` : "—"}
                            {" · "}{formatDateTime(c.created_at)}
                            {c.next_action_date ? ` · next call ${formatDateTime(c.next_action_date)}` : ""}
                            {c.notes ? ` — ${c.notes}` : ""}
                          </div>
                        ));
                      })()}
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


/**
 * The contact card at the top of a lead's Overview: the full phone number,
 * plus one-tap Call / WhatsApp / Email. The links open the device's dialer /
 * WhatsApp / mail app (frontend-only — no backend). Works on desktop too.
 */
function ContactActions({
  name,
  phone,
  altPhone,
  email,
}: {
  name: string;
  phone: string | null;
  altPhone: string | null;
  email: string | null;
}) {
  const tel = telHref(phone);
  const wa = whatsAppHref(phone);
  const mail = mailtoHref(email);

  // Nothing to act on — don't render an empty card.
  if (!tel && !wa && !mail) return null;

  return (
    <div className="contact-actions">
      {phone ? (
        <div className="contact-actions__phone">
          <span className="contact-actions__label">Phone</span>
          <span className="contact-actions__number">{phone}</span>
          {altPhone && <span className="contact-actions__alt">Alt · {altPhone}</span>}
        </div>
      ) : email ? (
        <div className="contact-actions__phone">
          <span className="contact-actions__label">Email</span>
          <span className="contact-actions__number contact-actions__number--email">{email}</span>
        </div>
      ) : null}
      <div className="contact-actions__btns">
        {tel && (
          <a className="contact-act contact-act--call" href={tel} aria-label={`Call ${name}`}>
            <Phone size={18} aria-hidden="true" />
            <span>Call</span>
          </a>
        )}
        {wa && (
          <a
            className="contact-act contact-act--wa"
            href={wa}
            target="_blank"
            rel="noreferrer"
            aria-label={`WhatsApp ${name}`}
          >
            <MessageCircle size={18} aria-hidden="true" />
            <span>WhatsApp</span>
          </a>
        )}
        {mail && (
          <a className="contact-act contact-act--mail" href={mail} aria-label={`Email ${name}`}>
            <Mail size={18} aria-hidden="true" />
            <span>Email</span>
          </a>
        )}
      </div>
    </div>
  );
}
