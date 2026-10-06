import assert from "node:assert/strict";
import test from "node:test";
import { STRESS_EVENT_TYPE, isStressEventPage, stressEventEmptyText, stressEventQuery, stressEventRow } from "../../../app/features/market/stressEventsView.ts";

// Spec 4.4 / decision A2 (P0-9 M7): the full-year stress-event list in Market replay.
const complete = { annual_status: "complete", reason_code: "annual_coverage_complete", coverage_fraction: 1, coverage_percent: 100, years: [{ year: 2025, first_period: 0, last_period: 17519, period_count: 17520, coverage_fraction: 1, complete: true }] };
const partial = { annual_status: "partial", reason_code: "run_cancelled_before_full_coverage", coverage_fraction: 0.166, coverage_percent: 16.6, years: [{ year: 2025, first_period: 0, last_period: 2907, period_count: 2908, coverage_fraction: 0.166, complete: false }] };

test("a row shows the model start time, periods, the recorded shortfall, the stress type and a replay window", () => {
  const row = stressEventRow({ year: 2025, event_index: 2, start_period: 5000, last_period: 5003, periods: 4, shortfall_mwh: 1234.5 });
  assert.deepEqual(row, { key: "2025-2", start: "2025-04-15 04:00", startPeriod: 5000, periods: 4, shortfall: "1.23 GWh", type: STRESS_EVENT_TYPE, replayFrom: 4996 });
  assert.equal(STRESS_EVENT_TYPE, "stress (supply < demand)");
  assert.equal(stressEventRow({ year: 2025, event_index: 0, start_period: 1, last_period: 1, periods: 1, shortfall_mwh: null }).shortfall, null);
});

test("the query pages the whole year (no period window), 50 at a time", () => {
  assert.equal(stressEventQuery(2025, 50).toString(), "year=2025&limit=50&offset=50");
});

test("empty text: 'recorded in {year}' only for a complete year, the computed share otherwise, and never 'none' for an older ledger", () => {
  assert.equal(stressEventEmptyText({ status: "recorded" }, complete, 2025), "No stress events recorded in 2025.");
  assert.equal(stressEventEmptyText({ status: "recorded" }, partial, 2025), "No stress events in the 16.6% of 2025 that has been computed.");
  assert.match(stressEventEmptyText({ status: "not_recorded" }, complete, 2025), /does not record stress events/);
});

test("only a well-formed page is rendered; an unexpected body is an error, not an empty list", () => {
  assert.equal(isStressEventPage({ status: "recorded", items: [], total: 0, limit: 50, offset: 0, has_more: false }), true);
  assert.equal(isStressEventPage({ error: "unmocked API" }), false);
  assert.equal(isStressEventPage(null), false);
  assert.equal(isStressEventPage({ status: "recorded", items: {}, total: 0, limit: 50, offset: 0 }), false);
});
