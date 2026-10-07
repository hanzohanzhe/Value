import assert from "node:assert/strict";
import test from "node:test";
import { demandUnitText } from "../../../app/features/workspace/demandUnit.ts";
import { studyResolutionKey } from "../../../app/features/studies/studyResolutionKey.ts";
import { unservedDemandText } from "../../../app/features/runs/resultMetrics.ts";
import { deltaReferenceText } from "../../../app/features/results/comparisonReview.ts";
import { reviewExpiryText } from "../../../app/features/data/csvMappingFx.ts";
import { metricLabel } from "../../../app/features/shared/labels.ts";

// R5 (DECISIONS A28): the swap-data defects of the final four-role report.

test("S-F-高1: a legacy-labelled demand file says it is read as MW", () => {
  const text = demandUnitText({ runtime_unit_interpretation: { declared_unit: "MWh/period", runtime_unit: "MW" } });
  assert.match(text, /按 MW 读取/);
  assert.match(text, /表头写作 mwh/);
  assert.match(text, /MWh\/period/);
  assert.match(text, /请选择 MW/);
  assert.equal(demandUnitText({}), null);
  assert.equal(demandUnitText(undefined), null);
});

test("S-F-中1: a polled copy of the same Study keeps its resolution key", () => {
  const study = { id: "s", data_pack_id: "p", modules: { psm: "x" }, linked_run_count: 0 };
  const polled = { ...study, modules: { psm: "x" }, linked_run_count: 1, warnings: [] };
  assert.notEqual(study, polled);
  assert.equal(studyResolutionKey(study), studyResolutionKey(polled));
  assert.notEqual(studyResolutionKey(study), studyResolutionKey({ ...study, data_pack_id: "q" }));
  assert.equal(studyResolutionKey(undefined), "");
  assert.deepEqual(JSON.parse(studyResolutionKey(study)), { id: "s", data_pack_id: "p", modules: { psm: "x" } });
});

test("S-F-中2: unserved demand includes the stress shortfall and names the PSM-recorded part", () => {
  const both = unservedDemandText({ unserved_energy_a2_mwh: 28167.2, blackout_mwh: 417.64 });
  assert.equal(both.value, "28,167.2 MWh");
  assert.match(both.note, /incl\. stress shortfall/);
  assert.match(both.note, /417\.64 MWh recorded by the PSM/);
  const old = unservedDemandText({ blackout_mwh: 363.64 });
  assert.equal(old.value, "363.64 MWh");
  assert.equal(old.note, null);
  assert.equal(unservedDemandText({}).value, "Not evaluated");
});

test("S-F-高1 / 中2: comparison metric labels", () => {
  assert.equal(metricLabel("demand_mwh"), "Annual demand (MWh)");
  assert.equal(metricLabel("demand_served_mwh"), "Demand served (MWh)");
  assert.equal(metricLabel("unserved_energy_mwh"), "Unserved energy incl. stress shortfall (MWh)");
  assert.equal(metricLabel("recorded_unserved_energy_mwh"), "Unserved energy recorded by the PSM (MWh)");
});

test("S-F-低5: the comparison names its reference Run", () => {
  assert.match(deltaReferenceText("run-1", "VALUE 101 baseline"), /measured against VALUE 101 baseline \(run-1\), the first Run ticked/);
  assert.match(deltaReferenceText("run-1"), /measured against run-1,/);
});

test("S-F-低6: the review expiry is local time to the minute", () => {
  const text = reviewExpiryText("2026-10-07T22:05:02.444364+00:00");
  assert.match(text, /^\d{4}-\d{2}-\d{2} \d{2}:\d{2} local time$/);
  assert.equal(reviewExpiryText("not a date"), "not a date");
});
