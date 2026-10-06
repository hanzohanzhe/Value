import assert from "node:assert/strict";
import test from "node:test";
import { reasonMessage, resultStatusView } from "../../../app/features/shared/reasonCodes.ts";

// P0-9 S7 (G1-07): red is only for invalid.
test("only an invalid result is an error", () => {
  assert.deepEqual([resultStatusView("invalid", "attribution_run_identity_mismatch").isError, resultStatusView("invalid").tone], [true, "danger"]);
  for (const status of ["unavailable", "withheld", "not_recorded", "legacy_partial"]) assert.equal(resultStatusView(status, "x").isError, false, status);
  assert.equal(resultStatusView("unavailable", "attribution_evidence_not_recorded").label, "Unavailable");
  assert.equal(resultStatusView("withheld", "annual_evidence_withheld_for_nonannual_run").label, "Non-annual run");
  assert.equal(resultStatusView("withheld", "GF_RESULTS_WITHHELD_RAW_INVARIANTS_FAILED").label, "Withheld", "Q14 keeps the word");
  assert.equal(resultStatusView("reconciled").tone, "ok");
});

test("reason codes read as sentences; unknown codes stay visible", () => {
  assert.match(reasonMessage("attribution_evidence_not_recorded"), /copperplate/);
  assert.equal(reasonMessage("some_new_code"), "some new code");
  assert.equal(reasonMessage(null), "No reason was recorded.");
});

test("a stopped Run reads its precise coverage reason, not 'non-annual'", () => {
  const view = resultStatusView("withheld", "run_cancelled_before_full_coverage", 16.6);
  assert.equal(view.label, "Stopped · 16.6%");
  assert.equal(resultStatusView("withheld", "annual_period_boundary_incomplete", 40).label, "Partial year · 40%");
  assert.deepEqual([resultStatusView("withheld", "run_in_progress").label, resultStatusView("withheld", "run_in_progress").tone], ["Running", "info"]);
  assert.match(reasonMessage("cancelled_before_year_complete"), /cancelled before every declared year/);
  assert.match(view.message, /cancelled before it covered its years/);
  assert.doesNotMatch(view.message, /non-annual/);
  assert.match(reasonMessage("annual_period_boundary_incomplete"), /17,519/);
});
