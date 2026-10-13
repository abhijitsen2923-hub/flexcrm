// The channel-partner funnel totals shown on the Channel Partners page and the Dashboard: referred leads → site
// visits done → bookings done → sales closed, summed over every partner. Pure, no runtime imports (unit-tested in
// tests/partnerTotals.test.ts).

export interface PartnerFunnelStats {
  leads_total: number;
  leads_visited?: number; // absent from a backend older than these counts → 0
  leads_booked?: number;
  leads_sold: number;
}

export interface PartnerFunnel {
  referred: number;
  visited: number;
  booked: number;
  sold: number;
}

const count = (value: number | undefined): number => (Number.isFinite(value) && (value as number) > 0 ? (value as number) : 0);

export function partnerFunnel(partners: readonly { stats: PartnerFunnelStats }[]): PartnerFunnel {
  return partners.reduce<PartnerFunnel>(
    (sum, { stats }) => ({
      referred: sum.referred + count(stats.leads_total),
      visited: sum.visited + count(stats.leads_visited),
      booked: sum.booked + count(stats.leads_booked),
      sold: sum.sold + count(stats.leads_sold),
    }),
    { referred: 0, visited: 0, booked: 0, sold: 0 }
  );
}

/** "40% of referred" — a step of the funnel as a share of the referred leads ("" when nothing was referred). */
export function shareOfReferred(part: number, referred: number): string {
  if (referred <= 0) return "";
  return `${Math.round((part / referred) * 100)}% of referred`;
}
