import assert from "node:assert/strict";
import test from "node:test";

test("VALUE 101 client requests stay on the page's own origin (P0-1 UI gateway)", async () => {
  let value101ApiUrl;
  try {
    ({ value101ApiUrl } = await import("../app/features/learn/value101-api.mjs"));
  } catch {
    value101ApiUrl = undefined;
  }

  assert.equal(
    value101ApiUrl?.("/tutorials/value-101/completion-report"),
    "/api/tutorials/value-101/completion-report",
  );
});

test("no frontend source names an API port or a build-time API origin", async () => {
  const { readFile } = await import("node:fs/promises");
  const sources = await Promise.all([
    "../app/page.tsx", "../app/features/learn/value101-api.mjs", "../app/features/data/research-suite-api.mjs",
    "../app/features/shared/api.ts", "../app/features/market/ReplayExportPanel.tsx",
  ].map((name) => readFile(new URL(name, import.meta.url), "utf8")));
  for (const source of sources) {
    assert.doesNotMatch(source, /127\.0\.0\.1:8766|localhost:8766|NEXT_PUBLIC_VALUE_API_ORIGIN/);
  }
});

test("API helpers: relative base and launcher-access classification", async () => {
  const { apiUrl, API_BASE, isLauncherAccessFailure } = await import("../app/features/shared/api.ts");
  assert.equal(API_BASE, "/api");
  assert.equal(apiUrl("/workspace"), "/api/workspace");
  assert.equal(apiUrl("runs/a"), "/api/runs/a");
  assert.equal(isLauncherAccessFailure(421, undefined), true);
  assert.equal(isLauncherAccessFailure(502, "GF_GATEWAY_SESSION_MISMATCH"), true);
  // A missing session file means the engine is starting or stopped: offline, not "open from launcher".
  assert.equal(isLauncherAccessFailure(502, "GF_GATEWAY_SESSION_UNAVAILABLE"), false);
  assert.equal(isLauncherAccessFailure(403, "GF_SESSION_INVALID"), true);
  assert.equal(isLauncherAccessFailure(403, "GF_RUN_LOCKED"), false);
  assert.equal(isLauncherAccessFailure(502, "GF_GATEWAY_UPSTREAM_UNAVAILABLE"), false);
  assert.equal(isLauncherAccessFailure(500, "GF_SESSION_INVALID"), false);
});

test("VALUE 101 client requests honour an explicitly supplied API origin", async () => {
  let value101ApiUrl;
  try {
    ({ value101ApiUrl } = await import("../app/features/learn/value101-api.mjs"));
  } catch {
    value101ApiUrl = undefined;
  }

  assert.equal(
    value101ApiUrl?.("tutorials/value-101", "http://127.0.0.1:9901/"),
    "http://127.0.0.1:9901/api/tutorials/value-101",
  );
});
