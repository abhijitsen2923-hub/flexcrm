import { useEffect, useMemo, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Badge, Button, Modal, SelectField, TextField, useToast } from "../../../components";
import type { SiteVisit, SiteVisitFeedback } from "../../../types/realestate";
import type { Lead, User } from "../../../types";
import { formatDateTime } from "../../../utils/format";
import { useInventory } from "../../../hooks/useInventory";
import { usersService } from "../../../services/users";
import { leadsService } from "../../../services/leads";
import type { CreateSiteVisitPayload, UpdateSiteVisitPayload } from "../../../services/site-visits";
import { extractErrorMessage } from "../../../utils/errors";
import "./SiteVisitCalendar.css";

const FEEDBACK_TONE: Record<SiteVisitFeedback, "danger" | "warning" | "success"> = {
  hot: "danger",
  warm: "warning",
  cold: "success",
};

const FEEDBACK_LABELS: Record<SiteVisitFeedback, string> = {
  hot: "Hot 🔥",
  warm: "Warm",
  cold: "Cold ❄️",
};

function startOfWeek(d: Date): Date {
  const day = d.getDay();
  const diff = d.getDate() - day + (day === 0 ? -6 : 1);
  return new Date(d.getFullYear(), d.getMonth(), diff);
}

function addDays(d: Date, n: number): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
}

function sameDay(a: Date, b: Date): boolean {
  return a.toDateString() === b.toDateString();
}

// ISO string → value for <input type="datetime-local"> (local time, no seconds).
function toLocalInput(iso: string): string {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

const DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

interface Props {
  visits: SiteVisit[];
  onSchedule: (payload: CreateSiteVisitPayload) => Promise<SiteVisit>;
  onUpdateFeedback: (id: string, patch: UpdateSiteVisitPayload) => Promise<SiteVisit>;
}

interface ScheduleForm {
  leadId: string;
  projectId: string;
  assignedToId: string;
  scheduledAt: string;
  notes: string;
}

const BLANK: ScheduleForm = { leadId: "", projectId: "", assignedToId: "", scheduledAt: "", notes: "" };

export function SiteVisitCalendar({ visits, onSchedule, onUpdateFeedback }: Props) {
  const toast = useToast();
  const { projects } = useInventory();
  const [users, setUsers] = useState<User[]>([]);
  const [leads, setLeads] = useState<Lead[]>([]);
  const [weekStart, setWeekStart] = useState(() => startOfWeek(new Date()));
  const [scheduleOpen, setScheduleOpen] = useState(false);
  const [form, setForm] = useState<ScheduleForm>(BLANK);
  const [saving, setSaving] = useState(false);
  const [selectedVisit, setSelectedVisit] = useState<SiteVisit | null>(null);
  const [rescheduleAt, setRescheduleAt] = useState("");

  useEffect(() => {
    void usersService.list({ page_size: 100 }).then((r) => setUsers(r.items)).catch(() => {});
    void leadsService.list({ page_size: 100 }).then((r) => setLeads(r.items)).catch(() => {});
  }, []);

  const days = useMemo(() => Array.from({ length: 7 }, (_, i) => addDays(weekStart, i)), [weekStart]);

  const visitsByDay = useMemo(() => {
    const map = new Map<string, SiteVisit[]>();
    for (const v of visits) {
      const key = new Date(v.scheduledAt).toDateString();
      const existing = map.get(key) ?? [];
      existing.push(v);
      map.set(key, existing);
    }
    return map;
  }, [visits]);

  const prevWeek = () => setWeekStart((w) => addDays(w, -7));
  const nextWeek = () => setWeekStart((w) => addDays(w, 7));

  const handleSchedule = async () => {
    setSaving(true);
    try {
      await onSchedule({
        leadId: form.leadId || null,
        projectId: form.projectId,
        scheduledAt: form.scheduledAt,
        assignedToId: form.assignedToId || null,
        notes: form.notes || null,
      });
      toast.success("Site visit scheduled");
      setScheduleOpen(false);
      setForm(BLANK);
    } catch (e) {
      toast.error("Failed to schedule site visit", extractErrorMessage(e));
    } finally {
      setSaving(false);
    }
  };

  const patchVisit = async (patch: UpdateSiteVisitPayload, successMsg: string) => {
    if (!selectedVisit) return;
    setSaving(true);
    try {
      await onUpdateFeedback(selectedVisit.id, patch);
      toast.success(successMsg);
      setSelectedVisit(null);
    } catch (e) {
      toast.error("Update failed", extractErrorMessage(e));
    } finally {
      setSaving(false);
    }
  };

  const today = new Date();

  const projectOptions = [
    { value: "", label: "— Select site —" },
    ...projects.map((p) => ({ value: p.id, label: p.name })),
  ];
  const leadOptions = [
    { value: "", label: "— No lead —" },
    ...leads.map((l) => ({ value: l.id, label: `${l.contact_name} (#${l.lead_number})` })),
  ];
  const userOptions = [
    { value: "", label: "— Unassigned —" },
    ...users.map((u) => ({ value: u.id, label: `${u.first_name} ${u.last_name}` })),
  ];

  return (
    <div className="sv-calendar">
      {/* Toolbar */}
      <div className="sv-calendar__toolbar">
        <div className="sv-calendar__nav">
          <button className="sv-nav-btn" onClick={prevWeek} aria-label="Previous week"><ChevronLeft size={16} /></button>
          <span className="sv-calendar__range">
            {weekStart.toLocaleDateString(undefined, { month: "short", day: "numeric" })} –{" "}
            {addDays(weekStart, 6).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}
          </span>
          <button className="sv-nav-btn" onClick={nextWeek} aria-label="Next week"><ChevronRight size={16} /></button>
        </div>
        <Button variant="primary" size="sm" onClick={() => { setForm(BLANK); setScheduleOpen(true); }}>
          + Schedule Visit
        </Button>
      </div>

      {/* Grid */}
      <div className="sv-grid" role="grid">
        {days.map((day, i) => (
          <div
            key={i}
            className={["sv-grid__header", sameDay(day, today) ? "sv-grid__header--today" : ""].filter(Boolean).join(" ")}
            role="columnheader"
          >
            <span className="sv-grid__dayname">{DAY_LABELS[i]}</span>
            <span className="sv-grid__daynum">{day.getDate()}</span>
          </div>
        ))}

        {days.map((day, i) => {
          const dayVisits = visitsByDay.get(day.toDateString()) ?? [];
          return (
            <div
              key={i}
              className={["sv-grid__cell", sameDay(day, today) ? "sv-grid__cell--today" : ""].filter(Boolean).join(" ")}
              role="gridcell"
            >
              {dayVisits.map((v) => (
                <button
                  key={v.id}
                  className={[
                    "sv-event",
                    v.feedback ? `sv-event--${v.feedback}` : "",
                    v.attended === false ? "sv-event--absent" : "",
                    v.status === "cancelled" ? "sv-event--absent" : "",
                  ].filter(Boolean).join(" ")}
                  style={v.status === "cancelled" ? { opacity: 0.55, textDecoration: "line-through" } : undefined}
                  onClick={() => { setSelectedVisit(v); setRescheduleAt(toLocalInput(v.scheduledAt)); }}
                  title={formatDateTime(v.scheduledAt)}
                >
                  <span className="sv-event__time">
                    {new Date(v.scheduledAt).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}
                  </span>
                  <span className="sv-event__lead">{v.lead?.contactName ?? "Site visit"}</span>
                  {v.project && <span className="sv-event__project muted text-xs">{v.project.name}</span>}
                  {v.status === "cancelled" ? (
                    <Badge tone="neutral">Cancelled</Badge>
                  ) : (
                    v.feedback && <Badge tone={FEEDBACK_TONE[v.feedback]}>{FEEDBACK_LABELS[v.feedback]}</Badge>
                  )}
                </button>
              ))}
            </div>
          );
        })}
      </div>

      {/* Schedule modal */}
      <Modal open={scheduleOpen} title="Schedule Site Visit" onClose={() => setScheduleOpen(false)}>
        <div className="sv-form">
          <SelectField
            id="sv-project"
            label="Site (project)"
            value={form.projectId}
            onChange={(e) => setForm({ ...form, projectId: e.target.value })}
            options={projectOptions}
          />
          <SelectField
            id="sv-lead"
            label="Lead (optional)"
            value={form.leadId}
            onChange={(e) => setForm({ ...form, leadId: e.target.value })}
            options={leadOptions}
          />
          <TextField label="Date & Time" type="datetime-local" value={form.scheduledAt} onChange={(e) => setForm({ ...form, scheduledAt: e.target.value })} />
          <SelectField
            id="sv-assignee"
            label="Assign to"
            value={form.assignedToId}
            onChange={(e) => setForm({ ...form, assignedToId: e.target.value })}
            options={userOptions}
          />
          <TextField label="Notes" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
          <div className="sv-form__footer">
            <Button variant="secondary" onClick={() => setScheduleOpen(false)}>Cancel</Button>
            <Button variant="primary" loading={saving} disabled={!form.projectId || !form.scheduledAt} onClick={handleSchedule}>
              Schedule
            </Button>
          </div>
        </div>
      </Modal>

      {/* Visit detail modal */}
      {selectedVisit && (
        <Modal open title="Site Visit" onClose={() => setSelectedVisit(null)}>
          <div className="sv-detail">
            <p><strong>Lead:</strong> {selectedVisit.lead?.contactName ?? "—"}
              {selectedVisit.lead?.leadNumber ? ` (#${selectedVisit.lead.leadNumber})` : ""}
              {selectedVisit.lead?.contactPhone ? ` · ${selectedVisit.lead.contactPhone}` : ""}</p>
            <p><strong>Site:</strong> {selectedVisit.project?.name ?? "—"}</p>
            <p><strong>Scheduled:</strong> {formatDateTime(selectedVisit.scheduledAt)}</p>
            <p><strong>Status:</strong>{" "}
              <Badge tone={selectedVisit.status === "cancelled" ? "neutral" : "info"}>
                {selectedVisit.status}
              </Badge>
            </p>
            <p><strong>Attended:</strong> {selectedVisit.attended === null ? "Not recorded" : selectedVisit.attended ? "Yes" : "No"}</p>
            {selectedVisit.feedback && (
              <p><strong>Feedback:</strong> <Badge tone={FEEDBACK_TONE[selectedVisit.feedback]}>{FEEDBACK_LABELS[selectedVisit.feedback]}</Badge></p>
            )}

            {selectedVisit.status !== "cancelled" && (
              <>
                <div className="sv-detail__actions">
                  <span className="sv-detail__label">Mark attendance:</span>
                  <Button size="sm" variant="secondary" loading={saving} onClick={() => void patchVisit({ attended: true }, "Marked as attended")}>Attended</Button>
                  <Button size="sm" variant="secondary" loading={saving} onClick={() => void patchVisit({ attended: false }, "Marked as absent")}>Absent</Button>
                </div>

                <div className="sv-detail__actions">
                  <span className="sv-detail__label">Set feedback:</span>
                  {(["hot", "warm", "cold"] as SiteVisitFeedback[]).map((f) => (
                    <Button
                      key={f}
                      size="sm"
                      variant={selectedVisit.feedback === f ? "primary" : "secondary"}
                      loading={saving}
                      onClick={() => void patchVisit({ feedback: f }, "Feedback recorded")}
                    >
                      {FEEDBACK_LABELS[f]}
                    </Button>
                  ))}
                </div>

                <div className="sv-detail__actions" style={{ alignItems: "flex-end" }}>
                  <TextField
                    label="Reschedule"
                    type="datetime-local"
                    value={rescheduleAt}
                    onChange={(e) => setRescheduleAt(e.target.value)}
                  />
                  <Button size="sm" variant="secondary" loading={saving} disabled={!rescheduleAt} onClick={() => void patchVisit({ scheduledAt: rescheduleAt }, "Rescheduled")}>
                    Save time
                  </Button>
                  <Button size="sm" variant="danger" loading={saving} onClick={() => void patchVisit({ status: "cancelled" }, "Visit cancelled")}>
                    Cancel visit
                  </Button>
                </div>
              </>
            )}
          </div>
        </Modal>
      )}
    </div>
  );
}
