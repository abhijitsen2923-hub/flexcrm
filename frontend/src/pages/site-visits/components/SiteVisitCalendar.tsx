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

// Monday-based week start (matches the Mon–Sun column order).
function startOfWeek(d: Date): Date {
  const day = d.getDay();
  const diff = d.getDate() - day + (day === 0 ? -6 : 1);
  return new Date(d.getFullYear(), d.getMonth(), diff);
}

function addDays(d: Date, n: number): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
}

function addMonths(d: Date, n: number): Date {
  return new Date(d.getFullYear(), d.getMonth() + n, 1);
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
// How many events a month cell shows before collapsing into "+N more".
const MONTH_CELL_EVENT_CAP = 3;

type ViewMode = "week" | "month";

interface Props {
  visits: SiteVisit[];
  onSchedule: (payload: CreateSiteVisitPayload) => Promise<SiteVisit>;
  onUpdateFeedback: (id: string, patch: UpdateSiteVisitPayload) => Promise<SiteVisit>;
}

interface ScheduleForm {
  leadId: string;
  // A single visit can cover MULTIPLE projects on one day — one SiteVisit is
  // created per selected project so each has its own attendance/feedback.
  projectIds: string[];
  assignedToId: string;
  scheduledAt: string;
  notes: string;
}

const BLANK: ScheduleForm = { leadId: "", projectIds: [], assignedToId: "", scheduledAt: "", notes: "" };

export function SiteVisitCalendar({ visits, onSchedule, onUpdateFeedback }: Props) {
  const toast = useToast();
  const { projects } = useInventory();
  const [users, setUsers] = useState<User[]>([]);
  const [leads, setLeads] = useState<Lead[]>([]);
  const [viewMode, setViewMode] = useState<ViewMode>("month");
  // Any day inside the currently-viewed week/month; navigation moves it.
  const [cursor, setCursor] = useState(() => new Date());
  const [scheduleOpen, setScheduleOpen] = useState(false);
  const [form, setForm] = useState<ScheduleForm>(BLANK);
  const [saving, setSaving] = useState(false);
  const [selectedVisit, setSelectedVisit] = useState<SiteVisit | null>(null);
  const [rescheduleAt, setRescheduleAt] = useState("");

  useEffect(() => {
    void usersService.list({ page_size: 100 }).then((r) => setUsers(r.items)).catch(() => {});
    void leadsService.list({ page_size: 100 }).then((r) => setLeads(r.items)).catch(() => {});
  }, []);

  // Week = 7 days from Monday; month = a full 6-week grid so every month lays out
  // consistently (leading/trailing days spill from the adjacent months).
  const days = useMemo(() => {
    if (viewMode === "week") {
      const ws = startOfWeek(cursor);
      return Array.from({ length: 7 }, (_, i) => addDays(ws, i));
    }
    const gridStart = startOfWeek(new Date(cursor.getFullYear(), cursor.getMonth(), 1));
    return Array.from({ length: 42 }, (_, i) => addDays(gridStart, i));
  }, [viewMode, cursor]);

  const visitsByDay = useMemo(() => {
    const map = new Map<string, SiteVisit[]>();
    for (const v of visits) {
      const key = new Date(v.scheduledAt).toDateString();
      const existing = map.get(key) ?? [];
      existing.push(v);
      map.set(key, existing);
    }
    // Keep each day's visits in chronological order.
    for (const list of map.values()) {
      list.sort((a, b) => new Date(a.scheduledAt).getTime() - new Date(b.scheduledAt).getTime());
    }
    return map;
  }, [visits]);

  const goPrev = () => setCursor((c) => (viewMode === "week" ? addDays(c, -7) : addMonths(c, -1)));
  const goNext = () => setCursor((c) => (viewMode === "week" ? addDays(c, 7) : addMonths(c, 1)));

  const rangeLabel = useMemo(() => {
    if (viewMode === "week") {
      const ws = startOfWeek(cursor);
      return `${ws.toLocaleDateString(undefined, { month: "short", day: "numeric" })} – ${addDays(ws, 6).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}`;
    }
    return cursor.toLocaleDateString(undefined, { month: "long", year: "numeric" });
  }, [viewMode, cursor]);

  const toggleProject = (id: string) =>
    setForm((f) => ({
      ...f,
      projectIds: f.projectIds.includes(id)
        ? f.projectIds.filter((p) => p !== id)
        : [...f.projectIds, id],
    }));

  const handleSchedule = async () => {
    if (form.projectIds.length === 0 || !form.scheduledAt) return;
    setSaving(true);
    let ok = 0;
    const errors: string[] = [];
    // One SiteVisit per selected project (same lead/time/assignee/notes).
    for (const projectId of form.projectIds) {
      try {
        await onSchedule({
          leadId: form.leadId || null,
          projectId,
          scheduledAt: form.scheduledAt,
          assignedToId: form.assignedToId || null,
          notes: form.notes || null,
        });
        ok += 1;
      } catch (e) {
        errors.push(extractErrorMessage(e));
      }
    }
    if (ok > 0) {
      toast.success(`Scheduled ${ok} site visit${ok === 1 ? "" : "s"}`);
      setScheduleOpen(false);
      setForm(BLANK);
    }
    if (errors.length > 0) {
      toast.error(`${errors.length} visit${errors.length === 1 ? "" : "s"} couldn't be scheduled`, errors[0]);
    }
    setSaving(false);
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

  const leadOptions = [
    { value: "", label: "— No lead —" },
    ...leads.map((l) => ({ value: l.id, label: `${l.contact_name} (#${l.lead_number})` })),
  ];
  const userOptions = [
    { value: "", label: "— Unassigned —" },
    ...users.map((u) => ({ value: u.id, label: `${u.first_name} ${u.last_name}` })),
  ];

  const renderEvent = (v: SiteVisit) => (
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
      title={`${formatDateTime(v.scheduledAt)}${v.project ? ` · ${v.project.name}` : ""}`}
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
  );

  return (
    <div className="sv-calendar">
      {/* Toolbar */}
      <div className="sv-calendar__toolbar">
        <div className="sv-calendar__nav">
          <button className="sv-nav-btn" onClick={goPrev} aria-label={viewMode === "week" ? "Previous week" : "Previous month"}><ChevronLeft size={16} /></button>
          <span className="sv-calendar__range">{rangeLabel}</span>
          <button className="sv-nav-btn" onClick={goNext} aria-label={viewMode === "week" ? "Next week" : "Next month"}><ChevronRight size={16} /></button>
          <button className="sv-nav-btn sv-nav-btn--today" onClick={() => setCursor(new Date())}>Today</button>
        </div>
        <div className="sv-calendar__right">
          <div className="sv-viewtoggle" role="group" aria-label="Calendar view">
            <button
              className={["sv-viewtoggle__btn", viewMode === "week" ? "is-active" : ""].filter(Boolean).join(" ")}
              onClick={() => setViewMode("week")}
            >
              Week
            </button>
            <button
              className={["sv-viewtoggle__btn", viewMode === "month" ? "is-active" : ""].filter(Boolean).join(" ")}
              onClick={() => setViewMode("month")}
            >
              Month
            </button>
          </div>
          <Button variant="primary" size="sm" onClick={() => { setForm(BLANK); setScheduleOpen(true); }}>
            + Schedule Visit
          </Button>
        </div>
      </div>

      {/* Grid — a 7-column day-name header, then week (7) or month (42) cells. */}
      <div className={`sv-grid sv-grid--${viewMode}`} role="grid">
        {DAY_LABELS.map((label) => (
          <div key={label} className="sv-grid__dowhead" role="columnheader">{label}</div>
        ))}

        {days.map((day, i) => {
          const dayVisits = visitsByDay.get(day.toDateString()) ?? [];
          const isToday = sameDay(day, today);
          const inMonth = viewMode === "week" || day.getMonth() === cursor.getMonth();
          const shown = viewMode === "month" ? dayVisits.slice(0, MONTH_CELL_EVENT_CAP) : dayVisits;
          const extra = dayVisits.length - shown.length;
          return (
            <div
              key={i}
              className={[
                "sv-grid__cell",
                isToday ? "sv-grid__cell--today" : "",
                !inMonth ? "sv-grid__cell--muted" : "",
              ].filter(Boolean).join(" ")}
              role="gridcell"
            >
              <div className="sv-grid__cellhead">
                <span className="sv-grid__daynum">{day.getDate()}</span>
              </div>
              {shown.map(renderEvent)}
              {extra > 0 && (
                <button
                  className="sv-more"
                  onClick={() => { setCursor(day); setViewMode("week"); }}
                  title="Show this week"
                >
                  +{extra} more
                </button>
              )}
            </div>
          );
        })}
      </div>

      {/* Schedule modal */}
      <Modal open={scheduleOpen} title="Schedule Site Visit" onClose={() => setScheduleOpen(false)}>
        <div className="sv-form">
          <div className="sv-field">
            <span className="sv-field__label">Sites (projects) — select one or more</span>
            {projects.length === 0 ? (
              <p className="muted text-sm">No projects yet — add one in Inventory first.</p>
            ) : (
              <div className="sv-checklist">
                {projects.map((p) => (
                  <label key={p.id} className="sv-check">
                    <input
                      type="checkbox"
                      checked={form.projectIds.includes(p.id)}
                      onChange={() => toggleProject(p.id)}
                    />
                    <span>{p.name}</span>
                  </label>
                ))}
              </div>
            )}
            {form.projectIds.length > 1 && (
              <span className="muted text-xs">
                {form.projectIds.length} site visits will be created for this day (one per project).
              </span>
            )}
          </div>
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
            <Button variant="primary" loading={saving} disabled={form.projectIds.length === 0 || !form.scheduledAt} onClick={handleSchedule}>
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
