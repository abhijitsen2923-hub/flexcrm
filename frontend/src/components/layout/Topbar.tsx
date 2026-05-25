import { LogOut } from "lucide-react";
import { useLocation } from "react-router-dom";

import { useAuth } from "../../hooks/useAuth";
import { useRealtime } from "../../realtime";
import { Button } from "../ui/Button";


const PAGE_TITLES: Record<string, string> = {
  "/": "Dashboard",
  "/customers": "Customers",
  "/leads": "Leads",
  "/deals": "Deals",
  "/tasks": "Tasks",
  "/activities": "Activities",
  "/analytics": "Analytics",
  "/users": "Users"
};


function initialsFor(firstName: string, lastName: string): string {
  return `${firstName[0] ?? ""}${lastName[0] ?? ""}`.toUpperCase();
}


function ConnectionPill() {
  const { status } = useRealtime();
  const tone =
    status === "online" ? "online" : status === "connecting" ? "connecting" : "offline";
  const label =
    status === "online"
      ? "Live"
      : status === "connecting"
        ? "Connecting"
        : status === "offline"
          ? "Offline"
          : "Idle";
  return (
    <span className={`connection-pill connection-pill--${tone}`} title={`Realtime status: ${label}`}>
      <span className="connection-pill__dot" />
      {label}
    </span>
  );
}


export function Topbar() {
  const { user, logout } = useAuth();
  const location = useLocation();
  const title = PAGE_TITLES[location.pathname] ?? "FlexCRM";

  if (!user) {
    return null;
  }

  return (
    <header className="topbar">
      <div className="topbar__title">{title}</div>
      <div className="topbar__actions">
        <ConnectionPill />
        <div className="topbar__user">
          <div className="avatar">{initialsFor(user.first_name, user.last_name)}</div>
          <div className="user-meta">
            <span className="user-meta__name">
              {user.first_name} {user.last_name}
            </span>
            <span className="user-meta__role">{user.role}</span>
          </div>
          <Button
            variant="ghost"
            size="sm"
            icon={<LogOut size={14} />}
            onClick={() => void logout()}
            title="Sign out"
          >
            Sign out
          </Button>
        </div>
      </div>
    </header>
  );
}
