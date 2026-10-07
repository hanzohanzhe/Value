import assert from "node:assert/strict";
import test from "node:test";
import { changedDimensionRows, dimensionPathsText, metricDeltaShown, metricDeltaWithheldText, metricLabel, reviewReasonText, withheldDeltaSummary } from "../../../app/features/results/comparisonReview.ts";

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

test("a recorded module selection reads as module id and version", () => {
  const [row] = changedDimensionRows({ "module.storage_cost": [
    { contract_version: "value.storage-cost/v1", module_id: "dynamic-annual-storage-cost", module_version: "2.0.0", slot: "storage_cost" },
    { contract_version: "value.storage-cost/v1", module_id: "value-legacy-storage-tariff", module_version: "1.0.0", slot: "storage_cost" },
  ] }, {});
  assert.equal(row.detail, "dynamic-annual-storage-cost 2.0.0 → value-legacy-storage-tariff 1.0.0");
  assert.match(row.raw, /"contract_version"/);
  assert.equal(changedDimensionRows({ "module.x": [{ other: 1 }, { other: 2 }] }, {})[0].detail, "recorded values differ");
});

// AF3-1 (DECISIONS A23, round R2): annual deltas are gated per metric; each
// withheld metric states its reason; old responses keep the all-or-nothing flag.
test("annual deltas follow the per-metric gate and a withheld metric states its reason", () => {
  const reason = "VRE-curtailment differences need matching, reconciled curtailment-attribution evidence in every Run (module does not provide counterfactual snapshot).";
  const comparison = {
    metric_deltas_allowed: false, annual_metrics_withheld: false,
    metric_delta_gates: {
      cem_system_cost_gbp: { allowed: true, reason_code: null, definitions: [], reason: null },
      total_carbon_emissions_tco2e: { allowed: true, reason_code: null, definitions: [], reason: null },
      vre_curtailment_mwh: { allowed: false, reason_code: "module_does_not_provide_counterfactual_snapshot", definitions: [], reason },
      vre_curtailment_rate: { allowed: false, reason_code: "module_does_not_provide_counterfactual_snapshot", definitions: [] },
    },
    withheld_metric_deltas: ["vre_curtailment_mwh", "vre_curtailment_rate"],
  };
  assert.equal(metricDeltaShown(comparison, "cem_system_cost_gbp"), true);
  assert.equal(metricDeltaShown(comparison, "vre_curtailment_mwh"), false);
  assert.equal(metricDeltaWithheldText(comparison, "cem_system_cost_gbp"), null);
  assert.equal(metricDeltaWithheldText(comparison, "vre_curtailment_mwh"), `Delta withheld: ${reason}`);
  assert.equal(metricDeltaWithheldText(comparison, "vre_curtailment_rate"), "Delta withheld (module does not provide counterfactual snapshot).");
  assert.equal(withheldDeltaSummary(comparison), "Deltas are withheld for 2 of 4 metrics (Vre Curtailment Mwh, Vre Curtailment Rate); each states its reason below. The other metrics show their deltas.");
  assert.equal(metricLabel("total_carbon_emissions_tco2e"), "Total Carbon Emissions Tco2e");
});

test("every-metric, none, teaching and legacy responses", () => {
  const gate = (allowed) => ({ allowed, reason_code: allowed ? null : "metric_definition_differs", definitions: allowed ? [] : ["cost"], reason: allowed ? null : "The Runs compute this metric under different cost definitions." });
  const all = { metric_deltas_allowed: false, annual_metrics_withheld: false, metric_delta_gates: { a: gate(false), b: gate(false) }, withheld_metric_deltas: ["a", "b"] };
  assert.equal(withheldDeltaSummary(all), "Annual deltas are withheld for every metric; each metric states its reason below.");
  const none = { metric_deltas_allowed: true, annual_metrics_withheld: false, metric_delta_gates: { a: gate(true) }, withheld_metric_deltas: [] };
  assert.equal(withheldDeltaSummary(none), null);
  assert.equal(metricDeltaShown(none, "a"), true);
  const teaching = { metric_deltas_allowed: false, annual_metrics_withheld: true, metric_delta_gates: {}, withheld_metric_deltas: [] };
  assert.equal(withheldDeltaSummary(teaching), null);
  assert.equal(metricDeltaWithheldText(teaching, "a"), null);
  const legacy = { metric_deltas_allowed: false, annual_metrics_withheld: false };
  assert.equal(metricDeltaShown(legacy, "a"), false);
  assert.equal(withheldDeltaSummary(legacy), "Annual deltas are withheld: the required definitions, scope or attribution evidence are incomplete.");
  assert.equal(metricDeltaShown({ metric_deltas_allowed: true, annual_metrics_withheld: false }, "a"), true);
  // The summary never shows Chinese text on the English Compare page (R3M-7).
  for (const text of [withheldDeltaSummary(all), withheldDeltaSummary(legacy), metricDeltaWithheldText(legacy, "a")]) assert.doesNotMatch(text, /[一-鿿]/);
});
