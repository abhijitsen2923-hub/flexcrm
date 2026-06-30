import { useEffect, useState } from "react";

import { Button } from "../ui/Button";
import { Spinner } from "../ui/Spinner";


interface SessionRestoreScreenProps {
  /** Restore failed transiently (offline / server cold) — offer a retry. */
  failed?: boolean;
  onRetry: () => void;
}


export function SessionRestoreScreen({ failed, onRetry }: SessionRestoreScreenProps) {
  // After a few seconds of waiting, set expectations: the backend may be cold.
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    if (failed) {
      return;
    }
    const timer = window.setTimeout(() => setSlow(true), 4000);
    return () => window.clearTimeout(timer);
  }, [failed]);

  if (failed) {
    return (
      <div
        className="loading-block"
        style={{ flexDirection: "column", gap: "0.85rem", textAlign: "center", padding: "var(--space-6)" }}
      >
        <div className="text-sm muted" style={{ maxWidth: "22rem" }}>
          We couldn&rsquo;t reach the server. Your session is still saved — please try again.
        </div>
        <Button variant="primary" onClick={onRetry}>
          Try again
        </Button>
      </div>
    );
  }

  return (
    <div className="loading-block">
      <Spinner label={slow ? "Waking up the server, one moment…" : "Restoring your session…"} />
    </div>
  );
}
