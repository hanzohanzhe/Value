import assert from "node:assert/strict";
import test from "node:test";
import { RUN_SCOPE_LABELS, runModesForStudy, selectedRunScope } from "../app/features/workspace/runScope.ts";
import { preflightMatches } from "../app/features/workspace/preflightIdentity.ts";

test("ordinary Study hides pack-permitted lesson and invalidates the prior lesson scope", () => {
  const project = { id: "extension-study", revision_sha256: "revision", data_pack_id: "copy", extensions: {} };
  const pack = { allowed_run_modes: ["smoke", "two_year_smoke", "value_101_day", "two_year", "full"] };
  const options = runModesForStudy(project, pack);
  assert.deepEqual(options, ["smoke", "two_year_smoke", "two_year", "full"]);
  const selected = selectedRunScope("value_101_day", options);
  assert.equal(selected, "smoke");
  assert.ok(options.includes(selected));
  assert.equal(RUN_SCOPE_LABELS[selected], "Two-period wiring check");
  const oldReport = { project_id: project.id, project_revision_sha256: project.revision_sha256, data_pack_id: project.data_pack_id, mode: "value_101_day" };
  assert.equal(preflightMatches(oldReport, project, selected), false);
});

test("teaching and locked historical lesson remain eligible while incompatible lock stays unavailable", () => {
  const pack = { allowed_run_modes: ["smoke", "value_101_day"] };
  assert.equal(selectedRunScope("value_101_day", runModesForStudy({ extensions: { value_101: {} } }, pack)), "value_101_day");
  assert.deepEqual(runModesForStudy({ extensions: { frozen_recovery: { required_mode: "value_101_day" } } }, pack), ["value_101_day"]);
  assert.equal(selectedRunScope("smoke", runModesForStudy({ extensions: { frozen_recovery: { required_mode: "full" } } }, pack)), null);
});
