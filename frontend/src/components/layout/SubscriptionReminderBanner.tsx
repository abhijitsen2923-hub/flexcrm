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

  const urgencyClass = isExpired ? "expired" : isUrgent ? "urgent" : "warning";
  const iconColor = isExpired ? "#fca5a5" : "#fcd34d";

  return (
    <>
      <div className={`sub-reminder-banner sub-reminder-banner--${urgencyClass}`} role="alert">
        <div className="sub-reminder-banner__content">
          <AlertTriangle size={18} className="sub-reminder-banner__icon" style={{ color: iconColor }} />
          <div className="sub-reminder-banner__text">
            <span>Your subscription is about to end in </span>
            <span className={`sub-reminder-banner__badge sub-reminder-banner__badge--${urgencyClass}`}>{daysLabel}</span>.
            <span>
              {" "}Kindly contact with your provider for make the paymant to use the application semmlessly.
            </span>
          </div>
        </div>

        <div className="sub-reminder-banner__actions">
          {sub.provider_contact && (
            <button
              type="button"
              className="sub-reminder-banner__contact-btn"
              onClick={() => setShowContactModal(true)}
            >
              <PhoneCall size={12} />
              <span>Contact Provider</span>
            </button>
          )}

          <button
            type="button"
            className="sub-reminder-banner__close-btn"
            onClick={() => setDismissed(true)}
            aria-label="Dismiss payment reminder"
            title="Dismiss for this session (reappears on refresh)"
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
