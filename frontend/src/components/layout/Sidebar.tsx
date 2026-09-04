import {
  Activity,
  Award,
  Banknote,
  BarChart3,
  Briefcase,
  Building2,
  CalendarDays,
  ChevronDown,
  ClipboardCheck,
  ClipboardList,
  Coins,
  CreditCard,
  FileCheck2,
  FileText,
  Handshake,
  Landmark,
  PieChart,
  KeyRound,
  Layers,
  LayoutDashboard,
  Plug,
  Receipt,
  Settings2,
  Sparkles,
  Target,
  TrendingUp,
  Truck,
  UserRound,
  Users,
  Users2,
  Wallet,
  X,
  type LucideIcon
} from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";

import { mergeModules } from "../../config/features";
import { useAuth } from "../../hooks/useAuth";
import { useOrgModules } from "../../context/OrgContext";
import { usePermissions } from "../../hooks/usePermissions";
import { sidebarStorage } from "../../services/storage";
import type { PermissionCode } from "../../types/crm";


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

interface NavGroup {
  key: string;
  label: string;
  icon: LucideIcon;
  items: NavItem[];
}

// A nav entry is either a top-level link or a collapsible group of links.
type NavEntry = { type: "item"; item: NavItem } | { type: "group"; group: NavGroup };


const NAV: ReadonlyArray<NavEntry> = [
  // Everyday core CRM — always flat at the top.
  { type: "item", item: { to: "/", label: "Dashboard", icon: LayoutDashboard, requires: ["DASHBOARD_VIEW"] } },
  { type: "item", item: { to: "/leads", label: "Leads", icon: Sparkles, requires: ["LEAD_VIEW"] } },
  { type: "item", item: { to: "/customers", label: "Customers", icon: UserRound, requires: ["CUSTOMER_VIEW"] } },
  { type: "item", item: { to: "/deals", label: "Deals", icon: Briefcase, requires: ["DEAL_VIEW"], moduleKey: "deals" } },
  { type: "item", item: { to: "/tasks", label: "Tasks", icon: ClipboardList, requires: ["TASK_VIEW"], moduleKey: "tasks" } },
  { type: "item", item: { to: "/activities", label: "Activities", icon: Activity, requires: ["ACTIVITY_VIEW"], moduleKey: "activities" } },

  // Finance vertical.
  {
    type: "group",
    group: {
      key: "finance",
      label: "Finance",
      icon: PieChart,
      items: [
        { to: "/finance/dashboard", label: "Finance Dashboard", icon: PieChart, requires: ["FINANCE_VIEW"], moduleKey: "finance" },
        { to: "/finance", end: true, label: "Expenses", icon: Receipt, requires: ["FINANCE_VIEW"], moduleKey: "finance" },
        { to: "/finance/income", label: "Income", icon: Coins, requires: ["FINANCE_VIEW"], moduleKey: "finance" },
        { to: "/finance/demands", label: "Customer Demands", icon: CreditCard, requires: ["FINANCE_VIEW"], moduleKey: "finance" },
        { to: "/finance/receivables", label: "Booking Receivables", icon: Banknote, requires: ["FINANCE_VIEW"], moduleKey: "finance" },
        { to: "/finance/vendors", label: "Vendors", icon: Truck, requires: ["FINANCE_VIEW"], moduleKey: "finance" },
        { to: "/finance/vendor-payments", label: "Vendor Payments", icon: Wallet, requires: ["FINANCE_VIEW"], moduleKey: "finance" },
        { to: "/finance/payroll", label: "Payroll", icon: Users2, requires: ["FINANCE_SETTINGS_MANAGE"], moduleKey: "finance" },
        { to: "/finance/budgets", label: "Budgets", icon: Target, requires: ["FINANCE_VIEW"], moduleKey: "finance" },
        { to: "/finance/bank", label: "Bank & Cash", icon: Landmark, requires: ["FINANCE_VIEW"], moduleKey: "finance" },
        { to: "/finance/sales", label: "Revenue", icon: TrendingUp, requires: ["FINANCE_VIEW"], moduleKey: "finance" },
        { to: "/finance/reports", label: "Reports", icon: FileText, requires: ["FINANCE_VIEW"], moduleKey: "finance" },
        { to: "/finance/settings", label: "Finance Settings", icon: Settings2, requires: ["FINANCE_SETTINGS_MANAGE"], moduleKey: "finance" }
      ]
    }
  },

  // HR.
  {
    type: "group",
    group: {
      key: "hr",
      label: "HR",
      icon: Award,
      items: [{ to: "/hr", label: "HR", icon: Award, requires: ["HR_VIEW"], moduleKey: "hr" }]
    }
  },

  // Real-estate modules.
  {
    type: "group",
    group: {
      key: "realEstate",
      label: "Real Estate",
      icon: Building2,
      items: [
        { to: "/projects", label: "Projects", icon: Building2, requires: ["LEAD_VIEW"], moduleKey: "projects" },
        { to: "/inventory", label: "Inventory", icon: Layers, requires: ["LEAD_VIEW"], moduleKey: "inventory" },
        { to: "/site-visits", label: "Site Visits", icon: CalendarDays, requires: ["LEAD_VIEW"], moduleKey: "site_visits" },
        { to: "/bookings", label: "Bookings", icon: ClipboardCheck, requires: ["LEAD_MANAGE"], moduleKey: "bookings" },
        { to: "/trackers/registration", label: "Registration", icon: FileCheck2, requires: ["LEAD_MANAGE"], moduleKey: "bookings" },
        { to: "/trackers/possession", label: "Possession", icon: KeyRound, requires: ["LEAD_MANAGE"], moduleKey: "bookings" },
        { to: "/channel-partners", label: "Channel Partners", icon: Handshake, requires: ["USER_VIEW"], moduleKey: "bookings" }
      ]
    }
  },

  // Cross-cutting — flat at the bottom.
  { type: "item", item: { to: "/integrations", label: "Integrations", icon: Plug, requires: ["ORG_MANAGE"], moduleKeys: ["meta_facebook", "meta_instagram", "portal_99acres", "sheet_leads"] } },
  { type: "item", item: { to: "/analytics", label: "Analytics", icon: BarChart3, requires: ["ANALYTICS_VIEW"] } },
  { type: "item", item: { to: "/users", label: "Users", icon: Users, requires: ["USER_VIEW"] } }
];


// True when `pathname` falls inside one of the group's item routes — used to
// auto-open the active group and to hint a collapsed group holds the active page.
function isActiveGroup(group: NavGroup, pathname: string): boolean {
  return group.items.some((it) => pathname === it.to || pathname.startsWith(it.to + "/"));
}


interface SidebarProps {
  open: boolean;
  onClose: () => void;
}


export function Sidebar({ open, onClose }: SidebarProps) {
  const { user } = useAuth();
  const { any } = usePermissions();
  const orgModules = useOrgModules();
  const modules = mergeModules(orgModules);
  const { pathname } = useLocation();

  const [expanded, setExpanded] = useState<Record<string, boolean>>(() => sidebarStorage.get());

  // Auto-open the group that contains the current route (on mount + each nav).
  // Only opens — a group the user collapsed stays collapsed until they navigate
  // back into it. Uses a functional update so it never reads stale state.
  useEffect(() => {
    const active = NAV.find((e) => e.type === "group" && isActiveGroup(e.group, pathname));
    if (!active || active.type !== "group") return;
    const key = active.group.key;
    setExpanded((prev) => {
      if (prev[key]) return prev;
      const next = { ...prev, [key]: true };
      sidebarStorage.set(next);
      return next;
    });
  }, [pathname]);

  const toggleGroup = (key: string) => {
    setExpanded((prev) => {
      const next = { ...prev, [key]: !prev[key] };
      sidebarStorage.set(next);
      return next;
    });
  };

  // Per-item visibility: hidden entirely for platform admins (they get only the
  // Platform Admin link), gated by any-of `moduleKeys`, by `moduleKey`, and by
  // holding at least one of `requires`.
  const isVisible = (item: NavItem): boolean => {
    if (user?.is_platform_admin) return false;
    if (item.moduleKeys && !item.moduleKeys.some((k) => modules[k])) return false;
    if (item.moduleKey && !modules[item.moduleKey]) return false;
    return any(item.requires);
  };

  const renderLink = (item: NavItem) => (
    <NavLink
      key={item.to}
      to={item.to}
      end={item.end ?? item.to === "/"}
      className={({ isActive }) => ["sidebar__link", isActive ? "is-active" : null].filter(Boolean).join(" ")}
      onClick={onClose}
    >
      <item.icon size={16} />
      {item.label}
    </NavLink>
  );

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
        {NAV.map((entry) => {
          if (entry.type === "item") {
            return isVisible(entry.item) ? renderLink(entry.item) : null;
          }

          // Group: render only if it has at least one visible child.
          const items = entry.group.items.filter(isVisible);
          if (items.length === 0) return null;

          const isOpen = expanded[entry.group.key] ?? false;
          const GroupIcon = entry.group.icon;
          const panelId = `sidebar-group-${entry.group.key}`;
          const hasActive = isActiveGroup(entry.group, pathname);

          return (
            <div className="sidebar__group" key={entry.group.key}>
              <button
                type="button"
                className="sidebar__group-toggle"
                aria-expanded={isOpen}
                aria-controls={panelId}
                data-open={isOpen ? "true" : "false"}
                data-active={!isOpen && hasActive ? "true" : undefined}
                onClick={() => toggleGroup(entry.group.key)}
              >
                <GroupIcon size={16} />
                <span className="sidebar__group-name">{entry.group.label}</span>
                <ChevronDown className="sidebar__group-chevron" size={16} />
              </button>
              {isOpen && (
                <div className="sidebar__group-items" id={panelId}>
                  {items.map(renderLink)}
                </div>
              )}
            </div>
          );
        })}
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
