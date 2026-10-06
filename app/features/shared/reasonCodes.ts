// Result states and reason codes (P0-9 S7; G1-07; spec 1.1, 4.6).
// Only "invalid" is an error (red frame). "unavailable" means no evidence of this
// kind was recorded; "withheld" means values exist but are not published here.
import { valueStateText, type ValueStateKey } from "./valueStates.ts";
import { COVERAGE_REASON_TEXT } from "./coverageView.ts";

export type ResultStatusView = { state: ValueStateKey | "reconciled"; tone: "danger" | "caution" | "muted" | "ok" | "info"; label: string; message: string; isError: boolean };

const REASON_MESSAGES: Record<string, string> = {
  // Precise annual-coverage codes (gridform_core/result_coverage.py); result
  // queries return these in reason_code and the older wording in legacy_reason_code.
  ...COVERAGE_REASON_TEXT,
  cancelled_before_year_complete: "The Run was cancelled before every declared year was computed; the missing years have no results.",
  failed_before_year_complete: "The Run stopped with a failure before every declared year was computed; the missing years have no results.",
  result_artifact_missing: "This Run did not write the result artifact for this query.",
  attribution_evidence_not_recorded: "This Run did not record VRE curtailment attribution (for example, copperplate balancing records none).",
  legacy_contract_did_not_measure_avoided_curtailment: "This older ledger did not measure avoided curtailment.",
  module_does_not_provide_counterfactual_snapshot: "The selected PSM does not provide matched VRE counterfactual snapshots.",
  selected_balancing_does_not_provide_final_zonal_dispatch: "The selected balancing module does not provide final zonal dispatch evidence.",
  vre_curtailment_attribution_artifact_missing: "The compact attribution artifact is missing.",
  // Older wording, still recorded by Runs written before the precise codes.
  annual_evidence_withheld_for_nonannual_run: "Annual values are not published for a non-annual Run or a partial year.",
  immutable_completed_run_required: "Results are published once the Run has completed.",
  source_has_active_transaction_files: "The ledger is still being written; try again when the Run has finished.",
  vre_curtailment_annual_year_set_invalid: "The years in the ledger differ from the years the Run declared.",
  attribution_counterfactual_identity_mismatch: "Attribution periods do not match the accounting periods they explain.",
  attribution_run_identity_mismatch: "The evidence names a different Run.",
  attribution_source_run_identity_unknown: "The evidence does not record which Run produced it.",
  attribution_source_identity_mismatch: "The evidence's data or module identity differs from this Run's.",
  attribution_method_or_proof_invalid: "The attribution method or its proof is not the one this version accepts.",
  source_changed_during_query: "The source changed while it was being read; reload the page.",
  // Q14 (gridform_core/result_advisories.py, F-P09-6): the codes of result_publication
  // when a doctoral reproduction Run's annual results are withheld; and the
  // production-policy publication block of P0-4 S7 (backend/model_runner.py, F-P04-4).
  GF_RESULTS_WITHHELD_RAW_INVARIANTS_FAILED: "A raw invariant of this reproduction Run failed, so its annual results are not published on result pages; Inspect and exports keep them.",
  GF_RESULTS_WITHHELD_RAW_INVARIANTS_NOT_EVALUATED: "The raw invariants of this reproduction Run were not evaluated, so its annual results are not published on result pages; Inspect and exports keep them.",
  GF_VALIDATION_GATE_FAILED: "A validation gate (run invariants, energy balance or storage limits) failed, so annual results are not published.",
  GF_VALIDATION_CONTRACT_OR_MECHANISM: "A required contract or analytical-invariant check failed, so annual results are not published.",
};

/** F-P09-6: the reason codes under which a result is "Withheld" in the Q14 sense. */
export const Q14_WITHHELD_REASON_CODES: readonly string[] = ["GF_RESULTS_WITHHELD_RAW_INVARIANTS_FAILED", "GF_RESULTS_WITHHELD_RAW_INVARIANTS_NOT_EVALUATED"];

export function reasonMessage(reasonCode: string | null | undefined): string {
  if (!reasonCode) return "No reason was recorded.";
  return REASON_MESSAGES[reasonCode] ?? reasonCode.replaceAll("_", " ");
}

// Designer ruling 2: a result held back for coverage says why in its own word;
// "Withheld" stays for Q14 (reproduction runs that did not pass their raw invariants).
const COVERAGE_STATE_BY_REASON: Readonly<Record<string, { state: ValueStateKey; tone: ResultStatusView["tone"] }>> = {
  annual_evidence_withheld_for_nonannual_run: { state: "non_annual", tone: "caution" },
  run_in_progress: { state: "in_progress", tone: "info" },
  immutable_completed_run_required: { state: "in_progress", tone: "info" },
  run_cancelled_before_full_coverage: { state: "stopped", tone: "caution" },
  run_failed_before_full_coverage: { state: "stopped", tone: "caution" },
  annual_period_boundary_incomplete: { state: "partial_year", tone: "caution" },
};

export function resultStatusView(status: string, reasonCode?: string | null, coveragePercent?: number | null): ResultStatusView {
  const message = reasonMessage(reasonCode);
  switch (status) {
    case "reconciled": return { state: "reconciled", tone: "ok", label: "Reconciled", message: "", isError: false };
    case "invalid": return { state: "invalid", tone: "danger", label: valueStateText("invalid"), message, isError: true };
    case "withheld": {
      const coverage = reasonCode ? COVERAGE_STATE_BY_REASON[reasonCode] : undefined;
      if (coverage) return { state: coverage.state, tone: coverage.tone, label: valueStateText(coverage.state, coveragePercent), message, isError: false };
      return { state: "withheld", tone: "caution", label: valueStateText("withheld"), message, isError: false };
    }
    default: return { state: "unavailable", tone: "muted", label: valueStateText("unavailable"), message, isError: false };
  }
}
