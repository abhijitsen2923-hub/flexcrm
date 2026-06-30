// Cloudflare Worker for the FlexCRM static site.
//
// - fetch:     serves the Vite SPA via the static-assets binding. (With Workers
//              Static Assets, asset/SPA requests are served by the platform
//              before the Worker runs; this delegation is a safe fallback.)
// - scheduled: on a cron, pings the backend DB health endpoint to keep the Neon
//              serverless compute warm so real requests don't pay a cold-start.

const DEFAULT_KEEPALIVE_URL =
  "https://flexcrm-backend-539170436218.asia-south1.run.app/health/db";

export default {
  async fetch(request, env) {
    return env.ASSETS.fetch(request);
  },

  async scheduled(_event, env, ctx) {
    const url = env.KEEPALIVE_URL || DEFAULT_KEEPALIVE_URL;
    ctx.waitUntil(
      fetch(url, { method: "GET", headers: { "user-agent": "flexcrm-keepalive" } }).catch(() => {})
    );
  },
};
