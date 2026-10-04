import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { GROUPS, groupFiles } from "../../../scripts/run-ui-tests.mjs";

test("every group resolves to real test files, and no group is empty", () => {
  for (const group of Object.keys(GROUPS)) {
    const files = groupFiles(group);
    assert.ok(files.length > 0, `${group} matched no files`);
    assert.ok(files.every((file) => file.endsWith(".test.mjs")));
  }
});

test("groups keep browser harnesses, SSR tests and source scans apart", () => {
  assert.ok(groupFiles("unit").every((file) => file.startsWith("tests/frontend/unit/")));
  assert.ok(groupFiles("render").every((file) => file.startsWith("tests/frontend/render/")));
  assert.ok(groupFiles("harness").every((file) => /^tests\/frontend\/[^/]+\.test\.mjs$/.test(file)));
  const contracts = groupFiles("source-contracts");
  assert.ok(contracts.every((file) => /^tests\/[^/]+\.test\.mjs$/.test(file)));
  assert.ok(!contracts.includes("tests/rendered-html.test.mjs"), "rendered-html needs `vinext build`");
});

test("an unknown group is an error, never an empty green run", () => {
  assert.throws(() => groupFiles("units"), /unknown UI test group/);
});

test("package.json exposes the four groups under their documented names", async () => {
  const { scripts } = JSON.parse(await readFile(new URL("../../../package.json", import.meta.url), "utf8"));
  assert.equal(scripts["test:ui-unit"], "node scripts/run-ui-tests.mjs unit");
  assert.equal(scripts["test:ui-render"], "node scripts/run-ui-tests.mjs render");
  assert.equal(scripts["test:ui-harness"], "node scripts/run-ui-tests.mjs harness");
  assert.equal(scripts["test:source-contracts"], "node scripts/run-ui-tests.mjs source-contracts");
  assert.equal(scripts["test:e2e:offline"], "node e2e/run-tests.mjs --offline");
});
