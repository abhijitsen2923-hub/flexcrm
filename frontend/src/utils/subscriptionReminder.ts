/**
 * Calculate the number of calendar days remaining until an end date.
 * Returns null if the date string is missing or invalid.
 * Positive = days remaining in future.
 * 0 = ends today.
 * Negative = expired days ago.
 */
export function calculateDaysRemaining(endDateStr: string | null | undefined, now: Date = new Date()): number | null {
  if (!endDateStr) return null;
  const parts = endDateStr.split("-").map(Number);
  if (parts.length !== 3 || isNaN(parts[0]) || isNaN(parts[1]) || isNaN(parts[2])) {
    return null;
  }
  const target = new Date(parts[0], parts[1] - 1, parts[2]);
  target.setHours(0, 0, 0, 0);

  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  today.setHours(0, 0, 0, 0);

  const diffMs = target.getTime() - today.getTime();
  return Math.round(diffMs / (1000 * 60 * 60 * 24));
}

