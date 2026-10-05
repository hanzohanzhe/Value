// Result states and reason codes (P0-9 S7; G1-07; spec 1.1, 4.6).
// Only "invalid" is an error (red frame). "unavailable" means no evidence of this
// kind was recorded; "withheld" means values exist but are not published here.
import { valueStateText, type ValueStateKey } from "./valueStates.ts";

export type ResultStatusView = { state: ValueStateKey | "reconciled"; tone: "danger" | "caution" | "muted" | "ok"; label: string; message: string; isError: boolean };

const REASON_MESSAGES: Record<string, string> = {
  result_artifact_missing: "This Run did not write the result artifact for this query.",
  attribution_evidence_not_recorded: "This Run did not record VRE curtailment attribution (for example, copperplate balancing records none).",
  legacy_contract_did_not_measure_avoided_curtailment: "This older ledger did not measure avoided curtailment.",
  module_does_not_provide_counterfactual_snapshot: "The selected PSM does not provide matched VRE counterfactual snapshots.",
  selected_balancing_does_not_provide_final_zonal_dispatch: "The selected balancing module does not provide final zonal dispatch evidence.",
  vre_curtailment_attribution_artifact_missing: "The compact attribution artifact is missing.",
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
};

export function reasonMessage(reasonCode: string | null | undefined): string {
  if (!reasonCode) return "No reason was recorded.";
  return REASON_MESSAGES[reasonCode] ?? reasonCode.replaceAll("_", " ");
}

export function resultStatusView(status: string, reasonCode?: string | null): ResultStatusView {
  const message = reasonMessage(reasonCode);
  switch (status) {
    case "reconciled": return { state: "reconciled", tone: "ok", label: "Reconciled", message: "", isError: false };
    case "invalid": return { state: "invalid", tone: "danger", label: valueStateText("invalid"), message, isError: true };
    case "withheld": return { state: "withheld", tone: "caution", label: valueStateText("withheld"), message, isError: false };
    default: return { state: "unavailable", tone: "muted", label: valueStateText("unavailable"), message, isError: false };
  }
}
