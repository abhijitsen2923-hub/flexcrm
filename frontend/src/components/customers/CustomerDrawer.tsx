import { X } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { Badge, Button, EmptyState, LoadingBlock, Modal } from "../../components";
import { bookingsService } from "../../services/bookings";
import { customersService } from "../../services/customers";
import { siteVisitsService } from "../../services/site-visits";
import { DocumentPreview } from "../../pages/bookings/components/DocumentPreview";
import type { Customer } from "../../types";
import type { Booking, SiteVisit } from "../../types/realestate";
import { formatCurrency, formatDate, formatDateTime } from "../../utils/format";

type TabKey = "overview" | "purchases" | "payments" | "visits";

const UNIT_TYPE_LABEL: Record<string, string> = {
  residential: "Residential",
  parking: "Parking",
  shop: "Shop",
  godown: "Godown",
};

const UNIT_STATUS_TONE: Record<string, "success" | "warning" | "primary" | "info" | "neutral"> = {
  available: "success",
  hold: "warning",
  booked: "primary",
  registered: "info",
  sold: "neutral",
};

interface Props {
  open: boolean;
  customer: Customer | null;
  onClose: () => void;
}

export function CustomerDrawer({ open, customer, onClose }: Props) {
  const [tab, setTab] = useState<TabKey>("overview");
  const [full, setFull] = useState<Customer | null>(null);
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [visits, setVisits] = useState<SiteVisit[]>([]);
  const [loading, setLoading] = useState(false);
  const [docHtml, setDocHtml] = useState<string | null>(null);
  const [docTitle, setDocTitle] = useState("");

  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", handler);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  useEffect(() => {
    if (!open || !customer) {
      setFull(null);
      setBookings([]);
      setVisits([]);
      setTab("overview");
      return;
    }
    let cancelled = false;
    setLoading(true);
    void (async () => {
      try {
        const [c, bks] = await Promise.all([
          customersService.get(customer.id).catch(() => customer),
          bookingsService.list({ customerId: customer.id }).catch(() => [] as Booking[]),
        ]);
        if (cancelled) return;
        setFull(c);
        setBookings(bks);
        const leadId = c.source_lead_id ?? c.source_lead?.id ?? null;
        if (leadId) {
          const sv = await siteVisitsService.list({ leadId }).catch(() => [] as SiteVisit[]);
          if (!cancelled) setVisits(sv);
        } else if (!cancelled) {
          setVisits([]);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, customer?.id]);

  async function generateDoc(bookingId: string, docType: "booking_form" | "allotment_letter") {
    try {
      const { html, title } = await bookingsService.getDocumentHtml(bookingId, docType);
      setDocHtml(html);
      setDocTitle(title);
    } catch {
      /* preview failure is non-critical */
    }
  }

  if (!open || !customer) return null;
  const c = full ?? customer;
  const payments = bookings.flatMap((b) => b.paymentSchedules);

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
                      ? `Purchases (${bookings.length})`
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
                      <DetailRow label="Lifetime value" value={formatCurrency(c.ltv ?? "0", "INR")} />
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
                        {bookings.map((b) => (
                          <div key={b.id} className="card" style={{ padding: "0.85rem 1rem" }}>
                            <div className="row row--between" style={{ alignItems: "flex-start" }}>
                              <div>
                                <strong>{b.unit ? `${b.unit.projectName} · ${b.unit.towerName}` : "Unit"}</strong>
                                <div className="muted text-sm" style={{ marginTop: 2 }}>
                                  {b.unit
                                    ? `${UNIT_TYPE_LABEL[b.unit.unitType] ?? b.unit.unitType} · Unit ${b.unit.unitNumber} · Floor ${b.unit.floor} · ${b.unit.area} ${b.unit.areaUnit}`
                                    : `Unit ${b.unitId.slice(0, 8)}`}
                                </div>
                              </div>
                              {b.unit && <Badge tone={UNIT_STATUS_TONE[b.unit.status] ?? "neutral"}>{b.unit.status}</Badge>}
                            </div>
                            <div className="row" style={{ gap: "1.25rem", marginTop: "0.6rem", flexWrap: "wrap" }}>
                              <Meta label="Price" value={b.unit ? formatCurrency(b.unit.basePrice, "INR") : "—"} />
                              <Meta label="Booking" value={b.status} />
                              <Meta label="Registration" value={b.scheduledDate ? formatDate(b.scheduledDate) : "—"} />
                            </div>
                            <div className="row" style={{ gap: "0.5rem", marginTop: "0.6rem", flexWrap: "wrap" }}>
                              <Button size="sm" variant="ghost" onClick={() => void generateDoc(b.id, "allotment_letter")}>
                                Allotment Letter
                              </Button>
                              <Button size="sm" variant="ghost" onClick={() => void generateDoc(b.id, "booking_form")}>
                                Booking Form
                              </Button>
                            </div>
                          </div>
                        ))}
                      </div>
                    ))}

                  {tab === "payments" &&
                    (payments.length === 0 ? (
                      <EmptyState title="No payment schedule" description="Installments appear here once a payment plan is set." />
                    ) : (
                      <table className="table">
                        <thead>
                          <tr>
                            <th style={{ textAlign: "left" }}>Installment</th>
                            <th style={{ textAlign: "left" }}>Due</th>
                            <th style={{ textAlign: "right" }}>Demand</th>
                            <th style={{ textAlign: "right" }}>Paid</th>
                            <th style={{ textAlign: "right" }}>Outstanding</th>
                          </tr>
                        </thead>
                        <tbody>
                          {payments.map((p) => (
                            <tr key={p.id}>
                              <td>{p.installmentName}</td>
                              <td>
                                {formatDate(p.dueDate)} {p.isOverdue && <Badge tone="danger">Overdue</Badge>}
                              </td>
                              <td style={{ textAlign: "right" }}>{formatCurrency(p.demandAmount, "INR")}</td>
                              <td style={{ textAlign: "right" }}>{formatCurrency(p.paidAmount, "INR")}</td>
                              <td style={{ textAlign: "right" }}>{formatCurrency(p.outstanding, "INR")}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
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

            <footer className="drawer__footer">
              <Button variant="secondary" onClick={onClose}>
                Close
              </Button>
            </footer>
          </div>
        </div>,
        document.body
      )}

      {docHtml && (
        <Modal open title={docTitle} size="lg" onClose={() => setDocHtml(null)}>
          <DocumentPreview html={docHtml} title={docTitle} onClose={() => setDocHtml(null)} />
        </Modal>
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

function Meta({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div>
      <div className="muted text-xs">{label}</div>
      <div style={{ fontWeight: 600 }}>{value}</div>
    </div>
  );
}
