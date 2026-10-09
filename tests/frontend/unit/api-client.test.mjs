import assert from "node:assert/strict";
import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import {
  API_BASE, ApiError, DEFAULT_TIMEOUT_MS, FRONTEND_CONTRACT_VERSION, LONG_TIMEOUT_MS, LauncherAccessError, TIMEOUT_ERROR_CODE,
  apiFetch, apiUrl, classifyRefreshFailure, contractStatus, defaultTimeoutMs, getJson, readJson, sendJson,
} from "../../../app/lib/api.ts";

// P1 spec 4 (W2): the single API client.
const root = path.resolve(import.meta.dirname, "../../..");

function withFetch(t, implementation) {
  const original = globalThis.fetch;
  t.after(() => { globalThis.fetch = original; });
  globalThis.fetch = implementation;
}

// A fetch that never answers but honours its AbortSignal, like the real one.
const hangingFetch = (_url, init) => new Promise((_resolve, reject) => {
  const abort = () => reject(new DOMException("aborted", "AbortError"));
  if (init.signal.aborted) abort();
  else init.signal.addEventListener("abort", abort);
});

test("apiUrl builds same-origin /api paths", () => {
  assert.equal(API_BASE, "/api");
  assert.equal(apiUrl("workspace"), "/api/workspace");
  assert.equal(apiUrl("/runs/r1"), "/api/runs/r1");
});

test("the status is checked before the body: an HTML error page is an ApiError with its status, not a parse error", async () => {
  const error = await readJson(new Response("<html>502 Bad Gateway</html>", { status: 502 })).catch((reason) => reason);
  assert.ok(error instanceof ApiError);
  assert.equal(error.status, 502);
  assert.equal(error.code, null);
  assert.equal(error.message, "Request failed (HTTP 502)");
});

test("an error body gives message, code and detail", async () => {
  const body = { error: "Study changed", error_code: "GF_REVISION_CONFLICT", current_revision: 3 };
  const error = await readJson(new Response(JSON.stringify(body), { status: 409 })).catch((reason) => reason);
  assert.ok(error instanceof ApiError);
  assert.equal(error.message, "Study changed");
  assert.equal(error.code, "GF_REVISION_CONFLICT");
  assert.deepEqual(error.detail, body);
});

test("a launcher refusal is a LauncherAccessError; an unreadable success is never data", async () => {
  await assert.rejects(readJson(new Response(JSON.stringify({ error_code: "GF_SESSION_INVALID" }), { status: 403 })), LauncherAccessError);
  await assert.rejects(readJson(new Response("", { status: 421 })), LauncherAccessError);
  await assert.rejects(readJson(new Response("not json", { status: 200 })), (error) => error instanceof ApiError && error.code === "GF_RESPONSE_UNREADABLE");
  await assert.rejects(readJson(new Response("null", { status: 200 })), (error) => error instanceof ApiError && error.code === "GF_RESPONSE_UNREADABLE");
  assert.deepEqual(await readJson(new Response(JSON.stringify({ ok: true }), { status: 200 })), { ok: true });
});

test("a request that outlives its timeout is an ApiError GF_REQUEST_TIMEOUT with status 0 (counted as unreachable)", async (t) => {
  withFetch(t, hangingFetch);
  const error = await apiFetch("/api/workspace", { timeoutMs: 20 }).catch((reason) => reason);
  assert.ok(error instanceof ApiError);
  assert.equal(error.status, 0);
  assert.equal(error.code, TIMEOUT_ERROR_CODE);
  assert.equal(classifyRefreshFailure(error), "unreachable");
});

test("the caller's own abort still rejects with AbortError, not a timeout", async (t) => {
  withFetch(t, hangingFetch);
  const controller = new AbortController();
  const pending = apiFetch("/api/workspace", { signal: controller.signal, timeoutMs: 10_000 });
  controller.abort();
  await assert.rejects(pending, (error) => error.name === "AbortError" && !(error instanceof ApiError));
  const already = new AbortController();
  already.abort();
  await assert.rejects(apiFetch("/api/workspace", { signal: already.signal }), (error) => error.name === "AbortError");
});

test("timeouts: 30 s for ordinary reads, long for whole-Run reads and every mutation", () => {
  assert.equal(DEFAULT_TIMEOUT_MS, 30_000);
  assert.equal(defaultTimeoutMs("/api/workspace"), DEFAULT_TIMEOUT_MS);
  assert.equal(defaultTimeoutMs("/api/runs/r1"), DEFAULT_TIMEOUT_MS);
  assert.equal(defaultTimeoutMs("/api/health", "HEAD"), DEFAULT_TIMEOUT_MS);
  for (const url of ["/api/runs/r1/market/dispatch?year=2025", "/api/runs/r1/network-redispatch/annual", "/api/runs/r1/domains/network/summary",
    "/api/runs/r1/results/vre-curtailment", "/api/comparisons?runs=a,b", "/api/data-workbench/v1/jobs", "/api/runs/r1/replay-exports"]) {
    assert.equal(defaultTimeoutMs(url), LONG_TIMEOUT_MS, url);
  }
  assert.equal(defaultTimeoutMs("/api/projects", "POST"), LONG_TIMEOUT_MS);
  assert.equal(defaultTimeoutMs("/api/runs/r1", "DELETE"), LONG_TIMEOUT_MS);
});

test("getJson asks for no-store and passes the timeout through; sendJson posts JSON", async (t) => {
  const calls = [];
  withFetch(t, async (url, init) => { calls.push({ url, init }); return new Response(JSON.stringify({ ok: true }), { status: 200 }); });
  assert.deepEqual(await getJson("/api/workspace"), { ok: true });
  assert.equal(calls[0].init.cache, "no-store");
  assert.ok(calls[0].init.signal instanceof AbortSignal);
  assert.deepEqual(await sendJson("/api/projects", { name: "x" }), { ok: true });
  assert.equal(calls[1].init.method, "POST");
  assert.equal(calls[1].init.headers["Content-Type"], "application/json");
  assert.equal(calls[1].init.body, JSON.stringify({ name: "x" }));
});

test("contract version: unknown until health answers; a service that does not report it is a different version", () => {
  assert.equal(FRONTEND_CONTRACT_VERSION, "value.expanded-frontend/v1");
  assert.equal(contractStatus(null), "unknown");
  assert.equal(contractStatus({ status: "ok", frontend_contract_version: FRONTEND_CONTRACT_VERSION }), "match");
  assert.equal(contractStatus({ status: "ok", frontend_contract_version: "value.expanded-frontend/v2" }), "mismatch");
  assert.equal(contractStatus({ status: "ok" }), "mismatch");
});

async function sources(directory, found = []) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const full = path.join(directory, entry.name);
    if (entry.isDirectory()) await sources(full, found);
    else if (/\.(tsx?|mjs)$/.test(entry.name)) found.push(full);
  }
  return found;
}

test("every request goes through app/lib/api.ts: no bare fetch() and no second client elsewhere in app/", async () => {
  const hits = [];
  for (const file of await sources(path.join(root, "app"))) {
    const relative = path.relative(root, file).split(path.sep).join("/");
    if (relative === "app/lib/api.ts") continue;
    const text = await readFile(file, "utf8");
    text.split("\n").forEach((line, index) => {
      if (/(?<![\w.])fetch\(/.test(line) || /globalThis\.fetch|window\.fetch/.test(line)) hits.push(`${relative}:${index + 1}: ${line.trim().slice(0, 120)}`);
      if (/export (?:async )?function (?:getJson|fetchNetworkJson)\b/.test(line)) hits.push(`${relative}:${index + 1}: second JSON client`);
    });
  }
  assert.deepEqual(hits, [], hits.join("\n"));
});
