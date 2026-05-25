import type { PropsWithChildren } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { useAuth } from "../../hooks/useAuth";
import { LoadingBlock } from "../ui/Spinner";


export function ProtectedRoute({ children }: PropsWithChildren) {
  const { user, loading, session } = useAuth();
  const location = useLocation();

  if (loading && session) {
    return <LoadingBlock label="Restoring your session…" />;
  }

  if (!user) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  return <>{children}</>;
}
