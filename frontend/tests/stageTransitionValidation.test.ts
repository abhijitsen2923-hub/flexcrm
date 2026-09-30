// Unit tests for the stage-transition modal's validation rules. Dependency-free: Node's built-in runner
// with native TypeScript stripping (Node >= 22.18 / 23.6).  Run:  npm test   (= node --test "tests/*.test.ts")
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import {
  FIELD_ELEMENT_IDS,
  MIN_COMMENT_LENGTH,
  TRANSITION_FIELD_ORDER,
  firstInvalidField,
  validateTransition,
  type TransitionFormState,
} from "../src/components/leads/stageTransitionValidation.ts";

const COMMENT = "Token received, unit confirmed with the buyer.";

// A complete, valid "Booked / Token" move by a manager who picks the salesperson.
function booked(overrides: Partial<TransitionFormState> = {}): TransitionFormState {
  return {
    intentRequired: false, // fixed from Booked onward
    intent: "",
    comment: COMMENT,
    isSiteVisitStage: false,
    siteProjectIds: [],
    siteDateTime: "",
    isBookedStage: true,
    hasExistingBooking: false,
    unitId: "unit-1",
    availableUnitCount: 3,
    salespersonId: "user-1",
    assignableUserCount: 2,
    tokenAmount: "11000",
    tokenMode: "neft",
    tokenDate: "2026-09-27",
    ...overrides,
  };
}

function plain(overrides: Partial<TransitionFormState> = {}): TransitionFormState {
  return booked({ isBookedStage: false, unitId: "", tokenAmount: "", tokenMode: "", tokenDate: "", ...overrides });
}

test("a complete booking has no errors", () => {
  assert.deepEqual(validateTransition(booked()), {});
  assert.equal(firstInvalidField({}), null);
});

test("comment: empty vs short vs whitespace-padded", () => {
  assert.match(validateTransition(plain({ comment: "" })).comment ?? "", /Add a comment/);
  assert.equal(validateTransition(plain({ comment: "short" })).comment, `${MIN_COMMENT_LENGTH - 5} more characters required.`);
  assert.equal(validateTransition(plain({ comment: "   short   " })).comment, `${MIN_COMMENT_LENGTH - 5} more characters required.`);
  assert.equal(validateTransition(plain({ comment: "x".repeat(MIN_COMMENT_LENGTH) })).comment, undefined);
});

test("non-booking moves ignore the booking fields", () => {
  assert.deepEqual(validateTransition(plain()), {});
});

test("the reported case: phone booking with comment + unit missing (rest filled) says so, comment first", () => {
  const errors = validateTransition(booked({ comment: "", unitId: "", assignableUserCount: 0, salespersonId: "" }));
  assert.deepEqual(Object.keys(errors).sort(), ["comment", "unit"]);
  assert.equal(firstInvalidField(errors), "comment");
});

test("unit: required unless the lead already has a booking; explains when none are available", () => {
  assert.equal(validateTransition(booked({ unitId: "" })).unit, "Select a unit.");
  assert.match(validateTransition(booked({ unitId: "", availableUnitCount: 0 })).unit ?? "", /No available units/);
  assert.equal(validateTransition(booked({ unitId: "", availableUnitCount: 0, hasExistingBooking: true })).unit, undefined);
});

test("salesperson: required only when there are users to pick from", () => {
  assert.equal(validateTransition(booked({ salespersonId: "" })).salesperson, "Select a salesperson.");
  assert.equal(validateTransition(booked({ salespersonId: "", assignableUserCount: 0 })).salesperson, undefined);
  assert.equal(validateTransition(booked({ salespersonId: "__owner_reference__" })).salesperson, undefined);
});

test("token amount: whole rupees, at least ₹1 (what min=1 / step=1 enforced before noValidate)", () => {
  for (const bad of ["", "   ", "0", "0.5", "0.004", "11000.5", "-5", "abc", "1e400"]) {
    assert.ok(validateTransition(booked({ tokenAmount: bad })).tokenAmount, `expected an error for ${JSON.stringify(bad)}`);
  }
  for (const good of ["1", "11000", " 11000 "]) {
    assert.equal(validateTransition(booked({ tokenAmount: good })).tokenAmount, undefined, good);
  }
});

test("payment method and token date are required on a booking", () => {
  assert.ok(validateTransition(booked({ tokenMode: "" })).tokenMode);
  assert.ok(validateTransition(booked({ tokenDate: "" })).tokenDate);
});

test("site visit: needs a site and a date/time", () => {
  const errors = validateTransition(plain({ isSiteVisitStage: true }));
  assert.deepEqual(Object.keys(errors).sort(), ["siteDateTime", "siteProjects"]);
  assert.deepEqual(validateTransition(plain({ isSiteVisitStage: true, siteProjectIds: ["p1"], siteDateTime: "2026-09-28T10:00" })), {});
});

test("intent: required only when the move asks for it, and nothing counts as picked until chosen", () => {
  assert.equal(validateTransition(plain({ intentRequired: true })).intent, "Pick an intent — Low, Medium or High");
  assert.equal(validateTransition(plain({ intentRequired: true, intent: "low" })).intent, undefined);
  assert.equal(validateTransition(plain({ intentRequired: false })).intent, undefined); // Booked onward / closed
  assert.deepEqual(validateTransition(plain({ intentRequired: true, intent: "high" })), {});
});

test("first invalid field follows on-screen order", () => {
  // Intent sits at the top (beside the stage change), above the comment.
  assert.equal(firstInvalidField(validateTransition(plain({ intentRequired: true, comment: "" }))), "intent");
  assert.equal(firstInvalidField(validateTransition(booked({ tokenAmount: "", unitId: "" }))), "unit");
  assert.equal(firstInvalidField(validateTransition(booked({ tokenDate: "", tokenMode: "" }))), "tokenMode");
});

// Wiring guard: Save scrolls to document.getElementById(FIELD_ELEMENT_IDS[field]) — if a field's id in the
// modal is renamed, the scroll silently goes nowhere. Every id must be rendered by StageTransitionModal.
test("every validated field id is rendered by StageTransitionModal", () => {
  const modal = readFileSync(new URL("../src/components/leads/StageTransitionModal.tsx", import.meta.url), "utf8");
  assert.deepEqual(Object.keys(FIELD_ELEMENT_IDS).sort(), [...TRANSITION_FIELD_ORDER].sort());
  for (const [field, id] of Object.entries(FIELD_ELEMENT_IDS)) {
    const rendered = modal.includes(`id="${id}"`) || modal.includes(`id={FIELD_ELEMENT_IDS.${field}}`);
    assert.ok(rendered, `StageTransitionModal renders no element with id "${id}" (field "${field}")`);
  }
});

// Regression guard: for every input the OLD disabled-button rule saw, "no errors" must mean exactly what
// "Save enabled" meant before (deliberate additions: token date required; the token-amount min/step rule the
// browser used to enforce natively is now explicit).
test("parity with the previous canSubmit rule", () => {
  const oldCanSubmit = (s: TransitionFormState): boolean => {
    const siteVisitReady = !s.isSiteVisitStage || (s.siteProjectIds.length > 0 && Boolean(s.siteDateTime));
    const salespersonReady = s.assignableUserCount === 0 || Boolean(s.salespersonId);
    const bookedReady =
      !s.isBookedStage ||
      Boolean((s.hasExistingBooking || s.unitId) && Number(s.tokenAmount) > 0 && s.tokenMode && salespersonReady);
    return s.comment.trim().length >= MIN_COMMENT_LENGTH && siteVisitReady && bookedReady;
  };
  let checked = 0;
  for (const comment of ["", "short", COMMENT])
    for (const isSiteVisitStage of [false, true])
      for (const siteProjectIds of [[], ["p1"]])
        for (const siteDateTime of ["", "2026-09-28T10:00"])
          for (const isBookedStage of [false, true])
            for (const hasExistingBooking of [false, true])
              for (const unitId of ["", "u1"])
                for (const assignableUserCount of [0, 2])
                  for (const salespersonId of ["", "user-1"])
                    for (const tokenAmount of ["", "0", "11000"])
                      for (const tokenMode of ["", "neft"]) {
                        const s = booked({
                          comment, isSiteVisitStage, siteProjectIds, siteDateTime, isBookedStage, hasExistingBooking,
                          unitId, assignableUserCount, salespersonId, tokenAmount, tokenMode, tokenDate: "2026-09-27",
                        });
                        const ready = firstInvalidField(validateTransition(s)) === null;
                        assert.equal(ready, oldCanSubmit(s), JSON.stringify(s));
                        checked += 1;
                      }
  assert.equal(checked, 3 * 2 * 2 * 2 * 2 * 2 * 2 * 2 * 2 * 3 * 2);
});
