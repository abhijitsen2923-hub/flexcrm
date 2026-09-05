import { useEffect, useState } from "react";

import { BrandLoader } from "../ui/BrandLoader";
import { BrandMark } from "../ui/BrandMark";
import { Button } from "../ui/Button";


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
      <div className="brand-loader">
        <BrandMark size="lg" />
        <p className="brand-loader__status brand-loader__status--wide">
          We couldn&rsquo;t reach the server. Your session is still saved — please try again.
        </p>
        <Button variant="primary" onClick={onRetry}>
          Try again
        </Button>
      </div>
    );
  }

  return <BrandLoader status={slow ? "Waking the server, one moment…" : "Getting things ready…"} />;
}
