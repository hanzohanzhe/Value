import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { runModesForStudy, TWO_YEAR_RUN_MODES } from "../../../app/features/workspace/runScope.ts";
import { catalogBadge } from "../../../app/features/modules/modulesPage.ts";
import { translator } from "../../../app/i18n/index.ts";

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

// R5-3 低1 / 低6 / 中2: page wiring (source contract).  P1 W3: the actions live
// in the workbench state, the badge on the /modules page.
const page = ["../../../app/features/shell/useWorkbenchState.ts", "../../../app/modules/ModulesView.tsx"]
  .map((file) => readFileSync(new URL(file, import.meta.url), "utf8")).join("\n");
test("the saved-revision notice survives the readiness re-check", () => {
  // RR-1 (3): the cancel answer ("The Study was not changed") survives the re-check too.
  assert.match(page, /checkPreflight\(effectivePreflightMode, \{ project, askMigration: false, keepNotice: true \}\);/);
  assert.match(page, /if \(!options\.keepNotice\) setNotice\(""\)/);
});
test("the module badge counts experimental modules separately", () => {
  // P1 W4b: the badge is catalogBadge (modulesPage.ts) through the dictionaries (spec 6.4 wording).
  const modules = [{ status: "ready" }, { status: "experimental" }, { status: "experimental" }, { status: "ready" }, { status: "unavailable" }];
  assert.equal(catalogBadge(modules, translator("en")), "2 of 5 ready · 2 experimental");
  assert.equal(catalogBadge(modules.slice(0, 1), translator("en")), "1 of 1 ready", "no experimental part when there is none");
  assert.equal(catalogBadge(modules, translator("zh")), "2/5 就绪 · 2 个实验性");
  assert.match(page, /catalogBadge\(workspace\.modules, t\)/);
});
test("a quarantine Disable names the manifest copies it moved", () => {
  assert.match(page, /parked_manifests/);
});
