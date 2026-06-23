import { Navigate, Outlet } from "react-router-dom";
import { LoadingBlock } from "../../components";
import { useAuth } from "../../hooks/useAuth";

export function PartnerRoute() {
  const { user, loading } = useAuth();

  if (loading) return <LoadingBlock label="Loading…" />;
  if (!user) return <Navigate to="/login" replace />;
  // Brokers get the partner portal; other roles are redirected to the main app.
  if (user.role !== "broker") return <Navigate to="/" replace />;

  return <Outlet />;
}
