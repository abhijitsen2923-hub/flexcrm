import type { LeadIntent } from "../../types";
import { INTENT_LABEL } from "../../utils/leadIntent";

interface IntentBadgeProps {
  intent: LeadIntent | null | undefined;
  // e.g. " intent" → "High intent" (drawer header); the list rows use the bare label.
  suffix?: string;
  // Rows skip the "Not rated" pill to stay quiet; the drawer and history show it.
  showNotRated?: boolean;
}

/** High (green) / Medium (amber) / Low (grey) pill with a dot; dashed "Not rated" when there is none. */
export function IntentBadge({ intent, suffix = "", showNotRated = true }: IntentBadgeProps) {
  if (!intent && !showNotRated) return null;
  return (
    <span
      className={`badge intent-badge intent-badge--${intent ?? "none"}`}
      title={intent ? `${INTENT_LABEL[intent]} intent` : "Intent not rated yet"}
    >
      {intent ? `${INTENT_LABEL[intent]}${suffix}` : "Not rated"}
    </span>
  );
}
