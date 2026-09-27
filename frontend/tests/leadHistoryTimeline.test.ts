// Unit tests for the Stage History timeline merge (stage moves + owner changes). Run: npm test
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  actorName,
  assignmentSourceLabel,
  buildLeadTimeline,
} from "../src/components/leads/leadHistoryTimeline.ts";
import type { LeadAssignmentEvent, StageTransition } from "../src/types/crm.ts";

function stage(id: string, at: string, from: string | null, to: string): StageTransition {
  return {
    id, lead_id: "lead-1", from_stage_code: from, to_stage_code: to, comment: `moved to ${to}`,
    next_action_date: null, attachment_path: null, performed_by_id: null, performed_at: at, mentions: null,
  };
}

function owner(id: string, at: string, source: LeadAssignmentEvent["source"] = "reassign"): LeadAssignmentEvent {
  return {
    id, lead_id: "lead-1", source, performed_at: at,
    from_user_id: null, to_user_id: "u-2", performed_by_id: "u-1",
    from_user: null, to_user: { id: "u-2", first_name: "Bina", last_name: "Das" },
    performed_by: { id: "u-1", first_name: "Ravi", last_name: null },
  };
}

const keys = (entries: ReturnType<typeof buildLeadTimeline>) => entries.map((e) => e.key);

test("merges both histories newest-first", () => {
  const entries = buildLeadTimeline(
    [stage("s2", "2026-09-27T10:00:00Z", "new_enquiry", "call"), stage("s1", "2026-09-25T09:00:00Z", null, "new_enquiry")],
    [owner("o1", "2026-09-26T12:00:00Z")]
  );
  assert.deepEqual(keys(entries), ["stage-s2", "owner-o1", "stage-s1"]);
});

test("a lead created with an owner: owner change sorts above the 'created' stage entry at the same instant", () => {
  const at = "2026-09-27T10:00:00.123456Z";
  const entries = buildLeadTimeline([stage("s1", at, null, "new_enquiry")], [owner("o1", at, "created")]);
  assert.deepEqual(keys(entries), ["owner-o1", "stage-s1"]);
});

test("same kind + same instant keeps the API's order", () => {
  const at = "2026-09-27T10:00:00Z";
  const entries = buildLeadTimeline([], [owner("o2", at), owner("o1", at)]);
  assert.deepEqual(keys(entries), ["owner-o2", "owner-o1"]);
});

test("unparseable timestamps sink to the bottom instead of breaking the sort", () => {
  const entries = buildLeadTimeline([stage("bad", "not-a-date", null, "new_enquiry")], [owner("o1", "2026-09-27T10:00:00Z")]);
  assert.deepEqual(keys(entries), ["owner-o1", "stage-bad"]);
});

test("empty histories give an empty timeline", () => {
  assert.deepEqual(buildLeadTimeline([], []), []);
});

test("actorName: full, partial, blank and missing names", () => {
  assert.equal(actorName({ first_name: "Asha", last_name: "Roy" }, "Unassigned"), "Asha Roy");
  assert.equal(actorName({ first_name: "Ravi", last_name: null }, "Unassigned"), "Ravi");
  assert.equal(actorName({ first_name: "  ", last_name: " Das " }, "Unassigned"), "Das");
  assert.equal(actorName({ first_name: null, last_name: null }, "Unassigned"), "Unassigned");
  assert.equal(actorName(null, "Unassigned"), "Unassigned");
  assert.equal(actorName(undefined, "Unassigned"), "Unassigned");
});

test("source labels, with a safe fallback for unknown sources", () => {
  assert.equal(assignmentSourceLabel("bulk_reassign"), "Bulk reassigned");
  assert.equal(assignmentSourceLabel("import"), "Assigned on upload");
  assert.equal(assignmentSourceLabel("booking"), "Salesperson set at booking");
  assert.equal(assignmentSourceLabel("something_new"), "Owner changed");
});
