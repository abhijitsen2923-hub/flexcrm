import { Inbox } from "lucide-react";
import type { ReactNode } from "react";


interface EmptyStateProps {
  title: string;
  description?: string;
  icon?: ReactNode;
  action?: ReactNode;
}


export function EmptyState({ title, description, icon, action }: EmptyStateProps) {
  return (
    <div className="empty-state">
      <div className="empty-state__icon">{icon ?? <Inbox size={22} />}</div>
      <div style={{ fontWeight: 600, color: "var(--color-text)" }}>{title}</div>
      {description && <div className="text-sm">{description}</div>}
      {action && <div style={{ marginTop: "0.75rem" }}>{action}</div>}
    </div>
  );
}
