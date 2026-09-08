/**
 * Click-to-contact link builders — `tel:`, WhatsApp (`wa.me`) and `mailto:`.
 *
 * Frontend-only: tapping these opens the device's dialer / WhatsApp / mail app
 * with the number or address pre-filled. No backend involved. A full
 * WhatsApp-Business integration (templated sends + chat logged inside FlexCRM)
 * is a separate future project; these links are the interim UX.
 */

// FlexCRM tenants are India-based — a bare 10-digit number gets +91 for WhatsApp
// (wa.me requires a full international number, digits only, no "+").
const DEFAULT_COUNTRY_CODE = "91";

/** `tel:` href from a raw phone string, or null if there's nothing dialable. */
export function telHref(raw: string | null | undefined): string | null {
  if (!raw) return null;
  // Keep a leading "+" and digits; the dialer ignores spaces/dashes anyway.
  const cleaned = raw.trim().replace(/[^\d+]/g, "");
  return cleaned.replace(/\D/g, "") ? `tel:${cleaned}` : null;
}

/** Digits-with-country-code for wa.me, or null if not usable. */
export function toWhatsAppNumber(raw: string | null | undefined): string | null {
  if (!raw) return null;
  let digits = raw.replace(/\D/g, "").replace(/^0+/, ""); // drop trunk-prefix zeros
  if (!digits) return null;
  if (digits.length === 10) digits = DEFAULT_COUNTRY_CODE + digits;
  return digits;
}

/** `https://wa.me/<number>` href, or null if the phone isn't usable. */
export function whatsAppHref(raw: string | null | undefined): string | null {
  const n = toWhatsAppNumber(raw);
  return n ? `https://wa.me/${n}` : null;
}

/** `mailto:` href from an email, or null if it isn't a plausible address. */
export function mailtoHref(email: string | null | undefined): string | null {
  if (!email) return null;
  const trimmed = email.trim();
  return trimmed.includes("@") ? `mailto:${trimmed}` : null;
}
