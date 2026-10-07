import assert from "node:assert/strict";
import test from "node:test";
import { PLANNING_YEAR_NOT_RECORDED, planningYearFromPayload } from "../../../app/features/runs/planningView.ts";

// R4 (DECISIONS A27), four-role report R-中1: a planning summary without
// years[] (the v2 index summary) reads "not recorded" instead of throwing
// "Cannot read properties of undefined (reading 'find')".
test("planning summary without years[] is not recorded, not a JS error", () => {
  const v2 = { schema_version: "value.planning-project-index/v2", project_year_rows: 8, event_rows: 3 };
  assert.deepEqual(planningYearFromPayload(v2, 2025), { summary: null, error: PLANNING_YEAR_NOT_RECORDED });
  assert.deepEqual(planningYearFromPayload(null, 2025), { summary: null, error: PLANNING_YEAR_NOT_RECORDED });
  assert.deepEqual(planningYearFromPayload({ years: "x" }, 2025), { summary: null, error: PLANNING_YEAR_NOT_RECORDED });
  const year = { year: 2025, introduced_projects: 2, accounted_projects: 2, reconciled: true, breakdowns: { outcome: {} } };
  assert.deepEqual(planningYearFromPayload({ ...v2, years: [year] }, 2025), { summary: year, error: "" });
  assert.deepEqual(planningYearFromPayload({ years: [year, null] }, 2026), { summary: null, error: PLANNING_YEAR_NOT_RECORDED });
});

// R-中2: the Compare page names the actual reason annual deltas are withheld.
test("annual withholding notice follows the recorded reason", async () => {
  const { annualWithholdingNotice } = await import("../../../app/features/results/comparisonReview.ts");
  assert.equal(annualWithholdingNotice({ annual_metrics_withheld: false, annual_withholding: [] }), null);
  const teaching = annualWithholdingNotice({ annual_metrics_withheld: true, comparison_scope: "teaching_diagnostic", annual_withholding: [{ reason_code: "teaching_run", run_ids: ["a", "b"] }], run_ids: ["a", "b"] });
  assert.equal(teaching.title, "Teaching boundary");
  assert.match(teaching.lines[0], /48-period market day/);
  // A response without annual_withholding (older backend) keeps the scope rule.
  assert.equal(annualWithholdingNotice({ annual_metrics_withheld: true, comparison_scope: "teaching_diagnostic" }).title, "Teaching boundary");
  const q14 = annualWithholdingNotice({
    annual_metrics_withheld: true, comparison_scope: "annual_publication_withheld", run_ids: ["9749a2a3", "ab225ce5"],
    annual_withholding: [{ reason_code: "result_publication_withheld", run_ids: ["ab225ce5"], text: "is a reproduction Run whose annual results are withheld (Q14): raw invariant storage.single_direction (9343 rows) failed" }],
  });
  assert.equal(q14.title, "Annual results withheld");
  assert.equal(q14.lines[0], "ab225ce5 is a reproduction Run whose annual results are withheld (Q14): raw invariant storage.single_direction (9343 rows) failed. Its full ledger stays available in Inspect.");
  assert.equal(q14.lines[1], "No annual deltas are shown. The export lists the published annual values of 9749a2a3 without deltas.");
  assert.ok(!q14.lines.join(" ").includes("48-period"));
});

// R-低1: Inspect planning rows are project-years with a Year column.
test("planning table title counts project-year records", async () => {
  const { planningRecordsTitle, planningRowsPerYear } = await import("../../../app/features/runs/planningView.ts");
  const index = { total: 8, record_unit: "project_year", items: [{ year: 2026 }, { year: 2025 }] };
  assert.equal(planningRecordsTitle(index), "8 project-year records");
  assert.equal(planningRowsPerYear(index), true);
  const legacy = { total: 3, items: [{}, {}] };
  assert.equal(planningRecordsTitle(legacy), "3 durable project records");
  assert.equal(planningRowsPerYear(legacy), false);
});
