import assert from "node:assert/strict";
import test from "node:test";
import { resultYearFromSearch } from "../../../app/features/runs/resultYear.ts";
import { firstLine, runErrorSummary } from "../../../app/features/runs/runErrorView.ts";
import { matchRoute, readRouteLocation, routeUrl, legacyRedirect } from "../../../app/features/shell/routes.ts";
import { INSPECT_SEARCH_MAX, appliedSearch, readInspectSearch } from "../../../app/features/evidence/inspectQuery.ts";
import { modelPeriodLabel, modelTimeLabel, parsePeriodId, periodIdLabel } from "../../../app/features/shared/modelClock.ts";
import { axisLabelIndices, defaultResolution, replaySeriesStyle, technologyLabel } from "../../../app/features/market/dispatchView.ts";
import { FLOW_ARROWS, flowDirection, limitMw } from "../../../app/features/network/boundaryView.ts";
import { compareQueryValues, csvWithReference, defaultReferenceRun, effectiveReference, readCompareQuery, referenceFirst, runCreatedMs } from "../../../app/features/results/compareSelection.ts";

// P1 spec 5.1 / 6.5 (W4c): the Run centre and one Run's annual results.

test("the results page shows the year its URL names, else the latest recorded year", () => {
  assert.equal(resultYearFromSearch("?year=2025", [2025, 2026]), 2025);
  assert.equal(resultYearFromSearch("", [2025, 2026]), 2026);
  for (const bad of ["?year=2031", "?year=20x5", "?year=", "?year=-2025", "?year=2025.0"]) assert.equal(resultYearFromSearch(bad, [2025, 2026]), 2026, bad);
  assert.equal(resultYearFromSearch("?year=2025", []), null);
});

test("/runs is the Run centre and keeps the selected Run in its query; /runs/[runId] is one Run's results", () => {
  assert.deepEqual(matchRoute("/runs"), { view: "runCentre", runId: "", studyId: "" });
  assert.deepEqual(matchRoute("/runs/r1"), { view: "run", runId: "r1", studyId: "" });
  assert.equal(readRouteLocation("/runs", "?study=s1&run=r1").runId, "r1");
  const base = { path: null, dataContextId: "draft" };
  assert.equal(routeUrl({ ...base, view: "runCentre", studyId: "s1", runId: "r1", runStudyId: "s1" }, "", false), "/runs?study=s1&run=r1");
  assert.equal(routeUrl({ ...base, view: "run", studyId: "s1", runId: "r1", runStudyId: "s1" }, "?year=2025", true), "/runs/r1?year=2025");
  // An old Runs link with a Run opens that Run's results, without one the Run centre.
  assert.equal(legacyRedirect("?view=run&study=s&run=r"), "/runs/r?study=s");
  assert.equal(legacyRedirect("?view=run&study=s"), "/runs?study=s");
});

test("a Run error is its code and first diagnostic line; the rest stays available", () => {
  assert.equal(firstLine("\n  first line \nsecond"), "first line");
  assert.equal(firstLine(null), "");
  assert.equal(runErrorSummary({}), null);
  assert.deepEqual(runErrorSummary({ error_code: "GF_X", error: "Stopped in period 3\nTraceback\n  frame", error_detail: "detail line" }), { code: "GF_X", headline: "Stopped in period 3", rest: "Traceback\n  frame\ndetail line" });
  assert.deepEqual(runErrorSummary({ error_code: "GF_RUN_EXECUTION_IDENTITY_CHANGED", error: "", error_detail: "" }), { code: "GF_RUN_EXECUTION_IDENTITY_CHANGED", headline: "", rest: "" });
  // A detail equal to the headline is not repeated.
  assert.equal(runErrorSummary({ error: "Same", error_detail: "Same" }).rest, "");
});

// EM-低1 (spec 6.6): the reference Run of a comparison.
test("/compare?runs=&ref= names the ticked Runs and the reference; unknown text is dropped", () => {
  assert.deepEqual(readCompareQuery("?runs=a,b,a,,c%20d&ref=b"), { runs: ["a", "b"], ref: "b" });
  assert.deepEqual(readCompareQuery("?runs=a,b&ref=z"), { runs: ["a", "b"], ref: "" });
  assert.deepEqual(readCompareQuery(""), { runs: [], ref: "" });
  assert.equal(readCompareQuery(`?runs=${"r,".repeat(9)}${["1", "2", "3", "4", "5", "6", "7"].map((n) => `r${n}`).join(",")}`).runs.length, 6);
  assert.deepEqual(compareQueryValues(["a", "b"], "b"), { runs: "a,b", ref: "b" });
  assert.deepEqual(compareQueryValues([], "b"), { runs: null, ref: null });
  assert.deepEqual(compareQueryValues(["a"], "z"), { runs: "a", ref: null });
});

test("the default reference is the earliest-created baseline Run, else the earliest-created Run, else the first ticked", () => {
  const runs = [
    { id: "derived-20261008-120000-aa", project_id: "derived", created_at: "2026-10-08T12:00:00+01:00" },
    { id: "base-20261008-130000-bb", project_id: "base", created_at: "2026-10-08T13:00:00+01:00" },
    { id: "base-20261008-140000-cc", project_id: "base", created_at: null },
  ];
  const studies = [{ id: "derived", derivation: { source_study_id: "base" } }, { id: "base" }];
  assert.equal(runCreatedMs(runs[2]), Date.UTC(2026, 9, 8, 14, 0, 0));
  // The baseline Study's earliest Run, although the derived Run is older and was ticked first.
  assert.equal(defaultReferenceRun([runs[0].id, runs[2].id, runs[1].id], runs, studies), runs[1].id);
  // Without a derivation, the earliest-created Run.
  assert.equal(defaultReferenceRun([runs[1].id, runs[0].id], runs), runs[0].id);
  // Without creation times, the first ticked Run (as before).
  assert.equal(defaultReferenceRun(["x", "y"], [{ id: "x" }, { id: "y" }]), "x");
  assert.equal(effectiveReference(runs[1].id, [runs[0].id, runs[1].id], runs), runs[1].id);
  assert.equal(effectiveReference("gone", [runs[0].id, runs[1].id], runs), runs[0].id);
  assert.deepEqual(referenceFirst(["a", "b", "c"], "b"), ["b", "a", "c"]);
  assert.deepEqual(referenceFirst(["a", "b"], ""), ["a", "b"]);
});

test("the comparison CSV gains a reference_run_id row after schema_version", () => {
  const csv = "\uFEFFschema_version,value.run-comparison/v1\r\ncomparison_scope,annual_scientific\r\nrun_id,year\r\n";
  assert.equal(csvWithReference(csv, "run-b"), "schema_version,value.run-comparison/v1\r\nreference_run_id,run-b\r\ncomparison_scope,annual_scientific\r\nrun_id,year\r\n");
  assert.equal(csvWithReference("a,b\n", "x,\"y"), "reference_run_id,\"x,\"\"y\"\na,b\n");
});

// F3-19 (spec 6.6): Inspect's applied search in the URL.
test("Inspect reads ?q= and applies a trimmed, bounded search", () => {
  assert.equal(readInspectSearch("?tab=planning&q=%20wind%20"), "wind");
  assert.equal(readInspectSearch("?tab=planning"), "");
  assert.equal(appliedSearch("  solar  "), "solar");
  assert.equal(appliedSearch("x".repeat(INSPECT_SEARCH_MAX + 50)).length, INSPECT_SEARCH_MAX);
});

// F3-18 (spec 6.5): a model period as its UTC date and time, never "2025:137".
test("model periods read as UTC date and time on the fixed 365-day clock", () => {
  assert.equal(modelPeriodLabel(2025, 0), "2025-01-01 00:00 UTC");
  assert.equal(modelPeriodLabel(2025, 137), "2025-01-03 20:30 UTC");
  assert.equal(modelPeriodLabel(2025, 6553), "2025-05-17 12:30 UTC");
  // 29 February is never a model day: day 59 of 2028 is 1 March.
  assert.equal(modelPeriodLabel(2028, 59 * 48), "2028-03-01 00:00 UTC");
  assert.equal(modelPeriodLabel(2025, 3, 1), "2025-01-01 03:00 UTC");
  for (const bad of [[null, 1], [2025, -1], [2025, 1.5], [12, 3]]) assert.equal(modelPeriodLabel(...bad), null, String(bad));
  assert.deepEqual(parsePeriodId("2025:137"), { year: 2025, period: 137 });
  assert.equal(parsePeriodId("p-1"), null);
  assert.equal(periodIdLabel("2025:137"), "2025-01-03 20:30 UTC");
  assert.equal(periodIdLabel("custom"), "custom");
  assert.equal(modelTimeLabel("2025-07-01T16:00:00Z"), "2025-07-01 16:00 UTC");
  assert.equal(modelTimeLabel(""), "");
});

// Spec 1.2 / 2.1 (W4c): replay chart series, default resolution and axis labels.
test("replay series use the technology palette; same-colour series get a pattern", () => {
  assert.deepEqual(replaySeriesStyle("offshore_wind"), { color: "var(--tech-wind)", pattern: "hatch" });
  assert.deepEqual(replaySeriesStyle("onshore_wind"), { color: "var(--tech-wind)", pattern: "solid" });
  assert.deepEqual(replaySeriesStyle("natural_flow_hydro"), { color: "var(--tech-hydro)", pattern: "solid" });
  assert.deepEqual(replaySeriesStyle("reservoir_hydro"), { color: "var(--tech-hydro)", pattern: "dots" });
  assert.deepEqual(replaySeriesStyle("battery_storage"), { color: "var(--tech-storage)", pattern: "solid" });
  assert.deepEqual(replaySeriesStyle("hydrogen_storage"), { color: "var(--tech-storage)", pattern: "hatch" });
  assert.deepEqual(replaySeriesStyle("boundary_import"), { color: "var(--tech-import)", pattern: "dots" });
  assert.match(replaySeriesStyle("something_new").color, /^var\(--/);
  assert.equal(technologyLabel("biomass_and_waste"), "biomass and waste");
});

test("a 24-hour window opens at half-hour detail (R3-10); axis labels are spread evenly", () => {
  assert.equal(defaultResolution("24_hours"), "half_hour");
  assert.equal(defaultResolution("168_hours"), "daily");
  assert.deepEqual(axisLabelIndices(48, 5), [0, 12, 24, 35, 47]);
  assert.deepEqual(axisLabelIndices(3, 8), [0, 1, 2]);
  assert.deepEqual(axisLabelIndices(10, 1), [0]);
  assert.deepEqual(axisLabelIndices(0, 4), []);
});

// F3-13 (display part, W4c): corridor limits in MW and the transfer direction.
test("a per-period energy limit reads as MW; a signed transfer has a direction", () => {
  assert.equal(limitMw(5, 0.5), 10);
  assert.equal(limitMw(5, 1), 5);
  assert.equal(limitMw(null, 0.5), null);
  assert.equal(limitMw(5, 0), null);
  assert.equal(limitMw(5, undefined), null);
  assert.equal(flowDirection(2), "forward");
  assert.equal(flowDirection(-1.07), "reverse");
  assert.equal(flowDirection(0), "none");
  assert.equal(flowDirection(null), null);
  assert.deepEqual(FLOW_ARROWS, { forward: "→", reverse: "←", none: "·" });
});
