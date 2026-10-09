import assert from "node:assert/strict";
import test from "node:test";
import { renderTsx, textOf } from "../helpers/render-tsx.mjs";

// R7-5: a summary-trace staged/zonal Run showed "Solver evidence invalid"
// because per-period solver diagnostics are recorded only with the full trace
// profile. It now shows a neutral state word with a one-line reason; a summary
// with evidence errors still reads as invalid.
const FIXTURES = "tests/frontend/helpers/r75-fixtures.tsx";

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

test("a summary-trace Run shows a neutral not-recorded state word with its reason, in English and Chinese", async () => {
  const englishHtml = await renderTsx(FIXTURES, "SolverEvidenceIn", { locale: "en", summary: traceProfileSummary });
  assert.match(englishHtml, /class="badge blue"/);
  assert.doesNotMatch(englishHtml, /badge warn/);
  const english = textOf(englishHtml);
  assert.match(english, /Not recorded under this trace profile/);
  assert.match(english, /Per-period solver diagnostics are recorded only with the full trace profile\./);
  assert.doesNotMatch(english, /invalid/i);
  const chinese = textOf(await renderTsx(FIXTURES, "SolverEvidenceIn", { locale: "zh", summary: traceProfileSummary }));
  assert.match(chinese, /此追踪级别下未记录/);
  assert.match(chinese, /逐时段求解器诊断只在完整追踪级别下记录。/);
  assert.doesNotMatch(chinese, /无效/);
});

test("a full-trace Run with missing solver rows still shows Solver evidence invalid", async () => {
  const invalid = {
    ...traceProfileSummary,
    study_status: "solver_evidence_invalid",
    evidence_status: "invalid",
    evidence_errors: ["solver_diagnostics_missing_completed_period:2025:1:2025:1"],
    trace_level: undefined,
    evidence_reason: undefined,
  };
  const html = await renderTsx(FIXTURES, "SolverEvidenceIn", { locale: "en", summary: invalid });
  assert.match(html, /class="badge warn"/);
  const text = textOf(html);
  assert.match(text, /Solver evidence invalid/);
  assert.doesNotMatch(text, /trace profile/);
});
