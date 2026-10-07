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
