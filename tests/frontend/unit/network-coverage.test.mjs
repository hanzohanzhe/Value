import assert from "node:assert/strict";
import test from "node:test";
import {
  annualTotalsPublishable, coveragePill, coverageStateKey, reliabilityEmptyText, yearCoveragePercent, yearCoveragePill, yearTotalsPublishable,
} from "../../../app/features/shared/coverageView.ts";
import { valueStateText, valueStateTone } from "../../../app/features/shared/valueStates.ts";
import { modelTimestamp, reliabilityQuery, reliabilityRow, replayWindowStart } from "../../../app/features/network/reliabilityView.ts";
import { payload } from "../helpers/fixtures.mjs";

// P0-9 S5/S6 (F3-02, F3-07; spec 4.2, 4.4, 4.6).
const partial = {
  annual_status: "partial", reason_code: "run_cancelled_before_full_coverage", coverage_fraction: 2908 / 17520, coverage_percent: 16.6,
  years: [{ year: 2025, first_period: 0, last_period: 2907, period_count: 2908, coverage_fraction: 2908 / 17520, complete: false }],
};
const complete = {
  annual_status: "complete", reason_code: "annual_coverage_complete", coverage_fraction: 1, coverage_percent: 100,
  years: [{ year: 2025, first_period: 0, last_period: 17519, period_count: 17520, coverage_fraction: 1, complete: true }],
};

test("a cancelled 16.6 % year reads 'Stopped · 16.6%' and its totals are not published", () => {
  // Designer ruling 2: cancelled/stopped -> "Stopped · n%"; "Withheld" is only Q14.
  assert.deepEqual(coveragePill(partial).text, "Stopped · 16.6%");
  assert.equal(coveragePill(partial).tone, "caution");
  assert.equal(annualTotalsPublishable(partial), false);
  assert.equal(yearCoveragePill(partial, 2025).text, "Stopped · 16.6%");
  assert.equal(yearTotalsPublishable(partial, 2025), false);
});

test("designer ruling 2: partial, running and stopped years each have their own word", () => {
  const boundary = { ...partial, reason_code: "annual_period_boundary_incomplete" };
  assert.equal(coveragePill(boundary).text, "Partial year · 16.6%");
  assert.equal(coverageStateKey(boundary), "partial_year");
  assert.equal(coverageStateKey(partial), "stopped");
  assert.equal(coverageStateKey({ ...partial, reason_code: "run_failed_before_full_coverage" }), "stopped");
  const running = { ...partial, annual_status: "in_progress", reason_code: "run_in_progress" };
  assert.deepEqual([yearCoveragePill(running, 2025).text, yearCoveragePill(running, 2025).tone], ["Running", "info"]);
  assert.equal(coverageStateKey(running), "in_progress");
  assert.equal(yearCoveragePercent(partial, 2025), 2908 / 17520 * 100);
  assert.equal(valueStateText("stopped", 16.6), "Stopped · 16.6%");
  assert.equal(valueStateTone("stopped"), "amber");
  for (const coverage of [partial, boundary, running]) assert.notEqual(coveragePill(coverage).text, "Withheld");
});

test("pill texts and tones follow spec 4.2", () => {
  assert.deepEqual([coveragePill(complete).text, coveragePill(complete).tone], ["Complete year", "ok"]);
  assert.equal(coveragePill({ ...partial, annual_status: "non_annual", reason_code: "annual_evidence_withheld_for_nonannual_run" }).text, "Non-annual run");
  assert.equal(coveragePill({ ...partial, annual_status: "invalid" }).tone, "danger");
  assert.equal(coveragePill(complete, { withheld: true }).text, "Withheld");
  assert.equal(coveragePill(null).text, "Coverage not recorded");
  assert.equal(annualTotalsPublishable(complete), true);
  assert.equal(annualTotalsPublishable(null), true, "an older backend keeps its totals under 'Coverage not recorded'");
});

test("the VALUE 101 day fixture is a non-annual run", () => {
  const coverage = payload("value-101-day.vre-summary").coverage;
  assert.equal(coveragePill(coverage).text, "Non-annual run");
  assert.equal(yearTotalsPublishable(coverage, 2025), false);
});

test("the empty reliability sentence claims a whole year only for a complete year", () => {
  assert.equal(reliabilityEmptyText(complete, 2025), "No stress events recorded in 2025.");
  assert.equal(reliabilityEmptyText(partial, 2025), "No stress events in the 16.6% of 2025 that has been computed.");
  assert.doesNotMatch(reliabilityEmptyText(null, 2025), /recorded in 2025\.$/);
});

test("reliability rows are dated, typed and replayable; the query is the whole year", () => {
  const row = reliabilityRow({ event_id: "observed-2025-5000-5003", year: 2025, start_period: 5000, end_period: 5003, observed_half_hours: 4, unserved_mwh: 12.5, affected_zones_json: "[\"north\",\"south\"]" });
  assert.equal(row.start, "2025-04-15 04:00");
  assert.equal(row.periods, 4);
  assert.equal(row.shortfall, "12.5 MWh");
  assert.equal(row.type, "lost load (network)");
  assert.equal(row.zones, "north, south");
  assert.equal(replayWindowStart(5000), 4996);
  assert.equal(replayWindowStart(1), 0);
  assert.equal(modelTimestamp(2025, 0), "2025-01-01 00:00");
  const query = reliabilityQuery(2025, 50);
  assert.equal(query.get("period_from"), null);
  assert.equal(query.get("limit"), "50");
  assert.equal(query.get("offset"), "50");
  assert.equal(reliabilityRow({ event_id: "x", year: 2025, start_period: 1, end_period: 2 }).shortfall, null);
});
