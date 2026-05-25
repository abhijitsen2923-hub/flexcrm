import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";


export default defineConfig({
  plugins: [react()],
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
