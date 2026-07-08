import { Badge, Card, EmptyState, LoadingBlock } from "../../components";
import { useBookings } from "../../hooks/useBookings";
import { useInventory } from "../../hooks/useInventory";
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

  function unitLabel(unitId: string): string {
    for (const p of projects) {
      for (const t of p.towers) {
        const u = t.units.find((x) => x.id === unitId);
        if (u) return `${p.name} · ${t.name} · ${u.unitNumber}`;
      }
    }
    return `Unit ${unitId.slice(0, 8)}`;
  }

  if (loading) return <LoadingBlock label="Loading registration tracker…" />;

  return (
    <div className="tracker-page">
      <div className="page-header">
        <div className="page-header__titles">
          <h1>Registration Tracker</h1>
          <p>End-to-end booking progress through the four-step registration pipeline.</p>
        </div>
      </div>

      {bookings.length === 0 ? (
        <EmptyState
          title="No bookings yet"
          description="Create a booking from the Inventory screen to start tracking."
        />
      ) : (
        <div className="tracker-list">
          {bookings.map((booking) => {
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
      )}
    </div>
  );
}
