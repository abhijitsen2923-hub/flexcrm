import { useMemo, useState } from "react";
import { Badge, Card, EmptyState, LoadingBlock, SelectField } from "../../components";
import { useBookings } from "../../hooks/useBookings";
import { useInventory } from "../../hooks/useInventory";
import { groupByProject, locateUnit, unitLocationLabel } from "../../utils/unitLocation";
import "./RegistrationTrackerPage.css";

const STEPS = [
  "Unit Reserved",
  "KYC & Customer",
  "Pricing Confirmed",
  "Docs & Schedule",
];

export default function RegistrationTrackerPage() {
  const { bookings, loading } = useBookings();
  const { projects } = useInventory();
  const [projectFilter, setProjectFilter] = useState<string>("all");

  function unitLabel(unitId: string): string {
    return unitLocationLabel(locateUnit(projects, unitId), unitId);
  }

  const groups = useMemo(() => groupByProject(bookings, projects), [bookings, projects]);
  const projectOptions = useMemo(
    () => [
      { value: "all", label: "All projects" },
      ...groups.map((g) => ({ value: g.projectId, label: g.projectName })),
    ],
    [groups],
  );
  // Fall back to "all" when the selected project no longer exists among the current
  // groups (e.g. its bookings became non-locatable after an inventory refresh), so
  // the page never renders a blank body with a stale filter.
  const effectiveFilter = projectFilter === "all" || groups.some((g) => g.projectId === projectFilter) ? projectFilter : "all";
  const visibleGroups = effectiveFilter === "all" ? groups : groups.filter((g) => g.projectId === effectiveFilter);

  if (loading) return <LoadingBlock label="Loading registration tracker…" />;

  return (
    <div className="tracker-page">
      <div className="page-header">
        <div className="page-header__titles">
          <h1>Registration Tracker</h1>
          <p>Booking progress through the four-step registration pipeline, grouped by project.</p>
        </div>
        {groups.length > 0 && (
          <div style={{ minWidth: 220 }}>
            <SelectField
              id="registration-project-filter"
              label="Project"
              value={effectiveFilter}
              onChange={(e) => setProjectFilter(e.target.value)}
              options={projectOptions}
            />
          </div>
        )}
      </div>

      {bookings.length === 0 ? (
        <EmptyState
          title="No bookings yet"
          description="Create a booking from the Inventory screen to start tracking."
        />
      ) : (
        <div className="stack" style={{ gap: "1.5rem" }}>
          {visibleGroups.map((group) => (
            <div key={group.projectId}>
              <div className="row row--between" style={{ alignItems: "baseline", marginBottom: "0.5rem" }}>
                <h2 className="text-lg" style={{ margin: 0 }}>{group.projectName}</h2>
                <span className="muted text-sm">{group.items.length} booking{group.items.length === 1 ? "" : "s"}</span>
              </div>
              <div className="tracker-list">
                {group.items.map((booking) => {
                  const isConfirmed = booking.status === "confirmed";
                  return (
                    <Card key={booking.id}>
                      <div className="tracker-card">
                        <div className="tracker-card__info">
                          <div className="tracker-card__id">{booking.customer?.contactName ?? `#${booking.id.slice(0, 8)}`}</div>
                          <div className="muted text-xs" style={{ marginTop: 2 }}>
                            #{booking.id.slice(0, 8)} · {unitLabel(booking.unitId)}
                          </div>
                          <div style={{ marginTop: 4 }}>
                            <Badge tone={isConfirmed ? "success" : booking.status === "cancelled" ? "neutral" : "warning"}>
                              {booking.status.charAt(0).toUpperCase() + booking.status.slice(1)}
                            </Badge>
                          </div>
                          {booking.scheduledDate && (
                            <div className="muted text-xs" style={{ marginTop: 4 }}>
                              Registration: {new Date(booking.scheduledDate).toLocaleDateString()}
                            </div>
                          )}
                        </div>

                        <div className="tracker-steps">
                          {STEPS.map((label, i) => {
                            const stepNum = i + 1;
                            // A confirmed booking has completed every step.
                            const done = isConfirmed || booking.step > stepNum;
                            const active = !isConfirmed && booking.step === stepNum;
                            return (
                              <div
                                key={i}
                                className={[
                                  "tracker-step",
                                  done ? "tracker-step--done" : "",
                                  active ? "tracker-step--active" : "",
                                ].filter(Boolean).join(" ")}
                              >
                                <div className="tracker-step__dot">{done ? "✓" : stepNum}</div>
                                {i < STEPS.length - 1 && (
                                  <div
                                    className={[
                                      "tracker-step__line",
                                      done ? "tracker-step__line--done" : "",
                                    ].filter(Boolean).join(" ")}
                                  />
                                )}
                                <div className="tracker-step__label">{label}</div>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    </Card>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
