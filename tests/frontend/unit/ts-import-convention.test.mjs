import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

// Pure view modules are imported with an explicit `.ts` suffix so that
// `node --test` (which does not resolve extensionless TypeScript imports) and
// tsc / vinext agree. That needs allowImportingTsExtensions (P0-9 S0, S1).
test("tsconfig allows .ts import suffixes for every frontend project", async () => {
  const base = JSON.parse(await readFile(new URL("../../../tsconfig.json", import.meta.url), "utf8"));
  assert.equal(base.compilerOptions.allowImportingTsExtensions, true);
  assert.equal(base.compilerOptions.noEmit, true, "allowImportingTsExtensions requires noEmit");
  const frontend = JSON.parse(await readFile(new URL("../../../tsconfig.frontend.json", import.meta.url), "utf8"));
  assert.equal(frontend.extends, "./tsconfig.json");
});

test("node loads a pure app module through its .ts suffix", async () => {
  const { readWorkspaceLocation } = await import("../../../app/features/workspace/workspaceLocation.ts");
  assert.equal(readWorkspaceLocation("?run=r1").runId, "r1");
});
