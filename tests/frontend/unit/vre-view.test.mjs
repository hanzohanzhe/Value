import assert from "node:assert/strict";
import test from "node:test";
import { kpiCoverageLine, seriesSegments, vreEventGroups, vreKpis } from "../../../app/features/market/vreView.ts";
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
