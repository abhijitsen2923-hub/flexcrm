import { useSyncExternalStore } from "react";

import { leadsService } from "../services/leads";
import { setReloadBlocker } from "../utils/chunkReload";
import { createImportJobStore, type ImportJobState } from "../utils/csvImport";
import { extractErrorMessage } from "../utils/errors";

// The one lead CSV import of this browser tab. Lives outside every page, so it keeps running (and
// reporting) while the user works elsewhere in the app.
export const leadImportJob = createImportJobStore();

// While it runs: closing/reloading the tab asks first, and the automatic reload after a deploy waits.
// Registered here (not in a component) so it holds on every page.
let unloadGuard: ((event: BeforeUnloadEvent) => void) | null = null;
leadImportJob.subscribe(() => {
  const running = leadImportJob.isRunning();
  if (running && !unloadGuard) {
    unloadGuard = (event) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", unloadGuard);
  } else if (!running && unloadGuard) {
    window.removeEventListener("beforeunload", unloadGuard);
    unloadGuard = null;
  }
});
setReloadBlocker(() => leadImportJob.isRunning());

/** Sign-out / session end: stop a running import and forget the last one (never shown to the next user). */
export function resetLeadImport(): void {
  leadImportJob.reset();
}

export function useLeadImportJob(): ImportJobState {
  return useSyncExternalStore(leadImportJob.subscribe, leadImportJob.getState, leadImportJob.getState);
}

/** Start importing `file` in the background. Returns false if an import is already running. */
export function startLeadImport(file: File, skipDuplicates: boolean): Promise<boolean> {
  return leadImportJob.start(
    { name: file.name, bytes: async () => new Uint8Array(await file.arrayBuffer()) },
    (chunk) => leadsService.importCsvChunk(chunk.text, file.name, { skipDuplicates, rowOffset: chunk.rowOffset }),
    extractErrorMessage,
    { skipDuplicates }
  );
}
