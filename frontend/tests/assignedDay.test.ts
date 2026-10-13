// Unit tests for the "Assigned today / yesterday / on a day" helpers (src/utils/assignedDay.ts). Run: npm test
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  assignedDayDate,
  assignedDayLabel,
  assignedDayPhrase,
  assignedDayQuery,
  countByStage,
  isPickableDay,
  localDay,
  parseAssignedParam,
} from "../src/utils/assignedDay.ts";
import { localDayRange } from "../src/utils/dateRange.ts";

// 11 Oct 2026, 09:15 local.
const NOW = new Date(2026, 9, 11, 9, 15);

test("today / yesterday / a picked day resolve to local calendar days", () => {
  assert.equal(assignedDayDate("today", NOW), "2026-10-11");
  assert.equal(assignedDayDate("yesterday", NOW), "2026-10-10");
  assert.equal(assignedDayDate("2026-10-04", NOW), "2026-10-04");
  assert.equal(assignedDayDate("", NOW), null);
  assert.equal(assignedDayDate("2026-13-45", NOW), null);
  assert.equal(assignedDayDate("tomorrow", NOW), null);
  // Month boundary: yesterday of 1 Nov is 31 Oct.
  assert.equal(assignedDayDate("yesterday", new Date(2026, 10, 1, 0, 5)), "2026-10-31");
  assert.equal(localDay(new Date(2026, 0, 5)), "2026-01-05");
});

test("query bounds are the local day, half-open (same as the Lead date filter)", () => {
  const range = localDayRange("2026-10-10", "2026-10-10");
  assert.deepEqual(assignedDayQuery("yesterday", NOW), { assigned_from: range.from, assigned_to: range.to });
  assert.deepEqual(assignedDayQuery("", NOW), {});
  const day = assignedDayQuery("today", NOW);
  assert.equal(Date.parse(day.assigned_to!) - Date.parse(day.assigned_from!), 24 * 60 * 60 * 1000);
});

test("labels and phrases", () => {
  assert.equal(assignedDayLabel("today", NOW), "Today");
  assert.equal(assignedDayLabel("yesterday", NOW), "Yesterday");
  assert.equal(assignedDayLabel("2026-10-11", NOW), "Today"); // a picked day that is today reads as Today
  assert.match(assignedDayLabel("2026-10-04", NOW), /4 Oct/);
  assert.equal(assignedDayPhrase("yesterday", NOW), "yesterday");
  assert.match(assignedDayPhrase("2026-10-04", NOW), /^on .*4 Oct/);
  assert.equal(assignedDayLabel("", NOW), "");
});

test("?assigned= from the dashboard link", () => {
  assert.equal(parseAssignedParam("today"), "today");
  assert.equal(parseAssignedParam(" Yesterday "), "yesterday");
  assert.equal(parseAssignedParam("2026-10-04"), "2026-10-04");
  assert.equal(parseAssignedParam("2026-02-31x"), "");
  assert.equal(parseAssignedParam("<script>"), "");
  assert.equal(parseAssignedParam(null), "");
});

test("status summary counts leads per stage in pipeline order", () => {
  const stages = [
    { code: "new_enquiry", name: "New Enquiry", position: 1 },
    { code: "call", name: "Call", position: 2 },
    { code: "follow_up", name: "Follow-up", position: 4 },
    { code: "not_interested", name: "Not Interested", position: 13 },
  ];
  const leads = ["follow_up", "call", "call", "not_interested", "call", "mystery"].map((stage_code) => ({ stage_code }));
  assert.deepEqual(countByStage(leads, stages), [
    { code: "call", name: "Call", count: 3 },
    { code: "follow_up", name: "Follow-up", count: 1 },
    { code: "not_interested", name: "Not Interested", count: 1 },
    { code: "mystery", name: "mystery", count: 1 },
  ]);
  assert.deepEqual(countByStage([], stages), []);
});

test("impossible dates are rejected, not rolled over (31 Feb is not 3 Mar)", () => {
  assert.equal(assignedDayDate("2026-02-31", NOW), null);
  assert.equal(parseAssignedParam("2026-02-31"), "");
  assert.equal(assignedDayDate("2028-02-29", NOW), "2028-02-29"); // a real leap day
});

test("the day box applies only whole, sensible dates (no half-typed years, nothing in the future)", () => {
  assert.equal(isPickableDay("0002-10-04", NOW), false);
  assert.equal(isPickableDay("0202-10-04", NOW), false);
  assert.equal(isPickableDay("2026-10-12", NOW), false); // tomorrow
  assert.equal(isPickableDay("2026-10-11", NOW), true);
  assert.equal(isPickableDay("2025-12-31", NOW), true);
  assert.equal(isPickableDay("", NOW), false);
});

test("a day from another year says the year", () => {
  assert.match(assignedDayLabel("2025-10-04", NOW), /2025/);
  assert.doesNotMatch(assignedDayLabel("2026-10-04", NOW), /2026/);
});
