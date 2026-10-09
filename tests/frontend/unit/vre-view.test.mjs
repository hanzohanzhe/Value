import assert from "node:assert/strict";
import test from "node:test";
import { kpiCoverageLine, seriesSegments, seriesShapes, vreEventGroups, vreLabels, vreKpis, vreYearCoverage } from "../../../app/features/market/vreView.ts";
import { payload } from "../helpers/fixtures.mjs";

// P0-9 S8 (R3-21, G1-08; spec 4.1, 4.5).
test("the VALUE 101 day shows its VRE in MWh, never 0 TWh", () => {
  const year = payload("value-101-day.vre-summary").years[0];
  const { unit, kpis } = vreKpis(year);
  assert.equal(unit, "MWh");
  for (const item of kpis) assert.doesNotMatch(item.value ?? "", /TWh/);
  assert.match(kpis.find((item) => item.key === "available").value, / MWh$/);
  assert.equal(kpiCoverageLine(year), "48 periods · non-annual");
});

test("a full chronology year is labelled by its year and large values move to TWh", () => {
  const year = { year: 2030, period_count: 17520, full_chronology: true, available_vre_mwh: 2.5e8, accepted_vre_mwh: 2.4e8, neutral_unused_vre_mwh: 1e7, pre_balancing_excess_mwh: null, balancing_curtailment_mwh: 5e6, storage_charge_mwh: 3e6, export_mwh: 0, flexible_demand_mwh: 0 };
  const { unit, kpis } = vreKpis(year);
  assert.equal(unit, "TWh");
  assert.equal(kpis[0].value, "250 TWh");
  assert.equal(kpis.find((item) => item.key === "excess").value, null);
  assert.equal(kpiCoverageLine(year), "2030");
});

test("unused VRE and excess + curtailment are two event groups", () => {
  const year = payload("toy-v7.vre-summary").years[0];
  const groups = vreEventGroups(year);
  assert.deepEqual(groups.map((group) => group.key), ["unused_vre", "excess_curtailment"]);
  assert.equal(groups[0].events.basis, "unused_vre");
  assert.equal(groups[1].events.basis, "excess_plus_balancing_curtailment");
  assert.match(groups[1].basisNote, /not all of it is VRE/);
  // the toy keeps curtailment (period 2) and excess (period 3) in different periods
  assert.equal(groups[1].events.affected_periods, 2);
  assert.equal(groups[0].events.affected_periods, 1);
});

test("a missing value breaks the line instead of dropping it to 0", () => {
  const items = [{ vre_available_mwh: 1 }, { vre_available_mwh: null }, { vre_available_mwh: 3 }, { vre_available_mwh: 4 }];
  const segments = seriesSegments(items, "vre_available_mwh", (index) => index * 10, (value) => value);
  assert.deepEqual(segments, ["0,1", "20,3 30,4"]);
});

test("a partial year of a cancelled annual Run reads 'Stopped · n%', not non-annual (review response, S8; designer ruling 2)", () => {
  const year = { year: 2025, period_count: 2908, full_chronology: false };
  const cancelled = { annual_status: "partial", reason_code: "run_cancelled_before_full_coverage", coverage_fraction: 2908 / 17520, coverage_percent: 16.6, years: [{ year: 2025, first_period: 0, last_period: 2907, period_count: 2908, coverage_fraction: 2908 / 17520, complete: false }] };
  const coverage = vreYearCoverage(year, cancelled);
  assert.equal(coverage.line, "2025 · Stopped · 16.6%");
  assert.equal(coverage.badge, "Stopped · 16.6%");
  assert.equal(coverage.tone, "warn");
  assert.match(coverage.heading, /^Stopped · 16\.6% — not an annual result$/);
  assert.doesNotMatch(kpiCoverageLine(year, cancelled), /non-annual/);
  // a complete year inside a stopped Run keeps its year label, as on the Runs page
  const twoYears = { ...cancelled, years: [{ year: 2025, first_period: 0, last_period: 17519, period_count: 17520, coverage_fraction: 1, complete: true }] };
  assert.deepEqual(vreYearCoverage({ year: 2025, period_count: 17520, full_chronology: true }, twoYears), { line: "2025", badge: "Complete year", tone: "good", heading: "Annual accounting" });
  // only a non-annual Run is called non-annual
  const smoke = { annual_status: "non_annual", reason_code: "annual_evidence_withheld_for_nonannual_run", coverage_fraction: 0, coverage_percent: 0, years: [] };
  assert.equal(kpiCoverageLine({ year: 2025, period_count: 48, full_chronology: false }, smoke), "48 periods · non-annual");
  assert.equal(vreYearCoverage({ year: 2025, period_count: 48, full_chronology: false }, smoke).badge, "Non-annual run");
});

test("designer ruling 4: an isolated value and a one-bucket view are dots, not zero-length lines", () => {
  const items = [{ vre_available_mwh: 1 }, { vre_available_mwh: null }, { vre_available_mwh: 3 }, { vre_available_mwh: null }, { vre_available_mwh: 5 }, { vre_available_mwh: 6 }];
  const shapes = seriesShapes(items, "vre_available_mwh", (index) => index * 10, (value) => value);
  assert.deepEqual(shapes.lines, ["40,5 50,6"]);
  assert.deepEqual(shapes.dots, [{ x: 0, y: 1 }, { x: 20, y: 3 }]);
  // the VALUE 101 daily view has one bucket: every recorded series is one dot
  const day = payload("value-101-day.vre-timeline-daily").items;
  assert.equal(day.length, 1);
  const single = seriesShapes(day, "vre_available_mwh", () => 56, (value) => value);
  assert.deepEqual([single.lines.length, single.dots.length], [0, 1]);
});

test("designer ruling 5: a group without events says so instead of a 0 MWh peak", () => {
  const year = payload("toy-v7.vre-summary").years[0];
  const quiet = { ...year, unused_vre_events: { ...year.unused_vre_events, affected_periods: 0, peak_event_mwh: 0, peak_event_timestamp: "2025-01-01T00:00" } };
  const groups = vreEventGroups(quiet);
  assert.deepEqual(groups.map((group) => group.noEvents), [true, false]);
});

test("C20: the corrected rule set's columns are named for what they are, with one VRE event group", () => {
  const year = payload("value-101-day.vre-summary");
  assert.equal(year.curtailment_semantics, "vre_available_minus_gross_output");
  const labels = vreLabels(year);
  assert.deepEqual([labels.excess, labels.curtailment, labels.accepted], ["Non-VRE spill", "VRE curtailment", "Accepted VRE (gross output)"]);
  const kpis = vreKpis(year.years[0], year).kpis;
  assert.equal(kpis.find((item) => item.key === "excess").label, "Non-VRE spill");
  const groups = vreEventGroups(year.years[0]);
  assert.deepEqual(groups.map((group) => group.key), ["unused_vre"]);
  assert.equal(groups[0].events.basis, "corrected_unused_vre");
  assert.match(groups[0].basisNote, /gross renewable output/);
  // the doctoral columns keep their words
  assert.deepEqual([vreLabels(payload("toy-v7.vre-summary")).excess, vreLabels(null).curtailment], ["Pre-balancing excess", "Balancing curtailment"]);
});
