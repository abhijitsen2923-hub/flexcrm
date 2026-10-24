import { AlertTriangle, PhoneCall, X } from "lucide-react";
import { useState } from "react";

import { useOrg } from "../../context/OrgContext";
import { calculateDaysRemaining } from "../../utils/subscriptionReminder";

export function SubscriptionReminderBanner() {
  const { org } = useOrg();
  // State is in-memory only: closing it hides it for this view,
  // but page refresh or re-login remounts the component and restores visibility.
  const [dismissed, setDismissed] = useState(false);
  const [showContactModal, setShowContactModal] = useState(false);

  const sub = org?.subscription;
  if (dismissed || !sub || !sub.reminder_enabled) {
    return null;
  }

  const days = calculateDaysRemaining(sub.end_date);
  const isExpired = days !== null && days <= 0;
  const isUrgent = days !== null && days <= 3;

  let daysLabel = "soon";
  if (days !== null) {
    if (days < 0) daysLabel = `${Math.abs(days)} day${Math.abs(days) > 1 ? "s" : ""} ago`;
    else if (days === 0) daysLabel = "today";
    else if (days === 1) daysLabel = "1 day (tomorrow)";
    else daysLabel = `${days} days`;
  }

  const bannerStyle: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: "0.75rem",
    padding: "0.5rem 1rem",
    fontSize: "0.875rem",
    lineHeight: "1.25rem",
    background: isExpired
      ? "linear-gradient(90deg, #7f1d1d 0%, #991b1b 100%)"
      : isUrgent
      ? "linear-gradient(90deg, #78350f 0%, #92400e 100%)"
      : "linear-gradient(90deg, #451a03 0%, #78350f 100%)",
    color: "#fef3c7",
    borderBottom: isExpired ? "1px solid #b91c1c" : "1px solid #d97706",
    zIndex: 40,
    boxShadow: "0 2px 4px rgba(0, 0, 0, 0.15)",
  };

  const badgeStyle: React.CSSProperties = {
    display: "inline-block",
    padding: "0.125rem 0.375rem",
    borderRadius: "0.25rem",
    fontWeight: 700,
    fontSize: "0.8125rem",
    background: isExpired ? "#ef4444" : isUrgent ? "#f59e0b" : "rgba(245, 158, 11, 0.25)",
    color: isExpired || isUrgent ? "#18181b" : "#fef3c7",
    margin: "0 0.25rem",
  };

  return (
    <>
      <div style={bannerStyle} role="alert">
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flex: 1, minWidth: 0 }}>
          <AlertTriangle size={18} style={{ flexShrink: 0, color: isExpired ? "#fca5a5" : "#fcd34d" }} />
          <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            <span>Your subscription is about to end in </span>
            <span style={badgeStyle}>{daysLabel}</span>.
            <span style={{ opacity: 0.95, marginLeft: "0.25rem" }}>
              Kindly contact with your provider for make the paymant to use the application semmlessly.
            </span>
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexShrink: 0 }}>
          {sub.provider_contact && (
            <button
              type="button"
              onClick={() => setShowContactModal(true)}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "0.25rem",
                padding: "0.25rem 0.625rem",
                borderRadius: "0.375rem",
                fontSize: "0.75rem",
                fontWeight: 600,
                background: "rgba(255, 255, 255, 0.15)",
                color: "#ffffff",
                border: "1px solid rgba(255, 255, 255, 0.3)",
                cursor: "pointer",
              }}
            >
              <PhoneCall size={12} />
              <span>Contact Provider</span>
            </button>
          )}

          <button
            type="button"
            onClick={() => setDismissed(true)}
            aria-label="Dismiss payment reminder"
            title="Dismiss for this session (reappears on refresh)"
            style={{
              background: "transparent",
              border: "none",
              color: "rgba(254, 243, 199, 0.8)",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              padding: "0.25rem",
              borderRadius: "0.25rem",
            }}
          >
            <X size={16} />
          </button>
        </div>
      </div>

      {showContactModal && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            backgroundColor: "rgba(0, 0, 0, 0.6)",
            backdropFilter: "blur(2px)",
            zIndex: 100,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "1rem",
          }}
          onClick={() => setShowContactModal(false)}
        >
          <div
            style={{
              backgroundColor: "#1e293b",
              color: "#f8fafc",
              border: "1px solid #334155",
              borderRadius: "0.75rem",
              padding: "1.25rem",
              maxWidth: "24rem",
              width: "100%",
              boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.5)",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
              <h3 style={{ margin: 0, fontSize: "1rem", fontWeight: 600 }}>Provider Payment Contact</h3>
              <button
                type="button"
                onClick={() => setShowContactModal(false)}
                style={{ background: "transparent", border: "none", color: "#94a3b8", cursor: "pointer" }}
              >
                <X size={18} />
              </button>
            </div>
            <p style={{ fontSize: "0.8125rem", color: "#94a3b8", marginBottom: "1rem" }}>
              Please reach out to your FlexCRM service provider to renew your subscription and maintain uninterrupted access:
            </p>
            <div
              style={{
                padding: "0.75rem",
                borderRadius: "0.5rem",
                backgroundColor: "#0f172a",
                border: "1px solid #334155",
                fontSize: "0.875rem",
                fontWeight: 600,
                color: "#60a5fa",
                wordBreak: "break-word",
              }}
            >
              {sub.provider_contact}
            </div>
            <div style={{ marginTop: "1.25rem", display: "flex", justifyContent: "flex-end" }}>
              <button
                type="button"
                onClick={() => setShowContactModal(false)}
                style={{
                  padding: "0.375rem 0.75rem",
                  borderRadius: "0.375rem",
                  backgroundColor: "#334155",
                  color: "#f8fafc",
                  fontSize: "0.75rem",
                  fontWeight: 500,
                  border: "none",
                  cursor: "pointer",
                }}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
