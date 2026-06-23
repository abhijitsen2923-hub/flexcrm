import { useState } from "react";
import { Badge, Button, Card, EmptyState, LoadingBlock, Modal } from "../../components";
import { useBookings } from "../../hooks/useBookings";
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
  const [checked, setChecked] = useState<CheckedMap>({});
  const [activeId, setActiveId] = useState<string | null>(null);

  const step4 = bookings.filter((b) => b.step === 4);

  function getList(id: string): boolean[] {
    return checked[id] ?? makeBlank();
  }

  function toggle(id: string, idx: number) {
    setChecked((prev) => {
      const list = prev[id] ?? makeBlank();
      return { ...prev, [id]: list.map((v, i) => (i === idx ? !v : v)) };
    });
  }

  function doneCount(id: string) {
    return getList(id).filter(Boolean).length;
  }

  if (loading) return <LoadingBlock label="Loading possession tracker…" />;

  return (
    <div className="tracker-page">
      <div className="page-header">
        <div className="page-header__titles">
          <h1>Possession Tracker</h1>
          <p>Post-registration handover checklist for each completed booking.</p>
        </div>
      </div>

      {step4.length === 0 ? (
        <EmptyState
          title="No bookings at registration stage"
          description="Bookings appear here once all four wizard steps are complete."
        />
      ) : (
        <div className="tracker-list">
          {step4.map((booking) => {
            const done = doneCount(booking.id);
            const total = CHECKLIST.length;
            const allDone = done === total;
            const fillPct = `${Math.round((done / total) * 100)}%`;

            return (
              <Card key={booking.id}>
                <div className="possession-card">
                  <div className="possession-card__info">
                    <div className="possession-card__id">#{booking.id.slice(0, 8)}</div>
                    <div className="muted text-xs" style={{ marginTop: 2 }}>
                      Unit {booking.unitId.slice(0, 8)}
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
      )}

      {activeId && (
        <Modal open title="Possession Checklist" onClose={() => setActiveId(null)}>
          <div className="possession-checklist">
            {CHECKLIST.map((item, idx) => (
              <label key={idx} className="possession-check-item">
                <input
                  type="checkbox"
                  checked={getList(activeId)[idx]}
                  onChange={() => toggle(activeId, idx)}
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
