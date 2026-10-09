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
  // Designer ruling 2: a cancelled Run's year reads "Stopped · n%", never "Withheld" (Q14 only).
  assert.match(text, /Stopped · 16\.6%/);
  assert.doesNotMatch(text, /Withheld/);
  assert.match(text, /Annual totals are not shown for 2025/);
  assert.doesNotMatch(text, /total system cost/);
  assert.doesNotMatch(text, /£240/);
});

// W4c (P1 spec 6.5): one model year at a time (?year=), KPIs as Metric, the
// cost trend as a ChartFrame with a data table, the capacity as a DataTable.
const two = { annual_status: "complete", reason_code: "annual_coverage_complete", coverage_fraction: 1, coverage_percent: 100, years: [2025, 2026].map((year) => ({ year, first_period: 0, last_period: 17519, period_count: 17520, coverage_fraction: 1, complete: true })) };
const twoYears = [{ year: 2025, metrics: { ...metrics, total_system_cost_gbp: 14_700_000 }, capacity_mw: { ccgt: 1200.5 } }, { year: 2026, metrics: { ...metrics, total_system_cost_gbp: 14_425_000 } }];

test("the latest year is shown by default; ?year= shows another year with the same figures", async () => {
  const latest = await renderTsx(RESULTS, "AnnualResults", { runId: "r", results: twoYears, coverage: two });
  assert.match(latest, /<small>Latest completed year<\/small><strong>2026<\/strong>/);
  assert.match(latest, /£14\.425m total system cost/);
  assert.match(latest, /<button type="button" aria-pressed="true" class="is-selected"><b>2026<\/b>/);
  assert.match(latest, /<button type="button" aria-pressed="false"><b>2025<\/b><small>Complete year<\/small><\/button>/);
  const earlier = await renderTsx(RESULTS, "AnnualResults", { runId: "r", results: twoYears, coverage: two, year: 2025 });
  assert.match(earlier, /<small>Model year<\/small><strong>2025<\/strong>/);
  assert.match(earlier, /£14\.70m total system cost/);
  // A year the Run does not have falls back to the latest.
  assert.match(await renderTsx(RESULTS, "AnnualResults", { runId: "r", results: twoYears, coverage: two, year: 2031 }), /<strong>2026<\/strong>/);
});

test("KPIs are Metric components; the trend is a ChartFrame with a data table; capacity is a DataTable", async () => {
  const html = await renderTsx(RESULTS, "AnnualResults", { runId: "r", results: twoYears, coverage: two, year: 2025 });
  assert.match(html, /<div class="v-metric"><span class="v-metric__label">Average system cost<\/span><span class="v-metric__value">£12\/MWh served<\/span><\/div>/);
  assert.match(html, /<span class="v-metric__label">Annualised capital<\/span><span class="v-metric__value">£100<\/span>/);
  assert.match(html, /<figure class="v-chart">[\s\S]*Annual system cost[\s\S]*Show data table/);
  assert.match(html, /<summary>Capacity used by the PSM<\/summary><div class="v-table-scroll"[^>]*><table class="v-table"><caption class="v-visually-hidden">Capacity used by the PSM<\/caption>/);
  assert.match(html, /<th scope="row">ccgt<\/th><td class="v-num">1,200\.5 MW<\/td>/);
  // Unavailable curtailment evidence names its reason under the state word, never 0.
  assert.match(textOf(html), /Final VRE curtailment ○ Unavailable attribution evidence unavailable/);
});

test("the results page header names the Study, scope and Run and keeps the year in a select", async () => {
  const run = { id: "value-101-basel-20261008-135057-9a8dd37e", project_id: "s", project_name: "VALUE 101 baseline", mode: "two_year", status: "completed", current_stage: "Run completed", completed_years: 2, total_years: 2, updated_at: "", results: twoYears, result_coverage: two };
  const html = await renderTsx("app/features/runs/RunResultsPage.tsx", "default", { run, launching: "", year: 2025, onYearChange() {}, onOpenRunCentre() {}, onOpenInspect() {}, onRecoveredStudyCreated: async () => {} });
  assert.match(html, /<h2 tabindex="-1">Annual results<\/h2><p>VALUE 101 baseline · Two full model years · Run 9a8dd37e<\/p>/);
  assert.match(html, /<select><option value="2025" selected="">2025<\/option><option value="2026">2026<\/option><\/select>/);
  assert.match(html, /<strong>2025<\/strong>/);
  // With its actions, the page also shows the Run's status panel: after the results of a
  // completed Run, before them for any other Run.
  const noop = async () => {};
  const actions = { resumeRun: noop, rerunAsCopperplate: noop, lifecycleAction: noop };
  const page = (props) => renderTsx("app/features/runs/RunResultsPage.tsx", "default", { launching: "", year: null, onYearChange() {}, onOpenRunCentre() {}, onOpenInspect() {}, onRecoveredStudyCreated: noop, selectedRunSourceMutable: true, actions, ...props });
  const done = await page({ run });
  assert.ok(done.indexOf("latest-result") < done.indexOf("run-status-panel"), "a completed Run: results first");
  assert.match(done, /Remove from workspace/);
  const failed = await page({ run: { ...run, status: "failed", error_code: "GF_X", error: "Stopped" } });
  assert.ok(failed.indexOf("run-status-panel") < failed.indexOf("latest-result"), "a failed Run: status first");
  assert.match(failed, /<b>GF_X: <\/b>Stopped/);
  const empty = await renderTsx("app/features/runs/RunResultsPage.tsx", "default", { run: undefined, launching: "", year: null, onYearChange() {}, onOpenRunCentre() {}, onOpenInspect() {}, onRecoveredStudyCreated: async () => {} });
  assert.match(empty, /No Run selected/);
});
