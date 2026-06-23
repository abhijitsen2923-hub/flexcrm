import { useMemo, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Badge, Button, Modal, SelectField, TextField, useToast } from "../../../components";
import type { SiteVisit, SiteVisitFeedback } from "../../../types/realestate";
import { formatDateTime } from "../../../utils/format";
import type { CreateSiteVisitPayload } from "../../../services/site-visits";
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

const DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

interface Props {
  visits: SiteVisit[];
  onSchedule: (payload: CreateSiteVisitPayload) => Promise<SiteVisit>;
  onUpdateFeedback: (id: string, patch: { attended?: boolean; feedback?: SiteVisitFeedback | null; notes?: string }) => Promise<SiteVisit>;
}

interface SlotEvent {
  visit: SiteVisit;
  day: Date;
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
  const [weekStart, setWeekStart] = useState(() => startOfWeek(new Date()));
  const [scheduleOpen, setScheduleOpen] = useState(false);
  const [form, setForm] = useState<ScheduleForm>(BLANK);
  const [saving, setSaving] = useState(false);
  const [selectedVisit, setSelectedVisit] = useState<SiteVisit | null>(null);

  const days = useMemo(
    () => Array.from({ length: 7 }, (_, i) => addDays(weekStart, i)),
    [weekStart]
  );

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
        leadId: form.leadId,
        projectId: form.projectId,
        scheduledAt: form.scheduledAt,
        assignedToId: form.assignedToId || null,
        notes: form.notes || null,
      });
      toast.success("Site visit scheduled");
      setScheduleOpen(false);
      setForm(BLANK);
    } catch {
      toast.error("Failed to schedule site visit");
    } finally {
      setSaving(false);
    }
  };

  const handleFeedback = async (feedback: SiteVisitFeedback) => {
    if (!selectedVisit) return;
    setSaving(true);
    try {
      await onUpdateFeedback(selectedVisit.id, { feedback });
      toast.success("Feedback recorded");
      setSelectedVisit(null);
    } catch {
      toast.error("Failed to save feedback");
    } finally {
      setSaving(false);
    }
  };

  const handleMarkAttended = async (attended: boolean) => {
    if (!selectedVisit) return;
    setSaving(true);
    try {
      await onUpdateFeedback(selectedVisit.id, { attended });
      toast.success(attended ? "Marked as attended" : "Marked as absent");
      setSelectedVisit(null);
    } catch {
      toast.error("Failed to update attendance");
    } finally {
      setSaving(false);
    }
  };

  const today = new Date();

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
        <Button variant="primary" size="sm" onClick={() => setScheduleOpen(true)}>
          + Schedule Visit
        </Button>
      </div>

      {/* Grid */}
      <div className="sv-grid" role="grid">
        {/* Day headers */}
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

        {/* Cells */}
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
                  ].filter(Boolean).join(" ")}
                  onClick={() => setSelectedVisit(v)}
                  title={formatDateTime(v.scheduledAt)}
                >
                  <span className="sv-event__time">
                    {new Date(v.scheduledAt).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}
                  </span>
                  <span className="sv-event__lead">Lead {v.leadId.slice(0, 6)}</span>
                  {v.feedback && (
                    <Badge tone={FEEDBACK_TONE[v.feedback]}>{FEEDBACK_LABELS[v.feedback]}</Badge>
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
          <TextField label="Lead ID" value={form.leadId} onChange={(e) => setForm({ ...form, leadId: e.target.value })} />
          <TextField label="Project ID" value={form.projectId} onChange={(e) => setForm({ ...form, projectId: e.target.value })} />
          <TextField label="Date & Time" type="datetime-local" value={form.scheduledAt} onChange={(e) => setForm({ ...form, scheduledAt: e.target.value })} />
          <TextField label="Assign to (User ID)" value={form.assignedToId} onChange={(e) => setForm({ ...form, assignedToId: e.target.value })} />
          <TextField label="Notes" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
          <div className="sv-form__footer">
            <Button variant="secondary" onClick={() => setScheduleOpen(false)}>Cancel</Button>
            <Button variant="primary" loading={saving} disabled={!form.leadId || !form.scheduledAt} onClick={handleSchedule}>
              Schedule
            </Button>
          </div>
        </div>
      </Modal>

      {/* Visit detail / feedback modal */}
      {selectedVisit && (
        <Modal open title="Site Visit" onClose={() => setSelectedVisit(null)}>
          <div className="sv-detail">
            <p><strong>Lead:</strong> {selectedVisit.leadId}</p>
            <p><strong>Scheduled:</strong> {formatDateTime(selectedVisit.scheduledAt)}</p>
            <p><strong>Attended:</strong> {selectedVisit.attended === null ? "Not recorded" : selectedVisit.attended ? "Yes" : "No"}</p>
            {selectedVisit.feedback && (
              <p><strong>Feedback:</strong> <Badge tone={FEEDBACK_TONE[selectedVisit.feedback]}>{FEEDBACK_LABELS[selectedVisit.feedback]}</Badge></p>
            )}

            <div className="sv-detail__actions">
              <span className="sv-detail__label">Mark attendance:</span>
              <Button size="sm" variant="secondary" loading={saving} onClick={() => handleMarkAttended(true)}>Attended</Button>
              <Button size="sm" variant="secondary" loading={saving} onClick={() => handleMarkAttended(false)}>Absent</Button>
            </div>

            <div className="sv-detail__actions">
              <span className="sv-detail__label">Set feedback:</span>
              {(["hot", "warm", "cold"] as SiteVisitFeedback[]).map((f) => (
                <Button
                  key={f}
                  size="sm"
                  variant={selectedVisit.feedback === f ? "primary" : "secondary"}
                  loading={saving}
                  onClick={() => handleFeedback(f)}
                >
                  {FEEDBACK_LABELS[f]}
                </Button>
              ))}
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
