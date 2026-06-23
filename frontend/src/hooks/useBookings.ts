import { useCallback, useEffect, useState } from "react";
import { bookingsService, type CreateBookingPayload } from "../services/bookings";
import type { Booking, BookingStep, PricingSnapshot } from "../types/realestate";

export function useBookings(filters?: { unitId?: string; customerId?: string; status?: string }) {
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await bookingsService.list(filters);
      setBookings(data);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, [filters?.unitId, filters?.customerId, filters?.status]);

  useEffect(() => { refresh(); }, [refresh]);

  const create = useCallback(async (payload: CreateBookingPayload) => {
    const created = await bookingsService.create(payload);
    setBookings((prev) => [created, ...prev]);
    return created;
  }, []);

  const advanceStep = useCallback(async (id: string, step: BookingStep, data: Record<string, unknown>) => {
    const updated = await bookingsService.advanceStep(id, step, data);
    setBookings((prev) => prev.map((b) => (b.id === id ? updated : b)));
    return updated;
  }, []);

  const setPricing = useCallback(async (id: string, pricing: PricingSnapshot) => {
    const updated = await bookingsService.setPricing(id, pricing);
    setBookings((prev) => prev.map((b) => (b.id === id ? updated : b)));
    return updated;
  }, []);

  return { bookings, loading, error, refresh, create, advanceStep, setPricing };
}
