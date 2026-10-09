import assert from "node:assert/strict";
import test from "node:test";
import { renderTsx } from "../helpers/render-tsx.mjs";

// P1-polish: rendered markup for the designer rulings R-1..R-18 of 2026-10-09.
const text = (html) => html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();

const COMPARE = "app/features/results/ComparisonWorkspace.tsx";
const compareRun = (id, project, mode = "two_year") => ({ id, project_id: project, project_name: project, mode, status: "completed", created_at: "2026-10-08T12:00:00Z", updated_at: "2026-10-08T12:00:00Z" });

test("R-4: Compare has one page header with the export actions and scope names instead of codes", async () => {
  const html = await renderTsx(COMPARE, "default", { title: "Compare Runs", description: "Tick two to six completed Runs.", runs: [compareRun("a-r", "A"), compareRun("b-r", "B")], initialRuns: [] });
  assert.match(html, /<header class="v-page-header"><div class="v-page-header__text"><h2 tabindex="-1">Compare Runs<\/h2><p>Tick two to six completed Runs\.<\/p><\/div><div class="v-page-header__actions"><div class="comparison-actions"><button class="secondary" disabled="">Export CSV<\/button><button class="secondary" disabled="">Export JSON<\/button>/);
  assert.doesNotMatch(html, /Compare completed runs|Scenario comparison|comparison-heading/);
  assert.match(text(html), /A Two full model years ·/);
  assert.doesNotMatch(text(html), /two_year/);
  assert.match(html, /<section class="comparison-workspace" aria-label="Compare Runs">/);
});

test("R-4: the teaching-pair rule stays visible when VALUE 101 Runs can be compared", async () => {
  const html = await renderTsx(COMPARE, "default", { title: "Compare Runs", runs: [compareRun("a-r", "A", "value_101_day"), compareRun("b-r", "B", "value_101_day")] });
  assert.match(text(html), /VALUE 101 teaching Runs are compared by model identity only; their annual cost and carbon deltas are withheld\./);
  const annual = await renderTsx(COMPARE, "default", { title: "Compare Runs", runs: [compareRun("a-r", "A"), compareRun("b-r", "B")] });
  assert.doesNotMatch(annual, /comparison-tutorial-note/);
});

const RESULTS = "app/features/runs/RunResults.tsx";
const completeYear = { annual_status: "complete", reason_code: "annual_coverage_complete", coverage_fraction: 1, coverage_percent: 100, years: [{ year: 2025, first_period: 0, last_period: 17519, period_count: 17520, coverage_fraction: 1, complete: true }] };
const yearMetrics = (extra) => ({ system_cost_definition_id: "value.cem-system-resource-cost/v1", total_system_cost_gbp: 240, cost_per_mwh_gbp: 12, total_levelized_capital_cost_gbp: 100, total_operational_cost_gbp: 140, system_cost_includes_voll: false, blackout_mwh: 0, ...extra });

test("R-7: a missing final curtailment explains its reason code from the dictionary; an unknown code stays a phrase", async () => {
  const known = text(await renderTsx(RESULTS, "AnnualResults", { runId: "r", results: [{ year: 2025, metrics: yearMetrics({ vre_curtailment_attribution_reason_code: "module_does_not_provide_counterfactual_snapshot" }) }], coverage: completeYear }));
  assert.match(known, /The selected PSM does not provide matched VRE counterfactual snapshots\./);
  assert.doesNotMatch(known, /module does not provide counterfactual snapshot/);
  const unknown = text(await renderTsx(RESULTS, "AnnualResults", { runId: "r", results: [{ year: 2025, metrics: yearMetrics({ vre_curtailment_attribution_reason_code: "brand_new_reason" }) }], coverage: completeYear }));
  assert.match(unknown, /brand new reason/);
});

const RAIL = "app/features/shell/WorkspaceRail.tsx";
const railService = (state, failures = 0) => ({ state, failures, health: null, runtime: { python: "3.10.18", compatible: true }, architectureVersion: "value.contracts/v2" });

test("R-6: the service status lives in the sidebar; a lost or reduced service marks the menu button", async () => {
  const online = await renderTsx(RAIL, "default", { view: "overview", onNavigate() {}, onRetry() {}, service: railService("online") });
  assert.match(online, /aria-label="Open navigation"><i aria-hidden="true"><\/i><\/button>/);
  assert.match(online, /<div class="rail-foot"><div class="service online" role="status"/);
  const offline = await renderTsx(RAIL, "default", { view: "overview", onNavigate() {}, onRetry() {}, service: railService("offline", 3) });
  assert.match(offline, /aria-label="Open navigation · Backend offline"><i aria-hidden="true"><\/i><b class="rail-toggle-alert offline" aria-hidden="true"><\/b><\/button>/);
});

test("R-11: the sidebar is one labelled landmark holding the brand, navigation, status, language and version", async () => {
  for (const [locale, label] of [["en", "Sidebar"], ["zh", "侧栏"]]) {
    const html = await renderTsx("tests/frontend/helpers/p1-polish-fixtures.tsx", "RailIn", { locale, view: "overview", onNavigate() {}, onRetry() {}, service: railService("online") });
    assert.match(html, new RegExp(`^<aside class="rail" aria-label="${label}"><div class="rail-head"><div class="logo">`), locale);
    assert.match(html, /<nav aria-label="[^"]+">/, locale);
    assert.match(html, /<div class="locale-switch".*<small class="rail-version">.*<\/small><\/div><\/div><\/aside>$/, locale);
  }
});

test("R-18: the annual cost chart is titled 'Annual system cost' with 'Across the study' under it; bars are min(64 px, 60 % of the band)", async () => {
  const twoYears = { ...completeYear, years: [2025, 2026].map((year) => ({ ...completeYear.years[0], year })) };
  const results = [2025, 2026].map((year) => ({ year, metrics: yearMetrics({}) }));
  const wide = await renderTsx(RESULTS, "CostTrendChart", { results, coverage: twoYears, width: 400 });
  assert.match(wide, /<span class="v-chart__title"><span class="cost-trend-title">Annual system cost<\/span> <small class="cost-trend-kicker">Across the study<\/small><\/span>/);
  assert.equal((wide.match(/class="cost-trend-bar__value"[^>]*width="64"/g) ?? []).length, 2, "two bands of 162 px: 64 px bars");
  const narrow = await renderTsx(RESULTS, "CostTrendChart", { results, coverage: twoYears, width: 176 });
  assert.equal((narrow.match(/class="cost-trend-bar__value"[^>]*width="30"/g) ?? []).length, 2, "two bands of 50 px: 30 px bars");
});

test("R-16: a Run badge shows the state word in both languages and keeps the recorded code in its title", async () => {
  const en = await renderTsx("app/features/shared/presentation.tsx", "Badge", { tone: "good", title: "completed", children: "Completed" });
  assert.equal(en, '<span class="badge good" title="completed">Completed</span>');
  const { statusWord } = await import("../../../app/features/shared/labels.ts");
  assert.equal(statusWord("completed"), "Completed");
  assert.equal(statusWord("cancel_requested"), "Cancel requested");
  assert.equal(statusWord("worker_lost"), "Worker lost", "an unknown code reads as a phrase");
  const { readFile } = await import("node:fs/promises");
  for (const file of ["app/features/runs/RunHistoryTable.tsx", "app/features/runs/RunStatusPanel.tsx", "app/features/runs/RunWorkspace.tsx", "app/features/evidence/AuditView.tsx", "app/features/network/SystemResultsView.tsx"]) {
    const source = await readFile(new URL(`../../../${file}`, import.meta.url), "utf8");
    const badges = source.match(/<Badge [^>]*>\{(?:selectedRun \? )?statusWord\(/g) ?? [];
    assert.ok(badges.length > 0, file);
    for (const badge of badges) assert.match(badge, / title=\{/, `${file}: ${badge}`);
  }
});
