import { useEffect, useMemo, useState } from "react";
import { Badge, Button, Card, EmptyState, LoadingBlock, Modal, SelectField, useToast } from "../../components";
import { useBookings } from "../../hooks/useBookings";
import { useInventory } from "../../hooks/useInventory";
import { bookingsService } from "../../services/bookings";
import { groupByProject, locateUnit, unitLocationLabel } from "../../utils/unitLocation";
import "./PossessionTrackerPage.css";

const CHECKLIST = [
  "Demand note issued",
  "Final payment received",
  "Registration stamp duty paid",
  "Sub-registrar appointment scheduled",
  "Possession letter issued",
  "Key handover done",
  "Society paperwork filed",
];

type CheckedMap = Record<string, boolean[]>;

function makeBlank(): boolean[] {
  return CHECKLIST.map(() => false);
}

export default function PossessionTrackerPage() {
  const { bookings, loading } = useBookings();
  const { projects } = useInventory();
  const toast = useToast();
  const [checked, setChecked] = useState<CheckedMap>({});
  const [activeId, setActiveId] = useState<string | null>(null);
  const [projectFilter, setProjectFilter] = useState<string>("all");

  // Seed the checklist from each booking's persisted state (once per booking,
  // preserving any in-progress local edits).
  useEffect(() => {
    setChecked((prev) => {
      const next = { ...prev };
      for (const b of bookings) {
        if (next[b.id] === undefined) {
          next[b.id] = CHECKLIST.map((_, i) => b.possessionChecklist?.[i] ?? false);
        }
      }
      return next;
    });
  }, [bookings]);

  function unitLabel(unitId: string): string {
    return unitLocationLabel(locateUnit(projects, unitId), unitId);
  }

  // Confirmed bookings are the ones at the possession/handover stage, grouped by project.
  const groups = useMemo(() => {
    const step4 = bookings.filter((b) => b.status === "confirmed" || b.step === 4);
    return groupByProject(step4, projects);
  }, [bookings, projects]);

  const projectOptions = useMemo(
    () => [
      { value: "all", label: "All projects" },
      ...groups.map((g) => ({ value: g.projectId, label: g.projectName })),
    ],
    [groups],
  );
  // Fall back to "all" when the selected project no longer exists among the current
  // groups, so the page never renders a blank body with a stale filter.
  const effectiveFilter = projectFilter === "all" || groups.some((g) => g.projectId === projectFilter) ? projectFilter : "all";
  const visibleGroups = effectiveFilter === "all" ? groups : groups.filter((g) => g.projectId === effectiveFilter);
  const totalCount = groups.reduce((n, g) => n + g.items.length, 0);

  function getList(id: string): boolean[] {
    return checked[id] ?? makeBlank();
  }

  async function toggle(id: string, idx: number) {
    const current = checked[id] ?? makeBlank();
    const list = current.map((v, i) => (i === idx ? !v : v));
    setChecked((prev) => ({ ...prev, [id]: list }));
    try {
      await bookingsService.savePossessionChecklist(id, list);
    } catch {
      setChecked((prev) => ({ ...prev, [id]: current })); // revert on failure
      toast.error("Couldn't save checklist");
    }
  }

  function doneCount(id: string) {
    return getList(id).filter(Boolean).length;
  }

  if (loading && bookings.length === 0) return <LoadingBlock label="Loading possession tracker…" />;

  return (
    <div className="tracker-page">
      <div className="page-header">
        <div className="page-header__titles">
          <h1>Possession Tracker</h1>
          <p>Post-registration handover checklist for each completed booking, grouped by project.</p>
        </div>
        {groups.length > 0 && (
          <div style={{ minWidth: 220 }}>
            <SelectField
              id="possession-project-filter"
              label="Project"
              value={effectiveFilter}
              onChange={(e) => setProjectFilter(e.target.value)}
              options={projectOptions}
            />
          </div>
        )}
      </div>

      {totalCount === 0 ? (
        <EmptyState
          title="No bookings at registration stage"
          description="Bookings appear here once all four wizard steps are complete."
        />
      ) : (
        <div className="stack" style={{ gap: "1.5rem" }}>
          {visibleGroups.map((group) => (
            <div key={group.projectId}>
              <div className="row row--between" style={{ alignItems: "baseline", marginBottom: "0.5rem" }}>
                <h2 className="text-lg" style={{ margin: 0 }}>{group.projectName}</h2>
                <span className="muted text-sm">{group.items.length} unit{group.items.length === 1 ? "" : "s"}</span>
              </div>
              <div className="tracker-list">
                {group.items.map((booking) => {
                  const done = doneCount(booking.id);
                  const total = CHECKLIST.length;
                  const allDone = done === total;
                  const fillPct = `${Math.round((done / total) * 100)}%`;

                  return (
                    <Card key={booking.id}>
                      <div className="possession-card">
                        <div className="possession-card__info">
                          <div className="possession-card__id">{booking.customer?.contactName ?? `#${booking.id.slice(0, 8)}`}</div>
                          <div className="muted text-xs" style={{ marginTop: 2 }}>
                            #{booking.id.slice(0, 8)} · {unitLabel(booking.unitId)}
                          </div>
                        </div>

                        <div className="possession-card__progress">
                          <div
                            className="possession-progress-bar"
                            style={{ "--fill": fillPct } as React.CSSProperties}
                          >
                            <div className="possession-progress-bar__fill" />
                          </div>
                          <span className="muted text-sm">
                            {done}/{total}
                          </span>
                        </div>

                        <Badge tone={allDone ? "success" : done > 0 ? "warning" : "neutral"}>
                          {allDone ? "Handed over" : done > 0 ? "In progress" : "Pending"}
                        </Badge>

                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => setActiveId(booking.id)}
                        >
                          Checklist
                        </Button>
                      </div>
                    </Card>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}

      {activeId && (
        <Modal open title="Possession Checklist" onClose={() => setActiveId(null)}>
          <div className="possession-checklist">
            {CHECKLIST.map((item, idx) => (
              <label key={idx} className="possession-check-item">
                <input
                  type="checkbox"
                  checked={getList(activeId)[idx]}
                  onChange={() => void toggle(activeId, idx)}
                />
                <span className={getList(activeId)[idx] ? "done-text" : ""}>
                  {item}
                </span>
              </label>
            ))}
          </div>
        </Modal>
      )}
    </div>
  );
}
