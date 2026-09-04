import {
  Activity,
  Award,
  Banknote,
  BarChart3,
  Briefcase,
  Building2,
  CalendarDays,
  ClipboardCheck,
  ClipboardList,
  Coins,
  FileCheck2,
  FileText,
  Handshake,
  PieChart,
  KeyRound,
  Layers,
  LayoutDashboard,
  Plug,
  Receipt,
  Settings2,
  Sparkles,
  TrendingUp,
  Truck,
  UserRound,
  Users,
  Wallet,
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
  // Exact-match active state (else a parent path highlights on its sub-routes).
  end?: boolean;
  label: string;
  icon: LucideIcon;
  requires: PermissionCode[];
  moduleKey?: keyof ReturnType<typeof mergeModules>;
  // Any-of: item is shown when at least one of these modules is enabled.
  // Use instead of `moduleKey` for a nav that fronts several modules.
  moduleKeys?: Array<keyof ReturnType<typeof mergeModules>>;
}


const NAV: ReadonlyArray<NavItem> = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, requires: ["DASHBOARD_VIEW"] },
  { to: "/leads", label: "Leads", icon: Sparkles, requires: ["LEAD_VIEW"] },
  { to: "/customers", label: "Customers", icon: UserRound, requires: ["CUSTOMER_VIEW"] },
  { to: "/deals", label: "Deals", icon: Briefcase, requires: ["DEAL_VIEW"], moduleKey: "deals" },
  { to: "/tasks", label: "Tasks", icon: ClipboardList, requires: ["TASK_VIEW"], moduleKey: "tasks" },
  { to: "/activities", label: "Activities", icon: Activity, requires: ["ACTIVITY_VIEW"], moduleKey: "activities" },
  { to: "/finance/dashboard", label: "Finance Dashboard", icon: PieChart, requires: ["FINANCE_VIEW"], moduleKey: "finance" },
  { to: "/finance", end: true, label: "Expenses", icon: Receipt, requires: ["FINANCE_VIEW"], moduleKey: "finance" },
  { to: "/finance/income", label: "Income", icon: Coins, requires: ["FINANCE_VIEW"], moduleKey: "finance" },
  { to: "/finance/receivables", label: "Customer Receivables", icon: Banknote, requires: ["FINANCE_VIEW"], moduleKey: "finance" },
  { to: "/finance/vendors", label: "Vendors", icon: Truck, requires: ["FINANCE_VIEW"], moduleKey: "finance" },
  { to: "/finance/vendor-payments", label: "Vendor Payments", icon: Wallet, requires: ["FINANCE_VIEW"], moduleKey: "finance" },
  { to: "/finance/sales", label: "Revenue", icon: TrendingUp, requires: ["FINANCE_VIEW"], moduleKey: "finance" },
  { to: "/finance/reports", label: "Reports", icon: FileText, requires: ["FINANCE_VIEW"], moduleKey: "finance" },
  { to: "/finance/settings", label: "Finance Settings", icon: Settings2, requires: ["FINANCE_SETTINGS_MANAGE"], moduleKey: "finance" },
  { to: "/hr", label: "HR", icon: Award, requires: ["HR_VIEW"], moduleKey: "hr" },
  // Real-estate modules
  { to: "/projects", label: "Projects", icon: Building2, requires: ["LEAD_VIEW"], moduleKey: "projects" },
  { to: "/inventory", label: "Inventory", icon: Layers, requires: ["LEAD_VIEW"], moduleKey: "inventory" },
  { to: "/site-visits", label: "Site Visits", icon: CalendarDays, requires: ["LEAD_VIEW"], moduleKey: "site_visits" },
  { to: "/bookings", label: "Bookings", icon: ClipboardCheck, requires: ["LEAD_MANAGE"], moduleKey: "bookings" },
  { to: "/trackers/registration", label: "Registration", icon: FileCheck2, requires: ["LEAD_MANAGE"], moduleKey: "bookings" },
  { to: "/trackers/possession", label: "Possession", icon: KeyRound, requires: ["LEAD_MANAGE"], moduleKey: "bookings" },
  { to: "/channel-partners", label: "Channel Partners", icon: Handshake, requires: ["USER_VIEW"], moduleKey: "bookings" },
  { to: "/integrations", label: "Integrations", icon: Plug, requires: ["ORG_MANAGE"], moduleKeys: ["meta_facebook", "meta_instagram", "portal_99acres", "sheet_leads"] },
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
    if (item.moduleKeys && !item.moduleKeys.some((k) => modules[k])) return false;
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
            end={item.end ?? item.to === "/"}
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
