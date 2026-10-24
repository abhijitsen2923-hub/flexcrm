import assert from "node:assert/strict";
import { test } from "node:test";

import { calculateDaysRemaining } from "../src/utils/subscriptionReminder.ts";

test("calculateDaysRemaining: returns null for invalid or empty dates", () => {
  assert.equal(calculateDaysRemaining(null), null);
  assert.equal(calculateDaysRemaining(undefined), null);
  assert.equal(calculateDaysRemaining(""), null);
  assert.equal(calculateDaysRemaining("invalid-date"), null);
});

test("calculateDaysRemaining: correctly computes days relative to reference date", () => {
  const refDate = new Date(2026, 9, 24); // 2026-10-24

  // Exactly today
  assert.equal(calculateDaysRemaining("2026-10-24", refDate), 0);

  // Tomorrow
  assert.equal(calculateDaysRemaining("2026-10-25", refDate), 1);

  // 7 days in the future
  assert.equal(calculateDaysRemaining("2026-10-31", refDate), 7);

  // 1 day in the past (expired yesterday)
  assert.equal(calculateDaysRemaining("2026-10-23", refDate), -1);

  // 10 days in the past
  assert.equal(calculateDaysRemaining("2026-10-14", refDate), -10);
});

test("calculateDaysRemaining: handles month rollover and year rollover seamlessly", () => {
  const refDate = new Date(2026, 11, 31); // 2026-12-31

  // Next year
  assert.equal(calculateDaysRemaining("2027-01-05", refDate), 5);
});

