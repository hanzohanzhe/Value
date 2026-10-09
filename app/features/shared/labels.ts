// One label table for metric ids, status words and planning stage names
// (R4, four-role report R-低5 and S-低7(c)). A page shows a recorded code
// through these functions instead of building a heading from the field name
// ("Cem System Cost Gbp Per Mwh Served", "Failed: not_applicable",
// "Reproduction_with_declared_deviations"). An unknown code reads as a
// sentence-case phrase, so a new code never breaks a page.
// P1 W5: the labels are dictionary messages (label.*) in the interface language.
import { localizedTable, tr } from "../../i18n/index.ts";

/** Annual and comparison metric ids (gridform_core/results_summary). */
export const METRIC_LABELS: Readonly<Record<string, string>> = localizedTable({
  cem_system_cost_gbp: "label.metric.cem_system_cost_gbp",
  cem_system_cost_gbp_per_mwh_served: "label.metric.cem_system_cost_gbp_per_mwh_served",
  annualised_capital_gbp: "label.metric.annualised_capital_gbp",
  operating_resource_cost_gbp: "label.metric.operating_resource_cost_gbp",
  total_carbon_emissions_tco2e: "label.metric.total_carbon_emissions_tco2e",
  // R5 (S-F-高1/中2): all unserved energy of the A2 account (PSM-recorded plus
  // stress shortfall), the PSM-recorded part, annual demand and demand served.
  unserved_energy_mwh: "label.metric.unserved_energy_mwh",
  recorded_unserved_energy_mwh: "label.metric.recorded_unserved_energy_mwh",
  demand_mwh: "label.metric.demand_mwh",
  demand_served_mwh: "label.metric.demand_served_mwh",
  // R5 R-中2: the physical unused VRE every PSM records (VRE page definition).
  unused_vre_mwh: "label.metric.unused_vre_mwh",
  unused_vre_share_percent: "label.metric.unused_vre_share_percent",
  // R5-2 review: the doctoral ledger's surplus routed before the balancing stage (VRE page, G1-08).
  pre_balancing_excess_mwh: "label.metric.pre_balancing_excess_mwh",
  vre_curtailment_mwh: "label.metric.vre_curtailment_mwh",
  vre_curtailment_rate: "label.metric.vre_curtailment_rate",
  redispatch_net_impact_mwh: "label.metric.redispatch_net_impact_mwh",
  total_system_cost_gbp: "label.metric.total_system_cost_gbp",
});

/** Status words of checks, gates and scenarios (gridform_core/result_advisories and the validation reports). */
export const STATUS_LABELS: Readonly<Record<string, string>> = localizedTable({
  passed: "label.status.passed",
  failed: "label.status.failed",
  not_applicable: "label.status.not_applicable",
  not_evaluated: "label.status.not_evaluated",
  not_recorded: "label.status.not_recorded",
  not_run: "label.status.not_run",
  unavailable: "label.status.unavailable",
  reproduction_conformant: "label.status.reproduction_conformant",
  reproduction_with_declared_deviations: "label.status.reproduction_with_declared_deviations",
  declared_deviations: "label.status.declared_deviations",
  superseded_pre_fix: "label.status.superseded_pre_fix",
  expected_difference: "label.status.expected_difference",
  informational_scenario_difference: "label.status.informational_scenario_difference",
  required_reproduction_gate: "label.status.required_reproduction_gate",
  teaching_diagnostic: "label.status.teaching_diagnostic",
  // Run and capability states (P1 W5: shown translated by statusWord in another language).
  completed: "label.status.completed",
  running: "label.status.running",
  queued: "label.status.queued",
  snapshotting: "label.status.snapshotting",
  preparing: "label.status.preparing",
  cancel_requested: "label.status.cancel_requested",
  cancelled: "label.status.cancelled",
  archived: "label.status.archived",
  supported: "label.status.supported",
  experimental: "label.status.experimental",
  unsupported: "label.status.unsupported",
});

/** Planning outcomes and development stages; REPD spells some stages in title case. */
export const STAGE_LABELS: Readonly<Record<string, string>> = localizedTable({
  application_submitted: "label.stage.application_submitted",
  awaiting_construction: "label.stage.awaiting_construction",
  under_construction: "label.stage.under_construction",
  operational: "label.stage.operational",
  planning: "label.stage.planning",
  active: "label.stage.active",
  commissioned: "label.stage.commissioned",
  failed: "label.stage.failed",
  failed_planning: "label.stage.failed_planning",
  filtered: "label.stage.filtered",
  deferred: "label.stage.deferred",
  outside_scope: "label.stage.outside_scope",
});

/** A recorded code as a key of the tables: "Application Submitted" and "application_submitted" are one code. */
export function labelKey(code: string): string {
  return code.trim().toLowerCase().replace(/[\s-]+/g, "_");
}

/** An unknown code as a sentence-case phrase: "storage_single_direction" → "Storage single direction". */
export function codePhrase(code: string): string {
  const words = code.trim().replace(/[_\s]+/g, " ");
  return words ? words.charAt(0).toUpperCase() + words.slice(1) : code;
}

export function metricLabel(id: string): string {
  const leaf = id.split(".").at(-1) ?? id;
  return METRIC_LABELS[leaf] ?? codePhrase(leaf);
}

export function statusLabel(code: string | null | undefined, fallback = tr("label.notEvaluated")): string {
  if (code == null || code === "") return fallback;
  return STATUS_LABELS[labelKey(code)] ?? codePhrase(code);
}

export function stageLabel(code: string | null | undefined, fallback = tr("label.notRecorded")): string {
  if (code == null || code === "") return fallback;
  return STAGE_LABELS[labelKey(code)] ?? codePhrase(code);
}

/**
 * The Execution cell of a Run (R4 T-低1): while its inputs are being frozen
 * (lifecycle `snapshotting`) the recorded execution status is still `queued`;
 * the cell then reads "Preparing", like the preparation progress line.
 */
export function executionLabel(run: { status?: string | null; execution_status?: string | null } | null | undefined): string {
  if (run?.status === "snapshotting") return tr("label.preparing");
  return statusLabel(run?.execution_status ?? run?.status, tr("label.notRecorded"));
}

/**
 * A recorded status code shown as a state word (a Run badge, the context bar):
 * the label table's word in the interface language ("Completed", "Not
 * evaluated"; 已完成), an unknown code as a sentence-case phrase.  R-16
 * (P1-polish, ruling on D-W5-3): English shows the word too; the page puts the
 * recorded code in the element's title.
 */
export function statusWord(code: string | null | undefined): string {
  const text = String(code ?? "");
  if (!text) return text;
  const key = labelKey(text);
  return Object.hasOwn(STATUS_LABELS, key) ? STATUS_LABELS[key] : codePhrase(text);
}
