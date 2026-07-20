// Cloudflare Worker for the FlexCRM static site.
//
// - fetch:     serves the Vite SPA via the static-assets binding. (With Workers
//              Static Assets, asset/SPA requests are served by the platform
//              before the Worker runs; this delegation is a safe fallback.)
// - scheduled: one daily cron (30 3 * * *) → POST the secret-guarded reminder
//              endpoints on the backend.
//
// NOTE: the previous every-4-min /health/db keep-alive was removed — on Neon's
// free tier it kept the compute awake 24/7 and exhausted the monthly compute
// allowance, hard-suspending the DB for the rest of the cycle. Neon now
// auto-suspends when idle and wakes on the first request (client retries cover
// the brief cold start). Re-add a keep-alive only on a paid Neon plan.

const DEFAULT_REMINDERS_URL =
  "https://flexcrm-backend-539170436218.asia-south1.run.app/api/v1/cron/registration-reminders";
const DEFAULT_FOLLOWUP_URL =
  "https://flexcrm-backend-539170436218.asia-south1.run.app/api/v1/cron/followup-reminders";

export default {
  async fetch(request, env) {
    return env.ASSETS.fetch(request);
  },

  async scheduled(event, env, ctx) {
    // Daily: trigger reminder dispatch on the backend. Auth is the shared secret
    // in X-Cron-Key (Worker secret CRON_SECRET === backend CRON_SECRET). Always
    // send a body → a Content-Length header is present (Google's front-end in
    // front of Cloud Run returns 411 for a body-less POST).
    const post = (url) =>
      fetch(url, {
        method: "POST",
        body: "{}",
        headers: {
          "x-cron-key": env.CRON_SECRET || "",
          "content-type": "application/json",
          "user-agent": "flexcrm-cron",
        },
      }).catch(() => {});
    ctx.waitUntil(post(env.REMINDERS_URL || DEFAULT_REMINDERS_URL));
    ctx.waitUntil(post(env.FOLLOWUP_URL || DEFAULT_FOLLOWUP_URL));
  },
};
