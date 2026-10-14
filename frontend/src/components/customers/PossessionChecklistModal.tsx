import { useState } from "react";
import { Badge, Button, Modal, useToast } from "../../components";
import { bookingsService } from "../../services/bookings";
import type { Booking } from "../../types/realestate";
import { extractErrorMessage } from "../../utils/errors";
import { POSSESSION_CHECKLIST } from "../../utils/purchaseProgress";
import "./CustomerPurchaseCard.css";

interface Props {
  booking: Booking;
  onClose: () => void;
  /** The booking as saved after each tick, so the drawer holds the latest list (and reopens with it). */
  onSaved?: (updated: Booking) => void;
}

/**
 * The possession (handover) checklist for one booking, the same seven items as the Possession page. Each tick saves
 * straight away, like that page; ticking the last one is what moves the lead to Possession. One save at a time, so
 * two quick taps can't land out of order and leave an older list saved.
 */
export function PossessionChecklistModal({ booking, onClose, onSaved }: Props) {
  const toast = useToast();
  const [checked, setChecked] = useState<boolean[]>(() =>
    POSSESSION_CHECKLIST.map((_, i) => booking.possessionChecklist?.[i] ?? false)
  );
  const [saving, setSaving] = useState(false);
  const done = checked.filter(Boolean).length;
  const allDone = done === POSSESSION_CHECKLIST.length;

  async function toggle(index: number) {
    if (saving) return;
    const previous = checked;
    const next = checked.map((v, i) => (i === index ? !v : v));
    setChecked(next);
    setSaving(true);
    try {
      const updated = await bookingsService.savePossessionChecklist(booking.id, next);
      onSaved?.(updated);
    } catch (err) {
      setChecked(previous); // revert on failure
      toast.error("Couldn't save checklist", extractErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  // Not while a tick is saving: closing then could reopen the window on the list as it was before that tick.
  function close() {
    if (!saving) onClose();
  }

  const unit = booking.unit ? `${booking.unit.projectName} · ${booking.unit.towerName} · ${booking.unit.unitNumber}` : "Unit";

  return (
    <Modal
      open
      title="Possession checklist"
      onClose={close}
      footer={
        <Button variant="secondary" onClick={close} disabled={saving}>
          Done
        </Button>
      }
    >
      <div className="stack" style={{ gap: "0.5rem" }}>
        <div className="row row--between" style={{ alignItems: "center" }}>
          <span className="muted text-sm">{unit}</span>
          <Badge tone={allDone ? "success" : done > 0 ? "warning" : "neutral"}>
            {allDone ? "Handed over" : `${done} of ${POSSESSION_CHECKLIST.length} done`}
          </Badge>
        </div>
        <div className="purchase-checklist">
          {POSSESSION_CHECKLIST.map((item, index) => (
            <label key={item} className={`purchase-checklist__item${checked[index] ? " is-done" : ""}`}>
              <input type="checkbox" checked={checked[index]} disabled={saving} onChange={() => void toggle(index)} />
              <span>{item}</span>
            </label>
          ))}
        </div>
        <p className="muted text-xs" style={{ margin: 0 }}>Each tick is saved straight away.</p>
      </div>
    </Modal>
  );
}
