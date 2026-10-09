// Result states and reason codes (P0-9 S7; G1-07; spec 1.1, 4.6).
// Only "invalid" is an error (red frame). "unavailable" means no evidence of this
// kind was recorded; "withheld" means values exist but are not published here.
import { valueStateText, type ValueStateKey } from "./valueStates.ts";
import { COVERAGE_REASON_KEYS } from "./coverageView.ts";
import { localizedTable, tr } from "../../i18n/index.ts";

export type ResultStatusView = { state: ValueStateKey | "reconciled"; tone: "danger" | "caution" | "muted" | "ok" | "info"; label: string; message: string; isError: boolean };

// P1 W5: dictionary messages (reason.*, coverage.reason.*) in the interface language.
const REASON_MESSAGES: Readonly<Record<string, string>> = localizedTable({
  // Precise annual-coverage codes (gridform_core/result_coverage.py); result
  // queries return these in reason_code and the older wording in legacy_reason_code.
  ...COVERAGE_REASON_KEYS,
  cancelled_before_year_complete: "reason.cancelled_before_year_complete",
  failed_before_year_complete: "reason.failed_before_year_complete",
  result_artifact_missing: "reason.result_artifact_missing",
  attribution_evidence_not_recorded: "reason.attribution_evidence_not_recorded",
  legacy_contract_did_not_measure_avoided_curtailment: "reason.legacy_contract_did_not_measure_avoided_curtailment",
  module_does_not_provide_counterfactual_snapshot: "reason.module_does_not_provide_counterfactual_snapshot",
  selected_balancing_does_not_provide_final_zonal_dispatch: "reason.selected_balancing_does_not_provide_final_zonal_dispatch",
  vre_curtailment_attribution_artifact_missing: "reason.vre_curtailment_attribution_artifact_missing",
  // Older wording, still recorded by Runs written before the precise codes.
  annual_evidence_withheld_for_nonannual_run: "reason.annual_evidence_withheld_for_nonannual_run",
  immutable_completed_run_required: "reason.immutable_completed_run_required",
  source_has_active_transaction_files: "reason.source_has_active_transaction_files",
  vre_curtailment_annual_year_set_invalid: "reason.vre_curtailment_annual_year_set_invalid",
  attribution_counterfactual_identity_mismatch: "reason.attribution_counterfactual_identity_mismatch",
  attribution_run_identity_mismatch: "reason.attribution_run_identity_mismatch",
  attribution_source_run_identity_unknown: "reason.attribution_source_run_identity_unknown",
  attribution_source_identity_mismatch: "reason.attribution_source_identity_mismatch",
  attribution_method_or_proof_invalid: "reason.attribution_method_or_proof_invalid",
  source_changed_during_query: "reason.source_changed_during_query",
  // Q14 (gridform_core/result_advisories.py, F-P09-6): the codes of result_publication
  // when a doctoral reproduction Run's annual results are withheld; and the
  // production-policy publication block of P0-4 S7 (backend/model_runner.py, F-P04-4).
  GF_RESULTS_WITHHELD_RAW_INVARIANTS_FAILED: "reason.GF_RESULTS_WITHHELD_RAW_INVARIANTS_FAILED",
  GF_RESULTS_PENDING_RAW_INVARIANTS: "reason.GF_RESULTS_PENDING_RAW_INVARIANTS",
  GF_RESULTS_WITHHELD_RAW_INVARIANTS_NOT_EVALUATED: "reason.GF_RESULTS_WITHHELD_RAW_INVARIANTS_NOT_EVALUATED",
  GF_VALIDATION_GATE_FAILED: "reason.GF_VALIDATION_GATE_FAILED",
  GF_VALIDATION_CONTRACT_OR_MECHANISM: "reason.GF_VALIDATION_CONTRACT_OR_MECHANISM",
});

/** F-P09-6: the reason codes under which a result is "Withheld" in the Q14 sense. */
export const Q14_WITHHELD_REASON_CODES: readonly string[] = ["GF_RESULTS_WITHHELD_RAW_INVARIANTS_FAILED", "GF_RESULTS_WITHHELD_RAW_INVARIANTS_NOT_EVALUATED"];

export function reasonMessage(reasonCode: string | null | undefined): string {
  if (!reasonCode) return tr("reason.none");
  return REASON_MESSAGES[reasonCode] ?? reasonCode.replaceAll("_", " ");
}

// Designer ruling 2: a result held back for coverage says why in its own word;
// "Withheld" stays for Q14 (reproduction runs that did not pass their raw invariants).
const COVERAGE_STATE_BY_REASON: Readonly<Record<string, { state: ValueStateKey; tone: ResultStatusView["tone"] }>> = {
  annual_evidence_withheld_for_nonannual_run: { state: "non_annual", tone: "caution" },
  run_in_progress: { state: "in_progress", tone: "info" },
  immutable_completed_run_required: { state: "in_progress", tone: "info" },
  // R5 R-低2: a reproduction Run that is still running awaits its raw-invariant check.
  GF_RESULTS_PENDING_RAW_INVARIANTS: { state: "in_progress", tone: "info" },
  run_cancelled_before_full_coverage: { state: "stopped", tone: "caution" },
  run_failed_before_full_coverage: { state: "stopped", tone: "caution" },
  annual_period_boundary_incomplete: { state: "partial_year", tone: "caution" },
};

export function resultStatusView(status: string, reasonCode?: string | null, coveragePercent?: number | null): ResultStatusView {
  const message = reasonMessage(reasonCode);
  switch (status) {
    case "reconciled": return { state: "reconciled", tone: "ok", label: tr("reason.reconciled"), message: "", isError: false };
    case "invalid": return { state: "invalid", tone: "danger", label: valueStateText("invalid"), message, isError: true };
    case "withheld": {
      const coverage = reasonCode ? COVERAGE_STATE_BY_REASON[reasonCode] : undefined;
      if (coverage) return { state: coverage.state, tone: coverage.tone, label: valueStateText(coverage.state, coveragePercent), message, isError: false };
      return { state: "withheld", tone: "caution", label: valueStateText("withheld"), message, isError: false };
    }
    default: return { state: "unavailable", tone: "muted", label: valueStateText("unavailable"), message, isError: false };
  }
}
