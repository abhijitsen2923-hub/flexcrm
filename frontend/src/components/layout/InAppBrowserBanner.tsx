import { X } from "lucide-react";
import { useState } from "react";

const DISMISS_KEY = "flexcrm.iab-dismissed";

// In-app webviews (Instagram / Facebook / WhatsApp / etc.) often fail to persist
// localStorage, which silently drops the login session between actions ("Missing
// bearer token"). Detect them by their userAgent markers so we can nudge the user
// into a real browser, where the session sticks.
function isInAppBrowser(): boolean {
  if (typeof navigator === "undefined") {
    return false;
  }
  const ua = navigator.userAgent || "";
  return /Instagram|FBAN|FBAV|FB_IAB|WhatsApp|Line\/|Snapchat|Pinterest|Twitter|MicroMessenger|GSA/i.test(ua);
}

export function InAppBrowserBanner() {
  const [dismissed, setDismissed] = useState<boolean>(() => {
    try {
      return window.sessionStorage.getItem(DISMISS_KEY) === "1";
    } catch {
      return false;
    }
  });

  if (dismissed || !isInAppBrowser()) {
    return null;
  }

  const dismiss = () => {
    setDismissed(true);
    try {
      window.sessionStorage.setItem(DISMISS_KEY, "1");
    } catch {
      /* ignore */
    }
  };

  return (
    <div className="iab-banner" role="status">
      <span className="iab-banner__text">
        You&rsquo;re viewing FlexCRM inside another app&rsquo;s browser, which can sign you out
        unexpectedly. For the best experience, open this link in <strong>Chrome</strong> or{" "}
        <strong>Safari</strong> (tap the ⋯ menu → &ldquo;Open in browser&rdquo;).
      </span>
      <button className="iab-banner__close" onClick={dismiss} aria-label="Dismiss">
        <X size={16} />
      </button>
    </div>
  );
}
