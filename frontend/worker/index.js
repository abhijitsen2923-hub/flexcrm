// Cloudflare Worker for the FlexCRM static site.
//
// - fetch:     serves the Vite SPA via the static-assets binding. (With Workers
//              Static Assets, asset/SPA requests are served by the platform
//              before the Worker runs; this delegation is a safe fallback.)
// - scheduled: two crons (see wrangler.jsonc). Every 4 min → ping the backend DB
//              health endpoint to keep Neon warm. Daily (30 3 * * *) → POST the
//              secret-guarded registration-reminders endpoint on the backend.

const DEFAULT_KEEPALIVE_URL =
  "https://flexcrm-backend-539170436218.asia-south1.run.app/health/db";
const DEFAULT_REMINDERS_URL =
  "https://flexcrm-backend-539170436218.asia-south1.run.app/api/v1/cron/registration-reminders";

// Must match the daily schedule in wrangler.jsonc triggers.crons.
const REMINDERS_CRON = "30 3 * * *";

export default {
  async fetch(request, env) {
    return env.ASSETS.fetch(request);
  },

  async scheduled(event, env, ctx) {
    // Daily: trigger registration reminders on the backend. Auth is the shared
    // secret in X-Cron-Key (Worker secret CRON_SECRET === backend CRON_SECRET).
    if (event.cron === REMINDERS_CRON) {
      const url = env.REMINDERS_URL || DEFAULT_REMINDERS_URL;
      ctx.waitUntil(
        fetch(url, {
          method: "POST",
          headers: { "x-cron-key": env.CRON_SECRET || "", "user-agent": "flexcrm-cron" },
        }).catch(() => {})
      );
      return;
    }

    // Default (every 4 min): keep Neon's serverless compute warm.
    const url = env.KEEPALIVE_URL || DEFAULT_KEEPALIVE_URL;
    ctx.waitUntil(
      fetch(url, { method: "GET", headers: { "user-agent": "flexcrm-keepalive" } }).catch(() => {})
    );
  },
};
