import assert from "node:assert/strict";
import test from "node:test";
import { studyMethodologyText } from "../../../app/features/studies/methodologyChoice.ts";
import { publicationPending, rawInvariantsField, runNotices, VRE_PENDING_TEXT } from "../../../app/features/workspace/runValidation.ts";
import { unusedVreText } from "../../../app/features/runs/resultMetrics.ts";
import { metricLabel } from "../../../app/features/shared/labels.ts";
import { acceptedSupplyNote } from "../../../app/features/market/dispatchView.ts";
import { runEvidenceKey, runPreparing } from "../../../app/features/shared/stableRun.ts";
import { runHistoryEmpty } from "../../../app/features/runs/runHistoryView.ts";

// R5 (DECISIONS A28): the reproduce-role defects of the final acceptance report.

const catalogue = {
  default_profile_id: "value-corrected",
  profiles: [
    { id: "value-corrected", label: "Corrected methodology (default)", frozen: false, default: true },
    { id: "doctoral-lineage-0.6.0a2", label: "Doctoral reproduction (as implemented in VALUE 0.6.0-alpha.2)", frozen: true, default: false },
  ],
};

test("R-中1: a saved Study names the methodology it runs under", () => {
  assert.deepEqual(studyMethodologyText({}, catalogue), { label: "Corrected methodology (default)", profileId: "value-corrected", frozen: false });
  assert.deepEqual(studyMethodologyText({ "methodology.profile": "doctoral-lineage-0.6.0a2" }, catalogue),
    { label: "Doctoral reproduction", profileId: "doctoral-lineage-0.6.0a2", frozen: true });
  // Without the catalogue the recorded id is shown, never a guess.
  assert.equal(studyMethodologyText({ "methodology.profile": "doctoral-lineage-0.6.0a2" }, null).label, "doctoral-lineage-0.6.0a2");
  assert.equal(studyMethodologyText(undefined, null).label, "Default methodology");
});

test("R-中2: the Runs card shows unused VRE at the PSM boundary with its share", () => {
  assert.equal(unusedVreText({ unused_vre_mwh: 4002.89, available_vre_mwh: 128997.48 }), "4,002.89 MWh · 3.1% of available");
  assert.equal(unusedVreText({ unused_vre_mwh: 2 }), "2 MWh");
  assert.equal(unusedVreText({}), "Not recorded");
  assert.equal(metricLabel("unused_vre_mwh"), "Unused VRE at the PSM boundary (MWh)");
  assert.equal(metricLabel("unused_vre_share_percent"), "Unused VRE share of available VRE (%)");
});

test("R-低1: the evidence key ignores a re-polled copy and follows status and years", () => {
  const run = { id: "r", status: "snapshotting", completed_years: 0, preparation: { elapsed_seconds: 1 } };
  assert.equal(runEvidenceKey(run), runEvidenceKey({ ...run, preparation: { elapsed_seconds: 3 } }));
  assert.notEqual(runEvidenceKey(run), runEvidenceKey({ ...run, status: "running" }));
  assert.notEqual(runEvidenceKey({ ...run, status: "running" }), runEvidenceKey({ ...run, status: "running", completed_years: 1 }));
  assert.equal(runEvidenceKey(undefined), "");
  assert.equal(runPreparing(run), true);
  assert.equal(runPreparing({ status: "queued" }), true);
  assert.equal(runPreparing({ status: "running" }), false);
});

test("R-低2: a doctoral Run that is still running reads Pending, not withheld or not evaluated", () => {
  const pending = {
    methodology: { profile_id: "doctoral-lineage-0.6.0a2", frozen: true },
    result_publication: { status: "withheld", rule: "raw_invariants_must_pass", raw_invariants_status: "pending", reason_code: "GF_RESULTS_PENDING_RAW_INVARIANTS" },
  };
  assert.equal(publicationPending(pending.result_publication), true);
  assert.equal(rawInvariantsField(pending).text, "Pending");
  const notice = runNotices(pending).find((row) => row.id === "results_withheld");
  assert.equal(notice.tone, "info");
  assert.match(notice.title, /pending/);
  assert.doesNotMatch(notice.body, /not evaluated|withheld/i);
  assert.match(VRE_PENDING_TEXT, /still running/);
  const finished = { ...pending, result_publication: { status: "withheld", raw_invariants_status: "not_evaluated", reason_code: "GF_RESULTS_WITHHELD_RAW_INVARIANTS_NOT_EVALUATED" } };
  assert.equal(publicationPending(finished.result_publication), false);
  assert.equal(rawInvariantsField(finished).text, "Not evaluated");
  assert.match(runNotices(finished).find((row) => row.id === "results_withheld").title, /withheld/);
});

test("R-低10: Accepted supply states its balance boundary", () => {
  assert.match(acceptedSupplyNote({ accepted_supply_boundary: { boundary_id: "native_corrected_full_node_v1" } }), /storage charge/);
  assert.match(acceptedSupplyNote({ accepted_supply_boundary: { boundary_id: "default_psm_surplus_node_v1" } }), /pre-balancing surplus is outside/);
  assert.equal(acceptedSupplyNote({}), "Balance boundary not recorded.");
});

test("R-低13: the empty Run history does not promise two full years", () => {
  const body = runHistoryEmpty(0, false).body;
  assert.doesNotMatch(body, /two full years/);
  assert.match(body, /Check for/);
});

test("R5-2 review: a cross-boundary unused-VRE delta shows the gate reason; pre-balancing excess is labelled", async () => {
  const { metricDeltaShown, metricDeltaWithheldText, missingMetricValueText } = await import("../../../app/features/results/comparisonReview.ts");
  const comparison = {
    metric_deltas_allowed: true, annual_metrics_withheld: false,
    metric_delta_gates: { unused_vre_mwh: { allowed: false, reason_code: "unused_vre_boundary_differs", reason: "Unused VRE is measured at different PSM boundaries (after separate prebalancing excess, full node gross vre output); the doctoral pre-balancing excess is reported separately." } },
  };
  assert.equal(metricDeltaShown(comparison, "unused_vre_mwh"), false);
  assert.match(metricDeltaWithheldText(comparison, "unused_vre_mwh"), /different PSM boundaries/);
  assert.equal(metricLabel("pre_balancing_excess_mwh"), "Pre-balancing excess, reported separately (MWh)");
  assert.equal(missingMetricValueText("pre_balancing_excess_mwh"), "Not applicable");
});
