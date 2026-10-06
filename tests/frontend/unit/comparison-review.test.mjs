import assert from "node:assert/strict";
import test from "node:test";
import { changedDimensionRows, dimensionPathsText, reviewReasonText } from "../../../app/features/results/comparisonReview.ts";

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

// R-D7 / S-D9 / F-D5 (four-role report, round R1-5): changed dimensions are
// named by label and differing paths, not by thousands of characters of JSON.
test("changed identity dimensions read as label and differing paths; raw JSON is kept for request only", () => {
  const changed = {
    "module.storage_cost": ["dynamic-annual-storage-cost", "uat2-flat73-storage-offer"],
    "identity.method": [{ modules: { storage_cost: { id: "a" } } }, { modules: { storage_cost: { id: "b" } } }],
    "identity.data": [{ pack: { roles: { demand: "x" } } }, { pack: { roles: { demand: "y" } } }],
  };
  const details = {
    method: { label: "model method (modules, extensions, methodology)", paths: ["modules.storage_cost"], more_paths: 0 },
    data: { label: "data inputs", paths: Array.from({ length: 12 }, (_, i) => `pack.roles.r${i}`), more_paths: 13 },
  };
  const rows = changedDimensionRows(changed, details);
  assert.deepEqual(rows.map(({ key, label, detail }) => ({ key, label, detail })), [
    { key: "module.storage_cost", label: "module · storage cost", detail: "dynamic-annual-storage-cost → uat2-flat73-storage-offer" },
    { key: "identity.method", label: "model method (modules, extensions, methodology)", detail: "differs at modules.storage_cost" },
    { key: "identity.data", label: "data inputs", detail: `differs at ${details.data.paths.join(", ")} and 13 more` },
  ]);
  assert.equal(rows[0].raw, null);
  assert.match(rows[1].raw, /"storage_cost"/);
  for (const row of rows) assert.ok(row.detail.length < 400, "no raw JSON in the visible line");
});

test("without backend details an object dimension says the values differ; review paths come from the details", () => {
  const [row] = changedDimensionRows({ "identity.config": [{ a: 1 }, { a: 2 }] }, undefined);
  assert.equal(row.label, "identity.config");
  assert.equal(row.detail, "recorded values differ");
  assert.equal(dimensionPathsText({ data: { label: "data inputs", paths: ["pack.roles.demand"], more_paths: 0 } }, "data"), "pack.roles.demand");
  assert.equal(dimensionPathsText({ data: { label: "data inputs", paths: [], more_paths: 0 } }, "data"), null);
  assert.equal(dimensionPathsText(undefined, "method"), null);
});
