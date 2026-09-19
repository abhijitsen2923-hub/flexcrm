import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { reloadOnce } from "./utils/chunkReload";
import "./styles/global.css";


// Backstop for a stale chunk after a deploy: Vite fires `vite:preloadError` when
// a dynamically-imported module (JS or its CSS) fails to load. That event only
// ever means a preload failed, so recover with a one-time guarded reload — an
// open tab silently picks up the new build instead of crashing. Fires only on
// navigation to a not-yet-loaded route, never while typing on a loaded page.
window.addEventListener("vite:preloadError", (event) => {
  event.preventDefault();
  reloadOnce();
});


const container = document.getElementById("root");
if (!container) {
  throw new Error('Root container with id="root" not found in index.html');
}

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>
);
