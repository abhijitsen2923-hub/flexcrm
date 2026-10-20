// Decisions for renewing the login (refresh-token rotation) when several tabs share one saved session.
// Every renewal replaces the refresh token, and each tab keeps its own in-memory copy (services/storage.ts), so a tab
// can hold a token another tab has already replaced. These rules keep such a tab signed in instead of logging it out.
// Pure (no storage / network) so they're unit-tested; services/http.ts applies them.

export interface RenewalSession {
  accessToken: string;
  refreshToken: string;
  accessTokenExpiresAt?: string | null;
}

// An access token this close to expiry isn't worth adopting — renew instead.
const ACCESS_MARGIN_MS = 10_000;

function accessStillGood(session: RenewalSession, now: number): boolean {
  const expiresAt = Date.parse(session.accessTokenExpiresAt ?? "");
  return Boolean(session.accessToken) && !Number.isNaN(expiresAt) && expiresAt - now > ACCESS_MARGIN_MS;
}

export type BeforeRenewal<S extends RenewalSession> =
  | { kind: "adopt"; session: S } // another tab already renewed — use its session, no request
  | { kind: "renew"; refreshToken: string }; // renew with this refresh token

/**
 * Just before renewing (inside the cross-tab lock): if the saved session already carries a different refresh token,
 * another tab renewed meanwhile — use its fresh access token, or renew with ITS refresh token (ours is replaced).
 */
export function beforeRenewal<S extends RenewalSession>(mine: S, saved: S | null, now: number): BeforeRenewal<S> {
  if (saved && saved.refreshToken && saved.refreshToken !== mine.refreshToken) {
    return accessStillGood(saved, now) ? { kind: "adopt", session: saved } : { kind: "renew", refreshToken: saved.refreshToken };
  }
  return { kind: "renew", refreshToken: mine.refreshToken };
}

export type AfterRefusal<S extends RenewalSession> =
  | { kind: "adopt"; session: S } // another tab won the race — its saved session is the live one
  | { kind: "ended"; clearSaved: boolean }; // this login really ended; clear the saved one only if it's still ours

/**
 * The server refused the renewal (401). If the saved session has moved on to another refresh token, another tab
 * renewed — keep going with it. Otherwise the login ended; the saved copy is cleared only when it still holds the
 * refused token, so a tab can never wipe a newer login saved by another tab.
 */
export function afterRefusal<S extends RenewalSession>(refusedToken: string, saved: S | null): AfterRefusal<S> {
  if (saved && saved.refreshToken && saved.refreshToken !== refusedToken) {
    return { kind: "adopt", session: saved };
  }
  // A saved copy without a refresh token is useless too.
  return { kind: "ended", clearSaved: !saved?.refreshToken || saved.refreshToken === refusedToken };
}
