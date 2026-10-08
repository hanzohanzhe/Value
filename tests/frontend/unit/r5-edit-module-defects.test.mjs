import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { runModesForStudy, TWO_YEAR_RUN_MODES } from "../../../app/features/workspace/runScope.ts";

// R5-3 低2 (edit-module role): a one-year Study is not offered a scope that
// readiness refuses ("requires a project covering at least two years").
const pack = { allowed_run_modes: ["smoke", "two_year_smoke", "value_101_day", "two_year"] };
const study = { extensions: { value_101: {} } };

test("a one-year Study is not offered the two-year scopes", () => {
  assert.deepEqual([...TWO_YEAR_RUN_MODES], ["two_year_smoke", "two_year"]);
  assert.deepEqual(runModesForStudy({ ...study, start_year: 2025, end_year: 2025 }, pack), ["smoke", "value_101_day"]);
  assert.deepEqual(runModesForStudy({ ...study, start_year: "2025", end_year: "2025" }, pack), ["smoke", "value_101_day"]);
});

test("two or more years, or unknown years, keep every scope", () => {
  assert.deepEqual(runModesForStudy({ ...study, start_year: 2025, end_year: 2026 }, pack), pack.allowed_run_modes);
  assert.deepEqual(runModesForStudy(study, pack), pack.allowed_run_modes);
});

test("a frozen recovery keeps its required scope", () => {
  const recovery = { extensions: { frozen_recovery: { required_mode: "two_year" } }, start_year: 2025, end_year: 2025 };
  assert.deepEqual(runModesForStudy(recovery, pack), ["two_year"]);
});

// R5-3 低1 / 低6 / 中2: page wiring (source contract).
const page = readFileSync(new URL("../../../app/page.tsx", import.meta.url), "utf8");
test("the saved-revision notice survives the readiness re-check", () => {
  assert.match(page, /keepNotice: saved/);
  assert.match(page, /if \(!options\.keepNotice\) setNotice\(""\)/);
});
test("the module badge counts experimental modules separately", () => {
  assert.match(page, /experimentalModules \? ` · \$\{experimentalModules\} experimental` : ""/);
});
test("a quarantine Disable names the manifest copies it moved", () => {
  assert.match(page, /parked_manifests/);
});
