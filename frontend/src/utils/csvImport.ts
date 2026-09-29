// CSV lead import, sent in chunks (pure — unit-tested in tests/csvImport.test.ts).
//
// A whole file in one request ran for minutes on large sheets: past the 60 s client timeout the user saw
// "The request timed out" while the server kept importing. The browser now splits the file into chunks of
// IMPORT_CHUNK_ROWS data rows (each chunk = the header + its rows, sent as-is so the server parses exactly
// what it always did) and posts them one after another with a progress count. `rowOffset` keeps the row
// numbers in errors matching the sheet.
import type { LeadImportResult } from "../services/leads";

export const IMPORT_CHUNK_ROWS = 50;

export interface CsvChunk {
  text: string;
  rowOffset: number; // data rows before this chunk (server: row numbers start at 2 + rowOffset)
  rows: number;
}

export interface ImportProgress {
  done: number;
  total: number;
  waiting?: boolean; // the server asked us to slow down; the same chunk is re-sent shortly
}

// Waits before re-sending a chunk the server rate-limited (429). Cumulatively longer than the limiter's
// 60 s window, so the last try always lands in a fresh window.
export const RATE_LIMIT_WAITS_MS = [10_000, 20_000, 40_000];

export const MIXED_ENCODING_MESSAGE =
  "This file mixes text encodings, so some names would come out garbled. Open it in Excel and use " +
  "Save As → “CSV UTF-8 (Comma delimited)”, then upload that file.";

export interface ChunkedImportOutcome {
  result: LeadImportResult;
  failure: { error: unknown; rowsBefore: number } | null; // a chunk failed → the rest wasn't sent
  stopped: boolean; // the caller asked to stop between chunks
}

/** True when the bytes contain at least one well-formed multi-byte UTF-8 sequence. */
function hasUtf8Sequence(bytes: Uint8Array): boolean {
  for (let i = 0; i < bytes.length; i += 1) {
    const lead = bytes[i];
    const length = lead >= 0xc2 && lead <= 0xdf ? 2 : lead >= 0xe0 && lead <= 0xef ? 3 : lead >= 0xf0 && lead <= 0xf4 ? 4 : 0;
    if (length === 0 || i + length > bytes.length) continue;
    let valid = true;
    for (let k = 1; k < length; k += 1) {
      if ((bytes[i + k] & 0xc0) !== 0x80) valid = false;
    }
    if (valid) return true;
  }
  return false;
}

/** Bytes → text: UTF-8 (BOM dropped); UTF-16 when it has a BOM (Excel "Unicode text"); a legacy file with
 * no UTF-8 at all → Windows-1252 (Excel "CSV" on Windows). A file that MIXES UTF-8 with stray legacy bytes
 * is refused (MIXED_ENCODING_MESSAGE) — decoding it either way would silently garble names. */
export function decodeCsvBytes(bytes: Uint8Array): string {
  let text: string;
  if (bytes.length >= 2 && bytes[0] === 0xff && bytes[1] === 0xfe) {
    text = new TextDecoder("utf-16le").decode(bytes);
  } else if (bytes.length >= 2 && bytes[0] === 0xfe && bytes[1] === 0xff) {
    text = new TextDecoder("utf-16be").decode(bytes);
  } else {
    try {
      text = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    } catch {
      if (hasUtf8Sequence(bytes)) throw new Error(MIXED_ENCODING_MESSAGE);
      text = new TextDecoder("windows-1252").decode(bytes);
    }
  }
  return text.charCodeAt(0) === 0xfeff ? text.slice(1) : text;
}

/** The delimiter the server picks: whichever of , ; TAB | appears most in the first non-empty line
 * (comma on a tie / when none appears) — mirrors LeadImportService.import_csv. */
export function detectDelimiter(text: string): string {
  const firstLine = text.split(/\r\n|\n|\r/).find((line) => line.trim() !== "") ?? "";
  let best = ",";
  let bestCount = 0;
  for (const candidate of [",", ";", "\t", "|"]) {
    const count = firstLine.split(candidate).length - 1;
    if (count > bestCount) {
      best = candidate;
      bestCount = count;
    }
  }
  return best;
}

/** Split CSV text into records (raw text, line endings removed) the way Python's csv module reads it: a
 * quote is special only at the START of a field (so 5'10" stays literal), inside quotes the delimiter, ""
 * and line breaks are content. Empty lines are dropped, as csv.DictReader does. */
export function splitCsvRecords(text: string, delimiter = detectDelimiter(text)): string[] {
  const records: string[] = [];
  let start = 0;
  let inQuotes = false;
  let fieldStart = true;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (inQuotes) {
      if (ch === '"') {
        if (text[i + 1] === '"') i += 1; // escaped quote
        else inQuotes = false;
      }
      continue;
    }
    if (ch === '"' && fieldStart) {
      inQuotes = true;
      fieldStart = false;
    } else if (ch === delimiter) {
      fieldStart = true;
    } else if (ch === "\n" || ch === "\r") {
      records.push(text.slice(start, i));
      if (ch === "\r" && text[i + 1] === "\n") i += 1;
      start = i + 1;
      fieldStart = true;
    } else {
      fieldStart = false;
    }
  }
  if (start < text.length) records.push(text.slice(start));
  return records.filter((record) => record !== "");
}

/** Header + data rows → chunks of `size` data rows, each a complete little CSV. No header → no chunks. */
export function buildImportChunks(text: string, size = IMPORT_CHUNK_ROWS): { chunks: CsvChunk[]; totalRows: number } {
  const [header, ...rows] = splitCsvRecords(text);
  if (header === undefined || rows.length === 0) return { chunks: [], totalRows: 0 };
  const chunks: CsvChunk[] = [];
  for (let offset = 0; offset < rows.length; offset += size) {
    const part = rows.slice(offset, offset + size);
    chunks.push({ text: `${header}\n${part.join("\n")}\n`, rowOffset: offset, rows: part.length });
  }
  return { chunks, totalRows: rows.length };
}

export function emptyImportResult(): LeadImportResult {
  return { created: 0, promoted: 0, skipped: 0, errors: [], duplicates: [] };
}

export function mergeImportResults(into: LeadImportResult, part: LeadImportResult): LeadImportResult {
  return {
    created: into.created + part.created,
    promoted: into.promoted + part.promoted,
    skipped: into.skipped + part.skipped,
    errors: [...into.errors, ...part.errors],
    duplicates: [...into.duplicates, ...part.duplicates]
  };
}

/** A 429 from the rate limiter: rejected BEFORE the import ran, so re-sending the same chunk is safe. */
export function isRateLimited(error: unknown): boolean {
  return (error as { response?: { status?: number } } | null)?.response?.status === 429;
}

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

/** Upload chunks one after another. A rate-limited chunk (429 — nothing was imported) is re-sent after a
 * pause; any other failure stops the import (never re-sent blindly — a timed-out chunk may have been
 * saved). Also stops between chunks when `shouldStop()` says so. */
export async function runChunkedImport(
  chunks: CsvChunk[],
  upload: (chunk: CsvChunk) => Promise<LeadImportResult>,
  {
    onProgress,
    shouldStop,
    wait = sleep,
    rateLimitWaitsMs = RATE_LIMIT_WAITS_MS
  }: {
    onProgress?: (progress: ImportProgress) => void;
    shouldStop?: () => boolean;
    wait?: (ms: number) => Promise<void>;
    rateLimitWaitsMs?: number[];
  } = {}
): Promise<ChunkedImportOutcome> {
  const total = chunks.reduce((sum, chunk) => sum + chunk.rows, 0);
  let result = emptyImportResult();
  let done = 0;
  onProgress?.({ done, total });
  for (const chunk of chunks) {
    if (shouldStop?.()) return { result, failure: null, stopped: true };
    for (let attempt = 0; ; attempt += 1) {
      try {
        result = mergeImportResults(result, await upload(chunk));
        break;
      } catch (error) {
        if (isRateLimited(error) && attempt < rateLimitWaitsMs.length) {
          onProgress?.({ done, total, waiting: true });
          await wait(rateLimitWaitsMs[attempt]);
          continue;
        }
        return { result, failure: { error, rowsBefore: done }, stopped: false };
      }
    }
    done += chunk.rows;
    onProgress?.({ done, total });
  }
  return { result, failure: null, stopped: false };
}

// ---- background import job --------------------------------------------------------------------------------
// One import at a time per browser tab, run OUTSIDE any page: the upload dialog closes as soon as a file is
// picked, the user keeps working (any page), and a small status card (components/imports/LeadImportStatus)
// shows progress and the result. Plain store (subscribe/getState) for React's useSyncExternalStore.

export type ImportJobStatus = "idle" | "running" | "done" | "failed";

export interface ImportJobState {
  id: number; // increments per started import
  status: ImportJobStatus;
  fileName: string;
  skipDuplicates: boolean; // as chosen for this import (the recovery advice depends on it)
  progress: ImportProgress | null;
  result: LeadImportResult | null;
  stopped: { rowsBefore: number; totalRows: number; reason: string } | null; // done, but only part-way
  error: string | null; // failed before any chunk completed
}

export interface ImportFileSource {
  name: string;
  bytes: () => Promise<Uint8Array>;
}

export const NO_ROWS_MESSAGE = "The file has no rows to import (a header row plus at least one lead).";
const CANCELLED = new Error("import cancelled");

export function createImportJobStore() {
  let state: ImportJobState = {
    id: 0, status: "idle", fileName: "", skipDuplicates: true, progress: null, result: null, stopped: null, error: null
  };
  // Bumped by reset(): a running import whose generation is stale stops before its next request and never
  // writes state again (e.g. the user signed out — nothing of theirs may reach the next user in this tab).
  let generation = 0;
  let announcedId = 0;
  const listeners = new Set<() => void>();
  const set = (patch: Partial<ImportJobState>) => {
    state = { ...state, ...patch };
    listeners.forEach((listener) => listener());
  };

  return {
    getState: (): ImportJobState => state,
    subscribe(listener: () => void): () => void {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    isRunning: (): boolean => state.status === "running",
    /** Hide a finished import's card. */
    dismiss(): void {
      if (state.status !== "running") set({ status: "idle", progress: null, result: null, stopped: null, error: null });
    },
    /** Forget everything — also stops a running import before its next request (sign-out, session end). */
    reset(): void {
      generation += 1;
      set({ status: "idle", fileName: "", progress: null, result: null, stopped: null, error: null });
    },
    /** True the first time it's asked about a finished import (so its toast shows once, even across remounts). */
    shouldAnnounce(id: number): boolean {
      if (id <= announcedId) return false;
      announcedId = id;
      return true;
    },
    /** Start an import unless one is already running (then returns false and changes nothing). */
    async start(
      file: ImportFileSource,
      upload: (chunk: CsvChunk) => Promise<LeadImportResult>,
      describeError: (error: unknown) => string,
      options: { skipDuplicates?: boolean; wait?: (ms: number) => Promise<void>; rateLimitWaitsMs?: number[] } = {}
    ): Promise<boolean> {
      if (state.status === "running") return false;
      const mine = ++generation;
      const current = () => mine === generation;
      const update = (patch: Partial<ImportJobState>) => {
        if (current()) set(patch);
      };
      const { skipDuplicates = true, ...runOptions } = options;
      set({
        id: state.id + 1, status: "running", fileName: file.name, skipDuplicates,
        progress: null, result: null, stopped: null, error: null
      });
      try {
        const { chunks, totalRows } = buildImportChunks(decodeCsvBytes(await file.bytes()));
        if (chunks.length === 0) {
          update({ status: "failed", error: NO_ROWS_MESSAGE });
          return true;
        }
        const { result, failure } = await runChunkedImport(
          chunks,
          // Checked before every request, retries included: a reset import never sends another chunk.
          (chunk) => (current() ? upload(chunk) : Promise.reject(CANCELLED)),
          { ...runOptions, shouldStop: () => !current(), onProgress: (progress) => update({ progress }) }
        );
        if (!current()) return true;
        if (failure && failure.rowsBefore === 0) {
          update({ status: "failed", result, error: describeError(failure.error) });
        } else {
          update({
            status: "done",
            result,
            stopped: failure
              ? { rowsBefore: failure.rowsBefore, totalRows, reason: describeError(failure.error) }
              : null
          });
        }
      } catch (error) {
        update({ status: "failed", error: describeError(error) });
      }
      return true;
    }
  };
}

export type ImportJobStore = ReturnType<typeof createImportJobStore>;

/** One-line summary of a finished import, e.g. "120 leads created, 3 duplicates skipped, 2 row errors". */
export function importSummaryLine(result: LeadImportResult): string {
  const parts = [`${result.created} lead${result.created === 1 ? "" : "s"} created`];
  if (result.promoted > 0) parts.push(`${result.promoted} promoted to customer`);
  if (result.skipped > 0) parts.push(`${result.skipped} duplicate${result.skipped === 1 ? "" : "s"} skipped`);
  const flagged = result.duplicates.filter((d) => !d.skipped).length;
  if (flagged > 0) parts.push(`${flagged} duplicate${flagged === 1 ? "" : "s"} flagged`);
  if (result.errors.length > 0) parts.push(`${result.errors.length} row error${result.errors.length === 1 ? "" : "s"}`);
  return parts.join(", ");
}
