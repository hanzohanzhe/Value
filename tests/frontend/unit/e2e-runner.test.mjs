import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
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
