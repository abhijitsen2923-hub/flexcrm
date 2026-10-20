// Unit tests for login renewal across tabs (src/utils/sessionRenewal.ts). Run: npm test
import assert from "node:assert/strict";
import { test } from "node:test";

import { afterRefusal, beforeRenewal } from "../src/utils/sessionRenewal.ts";

const NOW = Date.parse("2026-10-19T17:00:00Z");
const inMinutes = (m: number) => new Date(NOW + m * 60_000).toISOString();
const session = (refreshToken: string, accessExpiresInMin = 15) => ({
  accessToken: `access-${refreshToken}`,
  refreshToken,
  accessTokenExpiresAt: inMinutes(accessExpiresInMin),
});

test("nothing renewed elsewhere → renew with this tab's token", () => {
  const mine = session("r1", -1);
  assert.deepEqual(beforeRenewal(mine, mine, NOW), { kind: "renew", refreshToken: "r1" });
  // Storage unavailable (some webviews) → this tab's own token.
  assert.deepEqual(beforeRenewal(mine, null, NOW), { kind: "renew", refreshToken: "r1" });
});

test("another tab renewed while this one waited → use its fresh session, no request", () => {
  const mine = session("r1", -1);
  const saved = session("r2", 14);
  assert.deepEqual(beforeRenewal(mine, saved, NOW), { kind: "adopt", session: saved });
});

test("another tab renewed long ago (its access token is stale too) → renew with ITS refresh token, not ours", () => {
  const mine = session("r1", -30);
  assert.deepEqual(beforeRenewal(mine, session("r2", -5), NOW), { kind: "renew", refreshToken: "r2" });
  // About to expire counts as stale.
  assert.deepEqual(beforeRenewal(mine, session("r2", 0.1), NOW), { kind: "renew", refreshToken: "r2" });
});

test("refused, but the saved login moved on → another tab won the race: keep going with it", () => {
  const saved = session("r2");
  assert.deepEqual(afterRefusal("r1", saved), { kind: "adopt", session: saved });
});

test("refused and the saved login is still the refused one (or gone) → ended; clear the saved copy", () => {
  assert.deepEqual(afterRefusal("r1", session("r1")), { kind: "ended", clearSaved: true });
  assert.deepEqual(afterRefusal("r1", null), { kind: "ended", clearSaved: true });
});

test("a saved session without a refresh token is never adopted", () => {
  const broken = { accessToken: "a", refreshToken: "", accessTokenExpiresAt: inMinutes(10) };
  assert.deepEqual(beforeRenewal(session("r1"), broken, NOW), { kind: "renew", refreshToken: "r1" });
  assert.deepEqual(afterRefusal("r1", broken), { kind: "ended", clearSaved: true });
});
