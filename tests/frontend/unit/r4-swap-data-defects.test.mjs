import assert from "node:assert/strict";
import test from "node:test";
import { MODEL_CLOCK_LABEL, modelClockSuffix, modelTimeText, modelTimestamp } from "../../../app/features/shared/modelClock.ts";
import { modelTimestamp as reliabilityTimestamp } from "../../../app/features/network/reliabilityView.ts";
import { stressEventRow } from "../../../app/features/market/stressEventsView.ts";

// R4 (DECISIONS A27), four-role report S-中1: model times are UTC on a fixed
// 365-day year, labelled "UTC model time" (gridform_core/model_clock.py).
test("model clock: UTC, 365-day year, no 29 February", () => {
  assert.equal(modelTimestamp(2025, 8720), "2025-07-01 16:00");
  assert.equal(modelTimestamp(2028, 59 * 48), "2028-03-01 00:00");
  assert.equal(modelTimestamp(2028, 17_519), "2028-12-31 23:30");
  assert.equal(modelTimestamp(2025, 25, 1), "2025-01-02 01:00");
  // One rule: the network and stress lists use the same function.
  assert.equal(reliabilityTimestamp, modelTimestamp);
  assert.equal(stressEventRow({ year: 2028, event_index: 1, start_period: 59 * 48, last_period: 59 * 48, periods: 1, shortfall_mwh: 1 }).start, "2028-03-01 00:00");
});

test("model clock labels and backend timestamps", () => {
  assert.equal(MODEL_CLOCK_LABEL, "UTC model time");
  assert.equal(modelClockSuffix("UTC"), " (UTC model time)");
  assert.equal(modelClockSuffix(""), "");
  assert.equal(modelClockSuffix(undefined), "");
  assert.equal(modelTimeText("2025-07-01T16:00:00Z"), "2025-07-01 16:00");
  assert.equal(modelTimeText("2025-07-01T16:00:00"), "2025-07-01 16:00");
  assert.equal(modelTimeText(null), "");
});

// S-中3 / S-低2: the timestamp report names the date order, the span and the data year.
test("timestamp coverage line and date orders", async () => {
  const { DATE_ORDERS, timestampCoverageText } = await import("../../../app/features/data/csvMappingFx.ts");
  assert.deepEqual(DATE_ORDERS.map((item) => item.value), ["auto", "day_first", "month_first"]);
  assert.equal(timestampCoverageText({ coverage: { span_days: 354.17, data_years: [2023] }, date_order: "day_first", date_order_basis: "detected: CSV line 578 has a first field above 12" }),
    "covers 354.17 days · data year 2023 · dates read as DD/MM/YYYY (detected: CSV line 578 has a first field above 12)");
  assert.equal(timestampCoverageText({ coverage: { span_days: 365, data_years: [2025] }, date_order: "iso" }), "covers 365 days · data year 2025");
  assert.equal(timestampCoverageText(null), "");
});

// S-低7(b): a missing curtailment metric reads "Unavailable" on Compare, as on Runs.
test("missing metric wording matches the Runs page", async () => {
  const { missingMetricValueText } = await import("../../../app/features/results/comparisonReview.ts");
  for (const metric of ["vre_curtailment_mwh", "vre_curtailment_rate", "redispatch_net_impact_mwh"]) assert.equal(missingMetricValueText(metric), "Unavailable");
  assert.equal(missingMetricValueText("total_carbon_emissions_tco2e"), "Not evaluated");
});
