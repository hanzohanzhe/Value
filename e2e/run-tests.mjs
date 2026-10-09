import { spawnSync } from "node:child_process";
import fs from "node:fs";
import net from "node:net";
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
//   VALUE_E2E_OUTPUT_DIR=<d>  artefact directory (default test-results; with --offline a
//                             temporary folder removed afterwards, so set it to keep traces)
//   VALUE_E2E_STATE_ROOT=<d>  parent of the services' temporary state; by default this
//                             runner creates one and removes it after Playwright exits
//
// The services listen on the fixed ports 18800 (UI) and 18766 (API): the UI
// gateway is started with --api-origin http://127.0.0.1:18766 and several specs
// name 18800. The page itself only calls its own origin (/api, P0-1), so the
// build needs no API address. Two e2e runs on one host therefore
// cannot overlap (P0_CONVENTIONS section 11: e2e and `p0_gate full` runs are
// serialised across lanes); an occupied port stops this runner before the build.
const E2E_PORTS = { ui: 18800, api: 18766 };
const root = path.resolve(import.meta.dirname, "..");
const offline = process.argv.includes("--offline");
const passthrough = process.argv.slice(2).filter((argument) => argument !== "--offline");
const environment = { ...process.env };
delete environment.NEXT_PUBLIC_VALUE_API_ORIGIN;
const subset = offline ? JSON.parse(fs.readFileSync(path.join(root, "e2e", "offline-subset.json"), "utf8")) : null;
let reportFolder = null;
// start-e2e-services.mjs creates its state directory inside this root. Playwright
// stops the web server with SIGTERM (gracefulShutdown in playwright.config.ts),
// but if the services die without cleaning up, the runner still removes it.
let stateRoot = null;
if (!environment.VALUE_E2E_STATE_ROOT) {
  stateRoot = fs.mkdtempSync(path.join(os.tmpdir(), "value-e2e-state-"));
  environment.VALUE_E2E_STATE_ROOT = stateRoot;
}
function finish(code) {
  if (stateRoot) fs.rmSync(stateRoot, { recursive: true, force: true });
  if (reportFolder) fs.rmSync(reportFolder, { recursive: true, force: true });
  process.exit(code);
}
if (offline) {
  environment.VALUE_E2E_UI_ONLY = "1";
  // The report and, unless VALUE_E2E_OUTPUT_DIR says otherwise, the traces and
  // screenshots of the registered failures live in a folder finish() removes.
  reportFolder = fs.mkdtempSync(path.join(os.tmpdir(), "value-e2e-offline-"));
  if (!environment.VALUE_E2E_JSON) environment.VALUE_E2E_JSON = path.join(reportFolder, "report.json");
  if (!environment.VALUE_E2E_OUTPUT_DIR) environment.VALUE_E2E_OUTPUT_DIR = path.join(reportFolder, "test-results");
  // A stale report from an earlier run must never be mistaken for this run's.
  fs.rmSync(environment.VALUE_E2E_JSON, { force: true });
}
function portFree(port, host = "127.0.0.1") {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.once("error", () => resolve(false));
    server.listen(port, host, () => server.close(() => resolve(true)));
  });
}
const wanted = environment.VALUE_E2E_UI_ONLY === "1" ? [E2E_PORTS.ui] : [E2E_PORTS.ui, E2E_PORTS.api];
const busy = [];
for (const port of wanted) if (!(await portFree(port))) busy.push(port);
if (busy.length) {
  console.error(`e2e: 127.0.0.1:${busy.join(", ")} already in use - another e2e or \`p0_gate full\` run (other lane?) `
    + "holds the fixed e2e ports. e2e runs are serialised across lanes (P0_CONVENTIONS section 11); wait and retry.");
  finish(1);
}
const vinext = path.join(root, "node_modules", "vinext", "dist", "cli.js");
if (process.env.VALUE_E2E_SKIP_BUILD !== "1") {
  const built = spawnSync(process.execPath, [vinext, "build"], { cwd: root, env: environment, stdio: "inherit" });
  if (built.status !== 0) finish(built.status ?? 1);
}
const playwrightArguments = offline
  ? [...subset.specs, `--project=${subset.project ?? "desktop-chromium"}`, `--timeout=${subset.timeout_ms ?? 30000}`, ...passthrough]
  : passthrough;
const result = spawnSync(
  process.execPath,
  [path.join(root, "node_modules", "@playwright", "test", "cli.js"), "test", ...playwrightArguments],
  { cwd: root, env: environment, stdio: "inherit" },
);
if (!offline) finish(result.status ?? 1);

// Offline mode: Playwright's own exit code is ignored on purpose (registered
// failures make it non-zero); the ratchet decides.
let report;
try {
  report = JSON.parse(fs.readFileSync(environment.VALUE_E2E_JSON, "utf8"));
} catch (error) {
  console.error(`offline e2e: no usable Playwright report at ${environment.VALUE_E2E_JSON} (${error.message})`);
  finish(1);
}
const evaluation = evaluateOffline(report, subset);
console.log(`\n${describeEvaluation(evaluation)}`);
if (!process.env.VALUE_E2E_OUTPUT_DIR) {
  console.log("offline e2e: traces and screenshots were written to a temporary folder and removed; "
    + "set VALUE_E2E_OUTPUT_DIR=<folder> to keep them.");
}
finish(evaluation.ok ? 0 : 1);
