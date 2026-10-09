import assert from "node:assert/strict";
import test from "node:test";
import { ApiError, LauncherAccessError, classifyRefreshFailure, getJson } from "../../../app/lib/api.ts";
import { OFFLINE_AFTER_FAILURES, pollDelay, serviceState } from "../../../app/lib/poll.ts";
import { lifecycleNotice } from "../../../app/features/runs/lifecycleView.ts";

// P0-3 S8: degraded service, backoff and lifecycle notices.
const respond = (status, body) => async () => new Response(typeof body === "string" ? body : JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

test("getJson raises ApiError with status and code; a bad body is not mistaken for data", async (t) => {
  const original = globalThis.fetch;
  t.after(() => { globalThis.fetch = original; });
  globalThis.fetch = respond(503, { error: "catalogue stale", error_code: "GF_MODULE_CATALOG_STALE" });
  await assert.rejects(getJson("/api/workspace"), (error) => error instanceof ApiError && error.status === 503 && error.code === "GF_MODULE_CATALOG_STALE");
  globalThis.fetch = respond(500, "<html>broken</html>");
  await assert.rejects(getJson("/api/workspace"), (error) => error instanceof ApiError && error.status === 500);
  globalThis.fetch = respond(403, { error_code: "GF_SESSION_INVALID" });
  await assert.rejects(getJson("/api/workspace"), LauncherAccessError);
});

test("refresh failures are classified for the rail", () => {
  assert.equal(classifyRefreshFailure(new LauncherAccessError("GF_SESSION_INVALID")), "launcher");
  assert.equal(classifyRefreshFailure(new ApiError("x", 500, null)), "service_error");
  assert.equal(classifyRefreshFailure(new TypeError("Failed to fetch")), "unreachable");
});

test("polling backs off exponentially to 30 s", () => {
  assert.deepEqual([0, 1, 2, 3, 4, 5, 10].map(pollDelay), [2000, 4000, 8000, 16000, 30000, 30000, 30000]);
});

test("degraded after a failure or a degraded health status; offline after three failures", () => {
  assert.equal(serviceState(0, null, false), "loading");
  assert.equal(serviceState(0, "ok", true), "online");
  assert.equal(serviceState(0, "degraded", true), "degraded");
  assert.equal(serviceState(1, "ok", true), "degraded");
  assert.equal(serviceState(OFFLINE_AFTER_FAILURES - 1, null, false), "degraded");
  assert.equal(serviceState(OFFLINE_AFTER_FAILURES, "ok", true), "offline");
});

test("worker exited and worker lost are explained with their next step", () => {
  const exited = lifecycleNotice({ status: "failed", error_code: "GF_WORKER_EXITED", recovery: { latest_safe_point: { available: true, year: 2025, artifact: "x" } } });
  assert.equal(exited.kind, "worker_exited");
  assert.equal(exited.body, "Run stopped unexpectedly (worker exited). You can resume from the last annual checkpoint.");
  assert.equal(exited.canResume, true);
  assert.equal(lifecycleNotice({ status: "failed", error_code: "GF_WORKER_EXITED", source_study_status: "trash" }).canResume, false);
  assert.match(lifecycleNotice({ status: "failed", error_code: "GF_WORKER_EXITED", recovery: { latest_safe_point: { available: false } } }).resumeBlockedReason, /No verified annual checkpoint/);
  const lost = lifecycleNotice({ status: "running", worker_liveness: "lost" });
  assert.equal(lost.kind, "worker_lost");
  assert.match(lost.body, /^VALUE lost contact with this Run's worker \(for example after a restart\)\./);
  assert.equal(lifecycleNotice({ status: "running", worker_liveness: "alive" }), null);
  assert.equal(lifecycleNotice({ status: "failed", error_code: "GF_ZONAL_SOLVER" }), null);
});
