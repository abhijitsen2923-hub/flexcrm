// Cloudflare Worker for the FlexCRM static site.
//
// - fetch:     serves the Vite SPA via the static-assets binding. (With Workers
//              Static Assets, asset/SPA requests are served by the platform
//              before the Worker runs; this delegation is a safe fallback.)
// - scheduled: two daily crons (worker branches on event.cron):
//                • 30 3 * * *  → reminders + follow-ups + Meta token refresh + a Meta poll
//                • 30 15 * * * → a second Meta poll
//              So the Meta lead-sync poll runs TWICE daily (a backstop; OAuth pages
//              also get real-time webhooks), token refresh + reminders run ONCE daily.
//              All calls are secret-guarded (X-Cron-Key === backend CRON_SECRET).
//
// NOTE: the previous every-4-min /health/db keep-alive was removed — on Neon's
// free tier it kept the compute awake 24/7 and exhausted the monthly compute
// allowance, hard-suspending the DB for the rest of the cycle. Neon now
// auto-suspends when idle and wakes on the first request (client retries cover
// the brief cold start). The twice-daily Meta poll only wakes Neon twice a day,
// so it's free-tier-safe. Re-add a keep-alive only on a paid Neon plan.

const BACKEND = "https://flexcrm-backend-539170436218.asia-south1.run.app";
const DEFAULT_REMINDERS_URL = `${BACKEND}/api/v1/cron/registration-reminders`;
const DEFAULT_FOLLOWUP_URL = `${BACKEND}/api/v1/cron/followup-reminders`;
const DEFAULT_META_SYNC_URL = `${BACKEND}/api/v1/cron/meta-lead-sync`;
const DEFAULT_META_TOKEN_REFRESH_URL = `${BACKEND}/api/v1/cron/meta-token-refresh`;

// The daily cron that also carries reminders + follow-ups + token refresh. The
// second cron (30 15) only runs the Meta poll.
const DAILY_CRON = "30 3 * * *";

export default {
  async fetch(request, env) {
    return env.ASSETS.fetch(request);
  },

  async scheduled(event, env, ctx) {
    // Always send a body → a Content-Length header is present (Google's front-end
    // in front of Cloud Run returns 411 for a body-less POST). Auth is the shared
    // secret in X-Cron-Key (Worker secret CRON_SECRET === backend CRON_SECRET).
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

    // Meta lead-sync poll — runs on BOTH crons (twice daily).
    ctx.waitUntil(post(env.META_SYNC_URL || DEFAULT_META_SYNC_URL));

    // Once-daily work rides only the morning cron. (event.cron is undefined when
    // triggered manually via the dashboard "Trigger" button — treat that as daily.)
    if (!event.cron || event.cron === DAILY_CRON) {
      ctx.waitUntil(post(env.REMINDERS_URL || DEFAULT_REMINDERS_URL));
      ctx.waitUntil(post(env.FOLLOWUP_URL || DEFAULT_FOLLOWUP_URL));
      ctx.waitUntil(post(env.META_TOKEN_REFRESH_URL || DEFAULT_META_TOKEN_REFRESH_URL));
    }
  },
};
