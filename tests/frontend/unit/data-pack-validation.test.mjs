import assert from "node:assert/strict";
import test from "node:test";
import { inputsPresentSuffix, methodologyUse, validationLayers, worstStatus } from "../../../app/features/data/dataPackValidation.ts";

// Spec 11.2 (S-D2): three layers and methodology eligibility of one pack.
const eligible = (extra = {}) => ({ eligible: true, pack_class: "teaching", blocking_codes: [], warning_codes: [], ...extra });
const clean = {
  valid: true, errors: [], warnings: [],
  layers: { chronology: { findings: [] }, plausibility: { findings: [] } },
  profile_eligibility: { "value-corrected": eligible(), "doctoral-lineage-0.6.0a2": eligible() },
};
const negative = {
  valid: true, errors: [],
  warnings: ["market.france.price: unit is not declared; canonical role expects GBP/MWh"],
  layers: {
    chronology: { findings: [{ code: "GF_DATA_TIMESTAMPS", layer: "chronology", role: "demand.real", message: "real.csv:time duplicates" }, { code: "GF_DATA_PRICE_CURRENCY", layer: "chronology", role: "market.belgium.price", message: "EUR column" }] },
    plausibility: { findings: [{ code: "GF_DATA_PLAUSIBILITY_PRICE", layer: "plausibility", role: "market.france.price", message: "france price range [82, 6087] outside [-500, 5000] GBP/MWh" }] },
  },
  profile_eligibility: {
    "value-corrected": { eligible: false, blocking_codes: ["GF_DATA_PRICE_CURRENCY"], warning_codes: ["GF_DATA_TIMESTAMPS"] },
    "doctoral-lineage-0.6.0a2": eligible({ warning_codes: ["GF_DATA_PRICE_CURRENCY"] }),
  },
};

test("a clean pack passes every layer and is eligible for both profiles", () => {
  const layers = validationLayers(clean);
  assert.deepEqual(layers.map((layer) => [layer.label, layer.pill.tone, layer.pill.text]), [["Structural", "ok", "Passed"], ["Chronology", "ok", "Passed"], ["Plausibility", "ok", "Passed"]]);
  assert.equal(worstStatus(layers), "passed");
  assert.equal(inputsPresentSuffix("passed"), "inputs present · validation passed");
  assert.deepEqual(methodologyUse(clean).map((row) => [row.label, row.pill.tone, row.pill.text]), [["Corrected", "ok", "Eligible"], ["Doctoral reproduction", "ok", "Eligible"]]);
});

test("findings: warnings are amber, a finding that blocks a profile is red, and the worst status says so", () => {
  const [structural, chronology, plausibility] = validationLayers(negative);
  assert.deepEqual([structural.pill.tone, structural.pill.text], ["caution", "1 warning"]);
  assert.deepEqual(structural.rows[0], { object: "market.france.price", message: "unit is not declared; canonical role expects GBP/MWh", code: "GF_DATA_STRUCTURAL_WARNING", severity: "warning" });
  assert.deepEqual([chronology.pill.tone, chronology.pill.text, chronology.pill.title], ["danger", "Failed", "2 findings; blocks Corrected"]);
  assert.deepEqual(chronology.rows.map((row) => [row.code, row.object, row.severity]), [["GF_DATA_TIMESTAMPS", "demand.real", "warning"], ["GF_DATA_PRICE_CURRENCY", "market.belgium.price", "error"]]);
  assert.deepEqual([plausibility.pill.tone, plausibility.pill.text], ["caution", "1 warning"]);
  assert.equal(worstStatus([structural, chronology, plausibility]), "failed");
  const [corrected, doctoral] = methodologyUse(negative);
  assert.deepEqual([corrected.pill.tone, corrected.pill.text], ["caution", "Not eligible — blocked by GF_DATA_PRICE_CURRENCY"]);
  assert.deepEqual([doctoral.pill.tone, doctoral.pill.text, doctoral.pill.title], ["ok", "Eligible", "With warnings: GF_DATA_PRICE_CURRENCY"]);
});

test("a structurally invalid pack fails and is eligible for no profile", () => {
  const report = { ...clean, valid: false, errors: ["demand.real: required semantic role is not bound"], profile_eligibility: { "value-corrected": { eligible: false, blocking_codes: [] } } };
  const [structural] = validationLayers(report);
  assert.deepEqual([structural.pill.tone, structural.pill.text, structural.pill.title], ["danger", "Failed", "1 error"]);
  assert.equal(methodologyUse(report)[0].pill.text, "Not eligible — structural validation failed");
});

test("before the report loads the cached summary is used; without either everything is Not evaluated", () => {
  const cached = { status: "findings", valid: true, chronology_codes: [], plausibility_codes: ["GF_DATA_PLAUSIBILITY_PRICE"], profile_eligibility: clean.profile_eligibility };
  const layers = validationLayers(null, cached);
  assert.deepEqual(layers.map((layer) => layer.pill.text), ["Passed", "Passed", "1 warning"]);
  const none = validationLayers(null, { status: "not_evaluated" });
  assert.deepEqual(none.map((layer) => [layer.pill.tone, layer.pill.text]), [["muted", "Not evaluated"], ["muted", "Not evaluated"], ["muted", "Not evaluated"]]);
  assert.equal(worstStatus(none), "not_evaluated");
  assert.equal(inputsPresentSuffix("not_evaluated"), "inputs present · validation not evaluated");
  assert.deepEqual(methodologyUse(null, null).map((row) => [row.label, row.pill.text]), [["Corrected", "Not evaluated"], ["Doctoral reproduction", "Not evaluated"]]);
});

test("N-1: a pack outside the doctoral whitelist is not eligible for it, with the editor's reason", () => {
  const report = {
    ...clean,
    profile_eligibility: {
      "value-corrected": eligible({ pack_supported: true, pack_support_reason: null }),
      "doctoral-lineage-0.6.0a2": { eligible: false, pack_class: "user_workspace", pack_supported: false, pack_support_reason: "not a thesis-era pack", blocking_codes: ["VALUE_PROFILE_COMBINATION_UNSUPPORTED"], warning_codes: [] },
    },
  };
  assert.deepEqual(methodologyUse(report).map((row) => [row.label, row.pill.tone, row.pill.text]), [["Corrected", "ok", "Eligible"], ["Doctoral reproduction", "caution", "Not eligible — not a thesis-era pack"]]);
  // The whitelist code matches no finding, so the layers keep their own colours.
  assert.deepEqual(validationLayers(report).map((layer) => layer.pill.text), ["Passed", "Passed", "Passed"]);
});
