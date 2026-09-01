import { useState } from "react";
import { CalendarDays, List } from "lucide-react";
import { Card, DataTable, EmptyState } from "../../components";
import type { DataTableColumn } from "../../components";
import { useSiteVisits } from "../../hooks/useSiteVisits";
import { LoadingBlock } from "../../components/ui/Spinner";
import { SiteVisitCalendar } from "./components/SiteVisitCalendar";
import type { SiteVisit } from "../../types/realestate";
import { formatDateTime } from "../../utils/format";
import "./SiteVisitsPage.css";

const COLUMNS: DataTableColumn<SiteVisit>[] = [
  {
    key: "leadId",
    header: "Lead",
    render: (v) =>
      v.lead
        ? `${v.lead.contactName}${v.lead.leadNumber ? ` (#${v.lead.leadNumber})` : ""}`
        : v.leadId
          ? v.leadId.slice(0, 8) + "…"
          : "—",
  },
  { key: "projectId", header: "Site", render: (v) => v.project?.name ?? "—" },
  { key: "scheduledAt", header: "Scheduled", render: (v) => formatDateTime(v.scheduledAt) },
  { key: "status", header: "Status", render: (v) => (v.status === "cancelled" ? "Cancelled" : "Scheduled") },
  {
    key: "attended",
    header: "Attended",
    render: (v) =>
      v.attended === null ? "—" : v.attended ? "Yes" : "No",
  },
  {
    key: "feedback",
    header: "Feedback",
    render: (v) =>
      v.feedback
        ? { hot: "Hot 🔥", warm: "Warm", cold: "Cold ❄️" }[v.feedback]
        : "—",
  },
];

type ViewMode = "calendar" | "list";

export default function SiteVisitsPage() {
  const { visits, loading, schedule, updateFeedback } = useSiteVisits();
  const [view, setView] = useState<ViewMode>("calendar");

  if (loading && visits.length === 0) return <LoadingBlock label="Loading site visits…" />;

  return (
    <div className="sv-page">
      <div className="page-header">
        <h1 className="page-title">Site Visits</h1>
        <div className="view-toggle" role="group" aria-label="View mode">
          <button
            className={["view-toggle__btn", view === "calendar" ? "is-active" : ""].filter(Boolean).join(" ")}
            onClick={() => setView("calendar")}
            aria-label="Calendar view"
          >
            <CalendarDays size={14} /> Calendar
          </button>
          <button
            className={["view-toggle__btn", view === "list" ? "is-active" : ""].filter(Boolean).join(" ")}
            onClick={() => setView("list")}
            aria-label="List view"
          >
            <List size={14} /> List
          </button>
        </div>
      </div>

      {view === "calendar" ? (
        <SiteVisitCalendar
          visits={visits}
          onSchedule={schedule}
          onUpdateFeedback={updateFeedback}
        />
      ) : visits.length === 0 ? (
        <EmptyState
          icon={<CalendarDays size={32} />}
          title="No site visits scheduled"
          description="Schedule a site visit from the calendar view."
        />
      ) : (
        <Card>
          <DataTable columns={COLUMNS} rows={visits} rowKey={(v) => v.id} />
        </Card>
      )}
    </div>
  );
}
