import type { PropsWithChildren } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { useAuth } from "../../hooks/useAuth";
import { SessionRestoreScreen } from "./SessionRestoreScreen";
import { staffAppRedirect } from "./staffAppRedirect";


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

  // Portal-only roles go to their portal; platform admins to the admin console.
  const redirect = staffAppRedirect(user, location.pathname);
  if (redirect) {
    return <Navigate to={redirect} replace />;
  }

  return <>{children}</>;
}
