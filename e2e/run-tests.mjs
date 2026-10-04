import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { describeEvaluation, evaluateOffline } from "./offline-ratchet.mjs";

// Usage: node e2e/run-tests.mjs [playwright test arguments...]
//   e.g. node e2e/run-tests.mjs e2e/market-visibility.spec.ts --project=desktop-chromium
// Every argument is passed through to `playwright test`.
//
//   node e2e/run-tests.mjs --offline
//     runs the offline subset (e2e/offline-subset.json) against the UI only,
//     then applies the ratchet in e2e/offline-ratchet.mjs: unregistered failures
//     and registered failures that now pass both fail. Exit code is the ratchet's.
//
// Environment switches:
//   VALUE_E2E_UI_ONLY=1       serve only the UI; no Python API (specs that mock /api); implied by --offline
//   VALUE_E2E_CHROMIUM=<exe>  use this browser instead of the one Playwright expects
//   VALUE_E2E_SKIP_BUILD=1    reuse an existing dist/ (build first with `vinext build`)
//   VALUE_E2E_JSON=<file>     also write Playwright's JSON report there
//   VALUE_E2E_OUTPUT_DIR=<d>  artefact directory (default test-results)
const root = path.resolve(import.meta.dirname, "..");
const offline = process.argv.includes("--offline");
const passthrough = process.argv.slice(2).filter((argument) => argument !== "--offline");
const environment = {
  ...process.env,
  NEXT_PUBLIC_VALUE_API_ORIGIN: "http://127.0.0.1:18766",
};
const subset = offline ? JSON.parse(fs.readFileSync(path.join(root, "e2e", "offline-subset.json"), "utf8")) : null;
let reportFolder = null;
if (offline) {
  environment.VALUE_E2E_UI_ONLY = "1";
  if (!environment.VALUE_E2E_JSON) {
    reportFolder = fs.mkdtempSync(path.join(os.tmpdir(), "value-e2e-offline-"));
    environment.VALUE_E2E_JSON = path.join(reportFolder, "report.json");
  }
  // A stale report from an earlier run must never be mistaken for this run's.
  fs.rmSync(environment.VALUE_E2E_JSON, { force: true });
}
const vinext = path.join(root, "node_modules", "vinext", "dist", "cli.js");
if (process.env.VALUE_E2E_SKIP_BUILD !== "1") {
  const built = spawnSync(process.execPath, [vinext, "build"], { cwd: root, env: environment, stdio: "inherit" });
  if (built.status !== 0) process.exit(built.status ?? 1);
}
const playwrightArguments = offline
  ? [...subset.specs, `--project=${subset.project ?? "desktop-chromium"}`, `--timeout=${subset.timeout_ms ?? 30000}`, ...passthrough]
  : passthrough;
const result = spawnSync(
  process.execPath,
  [path.join(root, "node_modules", "@playwright", "test", "cli.js"), "test", ...playwrightArguments],
  { cwd: root, env: environment, stdio: "inherit" },
);
if (!offline) process.exit(result.status ?? 1);

// Offline mode: Playwright's own exit code is ignored on purpose (registered
// failures make it non-zero); the ratchet decides.
let report;
try {
  report = JSON.parse(fs.readFileSync(environment.VALUE_E2E_JSON, "utf8"));
} catch (error) {
  console.error(`offline e2e: no usable Playwright report at ${environment.VALUE_E2E_JSON} (${error.message})`);
  process.exit(1);
}
const evaluation = evaluateOffline(report, subset);
console.log(`\n${describeEvaluation(evaluation)}`);
if (reportFolder) fs.rmSync(reportFolder, { recursive: true, force: true });
process.exit(evaluation.ok ? 0 : 1);
