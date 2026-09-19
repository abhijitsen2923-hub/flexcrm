// Recovery for the classic SPA-after-deploy failure. When a new frontend build
// ships, Vite emits new content-hashed chunk filenames and the old ones stop
// existing. A tab that was already open still runs the old index-*.js, so
// navigating to a lazy route requests an old chunk hash that is gone — and
// Cloudflare's `not_found_handling: single-page-application` answers the missing
// /assets/*.js with index.html, so the dynamic import() rejects with a module /
// MIME error and the app would crash into the ErrorBoundary.
//
// The fix is to do the one thing the user would otherwise do by hand: reload
// once to fetch the fresh index.html + current chunk hashes. A sessionStorage
// timestamp guards against a reload loop, so a genuinely broken build surfaces
// the error instead of reloading forever. The reload only ever fires on
// navigation to a not-yet-loaded route (every dynamic import is route-level), so
// it cannot interrupt someone typing in an already-loaded form.

const RELOAD_STAMP_KEY = "flexcrm:chunk-reloaded-at";
const RELOAD_COOLDOWN_MS = 10_000;

const CHUNK_ERROR_RE =
  /dynamically imported module|module script|ChunkLoadError|Failed to fetch dynamically|Importing a module script failed|error loading dynamically imported module|Unable to preload/i;

/** True when an error looks like a failed dynamic-import / stale-chunk load. */
export function isChunkLoadError(error: unknown): boolean {
  if (!error) {
    return false;
  }
  const message =
    error instanceof Error
      ? error.message
      : typeof error === "string"
        ? error
        : String((error as { message?: unknown })?.message ?? "");
  return CHUNK_ERROR_RE.test(message);
}

function reloadedRecently(): boolean {
  try {
    const last = Number(sessionStorage.getItem(RELOAD_STAMP_KEY) || 0);
    return Number.isFinite(last) && Date.now() - last < RELOAD_COOLDOWN_MS;
  } catch {
    // Private mode / storage blocked — don't let the guard suppress a needed reload.
    return false;
  }
}

/**
 * Reload the page once to pick up a fresh build, guarded against a loop: at most
 * one reload per RELOAD_COOLDOWN_MS, so a genuinely broken build shows the error
 * instead of reloading endlessly. Returns true if a reload was triggered, false
 * if suppressed by the cooldown. Use this from a signal that is ITSELF proof of
 * a stale chunk (e.g. Vite's `vite:preloadError` event).
 */
export function reloadOnce(): boolean {
  if (reloadedRecently()) {
    return false;
  }
  try {
    sessionStorage.setItem(RELOAD_STAMP_KEY, String(Date.now()));
  } catch {
    // Ignore — still attempt the reload below.
  }
  window.location.reload();
  return true;
}

/**
 * Reload once (via {@link reloadOnce}) only when `error` looks like a stale-chunk
 * failure; returns false for non-chunk errors so real bugs still surface. Use
 * this where the caller has an error object but isn't certain it's a chunk issue
 * (the lazy-import wrapper, the ErrorBoundary).
 */
export function reloadOnceForChunkError(error: unknown): boolean {
  if (!isChunkLoadError(error)) {
    return false;
  }
  return reloadOnce();
}
