import type { PropsWithChildren } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { useAuth } from "../../hooks/useAuth";
import { SessionRestoreScreen } from "./SessionRestoreScreen";


export function ProtectedRoute({ children }: PropsWithChildren) {
  const { user, loading, session, restoreFailed, refreshProfile } = useAuth();
  const location = useLocation();

  // We have a session token but no profile yet: either restoring (spinner) or it
  // failed transiently (retry). Never bounce a still-valid session to /login.
  if (session && !user) {
    return (
      <SessionRestoreScreen
        failed={restoreFailed && !loading}
        onRetry={() => void refreshProfile()}
      />
    );
  }

  if (!user) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  // Portal-only roles never see the staff app — bounce them to their portal so a
  // broker/customer landing on "/" (or any deep link) lands in the right place.
  if (user.role === "broker") {
    return <Navigate to="/partner" replace />;
  }
  if (user.role === "customer") {
    return <Navigate to="/customer" replace />;
  }

  return <>{children}</>;
}
