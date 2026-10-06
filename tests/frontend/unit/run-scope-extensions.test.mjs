import assert from "node:assert/strict";
import test from "node:test";
import { EXTENSIONS_DO_NOT_RUN_NOTE, PSM_ONLY_RUN_MODES, RUN_SCOPE_LABELS, runModesForStudy, runScopeOptionLabel } from "../../../app/features/workspace/runScope.ts";

// F-D2 (DECISIONS A16-3, design spec 11.5): the one-day lesson runs the market
// step only, so its scope option says so whenever the Study selects extensions.
test("only the one-day lesson is a market-step-only scope", () => {
  assert.deepEqual([...PSM_ONLY_RUN_MODES], ["value_101_day"]);
  assert.equal(EXTENSIONS_DO_NOT_RUN_NOTE, "(extensions do not run)");
});

test("the one-day option carries the note only when extensions are selected", () => {
  const withExtension = { extensions: { value_101: {} }, selected_extensions: ["value-toy-audit-extension"] };
  assert.equal(runScopeOptionLabel("value_101_day", withExtension), "One-day market lesson (extensions do not run)");
  assert.equal(runScopeOptionLabel("value_101_day", { ...withExtension, selected_extensions: [] }), RUN_SCOPE_LABELS.value_101_day);
  assert.equal(runScopeOptionLabel("value_101_day", undefined), RUN_SCOPE_LABELS.value_101_day);
  for (const mode of ["smoke", "two_year_smoke", "two_year", "full"]) assert.equal(runScopeOptionLabel(mode, withExtension), RUN_SCOPE_LABELS[mode], mode);
});

test("the one-day option stays offered; preflight, not the list, blocks the combination", () => {
  const pack = { allowed_run_modes: ["smoke", "two_year_smoke", "value_101_day", "two_year"] };
  const study = { extensions: { value_101: {} }, selected_extensions: ["value-toy-audit-extension"] };
  assert.deepEqual(runModesForStudy(study, pack), ["smoke", "two_year_smoke", "value_101_day", "two_year"]);
});
