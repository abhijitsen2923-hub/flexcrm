import { useState } from "react";
import { Button, Modal, TextField, useToast } from "../../../components";
import { bookingsService } from "../../../services/bookings";
import type { Booking } from "../../../types/realestate";
import { extractErrorMessage } from "../../../utils/errors";

interface Props {
  booking: Booking;
  // Prefix for the field ids, so two screens that both show this form keep distinct, stable ids.
  idPrefix: string;
  onClose: () => void;
  // Called after the registration is saved (the window is closed by the caller).
  onRegistered: (updated: Booking) => void;
}

/**
 * "Register unit": the legal registration date, deed number and sub-registrar office. Saving marks the unit
 * Registered (POST /bookings/{id}/register, confirmed bookings only). Shared by the lead's Booking & Payments tab
 * and the Customer drawer's Purchases card.
 */
export function RegisterBookingModal({ booking, idPrefix, onClose, onRegistered }: Props) {
  const toast = useToast();
  const [form, setForm] = useState({
    date: booking.scheduledDate ?? new Date().toISOString().slice(0, 10),
    number: booking.registrationNumber ?? "",
    office: booking.subRegistrarOffice ?? "",
  });
  const [registering, setRegistering] = useState(false);

  async function confirm() {
    if (!form.date) {
      toast.error("Registration date is required");
      return;
    }
    setRegistering(true);
    try {
      const updated = await bookingsService.registerBooking(booking.id, {
        registration_date: form.date,
        registration_number: form.number.trim() || null,
        sub_registrar_office: form.office.trim() || null,
      });
      toast.success("Registered", "Unit marked Registered");
      onRegistered(updated);
    } catch (err) {
      toast.error("Could not register", extractErrorMessage(err));
    } finally {
      setRegistering(false);
    }
  }

  return (
    <Modal
      open
      title="Register unit"
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={registering}>Cancel</Button>
          <Button loading={registering} onClick={() => void confirm()}>Mark Registered</Button>
        </>
      }
    >
      <div className="stack" style={{ gap: "0.75rem" }}>
        <TextField id={`${idPrefix}-date`} label="Registration date" type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} required />
        <TextField id={`${idPrefix}-number`} label="Registration / deed no. (optional)" value={form.number} onChange={(e) => setForm({ ...form, number: e.target.value })} placeholder="e.g. SRO-2026-12345" />
        <TextField id={`${idPrefix}-office`} label="Sub-registrar office (optional)" value={form.office} onChange={(e) => setForm({ ...form, office: e.target.value })} placeholder="e.g. SRO Whitefield" />
      </div>
    </Modal>
  );
}
