// Pure validation for the stage-transition modal (no React / DOM), so the rules are unit-testable with
// `node --test` and the modal can show WHY a move can't be saved instead of silently disabling "Save".

export const MIN_COMMENT_LENGTH = 10;

export type TransitionField =
  | "comment"
  | "siteProjects"
  | "siteDateTime"
  | "unit"
  | "salesperson"
  | "tokenAmount"
  | "tokenMode"
  | "tokenDate";

// DOM id of each validated field in StageTransitionModal — the first invalid one is scrolled into view on
// Save (a test checks every id is actually rendered by the modal).
export const FIELD_ELEMENT_IDS: Readonly<Record<TransitionField, string>> = {
  comment: "transition-comment",
  siteProjects: "sv-projects",
  siteDateTime: "sv-datetime",
  unit: "bk-unit",
  salesperson: "bk-salesperson",
  tokenAmount: "bk-token",
  tokenMode: "bk-mode",
  tokenDate: "bk-date",
};

// Top-to-bottom order of the fields in the modal — the first invalid one is scrolled into view.
export const TRANSITION_FIELD_ORDER: readonly TransitionField[] = [
  "comment",
  "siteProjects",
  "siteDateTime",
  "unit",
  "salesperson",
  "tokenAmount",
  "tokenMode",
  "tokenDate",
];

export interface TransitionFormState {
  comment: string;
  isSiteVisitStage: boolean;
  siteProjectIds: readonly string[];
  siteDateTime: string;
  isBookedStage: boolean;
  hasExistingBooking: boolean;
  unitId: string;
  availableUnitCount: number;
  salespersonId: string;
  // Salesperson is only required when there ARE users to pick from (roles without USER_VIEW get none
  // and book as the lead's owner).
  assignableUserCount: number;
  tokenAmount: string;
  tokenMode: string;
  tokenDate: string;
}

export type TransitionErrors = Partial<Record<TransitionField, string>>;

/** Every unmet requirement for saving the move, keyed by field ({} = ready to save). */
export function validateTransition(s: TransitionFormState): TransitionErrors {
  const errors: TransitionErrors = {};

  const commentLength = s.comment.trim().length;
  if (commentLength < MIN_COMMENT_LENGTH) {
    errors.comment =
      commentLength === 0
        ? `Add a comment (at least ${MIN_COMMENT_LENGTH} characters).`
        : `${MIN_COMMENT_LENGTH - commentLength} more characters required.`;
  }

  if (s.isSiteVisitStage) {
    if (s.siteProjectIds.length === 0) errors.siteProjects = "Select at least one site.";
    if (!s.siteDateTime) errors.siteDateTime = "Pick the visit date & time.";
  }

  if (s.isBookedStage) {
    if (!s.hasExistingBooking && !s.unitId) {
      errors.unit =
        s.availableUnitCount === 0
          ? "No available units — add or release a unit in Inventory first."
          : "Select a unit.";
    }
    if (s.assignableUserCount > 0 && !s.salespersonId) errors.salesperson = "Select a salesperson.";
    // Whole rupees, at least ₹1 — the same rule the input's min="1" / step="1" enforced natively.
    const amount = Number(s.tokenAmount);
    if (!s.tokenAmount.trim() || !Number.isInteger(amount) || amount < 1) {
      errors.tokenAmount = "Enter a token amount of at least ₹1 (whole rupees).";
    }
    if (!s.tokenMode) errors.tokenMode = "Choose a payment method.";
    if (!s.tokenDate) errors.tokenDate = "Pick the date the token was received.";
  }

  return errors;
}

/** The first invalid field in on-screen order, or null when the form is ready. */
export function firstInvalidField(errors: TransitionErrors): TransitionField | null {
  return TRANSITION_FIELD_ORDER.find((field) => errors[field] !== undefined) ?? null;
}
