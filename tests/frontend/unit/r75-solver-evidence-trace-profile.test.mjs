import assert from "node:assert/strict";
import test from "node:test";
import { isSolverValidationSummary, solverEvidenceNotRecordedByTraceProfile } from "../../../app/features/network/networkRedispatch.ts";

// R7-5: a summary-trace staged/zonal Run records no per-period solver
// diagnostics by design. Its read model says "not_recorded_under_trace_profile";
// the page must accept that summary and must not treat it as invalid evidence.
const traceProfileSummary = {
  schema_version: "value.solver-validation-summary/v1",
  annual_status: "NOT_RECORDED",
  study_status: "NOT_RECORDED",
  solver_validated: false,
  solver_stack_validation_status: "solver_stack_not_yet_validated",
  inherited_unvalidated: false,
  first_causal_period: null,
  row_count: 0,
  warning_periods: 0,
  unvalidated_periods: 0,
  maximum_validated_ceiling_use: 0,
  phases: {},
  evidence_status: "not_recorded_under_trace_profile",
  evidence_reason: "per_period_solver_diagnostics_recorded_only_with_full_trace",
  trace_level: "summary",
  evidence_errors: [],
};

test("the trace-profile summary is a valid solver summary and reads as not recorded by profile", () => {
  assert.equal(isSolverValidationSummary(traceProfileSummary), true);
  assert.equal(solverEvidenceNotRecordedByTraceProfile(traceProfileSummary), true);
});

test("evidence errors or an invalid study status are never hidden behind the trace profile", () => {
  assert.equal(solverEvidenceNotRecordedByTraceProfile({ ...traceProfileSummary, evidence_errors: ["summary_contains_full_only_rows:network_solver_diagnostics:6"] }), false);
  assert.equal(solverEvidenceNotRecordedByTraceProfile({ ...traceProfileSummary, study_status: "solver_evidence_invalid" }), false);
  assert.equal(solverEvidenceNotRecordedByTraceProfile({ ...traceProfileSummary, evidence_status: "invalid" }), false);
  assert.equal(isSolverValidationSummary({ ...traceProfileSummary, evidence_status: "not_recorded_somehow" }), false);
});
