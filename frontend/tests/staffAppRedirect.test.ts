// Unit tests for staffAppRedirect: where a signed-in user is sent instead of the staff app page they asked for.
import assert from "node:assert/strict";
import { test } from "node:test";

import { staffAppRedirect } from "../src/components/routing/staffAppRedirect.ts";

const owner = { role: "owner", is_platform_admin: false } as const;
const platformAdmin = { role: "owner", is_platform_admin: true } as const;

test("a platform admin lands on the admin console, not the workspace Dashboard", () => {
  assert.equal(staffAppRedirect(platformAdmin, "/"), "/admin"); // after login ("from" defaults to "/")
  for (const path of ["/leads", "/customers", "/campaigns", "/users", "/finance/dashboard", "/no-such-page"]) {
    assert.equal(staffAppRedirect(platformAdmin, path), "/admin", path);
  }
});

test("a platform admin already on the admin console stays (no redirect loop)", () => {
  assert.equal(staffAppRedirect(platformAdmin, "/admin"), null);
  assert.equal(staffAppRedirect(platformAdmin, "/admin/"), null);
  assert.equal(staffAppRedirect(platformAdmin, "/administrator"), "/admin"); // only /admin itself counts
});

test("workspace users are unaffected", () => {
  for (const role of ["owner", "sales_manager", "sales_executive", "counselor"] as const) {
    for (const path of ["/", "/leads", "/admin"]) {
      assert.equal(staffAppRedirect({ role, is_platform_admin: false }, path), null, `${role} ${path}`);
    }
  }
  assert.equal(staffAppRedirect(owner, "/"), null);
});

test("portal roles still go to their portals", () => {
  assert.equal(staffAppRedirect({ role: "broker", is_platform_admin: false }, "/"), "/partner");
  assert.equal(staffAppRedirect({ role: "customer", is_platform_admin: false }, "/leads"), "/customer");
});
