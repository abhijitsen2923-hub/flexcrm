// Unit tests for localDayRange (picked local days → half-open UTC bounds for the leads date filters).
// Timezone-independent: assertions read the result back in LOCAL time. `npm test` also runs these under
// several TZ values in CI-less local checks (e.g. TZ=Asia/Kolkata, TZ=UTC).
import assert from "node:assert/strict";
import { test } from "node:test";

import { localDayRange } from "../src/utils/dateRange.ts";

function localParts(iso: string | undefined): string {
  assert.ok(iso, "expected a bound");
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

test("From = local midnight of the From day", () => {
  assert.equal(localParts(localDayRange("2026-09-20").from), "2026-09-20 00:00");
});

test("To is inclusive: local midnight of the day AFTER the To day", () => {
  assert.equal(localParts(localDayRange(undefined, "2026-09-20").to), "2026-09-21 00:00");
});

test("a single day (From = To) covers exactly that local day", () => {
  const { from, to } = localDayRange("2026-09-20", "2026-09-20");
  assert.equal(localParts(from), "2026-09-20 00:00");
  assert.equal(localParts(to), "2026-09-21 00:00");
});

test("open-ended ranges leave the other bound undefined", () => {
  assert.deepEqual(localDayRange(), { from: undefined, to: undefined });
  assert.equal(localDayRange("2026-09-20").to, undefined);
  assert.equal(localDayRange(undefined, "2026-09-20").from, undefined);
  assert.equal(localDayRange("", "").from, undefined);
});

test("month and year roll over", () => {
  assert.equal(localParts(localDayRange(undefined, "2026-09-30").to), "2026-10-01 00:00");
  assert.equal(localParts(localDayRange(undefined, "2026-12-31").to), "2027-01-01 00:00");
});

test("invalid input yields no bound instead of throwing", () => {
  assert.deepEqual(localDayRange("not-a-date", "2026-13-45"), { from: undefined, to: undefined });
});

test("IST example: 20 Sep 2026 → 2026-09-19T18:30Z … 2026-09-20T18:30Z (only when running in IST)", (t) => {
  if (new Date("2026-09-20T00:00:00").getTimezoneOffset() !== -330) {
    t.skip("not running in IST");
    return;
  }
  assert.deepEqual(localDayRange("2026-09-20", "2026-09-20"), {
    from: "2026-09-19T18:30:00.000Z",
    to: "2026-09-20T18:30:00.000Z",
  });
});

// Regression guard: the two existing date filters used this exact inline logic before the refactor.
test("identical to the previous inline next-action / stage-changed boundaries", () => {
  const oldFrom = (day: string) => new Date(`${day}T00:00:00`).toISOString();
  const oldTo = (day: string) => {
    const end = new Date(`${day}T00:00:00`);
    end.setDate(end.getDate() + 1);
    return end.toISOString();
  };
  for (const day of ["2026-01-01", "2026-03-29", "2026-09-20", "2026-10-25", "2026-12-31", "2028-02-29"]) {
    assert.deepEqual(localDayRange(day, day), { from: oldFrom(day), to: oldTo(day) }, day);
  }
});
