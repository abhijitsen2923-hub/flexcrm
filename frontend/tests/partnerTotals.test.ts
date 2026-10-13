// Unit tests for the channel-partner funnel totals (src/utils/partnerTotals.ts). Run: npm test
import assert from "node:assert/strict";
import { test } from "node:test";

import { partnerFunnel, shareOfReferred } from "../src/utils/partnerTotals.ts";

test("sums referred → visits → bookings → sales over every partner", () => {
  const partners = [
    { stats: { leads_total: 2, leads_visited: 2, leads_booked: 1, leads_sold: 1 } },
    { stats: { leads_total: 0, leads_visited: 0, leads_booked: 0, leads_sold: 0 } },
    { stats: { leads_total: 1, leads_visited: 1, leads_booked: 0, leads_sold: 0 } },
  ];
  assert.deepEqual(partnerFunnel(partners), { referred: 3, visited: 3, booked: 1, sold: 1 });
  assert.deepEqual(partnerFunnel([]), { referred: 0, visited: 0, booked: 0, sold: 0 });
});

test("an older backend without the visit / booking counts reads as 0, not NaN", () => {
  assert.deepEqual(partnerFunnel([{ stats: { leads_total: 4, leads_sold: 1 } }]), { referred: 4, visited: 0, booked: 0, sold: 1 });
});

test("share of referred", () => {
  assert.equal(shareOfReferred(1, 3), "33% of referred");
  assert.equal(shareOfReferred(0, 3), "0% of referred");
  assert.equal(shareOfReferred(0, 0), "");
});
