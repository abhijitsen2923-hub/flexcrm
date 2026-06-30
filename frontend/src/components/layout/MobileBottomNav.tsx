import { BarChart3, LayoutDashboard, Menu, Settings2, Sparkles, UserRound, type LucideIcon } from "lucide-react";
import { NavLink } from "react-router-dom";

import { useAuth } from "../../hooks/useAuth";
import { usePermissions } from "../../hooks/usePermissions";
import type { PermissionCode } from "../../types/crm";


interface MobileBottomNavProps {
  /** Opens the full nav drawer (the "More" tab). */
  onMore: () => void;
}

interface Tab {
  to: string;
  label: string;
  icon: LucideIcon;
  requires: PermissionCode[];
}

// The 4 primary destinations on phones; everything else lives behind "More",
// which opens the existing sidebar drawer (full nav, already permission-gated).
const TABS: Tab[] = [
  { to: "/", label: "Home", icon: LayoutDashboard, requires: ["DASHBOARD_VIEW"] },
  { to: "/leads", label: "Leads", icon: Sparkles, requires: ["LEAD_VIEW"] },
  { to: "/customers", label: "Customers", icon: UserRound, requires: ["CUSTOMER_VIEW"] },
  { to: "/analytics", label: "Analytics", icon: BarChart3, requires: ["ANALYTICS_VIEW"] },
];

const tabClass = ({ isActive }: { isActive: boolean }) =>
  ["bottom-nav__tab", isActive ? "is-active" : null].filter(Boolean).join(" ");


export function MobileBottomNav({ onMore }: MobileBottomNavProps) {
  const { user } = useAuth();
  const { any } = usePermissions();

  // Platform admins only have the admin console (mirrors the Sidebar guard).
  if (user?.is_platform_admin) {
    return (
      <nav className="bottom-nav" aria-label="Primary">
        <NavLink to="/admin" className={tabClass}>
          <Settings2 size={20} />
          <span>Admin</span>
        </NavLink>
      </nav>
    );
  }

  const tabs = TABS.filter((tab) => any(tab.requires));

  return (
    <nav className="bottom-nav" aria-label="Primary">
      {tabs.map((tab) => (
        <NavLink key={tab.to} to={tab.to} end={tab.to === "/"} className={tabClass}>
          <tab.icon size={20} />
          <span>{tab.label}</span>
        </NavLink>
      ))}
      <button type="button" className="bottom-nav__tab" onClick={onMore} aria-label="More menu">
        <Menu size={20} />
        <span>More</span>
      </button>
    </nav>
  );
}
