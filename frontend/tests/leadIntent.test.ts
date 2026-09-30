// Unit tests for the lead-intent helpers (src/utils/leadIntent.ts): the "fixed from Booked onward" rule
// (mirrors backend/app/core/lead_intent.py), the slider maths and the leads-list filter tokens. Run: npm test
import assert from "node:assert/strict";
import { test } from "node:test";

import type { PipelineStage } from "../src/types/crm.ts";
import {
  INTENT_OPTIONS,
  intentAtRatio,
  intentFilterLabel,
  intentIndex,
  intentSourceLabel,
  isIntentLocked,
  isLeadIntent,
  parseIntentFilter,
  serializeIntentFilter,
  stepIntent,
  toggleIntentFilter,
} from "../src/utils/leadIntent.ts";

// The seeded real-estate pipeline (backend/app/database/pipeline_seed.py).
const RE: [number, string, PipelineStage["category"]][] = [
  [1, "new_enquiry", "active"], [2, "call", "active"], [3, "did_not_pickup", "active"], [4, "follow_up", "active"],
  [5, "site_visit_confirmed", "active"], [6, "site_visit_done", "active"], [7, "interested", "active"],
  [8, "booked", "active"], [9, "agreement_payment", "active"], [10, "registration", "active"],
  [11, "possession", "active"], [12, "sold", "closed_won"], [13, "not_interested", "closed_lost"],
  [14, "disqualified", "closed_lost"],
];
const reStages: PipelineStage[] = RE.map(([position, code, category]) => ({
  id: code, industry: "real_estate", position, code, name: code, category, comment_required: true,
}));
const re = (code: string) => reStages.find((s) => s.code === code)!;

test("intent is asked before Booked and fixed from Booked onward and on closed stages", () => {
  const asked = ["new_enquiry", "call", "did_not_pickup", "follow_up", "site_visit_confirmed", "site_visit_done", "interested"];
  const fixed = ["booked", "agreement_payment", "registration", "possession", "sold", "not_interested", "disqualified"];
  for (const code of asked) assert.equal(isIntentLocked(re(code), reStages), false, code);
  for (const code of fixed) assert.equal(isIntentLocked(re(code), reStages), true, code);
  // Stage list not loaded yet: the seeded Booked position is the fallback.
  assert.equal(isIntentLocked(re("registration")), true);
  assert.equal(isIntentLocked(re("interested")), false);
  assert.equal(isIntentLocked(undefined, reStages), false);
  // Other industries: only closed stages fix it.
  assert.equal(isIntentLocked({ industry: "education", position: 11, category: "active" }), false);
  assert.equal(isIntentLocked({ industry: "education", position: 12, category: "closed_won" }), true);
});

test("slider: Low · Medium · High left to right, nothing set by default", () => {
  assert.deepEqual(INTENT_OPTIONS.map((o) => o.key), ["low", "medium", "high"]);
  assert.equal(intentIndex(null), -1);
  assert.equal(intentIndex("high"), 2);
  assert.equal(intentAtRatio(0), "low");
  assert.equal(intentAtRatio(0.2), "low");
  assert.equal(intentAtRatio(0.5), "medium");
  assert.equal(intentAtRatio(0.8), "high");
  assert.equal(intentAtRatio(1.4), "high");
  assert.equal(intentAtRatio(-3), "low");
  assert.equal(intentAtRatio(Number.NaN), "low");
});

test("keyboard: from not-set any arrow lands on Medium; steps clamp at the ends", () => {
  assert.equal(stepIntent(null, 1), "medium");
  assert.equal(stepIntent(null, -1), "medium");
  assert.equal(stepIntent("medium", 1), "high");
  assert.equal(stepIntent("high", 1), "high");
  assert.equal(stepIntent("low", -1), "low");
});

test("filter tokens: parse, toggle, canonical order, label", () => {
  assert.deepEqual([...parseIntentFilter(" High, none ,bogus")], ["high", "none"]);
  assert.equal(serializeIntentFilter(new Set(["none", "low", "high"])), "high,low,none");
  assert.equal(toggleIntentFilter("", "high"), "high");
  assert.equal(toggleIntentFilter("high", "none"), "high,none");
  assert.equal(toggleIntentFilter("high,none", "high"), "none");
  assert.equal(toggleIntentFilter("none", "none"), "");
  assert.equal(intentFilterLabel("none,medium"), "Medium, Not rated");
  assert.equal(intentFilterLabel(""), "");
});

test("small helpers", () => {
  assert.equal(isLeadIntent("high"), true);
  assert.equal(isLeadIntent("High"), false);
  assert.equal(isLeadIntent(""), false);
  assert.equal(intentSourceLabel("quick_set"), "changed in lead details");
  assert.equal(intentSourceLabel("stage_change"), "set on a stage change");
});
