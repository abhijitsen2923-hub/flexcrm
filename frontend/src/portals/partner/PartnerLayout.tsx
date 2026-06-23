import { ClipboardList, IndianRupee, PlusCircle, Sparkles } from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../../hooks/useAuth";
import "./PartnerLayout.css";

export function PartnerLayout() {
  const { user } = useAuth();

  return (
    <div className="partner-shell">
      <aside className="partner-sidebar">
        <div className="partner-sidebar__brand">
          <Sparkles size={18} />
          Partner Portal
        </div>
        <nav className="partner-sidebar__nav">
          <NavLink
            to="/partner/submit"
            className={({ isActive }) => `partner-link${isActive ? " is-active" : ""}`}
          >
            <PlusCircle size={16} /> Submit Lead
          </NavLink>
          <NavLink
            to="/partner/leads"
            className={({ isActive }) => `partner-link${isActive ? " is-active" : ""}`}
          >
            <ClipboardList size={16} /> My Leads
          </NavLink>
          <NavLink
            to="/partner/commissions"
            className={({ isActive }) => `partner-link${isActive ? " is-active" : ""}`}
          >
            <IndianRupee size={16} /> Commissions
          </NavLink>
        </nav>
        {user && (
          <div
            className="muted text-xs"
            style={{ padding: "var(--space-4)", marginTop: "auto", borderTop: "1px solid var(--color-border)" }}
          >
            {user.first_name} {user.last_name}
            <div style={{ opacity: 0.7 }}>{user.email}</div>
          </div>
        )}
      </aside>
      <main className="partner-main">
        <Outlet />
      </main>
    </div>
  );
}
