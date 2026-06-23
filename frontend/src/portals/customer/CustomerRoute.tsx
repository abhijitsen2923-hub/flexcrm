import { Navigate, Outlet } from "react-router-dom";
import { LoadingBlock } from "../../components";
import { useAuth } from "../../hooks/useAuth";

export function CustomerRoute() {
  const { user, loading } = useAuth();

  if (loading) return <LoadingBlock label="Loading…" />;
  if (!user) return <Navigate to="/login" replace />;
  // Only "customer" role gets the portal; staff are redirected to the main app.
  if (user.role !== "customer") return <Navigate to="/" replace />;

  return <Outlet />;
}
