import axios from "axios";

import type { ApiErrorPayload } from "../types";


export function extractErrorMessage(error: unknown, fallback = "Something went wrong."): string {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data as ApiErrorPayload | undefined;
    if (data?.error?.detail !== undefined) {
      const detail = data.error.detail;
      if (typeof detail === "string") {
        return detail;
      }
      try {
        return JSON.stringify(detail);
      } catch {
        return fallback;
      }
    }
    if (error.message) {
      return error.message;
    }
  }
  if (error instanceof Error) {
    return error.message;
  }
  return fallback;
}
