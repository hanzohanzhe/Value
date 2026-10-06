import assert from "node:assert/strict";
import test from "node:test";
import { costComposition, segmentTotal, unitCostText } from "../../../app/features/runs/resultMetrics.ts";

// P0-9 S9 (F3-04; spec 4.3).
const native = {
  system_cost_definition_id: "value.cem-system-resource-cost/v1", total_system_cost_gbp: 240,
  total_levelized_capital_cost_gbp: 100, total_operational_cost_gbp: 140,
  cm_mechanism_cost_gbp: null, cm_mechanism_cost_status: "not_modelled",
  decarbonization_mechanism_cost_gbp: null, decarbonization_mechanism_cost_status: "not_modelled",
  system_cost_includes_voll: false,
};

test("native: two segments 41.67 % / 58.33 %, mechanisms Not modelled, VoLL excluded", () => {
  const composition = costComposition(native);
  assert.equal(composition.definition, "native");
  assert.deepEqual(composition.segments.map((segment) => [segment.key, Number((segment.share * 100).toFixed(2))]), [["capital", 41.67], ["operating", 58.33]]);
  assert.equal(segmentTotal(composition), composition.headline);
  assert.deepEqual(composition.rows.filter((row) => row.state === "not_modelled").map((row) => row.label), ["Capacity mechanism", "Decarbonisation policy"]);
  assert.equal(composition.vollNote, "excludes VoLL");
});

test("legacy: five components add up to the 300 headline and include VoLL", () => {
  const composition = costComposition({
    system_cost_definition_id: "legacy_storage_tariff", total_system_cost_gbp: 300,
    total_levelized_capital_cost_gbp: 100, total_operational_cost_gbp: 80, lost_value_of_electricity_gbp: 50,
    cm_mechanism_cost_gbp: 40, decarbonization_mechanism_cost_gbp: 30,
  });
  assert.equal(composition.segments.length, 5);
  assert.equal(segmentTotal(composition), 300);
  assert.equal(composition.vollNote, "includes VoLL");
  assert.ok(composition.reconciled);
});

test("the bar always adds up to the headline; a recorded gap becomes a residual segment", () => {
  const composition = costComposition({ ...native, total_system_cost_gbp: 250 });
  assert.equal(segmentTotal(composition), 250);
  assert.equal(composition.segments.at(-1).key, "residual");
  const over = costComposition({ ...native, total_system_cost_gbp: 200 });
  assert.equal(over.reconciled, false);
  assert.deepEqual(over.segments, []);
  assert.ok(over.rows.some((row) => row.key === "residual" && row.amount === -40));
});

test("a memo row is listed but never drawn into the headline", () => {
  const composition = costComposition({ ...native, ror_hydro_compatibility_capital_gbp: 10.96e9 });
  assert.equal(segmentTotal(composition), 240);
  assert.match(composition.rows.at(-1).label, /^Memo: run-of-river hydro compatibility capital/);
});

test("an older Run without the VoLL flag says so", () => {
  const older = { ...native };
  delete older.system_cost_includes_voll;
  assert.equal(costComposition(older).vollNote, "VoLL basis not recorded");
});

test("the VoLL note follows the backend's declared basis (perfect foresight includes it; unknown is not guessed)", () => {
  assert.equal(costComposition({ ...native, system_cost_includes_voll: true }).vollNote, "includes VoLL");
  assert.equal(costComposition({ ...native, system_cost_includes_voll: null }).vollNote, "VoLL basis not recorded");
});

test("designer ruling 1: the unit-cost label follows the cost definition", () => {
  assert.equal(unitCostText({ ...native, cost_per_mwh_gbp: 61.234 }), "£61.23/MWh served");
  assert.equal(unitCostText({ system_cost_definition_id: "legacy_storage_tariff", cost_per_mwh_gbp: 55 }), "£55/MWh generated");
  assert.equal(unitCostText({ system_cost_definition_id: "something-else", cost_per_mwh_gbp: 55 }), "£55/MWh (basis not recorded)");
  assert.equal(unitCostText({ cost_per_mwh_gbp: 55 }), "£55/MWh (basis not recorded)");
  assert.equal(unitCostText({ ...native, cost_per_mwh_gbp: null }), "Not evaluated");
});
