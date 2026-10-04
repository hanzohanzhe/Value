import assert from "node:assert/strict";
import { readdir, readFile } from "node:fs/promises";
import test from "node:test";

// P0-9 S0 review: the gate (VALUE_NODE) and build/bin/vnode run Playwright
// with a node that is not on PATH, so the web server must be started by the
// same executable (process.execPath), never by a bare `node`.
test("playwright.config.ts starts the e2e services with the node running Playwright", async () => {
  const source = await readFile(new URL("../../../playwright.config.ts", import.meta.url), "utf8");
  const command = source.match(/webServer:\s*\{[\s\S]*?command:\s*([^\n]+)/);
  assert.ok(command, "webServer.command not found");
  assert.match(command[1], /process\.execPath/);
  assert.doesNotMatch(command[1], /^["'`]node\s/, "a bare `node` fails with exit 127 when node is not on PATH");
});

test("offline runs keep their report and artefacts in the folder the runner removes", async () => {
  const source = await readFile(new URL("../../../e2e/run-tests.mjs", import.meta.url), "utf8");
  assert.match(source, /environment\.VALUE_E2E_OUTPUT_DIR = path\.join\(reportFolder, "test-results"\)/);
  assert.match(source, /environment\.VALUE_E2E_JSON = path\.join\(reportFolder, "report\.json"\)/);
  assert.match(source, /if \(reportFolder\) fs\.rmSync\(reportFolder, \{ recursive: true, force: true \}\)/);
});

test("an occupied fixed e2e port stops the runner before the build", async () => {
  const source = await readFile(new URL("../../../e2e/run-tests.mjs", import.meta.url), "utf8");
  const check = source.indexOf("for (const port of wanted) if (!(await portFree(port)))");
  assert.ok(check > 0, "port preflight missing");
  assert.ok(check < source.indexOf('[vinext, "build"]'), "the preflight must run before `vinext build`");
  assert.match(source, /const E2E_PORTS = \{ ui: 18800, api: 18766 \}/);
});

test("specs write screenshots to the test's output folder, not a fixed test-results/ path", async () => {
  const folder = new URL("../../../e2e/", import.meta.url);
  const specs = (await readdir(folder)).filter((name) => name.endsWith(".spec.ts"));
  assert.ok(specs.length > 0);
  for (const name of specs) {
    const source = await readFile(new URL(name, folder), "utf8");
    assert.doesNotMatch(source, /["'`]test-results\//, `${name} writes into a fixed test-results/ folder`);
  }
});
