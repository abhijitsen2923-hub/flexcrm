import { useEffect, useState } from "react";

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

  return (
    <div className="brand-loader">
      <BrandMark size="lg" />
      {failed ? (
        <>
          <p className="brand-loader__status brand-loader__status--wide">
            We couldn&rsquo;t reach the server. Your session is still saved — please try again.
          </p>
          <Button variant="primary" onClick={onRetry}>
            Try again
          </Button>
        </>
      ) : (
        <>
          <div className="brand-loader__track" role="progressbar" aria-label="Loading">
            <div className="brand-loader__fill" />
          </div>
          <p className="brand-loader__status">
            {slow ? "Waking the server, one moment…" : "Restoring your session…"}
          </p>
        </>
      )}
    </div>
  );
}
