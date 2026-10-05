// Review reasons of a comparison (X0 S10b comparison gate, P0-4 S3; P0-9 S11).
// gridform_core/results_summary.compare_run_summaries decides them; this module
// only states each one in a sentence. An unknown reason is shown by its code.
import { profileBadge } from "../workspace/runValidation.ts";

export type ReviewReason = {
  reason: string;
  run_id?: string | null;
  advisory_id?: string | null;
  severity?: string | null;
  profile_ids?: (string | null)[];
  differing_fields?: string[];
};

function runPrefix(reason: ReviewReason): string {
  return reason.run_id ? `${reason.run_id}: ` : "";
}

export function reviewReasonText(reason: ReviewReason): string {
  switch (reason.reason) {
    case "advisory":
      return `${runPrefix(reason)}advisory ${reason.advisory_id ?? "(unnamed)"}${reason.severity ? ` (${reason.severity})` : ""} applies.`;
    case "validation_failed":
      return `${runPrefix(reason)}scientific validation failed.`;
    case "energy_balance_failed":
      return `${runPrefix(reason)}the energy balance check failed.`;
    case "run_invariants_failed":
      return `${runPrefix(reason)}the run invariants failed.`;
    case "annual_results_withheld":
      return `${runPrefix(reason)}annual results are withheld (reproduction run).`;
    case "methodology_differs": {
      const profiles = (reason.profile_ids ?? []).map((id) => id ? profileBadge({ status: "recorded", profile_id: id }).text : "methodology not recorded");
      const unique = [...new Set(profiles)];
      return unique.length > 1
        ? `The Runs use different methodologies: ${unique.join("; ")}.`
        : `The Runs record different methodology identities (${(reason.differing_fields ?? []).map((field) => field.replaceAll("_", " ")).join(", ") || "identity"}).`;
    }
    default:
      return `${runPrefix(reason)}${reason.reason.replaceAll("_", " ")}.`;
  }
}
