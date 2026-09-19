import { lazy, type ComponentType } from "react";

import { reloadOnceForChunkError } from "./chunkReload";

// Drop-in replacement for React.lazy that recovers from a stale-chunk load after
// a deploy: if the dynamic import fails because the hashed chunk is gone, reload
// once to fetch the current build (see chunkReload.ts) instead of crashing into
// the ErrorBoundary. A non-chunk import error (a real bug in the module) is
// rethrown so it still surfaces normally.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function lazyWithReload<T extends ComponentType<any>>(
  factory: () => Promise<{ default: T }>
) {
  return lazy(async () => {
    try {
      return await factory();
    } catch (error) {
      if (reloadOnceForChunkError(error)) {
        // A reload is underway — return a promise that never resolves so nothing
        // renders (and no error surfaces) before the page navigates away.
        return new Promise<{ default: T }>(() => {});
      }
      throw error;
    }
  });
}
