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

// R-低2: an unfinished Run's advisory count is marked provisional.
test("advisory summary of an unfinished Run is provisional", async () => {
  const { advisorySummaryText, ADVISORIES_PROVISIONAL_NOTE } = await import("../../../app/features/workspace/runValidation.ts");
  const advisories = [{ id: "a", severity: "high" }];
  assert.equal(advisorySummaryText({ advisories }), "1 advisory applies to this Run · 1 high");
  assert.equal(advisorySummaryText({ advisories, advisories_provisional: true }), `1 advisory applies to this Run · 1 high · ${ADVISORIES_PROVISIONAL_NOTE}`);
});

// R-低3: the "has started" notice stays with the Study and page that started the Run.
test("started-run notice is bound to its Study and page", async () => {
  const { startedRunNoticeVisible } = await import("../../../app/features/runs/runHistoryView.ts");
  const started = { runId: "r1", mode: "two_year", text: "The complete two-year model has started.", studyId: "s1", view: "run" };
  assert.equal(startedRunNoticeVisible(started, { view: "run", studyId: "s1" }), true);
  assert.equal(startedRunNoticeVisible(started, { view: "projects", studyId: "s1" }), false);
  assert.equal(startedRunNoticeVisible(started, { view: "run", studyId: "s2" }), false);
  assert.equal(startedRunNoticeVisible(null, { view: "run", studyId: "s1" }), false);
  assert.equal(startedRunNoticeVisible({ runId: "r1", mode: "smoke", text: "x" }, { view: "data", studyId: "" }), true);
});

// R-低4: the action that opens Inspect's artifact list is not called an export.
test("ledger action is named for what it does", async () => {
  const { NOTICE_ACTION_LABELS } = await import("../../../app/features/workspace/runValidation.ts");
  assert.equal(NOTICE_ACTION_LABELS.export_ledger, "Open ledger files");
});

// R-低5 / S-低7(c): one label table for metric ids, status words and stage names.
test("shared label table names metrics, statuses and stages", async () => {
  const { metricLabel, statusLabel, stageLabel, codePhrase, executionLabel } = await import("../../../app/features/shared/labels.ts");
  assert.equal(metricLabel("cem_system_cost_gbp_per_mwh_served"), "CEM system cost per MWh served (GBP/MWh)");
  assert.equal(metricLabel("total_carbon_emissions_tco2e"), "Total carbon emissions (tCO2e)");
  assert.equal(metricLabel("redispatch_net_impact_mwh"), "Redispatch net impact (MWh)");
  assert.equal(metricLabel("annual.some_new_metric"), "Some new metric");
  assert.equal(statusLabel("not_applicable"), "Not applicable");
  assert.equal(statusLabel("reproduction_with_declared_deviations"), "Reproduction with declared deviations");
  assert.equal(statusLabel("Reproduction_with_declared_deviations"), "Reproduction with declared deviations");
  assert.equal(statusLabel(null), "Not evaluated");
  assert.equal(stageLabel("application_submitted"), "Application submitted");
  assert.equal(stageLabel("Application Submitted"), "Application submitted");
  assert.equal(stageLabel("failed_planning"), "Failed planning");
  assert.equal(codePhrase("matching_recorded_configuration"), "Matching recorded configuration");
  // T-低1: the Execution cell reads "Preparing" while the inputs are frozen.
  assert.equal(executionLabel({ status: "snapshotting", execution_status: "queued" }), "Preparing");
  assert.equal(executionLabel({ status: "queued", execution_status: "queued" }), "Queued");
  assert.equal(executionLabel({ status: "completed", execution_status: "passed" }), "Passed");
  assert.equal(executionLabel({}), "Not recorded");
});

test("Run context bar reads preparing while the inputs are frozen (T-低1)", async () => {
  const { resolveRunContext } = await import("../../../app/features/workspace/runContext.ts");
  assert.equal(resolveRunContext({ run: { id: "r", status: "snapshotting", execution_status: "queued" } }).executionStatus, "preparing");
  assert.equal(resolveRunContext({ run: { id: "r", status: "queued", execution_status: "queued" } }).executionStatus, "queued");
});

// R-低6: a pack recovered from frozen inputs is never the default draft pack.
test("draft pack fallback skips recovered and overlay packs", async () => {
  const { defaultDraftPackId } = await import("../../../app/features/studies/draftPack.ts");
  const packs = [
    { id: "doctoral-101-recovered", complete: true, frozen_recovery_origin: { source_run_id: "ab225ce5" } },
    { id: "uk-empty", complete: false },
    { id: "value-101-network", complete: true, data_pack_type: "network_overlay" },
    { id: "value-101-baseline-v1", complete: true },
  ];
  assert.equal(defaultDraftPackId(packs, "value-uk-1000twh-reproduction"), "value-101-baseline-v1");
  assert.equal(defaultDraftPackId(packs, "doctoral-101-recovered"), "doctoral-101-recovered", "an explicit choice is kept");
  assert.equal(defaultDraftPackId(packs.slice(0, 2), "gone"), "uk-empty");
  assert.equal(defaultDraftPackId([packs[0]], "gone"), "doctoral-101-recovered");
  assert.equal(defaultDraftPackId([], "gone"), "");
});

// R-低7: a domain the methodology does not admit is not labelled "ready".
test("domain card badge follows the methodology verdict", async () => {
  const { domainBadgeText } = await import("../../../app/features/studies/methodologyChoice.ts");
  assert.equal(domainBadgeText("ready", true), "ready");
  assert.equal(domainBadgeText("contract_level", true), "contract level");
  assert.equal(domainBadgeText("ready", false), "not available with this methodology");
});

// R-低8: a first estimate is a range; a measured one is a single value in minutes or hours.
test("runtime estimate text", async () => {
  const { runtimeEstimateText } = await import("../../../app/features/runs/runHistoryView.ts");
  assert.equal(runtimeEstimateText({ runtime_seconds: 1051, runtime_range_seconds: [175.2, 1051.2] }), "estimated 3 min to 18 min (no comparable completed Run yet)");
  assert.equal(runtimeEstimateText({ runtime_seconds: 120 }), "estimated about 2 min");
  assert.equal(runtimeEstimateText({ runtime_seconds: 5400 }), "estimated about 1.5 hours");
  assert.equal(runtimeEstimateText({ runtime_range_seconds: [60, 60] }), "estimated about 1 min (no comparable completed Run yet)");
  assert.equal(runtimeEstimateText({}), "Runtime estimate not available");
});

// R-低10: the VRE page does not request the annual summary of a withheld Run.
test("withheld Run is recognised before annual requests", async () => {
  const { annualResultsWithheld, VRE_WITHHELD_TEXT } = await import("../../../app/features/workspace/runValidation.ts");
  assert.equal(annualResultsWithheld({ result_publication: { status: "withheld" } }), true);
  assert.equal(annualResultsWithheld({ result_publication: { status: "published" } }), false);
  assert.equal(annualResultsWithheld(undefined), false);
  assert.match(VRE_WITHHELD_TEXT, /Market replay and Inspect/);
});
