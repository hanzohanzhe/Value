// One label table for metric ids, status words and planning stage names
// (R4, four-role report R-低5 and S-低7(c)). A page shows a recorded code
// through these functions instead of building a heading from the field name
// ("Cem System Cost Gbp Per Mwh Served", "Failed: not_applicable",
// "Reproduction_with_declared_deviations"). An unknown code reads as a
// sentence-case phrase, so a new code never breaks a page.

/** Annual and comparison metric ids (gridform_core/results_summary). */
export const METRIC_LABELS: Readonly<Record<string, string>> = {
  cem_system_cost_gbp: "CEM system cost (GBP)",
  cem_system_cost_gbp_per_mwh_served: "CEM system cost per MWh served (GBP/MWh)",
  annualised_capital_gbp: "Annualised capital (GBP)",
  operating_resource_cost_gbp: "Operating resource cost (GBP)",
  total_carbon_emissions_tco2e: "Total carbon emissions (tCO2e)",
  // R5 (S-F-高1/中2): all unserved energy of the A2 account (PSM-recorded plus
  // stress shortfall), the PSM-recorded part, annual demand and demand served.
  unserved_energy_mwh: "Unserved energy incl. stress shortfall (MWh)",
  recorded_unserved_energy_mwh: "Unserved energy recorded by the PSM (MWh)",
  demand_mwh: "Annual demand (MWh)",
  demand_served_mwh: "Demand served (MWh)",
  vre_curtailment_mwh: "VRE curtailment (MWh)",
  vre_curtailment_rate: "VRE curtailment rate",
  redispatch_net_impact_mwh: "Redispatch net impact (MWh)",
  total_system_cost_gbp: "Total system cost (GBP)",
};

/** Status words of checks, gates and scenarios (gridform_core/result_advisories and the validation reports). */
export const STATUS_LABELS: Readonly<Record<string, string>> = {
  passed: "Passed",
  failed: "Failed",
  not_applicable: "Not applicable",
  not_evaluated: "Not evaluated",
  not_recorded: "Not recorded",
  not_run: "Not run",
  unavailable: "Unavailable",
  reproduction_conformant: "Reproduction conformant",
  reproduction_with_declared_deviations: "Reproduction with declared deviations",
  declared_deviations: "Declared deviations",
  superseded_pre_fix: "Superseded (pre-fix)",
  expected_difference: "Expected difference",
  informational_scenario_difference: "Informational scenario difference",
  required_reproduction_gate: "Required reproduction gate",
  teaching_diagnostic: "Teaching diagnostic",
};

/** Planning outcomes and development stages; REPD spells some stages in title case. */
export const STAGE_LABELS: Readonly<Record<string, string>> = {
  application_submitted: "Application submitted",
  awaiting_construction: "Awaiting construction",
  under_construction: "Under construction",
  operational: "Operational",
  planning: "Planning",
  active: "Active",
  commissioned: "Commissioned",
  failed: "Failed",
  failed_planning: "Failed planning",
  filtered: "Filtered",
  deferred: "Deferred",
  outside_scope: "Outside scope",
};

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

export function statusLabel(code: string | null | undefined, fallback = "Not evaluated"): string {
  if (code == null || code === "") return fallback;
  return STATUS_LABELS[labelKey(code)] ?? codePhrase(code);
}

export function stageLabel(code: string | null | undefined, fallback = "Not recorded"): string {
  if (code == null || code === "") return fallback;
  return STAGE_LABELS[labelKey(code)] ?? codePhrase(code);
}

/**
 * The Execution cell of a Run (R4 T-低1): while its inputs are being frozen
 * (lifecycle `snapshotting`) the recorded execution status is still `queued`;
 * the cell then reads "Preparing", like the preparation progress line.
 */
export function executionLabel(run: { status?: string | null; execution_status?: string | null } | null | undefined): string {
  if (run?.status === "snapshotting") return "Preparing";
  return statusLabel(run?.execution_status ?? run?.status, "Not recorded");
}
