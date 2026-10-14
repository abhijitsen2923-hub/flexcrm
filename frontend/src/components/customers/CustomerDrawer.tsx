import { X } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { Badge, Button, EmptyState, LoadingBlock, Modal, useToast } from "../../components";
import { usePipelines } from "../../context/PipelineContext";
import { useAuth } from "../../hooks/useAuth";
import { usePermissions } from "../../hooks/usePermissions";
import { invalidate } from "../../hooks/resourceCache";
import { useRealtimeRefresh } from "../../realtime";
import { bookingsService } from "../../services/bookings";
import { customersService } from "../../services/customers";
import { inventoryService } from "../../services/inventory";
import { leadsService } from "../../services/leads";
import { extractErrorMessage } from "../../utils/errors";
import { siteVisitsService } from "../../services/site-visits";
import { BookingWizard, type BookingWizardUnit } from "../../pages/bookings/components/BookingWizard";
import { DocumentPreview } from "../../pages/bookings/components/DocumentPreview";
import { PaymentPlanModal } from "../../pages/bookings/components/PaymentPlanModal";
import { RegisterBookingModal } from "../../pages/bookings/components/RegisterBookingModal";
import type { PriceDefaults } from "../../utils/priceDefaults";
import { StageTransitionModal } from "../leads/StageTransitionModal";
import type { Customer, Lead, PipelineStage } from "../../types";
import type { Booking, SiteVisit } from "../../types/realestate";
import { formatCurrency, formatDate, formatDateTime, formatInr } from "../../utils/format";
import { priceDefaultsForProject } from "../../utils/priceDefaults";
import {
  instalmentTotals,
  purchaseEventMatters,
  purchaseTotals,
  type LeadStageInfo,
  type PurchaseAction,
  type PurchasePerms,
} from "../../utils/purchaseProgress";
import { canSetStage } from "../../utils/stageAccess";
import { CustomerPurchaseCard } from "./CustomerPurchaseCard";
import { PossessionChecklistModal } from "./PossessionChecklistModal";

type TabKey = "overview" | "purchases" | "payments" | "visits";

interface Props {
  open: boolean;
  customer: Customer | null;
  onClose: () => void;
}

export function CustomerDrawer({ open, customer, onClose }: Props) {
  const [tab, setTab] = useState<TabKey>("overview");
  const [full, setFull] = useState<Customer | null>(null);
  const [bookings, setBookings] = useState<Booking[]>([]);
  // The customer's leads (for each booking's stage); empty for users without LEAD_VIEW.
  const [leads, setLeads] = useState<Lead[]>([]);
  const [visits, setVisits] = useState<SiteVisit[]>([]);
  const [loading, setLoading] = useState(false);
  const [docHtml, setDocHtml] = useState<string | null>(null);
  const [docTitle, setDocTitle] = useState("");
  const [docPdf, setDocPdf] = useState<{ bookingId: string; docType: "booking_form" | "allotment_letter" } | null>(null);
  const [portalCreds, setPortalCreds] = useState<{ email: string; temporary_password: string } | null>(null);
  const [inviting, setInviting] = useState(false);
  // Purchases card actions — each opens the same window the rest of the app uses.
  const [wizard, setWizard] = useState<{ booking: Booking; unit: BookingWizardUnit; priceDefaults: PriceDefaults | null } | null>(null);
  const [openingWizard, setOpeningWizard] = useState<string | null>(null); // booking id while its project loads
  const [payBooking, setPayBooking] = useState<Booking | null>(null);
  const [registerTarget, setRegisterTarget] = useState<Booking | null>(null);
  const [checklistTarget, setChecklistTarget] = useState<Booking | null>(null);
  const [move, setMove] = useState<{ lead: Lead; target: PipelineStage } | null>(null);
  const toast = useToast();
  const { user } = useAuth();
  const { has } = usePermissions();
  const { getStage } = usePipelines();
  const canViewLeads = has("LEAD_VIEW");
  const canManagePayments = has("FINANCE_RECORD_PAYMENT");
  const perms: PurchasePerms = {
    leadManage: has("LEAD_MANAGE"),
    recordPayment: canManagePayments,
    canSetStage: (code) => canSetStage(user?.role, code),
  };
  // A window opened from the drawer sits on top of it: Escape closes that window, not the drawer too.
  const overlayOpen = Boolean(docHtml || wizard || payBooking || registerTarget || checklistTarget || move);

  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !overlayOpen) onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose, overlayOpen]);

  // Page scroll lock, tied to the drawer being open only. Kept apart from the Escape listener: that one re-runs as
  // windows open and close, and re-locking then could capture a window's "hidden" and leave the page unscrollable.
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  // Every load gets a number; only the newest one may write state, so a slow first load can't overwrite a
  // reload that finished after an action (and nothing lands after the drawer closed or switched customer).
  const loadSeq = useRef(0);
  // Bumped whenever the drawer opens, closes or switches customer. An action that waits on the server before opening
  // a window (Complete booking loads the project's prices) checks it first, so nothing opens over a closed or
  // different customer's drawer. loadSeq can't be used for this: a live reload bumps it too.
  const drawerSession = useRef(0);

  async function load(target: Customer, silent: boolean) {
    const seq = ++loadSeq.current;
    if (!silent) setLoading(true);
    try {
      const [c, bks, lds] = await Promise.all([
        customersService.get(target.id).catch(() => target),
        bookingsService.list({ customerId: target.id }).catch(() => [] as Booking[]),
        // The lead's stage drives the progress strip; GET /leads needs LEAD_VIEW (accounts don't have it).
        canViewLeads
          ? leadsService
              .list({ customer_id: target.id, page_size: 50 })
              .then((r) => r.items)
              .catch(() => [] as Lead[])
          : Promise.resolve([] as Lead[]),
      ]);
      if (seq !== loadSeq.current) return;
      setFull(c);
      setBookings(bks);
      setLeads(lds);
      const leadId = c.source_lead_id ?? c.source_lead?.id ?? null;
      if (leadId) {
        const sv = await siteVisitsService.list({ leadId }).catch(() => [] as SiteVisit[]);
        if (seq === loadSeq.current) setVisits(sv);
      } else {
        setVisits([]);
      }
    } finally {
      if (seq === loadSeq.current) setLoading(false);
    }
  }

  // Quiet reload after an action or a live update — keeps the current tab on screen instead of a spinner.
  function reload() {
    if (open && customer) void load(customer, true);
  }

  useEffect(() => {
    drawerSession.current += 1;
    // A window opened for the previous customer (or before the drawer closed) never carries over to this one.
    setDocHtml(null);
    setWizard(null);
    setOpeningWizard(null);
    setPayBooking(null);
    setRegisterTarget(null);
    setChecklistTarget(null);
    setMove(null);
    if (!open || !customer) {
      loadSeq.current += 1; // drop any load still in flight
      setFull(null);
      setBookings([]);
      setLeads([]);
      setVisits([]);
      setTab("overview");
      setPortalCreds(null);
      setLoading(false);
      return;
    }
    void load(customer, false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, customer?.id]);

  // Live: a stage change of one of these leads (someone moved it, or a payment / registration / checklist moved it
  // automatically) or a status change of one of these units reloads the drawer.
  useRealtimeRefresh(
    (event) =>
      open &&
      !!customer &&
      purchaseEventMatters(
        event,
        bookings.map((b) => b.leadId).filter((id): id is string => !!id),
        bookings.map((b) => b.unitId)
      ),
    reload
  );

  async function generateDoc(bookingId: string, docType: "booking_form" | "allotment_letter") {
    try {
      const { html, title } = await bookingsService.getDocumentHtml(bookingId, docType);
      setDocHtml(html);
      setDocTitle(title);
      setDocPdf({ bookingId, docType });
    } catch {
      /* preview failure is non-critical */
    }
  }

  async function invitePortal() {
    if (!customer) return;
    setInviting(true);
    try {
      const creds = await customersService.grantPortalAccess(customer.id);
      setPortalCreds(creds);
      toast.success("Portal login created");
    } catch (e) {
      toast.error("Could not create portal login", extractErrorMessage(e));
    } finally {
      setInviting(false);
    }
  }

  // "Complete booking": reopen the booking wizard where the draft stopped, with the project's prices pre-filled
  // (the same defaults the Bookings page and the lead's Booking tab use).
  async function completeBooking(b: Booking) {
    const session = drawerSession.current;
    setOpeningWizard(b.id);
    try {
      const projects = await inventoryService.listProjects();
      // The drawer was closed or switched to another customer while the projects loaded: open nothing.
      if (session !== drawerSession.current) return;
      for (const p of projects) {
        for (const t of p.towers) {
          const u = t.units.find((x) => x.id === b.unitId);
          if (u) {
            setWizard({
              booking: b,
              unit: { ...u, towerName: t.name, projectName: p.name },
              priceDefaults: priceDefaultsForProject(p, u.unitType),
            });
            return;
          }
        }
      }
      // Unit not in the inventory list (e.g. its tower was archived): resume with what the booking knows.
      if (b.unit) setWizard({ booking: b, unit: b.unit, priceDefaults: null });
      else toast.error("Could not open the booking", "Its unit was not found.");
    } catch (err) {
      if (session === drawerSession.current) toast.error("Could not load the project's prices", extractErrorMessage(err));
    } finally {
      // A newer session already reset this (and may be opening another booking's wizard) — leave it alone.
      if (session === drawerSession.current) setOpeningWizard(null);
    }
  }

  function openMove(lead: Lead, stageCode: string) {
    const target = getStage(lead.industry, stageCode);
    if (!target) {
      toast.error("Stage not found", "Reload the page and try again.");
      return;
    }
    setMove({ lead, target });
  }

  function runAction(action: PurchaseAction, b: Booking, lead: Lead | null) {
    switch (action.kind) {
      case "complete_booking":
        void completeBooking(b);
        break;
      case "record_payment":
        setPayBooking(b);
        break;
      case "register":
        setRegisterTarget(b);
        break;
      case "possession":
        setChecklistTarget(b);
        break;
      case "move":
        if (lead && action.stageCode) openMove(lead, action.stageCode);
        break;
    }
  }

  if (!open || !customer) return null;
  const c = full ?? customer;
  const leadById = new Map(leads.map((l) => [l.id, l]));
  const totals = purchaseTotals(bookings);
  // Instalment rows of every booking, tagged with their unit; cancelled bookings' rows stay listed but uncounted.
  const scheduleRows = bookings.flatMap((b) => b.paymentSchedules.map((p) => ({ p, b })));
  const instalments = instalmentTotals(scheduleRows.filter((r) => r.b.status !== "cancelled").map((r) => r.p));
  const hasCancelledRows = scheduleRows.some((r) => r.b.status === "cancelled");

  return (
    <>
      {createPortal(
        <div className="modal-backdrop" role="dialog" aria-modal="true">
          <div className="drawer">
            <header className="drawer__header">
              <div>
                <div className="muted text-xs">Customer</div>
                <h2 style={{ marginTop: "0.25rem" }}>{c.contact_name}</h2>
                <div className="row" style={{ gap: "0.5rem", marginTop: "0.5rem", alignItems: "center", flexWrap: "wrap" }}>
                  {c.company_name && <span className="muted text-sm">{c.company_name}</span>}
                  <Badge tone="info">{c.lifecycle_stage}</Badge>
                  <Badge tone={c.status === "active" ? "success" : c.status === "churned" ? "danger" : "neutral"}>
                    {c.status}
                  </Badge>
                  {c.source_lead && <Badge tone="success">Lead #{c.source_lead.lead_number}</Badge>}
                </div>
              </div>
              <button type="button" className="btn btn--ghost btn--icon" onClick={onClose} aria-label="Close drawer">
                <X size={18} />
              </button>
            </header>

            <div className="drawer__tabs">
              {(["overview", "purchases", "payments", "visits"] as TabKey[]).map((k) => (
                <button
                  key={k}
                  type="button"
                  className={`tab ${tab === k ? "tab--active" : ""}`}
                  onClick={() => setTab(k)}
                >
                  {k === "overview"
                    ? "Overview"
                    : k === "purchases"
                      ? `Purchases (${totals.count})`
                      : k === "payments"
                        ? "Payments"
                        : `Site Visits (${visits.length})`}
                </button>
              ))}
            </div>

            <div className="drawer__body">
              {loading ? (
                <LoadingBlock label="Loading customer history…" />
              ) : (
                <>
                  {tab === "overview" && (
                    <div className="stack">
                      <DetailRow label="Contact" value={c.contact_name} />
                      <DetailRow label="Company" value={c.company_name || "—"} />
                      <DetailRow label="Email" value={c.email ?? "—"} />
                      <DetailRow label="Phone" value={c.phone ?? "—"} />
                      <DetailRow label="Address" value={c.address ?? "—"} />
                      <DetailRow label="Lead source" value={c.source ?? "—"} />
                      <DetailRow label="Lifecycle" value={c.lifecycle_stage} />
                      <DetailRow label="Status" value={c.status} />
                      <DetailRow
                        label="Owner"
                        value={
                          c.current_owner
                            ? `${c.current_owner.first_name} ${c.current_owner.last_name}`
                            : "—"
                        }
                      />
                      <DetailRow label="Lifetime value" value={formatCurrency(c.ltv ?? "0", "INR")} />
                      <DetailRow label="Sale value (at close)" value={c.sale_value ? formatCurrency(c.sale_value, "INR") : "—"} />
                      <DetailRow
                        label="Origin"
                        value={c.source_lead ? `Lead #${c.source_lead.lead_number} — ${c.source_lead.title}` : "Added manually"}
                      />
                      <DetailRow label="Customer since" value={formatDate(c.created_at)} />
                    </div>
                  )}

                  {tab === "purchases" &&
                    (bookings.length === 0 ? (
                      <EmptyState title="No purchases yet" description="Bookings for this customer will appear here." />
                    ) : (
                      <div className="stack">
                        {totals.count > 1 && (
                          <div className="purchase-summary text-sm" title="Cancelled bookings are not counted">
                            <span>
                              <span className="muted">{totals.count} purchases · Total</span> <strong>{formatInr(totals.total)}</strong>
                            </span>
                            <span>
                              <span className="muted">Paid</span> <strong>{formatInr(totals.paid)}</strong>
                            </span>
                            <span>
                              <span className="muted">Balance</span> <strong>{formatInr(totals.balance)}</strong>
                            </span>
                          </div>
                        )}
                        {bookings.map((b) => {
                          const lead = b.leadId ? leadById.get(b.leadId) ?? null : null;
                          const stage = lead ? getStage(lead.industry, lead.stage_code) : undefined;
                          const leadInfo: LeadStageInfo | null = lead
                            ? { stage_code: lead.stage_code, category: stage?.category ?? null }
                            : null;
                          return (
                            <CustomerPurchaseCard
                              key={b.id}
                              booking={b}
                              lead={leadInfo}
                              leadNumber={lead?.lead_number ?? null}
                              stageName={stage?.name ?? lead?.stage_code ?? null}
                              perms={perms}
                              canViewDocs={canViewLeads}
                              canManagePayments={canManagePayments}
                              busy={openingWizard === b.id}
                              onAction={(action) => runAction(action, b, lead)}
                              onMove={(code) => lead && openMove(lead, code)}
                              onPayments={() => setPayBooking(b)}
                              onDocument={(docType) => void generateDoc(b.id, docType)}
                            />
                          );
                        })}
                      </div>
                    ))}

                  {tab === "payments" &&
                    (scheduleRows.length === 0 ? (
                      <EmptyState title="No payment schedule" description="Installments appear here once a payment plan is set." />
                    ) : (
                      <div className="stack" style={{ gap: "0.6rem" }}>
                        <div className="purchase-summary text-sm">
                          <span>
                            <span className="muted">Demanded</span> <strong>{formatInr(instalments.demand)}</strong>
                          </span>
                          <span>
                            <span className="muted">Paid</span> <strong>{formatInr(instalments.paid)}</strong>
                          </span>
                          <span>
                            <span className="muted">Outstanding</span> <strong>{formatInr(instalments.outstanding)}</strong>
                          </span>
                          {hasCancelledRows && <span className="muted">Cancelled bookings not counted</span>}
                        </div>
                        <table className="table">
                          <thead>
                            <tr>
                              <th style={{ textAlign: "left" }}>Unit</th>
                              <th style={{ textAlign: "left" }}>Installment</th>
                              <th style={{ textAlign: "left" }}>Due</th>
                              <th style={{ textAlign: "right" }}>Demand</th>
                              <th style={{ textAlign: "right" }}>Paid</th>
                              <th style={{ textAlign: "right" }}>Outstanding</th>
                            </tr>
                          </thead>
                          <tbody>
                            {scheduleRows.map(({ p, b }) => (
                              <tr key={p.id}>
                                <td data-label="Unit">
                                  {b.unit ? `${b.unit.unitNumber} · ${b.unit.towerName}` : `Unit ${b.unitId.slice(0, 8)}`}{" "}
                                  {b.status === "cancelled" && <Badge tone="danger">Cancelled</Badge>}
                                </td>
                                <td data-label="Installment">{p.installmentName}</td>
                                <td data-label="Due">
                                  {formatDate(p.dueDate)} {p.isOverdue && <Badge tone="danger">Overdue</Badge>}
                                </td>
                                <td data-label="Demand" style={{ textAlign: "right" }}>{formatCurrency(p.demandAmount, "INR")}</td>
                                <td data-label="Paid" style={{ textAlign: "right" }}>{formatCurrency(p.paidAmount, "INR")}</td>
                                <td data-label="Outstanding" style={{ textAlign: "right" }}>{formatCurrency(p.outstanding, "INR")}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ))}

                  {tab === "visits" &&
                    (visits.length === 0 ? (
                      <EmptyState title="No site visits" description="Site visits scheduled for this customer's lead appear here." />
                    ) : (
                      <div className="stack">
                        {visits.map((v) => (
                          <div key={v.id} className="card" style={{ padding: "0.75rem 1rem" }}>
                            <div className="row row--between">
                              <strong>{v.project?.name ?? "Site"}</strong>
                              <span className="muted text-sm">{formatDateTime(v.scheduledAt)}</span>
                            </div>
                            <div className="muted text-sm" style={{ marginTop: 4 }}>
                              {v.attended === null ? "Not recorded" : v.attended ? "Attended" : "Absent"}
                              {v.feedback ? ` · ${v.feedback}` : ""}
                            </div>
                          </div>
                        ))}
                      </div>
                    ))}
                </>
              )}
            </div>

            <footer className="drawer__footer" style={{ flexDirection: "column", alignItems: "stretch", gap: "0.6rem" }}>
              {portalCreds && (
                <div className="card" style={{ padding: "0.6rem 0.8rem", fontSize: "0.8rem" }}>
                  <div><strong>Portal login created.</strong> Share with the buyer:</div>
                  <div style={{ marginTop: 4 }}>Email: <code>{portalCreds.email}</code></div>
                  <div>Temp password: <code>{portalCreds.temporary_password}</code></div>
                </div>
              )}
              <div className="row" style={{ justifyContent: "space-between", gap: "0.5rem" }}>
                <Button variant="secondary" onClick={() => void invitePortal()} loading={inviting}>
                  Invite to portal
                </Button>
                <Button variant="secondary" onClick={onClose}>
                  Close
                </Button>
              </div>
            </footer>
          </div>
        </div>,
        document.body
      )}

      {docHtml && (
        <Modal open title={docTitle} size="lg" onClose={() => setDocHtml(null)}>
          <DocumentPreview html={docHtml} title={docTitle} pdf={docPdf ?? undefined} onClose={() => setDocHtml(null)} />
        </Modal>
      )}

      {wizard && (
        <BookingWizard
          unit={wizard.unit}
          initialBooking={wizard.booking}
          priceDefaults={wizard.priceDefaults}
          // Closing part-way still keeps the steps already saved (e.g. the price) — reload either way.
          onClose={() => {
            setWizard(null);
            reload();
          }}
          onComplete={() => {
            setWizard(null);
            reload();
          }}
        />
      )}

      {payBooking && (
        <PaymentPlanModal
          booking={payBooking}
          onClose={() => setPayBooking(null)}
          onChanged={(updated) => {
            setPayBooking(updated);
            reload();
          }}
        />
      )}

      {registerTarget && (
        <RegisterBookingModal
          booking={registerTarget}
          idPrefix="customer-reg"
          onClose={() => setRegisterTarget(null)}
          onRegistered={() => {
            setRegisterTarget(null);
            reload();
          }}
        />
      )}

      {checklistTarget && (
        <PossessionChecklistModal
          // Seeded from the drawer's latest copy of the booking (found by id), not the object clicked earlier.
          booking={bookings.find((x) => x.id === checklistTarget.id) ?? checklistTarget}
          // Each saved tick replaces that booking here, so reopening the window shows the list as saved.
          onSaved={(updated) => setBookings((prev) => prev.map((x) => (x.id === updated.id ? updated : x)))}
          onClose={() => {
            setChecklistTarget(null);
            reload();
          }}
        />
      )}

      {move && (
        // The lead's normal stage-change window: same role, owner, comment and manager-only-Sold rules as the Leads page.
        <StageTransitionModal
          open
          lead={move.lead}
          targetStage={move.target}
          onClose={() => setMove(null)}
          onSubmit={async (payload) => {
            // Strip stages never book site visits; those are separate calendar calls on the Leads page.
            const { site_visits: _siteVisits, ...transition } = payload;
            await leadsService.createTransition(move.lead.id, transition);
            invalidate("leads:");
            toast.success("Stage updated", `Moved to ${move.target.name}`);
            reload();
          }}
        />
      )}
    </>
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
