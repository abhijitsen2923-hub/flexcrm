// Unit tests for a custom role's "Data access" helpers (src/utils/leadAccess.ts). Run: npm test
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  defaultCampaignFor,
  defaultSourceFor,
  describeLeadAccess,
  draftFromRole,
  draftIsLimited,
  draftProblem,
  draftToPayload,
  sourceOptionsFor,
  toggleValue,
} from "../src/utils/leadAccess.ts";

const SOURCES = [
  { value: "Walk-in", label: "Walk-in" },
  { value: "Website", label: "Website" },
  { value: "Facebook / Meta", label: "Facebook / Meta" },
  { value: "__other__", label: "Other…" },
];

test("an unrestricted role round-trips as all / all / not own-only", () => {
  const draft = draftFromRole(null);
  assert.deepEqual(draft, { ownOnly: false, campaignMode: "all", campaignIds: [], sourceMode: "all", sources: [] });
  assert.equal(draftIsLimited(draft), false);
  assert.equal(draftProblem(draft), null);
  assert.deepEqual(draftToPayload(draft), { own_leads_only: false, campaign_ids: null, sources: null });
});

test("a limited role loads into the form and saves back the same", () => {
  const draft = draftFromRole({
    own_leads_only: true,
    campaigns: [{ id: "c1", name: "Alpha" }, { id: "c2", name: "Beta" }],
    sources: ["Website"],
  });
  assert.equal(draft.campaignMode, "chosen");
  assert.equal(draftIsLimited(draft), true);
  assert.deepEqual(draftToPayload(draft), { own_leads_only: true, campaign_ids: ["c1", "c2"], sources: ["Website"] });
  // Own-only alone is a limit too.
  assert.equal(draftIsLimited({ ...draftFromRole(null), ownOnly: true }), true);
});

test("choosing 'some' with nothing picked can't be saved", () => {
  const none = { ...draftFromRole(null), campaignMode: "chosen" as const };
  assert.match(draftProblem(none) ?? "", /at least one campaign/);
  const noSources = { ...draftFromRole(null), sourceMode: "chosen" as const };
  assert.match(draftProblem(noSources) ?? "", /at least one source/);
});

test("sources are de-duplicated ignoring case and spacing; toggles are case-insensitive for labels", () => {
  const draft = { ...draftFromRole(null), sourceMode: "chosen" as const, sources: [" Website ", "website", "Expo  2026"] };
  assert.deepEqual(draftToPayload(draft).sources, ["Website", "Expo 2026"]);
  assert.deepEqual(toggleValue(["Website"], "website", false, true), []);
  assert.deepEqual(toggleValue(["a"], "b", true), ["a", "b"]);
  assert.deepEqual(toggleValue(["a", "b"], "a", false), ["b"]);
});

test("a role's access reads as one line", () => {
  assert.equal(describeLeadAccess(null), "All leads");
  assert.equal(describeLeadAccess({ own_leads_only: false, campaigns: null, sources: null }), "All leads");
  assert.equal(
    describeLeadAccess({
      own_leads_only: true,
      campaigns: [{ id: "1", name: "A" }, { id: "2", name: "B" }, { id: "3", name: "C" }, { id: "4", name: "D" }],
      sources: ["Website"],
    }),
    "Campaigns: A, B, C +1 more · Sources: Website · Only their own leads",
  );
  assert.equal(describeLeadAccess({ own_leads_only: false, campaigns: [], sources: null }), "Campaigns: none (removed)");
  // The signed-in user's own banner.
  assert.equal(describeLeadAccess({ own_leads_only: true, campaigns: ["Alpha"], sources: null }, "your"), "Campaigns: Alpha · Only your own leads");
});

test("a limited user's New Lead form offers only their sources and preselects a single campaign / source", () => {
  assert.equal(sourceOptionsFor(SOURCES, null), SOURCES);
  assert.equal(sourceOptionsFor(SOURCES, { own_leads_only: false, campaigns: ["A"], sources: null }), SOURCES);
  const limited = { own_leads_only: false, campaigns: ["Alpha"], sources: ["website", "Expo 2026"] };
  assert.deepEqual(sourceOptionsFor(SOURCES, limited), [
    { value: "Website", label: "Website" },
    { value: "Expo 2026", label: "Expo 2026" },
  ]);
  assert.equal(defaultCampaignFor(limited), "Alpha");
  assert.equal(defaultCampaignFor({ ...limited, campaigns: ["A", "B"] }), "");
  assert.equal(defaultCampaignFor(null), "");
  assert.equal(defaultSourceFor(SOURCES, limited), "");
  assert.equal(defaultSourceFor(SOURCES, { ...limited, sources: ["walk-in"] }), "Walk-in");
  assert.equal(defaultSourceFor(SOURCES, null), "");
});
