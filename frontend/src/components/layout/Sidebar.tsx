import {
  Activity,
  Award,
  BarChart3,
  Briefcase,
  Building2,
  CalendarDays,
  ClipboardCheck,
  ClipboardList,
  FileCheck2,
  Handshake,
  KeyRound,
  Layers,
  LayoutDashboard,
  Plug,
  Receipt,
  Settings2,
  Sparkles,
  UserRound,
  Users,
  X,
  type LucideIcon
} from "lucide-react";
import { NavLink } from "react-router-dom";

import { mergeModules } from "../../config/features";
import { useAuth } from "../../hooks/useAuth";
import { useOrgModules } from "../../context/OrgContext";
import type { PermissionCode } from "../../types/crm";
import { usePermissions } from "../../hooks/usePermissions";


interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  requires: PermissionCode[];
  moduleKey?: keyof ReturnType<typeof mergeModules>;
}


const NAV: ReadonlyArray<NavItem> = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, requires: ["DASHBOARD_VIEW"] },
  { to: "/leads", label: "Leads", icon: Sparkles, requires: ["LEAD_VIEW"] },
  { to: "/customers", label: "Customers", icon: UserRound, requires: ["CUSTOMER_VIEW"] },
  { to: "/deals", label: "Deals", icon: Briefcase, requires: ["DEAL_VIEW"], moduleKey: "deals" },
  { to: "/tasks", label: "Tasks", icon: ClipboardList, requires: ["TASK_VIEW"], moduleKey: "tasks" },
  { to: "/activities", label: "Activities", icon: Activity, requires: ["ACTIVITY_VIEW"], moduleKey: "activities" },
  { to: "/finance", label: "Finance", icon: Receipt, requires: ["FINANCE_VIEW"], moduleKey: "finance" },
  { to: "/hr", label: "HR", icon: Award, requires: ["HR_VIEW"], moduleKey: "hr" },
  // Real-estate modules
  { to: "/projects", label: "Projects", icon: Building2, requires: ["LEAD_VIEW"], moduleKey: "projects" },
  { to: "/inventory", label: "Inventory", icon: Layers, requires: ["LEAD_VIEW"], moduleKey: "inventory" },
  { to: "/site-visits", label: "Site Visits", icon: CalendarDays, requires: ["LEAD_VIEW"], moduleKey: "site_visits" },
  { to: "/bookings", label: "Bookings", icon: ClipboardCheck, requires: ["LEAD_MANAGE"], moduleKey: "bookings" },
  { to: "/trackers/registration", label: "Registration", icon: FileCheck2, requires: ["LEAD_MANAGE"], moduleKey: "bookings" },
  { to: "/trackers/possession", label: "Possession", icon: KeyRound, requires: ["LEAD_MANAGE"], moduleKey: "bookings" },
  { to: "/channel-partners", label: "Channel Partners", icon: Handshake, requires: ["USER_VIEW"], moduleKey: "bookings" },
  { to: "/integrations", label: "Integrations", icon: Plug, requires: ["ORG_MANAGE"], moduleKey: "meta_leads" },
  // Always-visible
  { to: "/analytics", label: "Analytics", icon: BarChart3, requires: ["ANALYTICS_VIEW"] },
  { to: "/users", label: "Users", icon: Users, requires: ["USER_VIEW"] }
];


interface SidebarProps {
  open: boolean;
  onClose: () => void;
}


export function Sidebar({ open, onClose }: SidebarProps) {
  const { user } = useAuth();
  const { any } = usePermissions();
  const orgModules = useOrgModules();
  const modules = mergeModules(orgModules);

  const visible = NAV.filter((item) => {
    if (user?.is_platform_admin) return false;
    if (item.moduleKey && !modules[item.moduleKey]) return false;
    return any(item.requires);
  });

  return (
    <aside className={["sidebar", open ? "is-open" : null].filter(Boolean).join(" ")}>
      <div className="sidebar__brand">
        <span className="sidebar__brand-chip">F</span>
        <span className="sidebar__brand-mark">Flex<span>CRM</span></span>
        <button className="sidebar__close" onClick={onClose} aria-label="Close menu">
          <X size={18} />
        </button>
      </div>
      <nav className="sidebar__nav">
        {visible.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            className={({ isActive }) =>
              ["sidebar__link", isActive ? "is-active" : null].filter(Boolean).join(" ")
            }
            onClick={onClose}
          >
            <item.icon size={16} />
            {item.label}
          </NavLink>
        ))}
        {user?.is_platform_admin && (
          <NavLink
            to="/admin"
            className={({ isActive }) =>
              ["sidebar__link", isActive ? "is-active" : null].filter(Boolean).join(" ")
            }
            onClick={onClose}
          >
            <Settings2 size={16} />
            Platform Admin
          </NavLink>
        )}
      </nav>
      <div className="sidebar__footer">
        v1.0 · {new Date().getFullYear()}
      </div>
    </aside>
  );
}
