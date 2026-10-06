import assert from "node:assert/strict";
import test from "node:test";
import { renderTsx, textOf } from "../helpers/render-tsx.mjs";

// P0-9 S9 + S5 (F3-04, F3-02; spec 4.2, 4.3) rendered offline.
const RESULTS = "app/features/runs/RunResults.tsx";
const metrics = {
  system_cost_definition_id: "value.cem-system-resource-cost/v1", total_system_cost_gbp: 240, cost_per_mwh_gbp: 12,
  total_levelized_capital_cost_gbp: 100, total_operational_cost_gbp: 140,
  cm_mechanism_cost_gbp: null, cm_mechanism_cost_status: "not_modelled",
  decarbonization_mechanism_cost_gbp: null, decarbonization_mechanism_cost_status: "not_modelled",
  system_cost_includes_voll: false, blackout_mwh: 0,
};
const complete = { annual_status: "complete", reason_code: "annual_coverage_complete", coverage_fraction: 1, coverage_percent: 100, years: [{ year: 2025, first_period: 0, last_period: 17519, period_count: 17520, coverage_fraction: 1, complete: true }] };

test("a complete year shows its composition, legend and Not modelled mechanisms, never £0", async () => {
  const html = await renderTsx(RESULTS, "AnnualResults", { runId: "r", results: [{ year: 2025, metrics }], coverage: complete });
  const text = textOf(html);
  assert.match(text, /Complete year/);
  assert.match(text, /Cost composition excludes VoLL/);
  assert.match(text, /Capacity mechanism Not modelled/);
  assert.match(text, /Decarbonisation policy Not modelled/);
  assert.doesNotMatch(text, /£0(?![.\d])/);
  assert.match(html, /cost-legend-swatch/);
});

test("a partial year withholds its annual totals", async () => {
  const partial = { annual_status: "partial", reason_code: "run_cancelled_before_full_coverage", coverage_fraction: 0.166, coverage_percent: 16.6, years: [{ year: 2025, first_period: 0, last_period: 2907, period_count: 2908, coverage_fraction: 2908 / 17520, complete: false }] };
  const text = textOf(await renderTsx(RESULTS, "AnnualResults", { runId: "r", results: [{ year: 2025, metrics }], coverage: partial }));
  assert.match(text, /Partial year · 16\.6%/);
  assert.match(text, /Annual totals are not shown for 2025/);
  assert.doesNotMatch(text, /total system cost/);
  assert.doesNotMatch(text, /£240/);
});
