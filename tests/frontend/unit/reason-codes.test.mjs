import assert from "node:assert/strict";
import test from "node:test";
import { reasonMessage, resultStatusView } from "../../../app/features/shared/reasonCodes.ts";

// P0-9 S7 (G1-07): red is only for invalid.
test("only an invalid result is an error", () => {
  assert.deepEqual([resultStatusView("invalid", "attribution_run_identity_mismatch").isError, resultStatusView("invalid").tone], [true, "danger"]);
  for (const status of ["unavailable", "withheld", "not_recorded", "legacy_partial"]) assert.equal(resultStatusView(status, "x").isError, false, status);
  assert.equal(resultStatusView("unavailable", "attribution_evidence_not_recorded").label, "Unavailable");
  assert.equal(resultStatusView("withheld", "annual_evidence_withheld_for_nonannual_run").label, "Withheld");
  assert.equal(resultStatusView("reconciled").tone, "ok");
});

test("reason codes read as sentences; unknown codes stay visible", () => {
  assert.match(reasonMessage("attribution_evidence_not_recorded"), /copperplate/);
  assert.equal(reasonMessage("some_new_code"), "some new code");
  assert.equal(reasonMessage(null), "No reason was recorded.");
});
