// Unit tests for syncOpenDrawer — keeping the open lead drawer current after a list refresh. Run: npm test
import assert from "node:assert/strict";
import { test } from "node:test";

import { syncOpenDrawer } from "../src/components/leads/drawerSync.ts";

type L = { id: string; updated_at: string };
const lead = (id: string, updated_at = "2026-09-28T10:00:00Z"): L => ({ id, updated_at });

test("no drawer open: nothing to do", () => {
  assert.deepEqual(syncOpenDrawer([lead("a")], null), { replaceWith: null, reloadHistory: false });
});

test("the list has a newer copy of the open lead: swap it in (its updated_at then reloads the history)", () => {
  const open = lead("a", "2026-09-28T10:00:00Z");
  const newer = lead("a", "2026-09-28T10:05:00Z");
  assert.deepEqual(syncOpenDrawer([lead("b"), newer], open), { replaceWith: newer, reloadHistory: false });
});

test("same object still in the list: leave the drawer alone", () => {
  const open = lead("a");
  assert.deepEqual(syncOpenDrawer([open, lead("b")], open), { replaceWith: null, reloadHistory: false });
});

test("the open lead dropped out of the filtered list (e.g. assigned away from 'Unassigned'): reload its history", () => {
  assert.deepEqual(syncOpenDrawer([lead("b"), lead("c")], lead("a")), { replaceWith: null, reloadHistory: true });
  assert.deepEqual(syncOpenDrawer([], lead("a")), { replaceWith: null, reloadHistory: true });
});
