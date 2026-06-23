import { CreditCard, FileDown, HelpCircle, Users } from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";
import "./CustomerLayout.css";

const TABS = [
  { to: "/customer/payments",  label: "Payments",  icon: CreditCard  },
  { to: "/customer/documents", label: "Documents", icon: FileDown     },
  { to: "/customer/service",   label: "Service",   icon: HelpCircle  },
  { to: "/customer/refer",     label: "Refer",     icon: Users       },
] as const;

export function CustomerLayout() {
  return (
    <div className="customer-portal">
      <main className="customer-main">
        <Outlet />
      </main>

      <nav className="customer-tabs" role="tablist" aria-label="Main navigation">
        {TABS.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) => `customer-tab${isActive ? " is-active" : ""}`}
            role="tab"
            aria-label={label}
          >
            <Icon size={22} strokeWidth={1.75} />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
