// Keeps the lead drawer in step with the (refreshed) leads list. Pure, so it's unit-testable.

export interface DrawerSync<T> {
  /** A newer copy of the open lead from the list, to swap into the drawer (null = keep the current one). */
  replaceWith: T | null;
  /** The open lead is no longer in the list — e.g. a reassignment or stage move dropped it out of the
   *  active filter — so its history must be reloaded explicitly (its updated_at can't reach the drawer). */
  reloadHistory: boolean;
}

export function syncOpenDrawer<T extends { id: string }>(leads: readonly T[], open: T | null): DrawerSync<T> {
  if (!open) return { replaceWith: null, reloadHistory: false };
  const refreshed = leads.find((lead) => lead.id === open.id);
  if (!refreshed) return { replaceWith: null, reloadHistory: true };
  return { replaceWith: refreshed !== open ? refreshed : null, reloadHistory: false };
}
