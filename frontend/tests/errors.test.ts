// extractErrorMessage: what a user reads when a request fails.
import assert from "node:assert/strict";
import { test } from "node:test";

import { extractErrorMessage } from "../src/utils/errors.ts";

const httpError = (status: number, detail: unknown) => ({
  isAxiosError: true,
  message: "Request failed",
  response: { status, data: { error: { code: "x", detail } } }
});

test("a 422 with the backend's own sentence shows that sentence", () => {
  const message = "CSV must include a `contact_name` column — accepted headers: Name, Contact…";
  assert.equal(extractErrorMessage(httpError(422, message)), message);
});

test("a 422 in FastAPI's field-error shape shows the field message", () => {
  assert.equal(
    extractErrorMessage(httpError(422, [{ loc: ["body", "campaign"], msg: "isn't in your campaign list" }])),
    "campaign: isn't in your campaign list"
  );
  assert.equal(extractErrorMessage(httpError(422, "  ")), "Some of the information looks incorrect. Please review and try again.");
});

test("server errors never leak details", () => {
  assert.equal(
    extractErrorMessage(httpError(500, "psycopg.errors.UniqueViolation: duplicate key…")),
    "Something went wrong on our end. Please try again in a moment."
  );
});
