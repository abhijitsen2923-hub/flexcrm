import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";


export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      // Only inject the SW registration script when building the customer portal
      // entry point.  The staff console gets a normal (no-SW) build.
      scope: "/customer/",
      manifest: {
        name: "FlexCRM Customer Portal",
        short_name: "FlexCRM",
        description: "Track your property booking, payments, and documents.",
        theme_color: "#2563eb",
        background_color: "#f8fafc",
        display: "standalone",
        start_url: "/customer/payments",
        scope: "/customer/",
        icons: [
          {
            src: "/icons/pwa.svg",
            sizes: "any",
            type: "image/svg+xml",
            purpose: "any maskable"
          }
        ]
      },
      workbox: {
        // NetworkFirst for all customer API calls — falls back to cache when
        // offline so previously viewed payment / document data is still readable.
        runtimeCaching: [
          {
            urlPattern: /\/api\/v1\/customer\/documents\/.+/,
            handler: "CacheFirst",
            options: {
              cacheName: "cp-documents",
              expiration: {
                maxEntries: 50,
                maxAgeSeconds: 7 * 24 * 60 * 60   // 7 days
              }
            }
          },
          {
            urlPattern: /\/api\/v1\/customer\//,
            handler: "NetworkFirst",
            options: {
              cacheName: "cp-api",
              networkTimeoutSeconds: 8,
              expiration: {
                maxEntries: 100,
                maxAgeSeconds: 24 * 60 * 60         // 24 hours
              }
            }
          }
        ]
      }
    })
  ],
  server: {
    host: "0.0.0.0",
    port: 5173,
    // Vite v6 ships strict allowedHosts by default. Permit tunnel hostnames
    // and any LAN host so the dev server is reachable from another laptop
    // (via ngrok, the LAN IP, or any reverse proxy).
    allowedHosts: [".ngrok-free.dev", ".ngrok-free.app", ".ngrok.io", "localhost", "127.0.0.1"],
    // Single-tunnel deployment: ngrok fronts only this dev server, so we
    // proxy `/api` (and its WS upgrade) to the backend container. The
    // browser then makes same-origin requests and CORS is moot.
    proxy: {
      "/api": {
        target: "http://backend:8000",
        changeOrigin: true,
        ws: true
      }
    }
  }
});
