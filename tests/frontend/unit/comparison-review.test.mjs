import assert from "node:assert/strict";
import test from "node:test";
import { reviewReasonText } from "../../../app/features/results/comparisonReview.ts";

// P0-9 S11 / X0 S10b comparison gate: each review reason in a sentence.
test("comparison review reasons are stated in sentences; an unknown reason keeps its code", () => {
  assert.equal(reviewReasonText({ reason: "methodology_differs", profile_ids: ["value-corrected", "doctoral-lineage-0.6.0a2"] }), "The Runs use different methodologies: Corrected methodology (default); Doctoral reproduction (as implemented in VALUE 0.6.0-alpha.2).");
  assert.equal(reviewReasonText({ reason: "methodology_differs", profile_ids: ["value-corrected", "value-corrected"], differing_fields: ["applied_corrections_sha256"] }), "The Runs record different methodology identities (applied corrections sha256).");
  assert.equal(reviewReasonText({ reason: "methodology_differs", profile_ids: [null, "value-corrected"] }), "The Runs use different methodologies: methodology not recorded; Corrected methodology (default).");
  assert.equal(reviewReasonText({ reason: "energy_balance_failed", run_id: "r2" }), "r2: the energy balance check failed.");
  assert.equal(reviewReasonText({ reason: "annual_results_withheld", run_id: "d1" }), "d1: annual results are withheld (reproduction run).");
  assert.equal(reviewReasonText({ reason: "advisory", run_id: "r1", advisory_id: "VALUE-ADV", severity: "high" }), "r1: advisory VALUE-ADV (high) applies.");
  assert.equal(reviewReasonText({ reason: "something_new" }), "something new.");
});
