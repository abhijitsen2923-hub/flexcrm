// Unit tests for the tenant campaign-list helpers (src/utils/campaigns.ts). Neutral names only.
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  CAMPAIGN_NAME_MAX_LEN,
  NEW_CAMPAIGN_VALUE,
  buildCampaignFilterOptions,
  buildCampaignFormOptions,
  campaignKey,
  campaignRejectionMessage,
  campaignSourceLabel,
  cleanCampaignName,
  findCampaignByKey,
  isCampaignListEvent,
  mergePreviewCount,
  renameConflictId,
  shouldUseLegacyCampaigns
} from "../src/utils/campaigns.ts";

const campaign = (name: string, is_active = true) => ({ id: name, name, is_active, needs_review: false });

function httpError(status: number, error: Record<string, unknown> = {}) {
  return { response: { status, data: { error } } };
}

test("cleanCampaignName trims, collapses whitespace and clamps like the backend", () => {
  assert.equal(cleanCampaignName("  Monsoon \t  Offer  2026 \n"), "Monsoon Offer 2026");
  assert.equal(cleanCampaignName("   "), "");
  assert.equal(cleanCampaignName(null), "");
  assert.equal(cleanCampaignName("x".repeat(500)).length, CAMPAIGN_NAME_MAX_LEN);
});

test("campaignKey: case and extra spaces don't matter, punctuation does", () => {
  assert.equal(campaignKey("Monsoon  OFFER"), campaignKey(" monsoon offer "));
  assert.notEqual(campaignKey("Promo 4.5L"), campaignKey("Promo 4.5 L"));
});

test("findCampaignByKey matches any spelling", () => {
  const list = [campaign("Monsoon Offer"), campaign("Expo Fair")];
  assert.equal(findCampaignByKey(list, "  MONSOON offer")?.name, "Monsoon Offer");
  assert.equal(findCampaignByKey(list, "Nope"), undefined);
  assert.equal(findCampaignByKey(list, "   "), undefined);
});

test("form options: tenant's active campaigns only; 'new' only when allowed; no built-in names", () => {
  const list = [campaign("Monsoon Offer"), campaign("Old Promo", false), campaign("Expo Fair")];
  const rep = buildCampaignFormOptions(list, { allowNew: false });
  assert.deepEqual(rep.map((o) => o.value), ["", "Expo Fair", "Monsoon Offer"]);
  const manager = buildCampaignFormOptions(list, { allowNew: true });
  assert.equal(manager.at(-1)?.value, NEW_CAMPAIGN_VALUE);
  assert.notEqual(NEW_CAMPAIGN_VALUE, "Other");
  // A brand-new workspace has nothing built in.
  assert.deepEqual(buildCampaignFormOptions([], { allowNew: false }), [{ value: "", label: "None" }]);
});

test("form options keep the current selection and merge legacy names by key", () => {
  const opts = buildCampaignFormOptions([campaign("Expo Fair")], {
    allowNew: true,
    legacyNames: ["expo fair", "Spring Offer"],
    current: "Gone Campaign"
  });
  assert.deepEqual(opts.map((o) => o.value), ["", "Expo Fair", "Gone Campaign", "Spring Offer", NEW_CAMPAIGN_VALUE]);
  // The sentinel itself is never duplicated as a value.
  const withSentinel = buildCampaignFormOptions([], { allowNew: true, current: NEW_CAMPAIGN_VALUE });
  assert.equal(withSentinel.filter((o) => o.value === NEW_CAMPAIGN_VALUE).length, 1);
  // Chosen in legacy mode, then the list came back for a rep: still selectable, so they can switch away.
  const stuck = buildCampaignFormOptions([campaign("Expo Fair")], { allowNew: false, current: NEW_CAMPAIGN_VALUE });
  assert.deepEqual(stuck.map((o) => o.value), ["", "Expo Fair", NEW_CAMPAIGN_VALUE]);
});

test("filter options: only campaigns on visible leads, one per campaign, inactive marked, selection kept", () => {
  const opts = buildCampaignFilterOptions(
    [campaign("Monsoon Offer"), campaign("Old Promo", false), campaign("Only On Others Leads")],
    ["monsoon offer", "Old Promo", "Walk-in Event", "  "],
    "Legacy Value"
  );
  assert.deepEqual(opts, [
    { value: "Monsoon Offer", label: "Monsoon Offer" },
    { value: "Old Promo", label: "Old Promo (inactive)" },
    { value: "Walk-in Event", label: "Walk-in Event" },
    { value: "Legacy Value", label: "Legacy Value" }
  ]);
  // A campaign with no visible leads isn't offered (a rep's list is scoped to their own leads).
  assert.ok(!opts.some((o) => o.value === "Only On Others Leads"));
  assert.deepEqual(buildCampaignFilterOptions([], [], ""), []);
});

test("isCampaignListEvent: list changes only, not every lead event", () => {
  assert.equal(isCampaignListEvent({ event: "campaign.updated", payload: { reason: "campaign_create" } }), true);
  assert.equal(isCampaignListEvent({ event: "lead.updated", payload: { count: 3, reason: "campaign_merge" } }), true);
  assert.equal(isCampaignListEvent({ event: "lead.updated", payload: { count: 2, reason: "sheet_relabel" } }), true);
  assert.equal(isCampaignListEvent({ event: "lead.updated", payload: { count: 2, reason: "bulk_reassign" } }), false);
  assert.equal(isCampaignListEvent({ event: "lead.created", payload: { id: "x" } }), false);
  assert.equal(isCampaignListEvent({ event: "lead.updated", payload: null }), false);
});

test("mergePreviewCount sums the sources' leads", () => {
  const rows = [
    { id: "a", lead_count: 3 },
    { id: "b", lead_count: 10 },
    { id: "c", lead_count: 7 }
  ];
  assert.equal(mergePreviewCount(rows, ["a", "c"]), 10);
  assert.equal(mergePreviewCount(rows, []), 0);
});

test("legacy mode only when the backend has no campaign list", () => {
  assert.equal(shouldUseLegacyCampaigns(httpError(404)), true); // older backend mid-deploy
  assert.equal(shouldUseLegacyCampaigns(httpError(409, { extra: { reason: "not_ready" } })), true);
  // A 5xx / network error comes from a backend that enforces the list: no free-text fallback.
  assert.equal(shouldUseLegacyCampaigns(httpError(503)), false);
  assert.equal(shouldUseLegacyCampaigns(new Error("Network Error")), false);
  assert.equal(shouldUseLegacyCampaigns(httpError(403)), false);
  assert.equal(shouldUseLegacyCampaigns(httpError(401)), false);
  assert.equal(shouldUseLegacyCampaigns(httpError(409, { extra: { reason: "stale" } })), false);
});

test("campaignRejectionMessage surfaces the backend's campaign reason only", () => {
  const unknown = httpError(422, {
    detail: [{ loc: ["body", "campaign"], msg: "'Monsoon Ofer' isn't in your campaign list. Did you mean 'Monsoon Offer'?" }],
    extra: { field: "campaign", reason: "unknown_campaign", suggestions: ["Monsoon Offer"] }
  });
  assert.match(campaignRejectionMessage(unknown) ?? "", /Did you mean 'Monsoon Offer'/);
  assert.ok(campaignRejectionMessage(httpError(422, { detail: "Old is inactive", extra: { reason: "inactive_campaign" } })));
  assert.equal(campaignRejectionMessage(httpError(422, { detail: [{ msg: "x" }] })), null);
  assert.equal(campaignRejectionMessage(httpError(409, { detail: "x", extra: { reason: "unknown_campaign" } })), null);
  assert.equal(campaignRejectionMessage(null), null);
});

test("renameConflictId offers a merge target on a name clash", () => {
  assert.equal(renameConflictId(httpError(409, { extra: { reason: "name_exists", conflict_campaign_id: "c1" } })), "c1");
  assert.equal(renameConflictId(httpError(409, { extra: { reason: "alias_of_other", conflict_campaign_id: "c2" } })), "c2");
  assert.equal(renameConflictId(httpError(409, { extra: { reason: "stale" } })), null);
  assert.equal(renameConflictId(httpError(422)), null);
});

test("campaignSourceLabel", () => {
  assert.equal(campaignSourceLabel("sheet"), "Google Sheet");
  assert.equal(campaignSourceLabel("something-new"), "something-new");
});
