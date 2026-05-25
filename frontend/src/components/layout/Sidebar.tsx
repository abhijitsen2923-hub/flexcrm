import {
  Activity,
  Award,
  BarChart3,
  Briefcase,
  ClipboardList,
  LayoutDashboard,
  Receipt,
  Sparkles,
  UserRound,
  Users,
  type LucideIcon
} from "lucide-react";
import { NavLink } from "react-router-dom";

import { FEATURES, type FeatureKey } from "../../config/features";
import { usePermissions } from "../../hooks/usePermissions";
import type { PermissionCode } from "../../types/crm";


interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  // The user needs at least one of these to see the nav item. Backend
  // enforces — this just hides affordances the user can't act on.
  requires: PermissionCode[];
  // Optional build-time feature gate. When set, the item only shows if the
  // matching flag in `config/features.ts` is true. Used to hide modules that
  // aren't ready to ship to end users yet (Deals/Tasks/Activities/Finance/HR).
  feature?: FeatureKey;
}


const NAV: ReadonlyArray<NavItem> = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, requires: ["DASHBOARD_VIEW"] },
  { to: "/leads", label: "Leads", icon: Sparkles, requires: ["LEAD_VIEW"] },
  { to: "/customers", label: "Customers", icon: UserRound, requires: ["CUSTOMER_VIEW"] },
  { to: "/deals", label: "Deals", icon: Briefcase, requires: ["DEAL_VIEW"], feature: "deals" },
  { to: "/tasks", label: "Tasks", icon: ClipboardList, requires: ["TASK_VIEW"], feature: "tasks" },
  { to: "/activities", label: "Activities", icon: Activity, requires: ["ACTIVITY_VIEW"], feature: "activities" },
  { to: "/finance", label: "Finance", icon: Receipt, requires: ["FINANCE_VIEW"], feature: "finance" },
  { to: "/hr", label: "HR", icon: Award, requires: ["HR_VIEW"], feature: "hr" },
  { to: "/analytics", label: "Analytics", icon: BarChart3, requires: ["ANALYTICS_VIEW"] },
  { to: "/users", label: "Users", icon: Users, requires: ["USER_VIEW"] }
];


export function Sidebar() {
  const { any } = usePermissions();
  const visible = NAV.filter(
    (item) => (item.feature === undefined || FEATURES[item.feature]) && any(item.requires),
  );
  return (
    <aside className="sidebar">
      <div className="sidebar__brand">
        <Sparkles size={20} />
        FlexCRM
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
          >
            <item.icon size={16} />
            {item.label}
          </NavLink>
        ))}
      </nav>
      <div className="sidebar__footer">
        v1.0 · {new Date().getFullYear()}
      </div>
    </aside>
  );
}
