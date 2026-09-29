// Unit tests for the chunked CSV import helpers (src/utils/csvImport.ts).
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  MIXED_ENCODING_MESSAGE,
  NO_ROWS_MESSAGE,
  buildImportChunks,
  createImportJobStore,
  importSummaryLine,
  decodeCsvBytes,
  detectDelimiter,
  mergeImportResults,
  runChunkedImport,
  splitCsvRecords,
  type CsvChunk
} from "../src/utils/csvImport.ts";
import type { LeadImportResult } from "../src/services/leads.ts";

const result = (created: number, extra: Partial<LeadImportResult> = {}): LeadImportResult => ({
  created, promoted: 0, skipped: 0, errors: [], duplicates: [], ...extra
});

test("decode: UTF-8 with or without BOM, Windows-1252 and UTF-16 files", () => {
  const utf8 = new TextEncoder().encode("name,city\nAsha,Kolkata ₹\n");
  assert.equal(decodeCsvBytes(utf8), "name,city\nAsha,Kolkata ₹\n");
  assert.equal(decodeCsvBytes(new Uint8Array([0xef, 0xbb, 0xbf, ...utf8])), "name,city\nAsha,Kolkata ₹\n");
  // "Café" + euro sign saved by Excel on Windows (not valid UTF-8).
  assert.equal(decodeCsvBytes(new Uint8Array([0x43, 0x61, 0x66, 0xe9, 0x20, 0x80])), "Café €");
  const utf16 = new Uint8Array([0xff, 0xfe, 0x61, 0x00, 0x2c, 0x00, 0x62, 0x00]);
  assert.equal(decodeCsvBytes(utf16), "a,b");
});

test("decode: a UTF-8 file with a stray legacy byte is refused, not silently garbled", () => {
  const name = new TextEncoder().encode("प्रिया,José\nO");
  const mixed = new Uint8Array([...name, 0x92, 0x42, 0x72, 0x69, 0x65, 0x6e]); // O’Brien with a cp1252 quote
  assert.throws(() => decodeCsvBytes(mixed), { message: MIXED_ENCODING_MESSAGE });
});

test("delimiter detection mirrors the server", () => {
  assert.equal(detectDelimiter("name;phone;city\n"), ";");
  assert.equal(detectDelimiter("name\tphone\n"), "\t");
  assert.equal(detectDelimiter("\n\nname,phone\n"), ",");
  assert.equal(detectDelimiter("name\n"), ",");
});

test("records: quoted fields keep delimiters, escaped quotes and line breaks", () => {
  const text = 'name,notes\r\n"Roy, Asha","said ""hi""\r\non two lines"\r\nBina,plain\n\n\nChitra,"x"\n';
  assert.deepEqual(splitCsvRecords(text), [
    "name,notes",
    '"Roy, Asha","said ""hi""\r\non two lines"',
    "Bina,plain",
    'Chitra,"x"'
  ]);
});

test("records: a quote in the middle of a field is literal (like Python's csv)", () => {
  assert.deepEqual(splitCsvRecords('name,height\nAsha,5\'10"\nBina,6\n'), ["name,height", "Asha,5'10\"", "Bina,6"]);
});

test("records: blank comma-only rows are kept (the server skips them), empty lines dropped", () => {
  assert.deepEqual(splitCsvRecords("a,b\n,,\n\nc,d"), ["a,b", ",,", "c,d"]);
});

test("chunks carry the header, their rows and the row offset", () => {
  const rows = Array.from({ length: 7 }, (_, i) => `P${i},+9199${i}`);
  const { chunks, totalRows } = buildImportChunks(["name,phone", ...rows].join("\n"), 3);
  assert.equal(totalRows, 7);
  assert.deepEqual(chunks.map((c) => [c.rowOffset, c.rows]), [[0, 3], [3, 3], [6, 1]]);
  assert.equal(chunks[1].text, "name,phone\nP3,+91993\nP4,+91994\nP5,+91995\n");
  assert.deepEqual(buildImportChunks("name,phone\n"), { chunks: [], totalRows: 0 });
  assert.deepEqual(buildImportChunks(""), { chunks: [], totalRows: 0 });
});

test("results merge", () => {
  const merged = mergeImportResults(
    result(2, { skipped: 1, errors: [{ row: 3, error: "x" }] }),
    result(3, { promoted: 1, errors: [{ row: 60, error: "y" }] })
  );
  assert.deepEqual(merged, {
    created: 5, promoted: 1, skipped: 1, errors: [{ row: 3, error: "x" }, { row: 60, error: "y" }], duplicates: []
  });
});

const chunk = (rowOffset: number, rows: number): CsvChunk => ({ text: "", rowOffset, rows });

test("upload runs chunks in order, merges results and reports progress", async () => {
  const seen: number[] = [];
  const progress: string[] = [];
  const outcome = await runChunkedImport(
    [chunk(0, 50), chunk(50, 50), chunk(100, 20)],
    async (c) => {
      seen.push(c.rowOffset);
      return result(c.rows);
    },
    { onProgress: (p) => progress.push(`${p.done}/${p.total}`) }
  );
  assert.deepEqual(seen, [0, 50, 100]);
  assert.equal(outcome.result.created, 120);
  assert.deepEqual(progress, ["0/120", "50/120", "100/120", "120/120"]);
  assert.equal(outcome.failure, null);
  assert.equal(outcome.stopped, false);
});

test("upload stops at the first failed chunk and never re-sends it", async () => {
  let calls = 0;
  const boom = new Error("timeout");
  const outcome = await runChunkedImport([chunk(0, 50), chunk(50, 50), chunk(100, 50)], async (c) => {
    calls += 1;
    if (c.rowOffset === 50) throw boom;
    return result(c.rows);
  });
  assert.equal(calls, 2);
  assert.equal(outcome.result.created, 50);
  assert.deepEqual(outcome.failure, { error: boom, rowsBefore: 50 });
});

test("a rate-limited chunk is re-sent after a pause; other errors are not", async () => {
  const rateLimited = { response: { status: 429 } };
  const attempts: number[] = [];
  const waits: number[] = [];
  const progress: string[] = [];
  const outcome = await runChunkedImport(
    [chunk(0, 50), chunk(50, 50)],
    async (c) => {
      attempts.push(c.rowOffset);
      if (c.rowOffset === 50 && attempts.filter((o) => o === 50).length <= 2) throw rateLimited;
      return result(c.rows);
    },
    {
      wait: async (ms) => { waits.push(ms); },
      rateLimitWaitsMs: [5, 10, 20],
      onProgress: (p) => progress.push(`${p.done}/${p.total}${p.waiting ? " waiting" : ""}`)
    }
  );
  assert.deepEqual(attempts, [0, 50, 50, 50]);
  assert.deepEqual(waits, [5, 10]);
  assert.equal(outcome.failure, null);
  assert.equal(outcome.result.created, 100);
  assert.ok(progress.includes("50/100 waiting"));

  // Still limited after every pause → reported as a failure, not an endless loop.
  const stuck = await runChunkedImport([chunk(0, 50)], async () => { throw rateLimited; }, {
    wait: async () => {}, rateLimitWaitsMs: [1, 1]
  });
  assert.equal(stuck.failure?.rowsBefore, 0);

  // A timeout (maybe saved server-side) is never re-sent.
  let calls = 0;
  const timedOut = await runChunkedImport([chunk(0, 50)], async () => { calls += 1; throw new Error("timeout"); }, {
    wait: async () => {}
  });
  assert.equal(calls, 1);
  assert.ok(timedOut.failure);
});

test("upload stops between chunks when asked", async () => {
  let calls = 0;
  const outcome = await runChunkedImport(
    [chunk(0, 50), chunk(50, 50)],
    async (c) => {
      calls += 1;
      return result(c.rows);
    },
    { shouldStop: () => calls >= 1 }
  );
  assert.equal(calls, 1);
  assert.equal(outcome.stopped, true);
  assert.equal(outcome.result.created, 50);
});

// ---- background import job store ---------------------------------------------------------------------------

const file = (text: string, name = "leads.csv") => ({ name, bytes: async () => new TextEncoder().encode(text) });
const describe = (error: unknown) => (error instanceof Error ? error.message : "failed");

test("job: runs in the background, reports progress, and finishes with the merged result", async () => {
  const store = createImportJobStore();
  const seen: string[] = [];
  store.subscribe(() => {
    const s = store.getState();
    seen.push(`${s.status}${s.progress ? ` ${s.progress.done}/${s.progress.total}` : ""}`);
  });
  const rows = Array.from({ length: 120 }, (_, i) => `P${i},+91${i}`);
  const started = store.start(file(["name,phone", ...rows].join("\n")), async (c) => result(c.rows), describe);
  assert.equal(store.isRunning(), true); // the caller can close the dialog right away
  assert.equal(await started, true);
  const state = store.getState();
  assert.equal(state.status, "done");
  assert.equal(state.fileName, "leads.csv");
  assert.equal(state.result?.created, 120);
  assert.equal(state.stopped, null);
  assert.deepEqual(seen, ["running", "running 0/120", "running 50/120", "running 100/120", "running 120/120", "done 120/120"]);
});

test("job: only one import at a time", async () => {
  const store = createImportJobStore();
  let release: () => void = () => {};
  const gate = new Promise<void>((resolve) => { release = resolve; });
  const first = store.start(file("name,phone\nA,1\n"), async (c) => { await gate; return result(c.rows); }, describe);
  assert.equal(await store.start(file("name,phone\nB,2\n"), async (c) => result(c.rows), describe), false);
  release();
  await first;
  assert.equal(store.getState().result?.created, 1);
  store.dismiss();
  assert.equal(store.getState().status, "idle");
  assert.equal(await store.start(file("name,phone\nB,2\n"), async (c) => result(c.rows), describe), true);
  assert.equal(store.getState().id, 2);
});

test("job: a part-way stop is 'done' with the reason; nothing imported is 'failed'", async () => {
  const store = createImportJobStore();
  const rows = Array.from({ length: 120 }, (_, i) => `P${i},+91${i}`);
  await store.start(file(["name,phone", ...rows].join("\n")), async (c) => {
    if (c.rowOffset === 100) throw new Error("The request timed out.");
    return result(c.rows);
  }, describe);
  assert.equal(store.getState().status, "done");
  assert.deepEqual(store.getState().stopped, { rowsBefore: 100, totalRows: 120, reason: "The request timed out." });

  await store.start(file("name,phone\nA,1\n"), async () => { throw new Error("CSV must include a `contact_name` column"); }, describe);
  assert.equal(store.getState().status, "failed");
  assert.equal(store.getState().error, "CSV must include a `contact_name` column");

  await store.start(file("name,phone\n"), async (c) => result(c.rows), describe);
  assert.equal(store.getState().error, NO_ROWS_MESSAGE);

  store.dismiss(); // dismissing never interrupts a running import
  assert.equal(store.getState().status, "idle");
});

test("job: reset (sign-out) stops a running import before its next request and clears everything", async () => {
  const store = createImportJobStore();
  const rows = Array.from({ length: 150 }, (_, i) => `P${i},+91${i}`);
  const sent: number[] = [];
  let release: () => void = () => {};
  const gate = new Promise<void>((resolve) => { release = resolve; });
  const run = store.start(
    file(["name,phone", ...rows].join("\n"), "someone-elses.csv"),
    async (c) => {
      sent.push(c.rowOffset);
      if (c.rowOffset === 0) await gate;
      return result(c.rows);
    },
    describe,
    { skipDuplicates: false }
  );
  await new Promise((r) => setTimeout(r, 0));
  assert.equal(store.getState().skipDuplicates, false);
  store.reset(); // the user signed out while chunk 1 was in flight
  release();
  await run;
  assert.deepEqual(sent, [0]); // no further chunk was sent
  assert.equal(store.getState().status, "idle");
  assert.equal(store.getState().fileName, "");
  assert.equal(store.getState().result, null);
  assert.equal(await store.start(file("name,phone\nA,1\n"), async (c) => result(c.rows), describe), true);
  assert.equal(store.getState().status, "done");
});

test("job: each finished import is announced once", async () => {
  const store = createImportJobStore();
  await store.start(file("name,phone\nA,1\n"), async (c) => result(c.rows), describe);
  const { id } = store.getState();
  assert.equal(store.shouldAnnounce(id), true);
  assert.equal(store.shouldAnnounce(id), false); // e.g. the status card remounted
});

test("summary line", () => {
  assert.equal(importSummaryLine(result(1)), "1 lead created");
  assert.equal(
    importSummaryLine(result(5, {
      promoted: 1, skipped: 2, errors: [{ row: 3, error: "x" }],
      duplicates: [
        { row: 4, contact_name: null, contact_email: null, contact_phone: null, matched: "#1", skipped: true },
        { row: 5, contact_name: null, contact_email: null, contact_phone: null, matched: "#2", skipped: false }
      ]
    })),
    "5 leads created, 1 promoted to customer, 2 duplicates skipped, 1 duplicate flagged, 1 row error"
  );
});
