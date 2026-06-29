import axios from "axios";

import type { ApiErrorPayload } from "../types";


const NETWORK_MESSAGE =
  "Unable to reach the server. Please check your internet connection and try again.";

const SERVER_MESSAGE_BY_STATUS: Record<number, string> = {
  500: "Something went wrong on our end. Please try again in a moment.",
  502: "The server is temporarily unavailable. Please try again shortly.",
  503: "The service is temporarily unavailable. Please try again in a moment.",
  504: "The server took too long to respond. Please try again.",
};

const CLIENT_MESSAGE_BY_STATUS: Record<number, string> = {
  400: "There was a problem with your request. Please check it and try again.",
  401: "Your session has expired or your sign-in details are incorrect. Please sign in again.",
  403: "You don't have permission to do that.",
  404: "We couldn't find what you were looking for.",
  408: "The request timed out. Please try again.",
  409: "That conflicts with existing data.",
  413: "The information you submitted is too large.",
  422: "Some of the information looks incorrect. Please review and try again.",
  429: "You're doing that too often. Please wait a moment and try again.",
};


function firstValidationMessage(detail: unknown): string | null {
  // FastAPI 422 payloads put an array of { loc, msg, type } in `detail`.
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { loc?: unknown[]; msg?: string };
    if (typeof first?.msg === "string" && first.msg.trim()) {
      const field = Array.isArray(first.loc) ? first.loc[first.loc.length - 1] : undefined;
      return field ? `${String(field)}: ${first.msg}` : first.msg;
    }
  }
  return null;
}


/**
 * Turn any thrown error into a short, user-friendly message for a toast or
 * inline form error.
 *
 * Never exposes raw server internals (SQL, schema names, stack types): network
 * failures and 5xx responses map to generic guidance, validation errors map to
 * a readable field hint, and other 4xx responses use the backend's deliberately
 * user-facing `detail` string (e.g. "A user with this email already exists.").
 */
export function extractErrorMessage(
  error: unknown,
  fallback = "Something went wrong. Please try again."
): string {
  if (axios.isAxiosError(error)) {
    // No response object → network failure, CORS block, or client-side timeout.
    if (!error.response) {
      if (error.code === "ECONNABORTED" || /timeout/i.test(error.message ?? "")) {
        return "The request timed out. Please try again.";
      }
      return NETWORK_MESSAGE;
    }

    const status = error.response.status;
    const detail = (error.response.data as ApiErrorPayload | undefined)?.error?.detail;

    // Server errors: never surface raw technical detail to the user.
    if (status >= 500) {
      return SERVER_MESSAGE_BY_STATUS[status] ?? fallback;
    }

    // Validation: show a readable field message if we can, else a generic hint.
    if (status === 422) {
      return firstValidationMessage(detail) ?? CLIENT_MESSAGE_BY_STATUS[422];
    }

    // Other client errors: the backend detail is written to be user-facing.
    if (typeof detail === "string" && detail.trim()) {
      return detail;
    }
    return CLIENT_MESSAGE_BY_STATUS[status] ?? fallback;
  }

  if (error instanceof Error && error.message && error.message !== "Network Error") {
    return error.message;
  }
  return fallback;
}
