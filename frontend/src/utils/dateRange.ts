// Picked LOCAL calendar days (YYYY-MM-DD from <input type="date">) → the half-open UTC instants the leads
// API filters on: `from` = local midnight of fromDay; `to` = local midnight of the day AFTER toDay, so the
// To day is included. Either bound may be omitted (open-ended range). Invalid input yields no bound.

function localMidnightISO(day: string, addDays = 0): string | undefined {
  const d = new Date(`${day}T00:00:00`); // no zone suffix → parsed as LOCAL midnight
  if (Number.isNaN(d.getTime())) return undefined;
  d.setDate(d.getDate() + addDays);
  return d.toISOString();
}

export function localDayRange(fromDay?: string, toDay?: string): { from?: string; to?: string } {
  return {
    from: fromDay ? localMidnightISO(fromDay) : undefined,
    to: toDay ? localMidnightISO(toDay, 1) : undefined,
  };
}
