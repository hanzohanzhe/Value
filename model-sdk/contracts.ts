/** Serializable mirror of the Python VALUE v2 contracts.
 *
 * Dataset and artifact roles are manifest-defined strings. The SDK deliberately
 * does not maintain a second hand-written role union.
 */

export type DatasetRole = string;
export type ExtensionNamespace = Record<string, unknown>;

export interface ArtifactReference {
  schema_version: "value.artifact/v2";
  artifact_id: string;
  kind: string;
  uri: string;
  media_type: string;
  checksum_sha256?: string | null;
  size_bytes?: number | null;
  extensions: ExtensionNamespace;
}

export interface ModuleSelection {
  schema_version: "value.module-selection/v2";
  slot: string;
  module_id: string;
  module_version: string;
  contract_version: string;
}

export interface LocalModuleInstallation {
  schema_version: "value.module-installation/v1";
  module_id: string;
  name: string;
  module_version: string;
  scientific_version?: string | null;
  slot: string;
  contract_version: string;
  implementation: string;
  bundle_sha256: string;
  source_sha256: string;
  installed_at: string;
  enabled: boolean;
  origin: "local_bundle";
  execution_boundary: "in_process_trusted_python";
  scientific_validation_status: "not_evaluated";
  conformance: {
    status: "passed" | "failed";
    errors: string[];
    warnings: string[];
  };
}

export interface ResolvedRun {
  schema_version: "value.resolved-run/v2";
  run_id: string;
  project_id: string;
  scenario_id: string;
  data_pack_id: string;
  start_year: number;
  end_year: number;
  modules: Record<string, ModuleSelection>;
  scientific_parameters: Record<string, unknown>;
  runtime_controls: Record<string, unknown>;
  extensions: ExtensionNamespace;
}

export interface AssetStateV2 {
  schema_version: "value.asset-state/v2";
  asset_id: string;
  technology: string;
  capacity_mw: number;
  energy_capacity_mwh?: number | null;
  region?: string | null;
  status: string;
  extensions: ExtensionNamespace;
}

export interface PlanningProject {
  schema_version: "value.planning-project/v2";
  project_id: string;
  name: string;
  source: string;
  technology: string;
  capacity_mw: number;
  original_capacity_mw: number;
  region: string;
  latitude?: number | null;
  longitude?: number | null;
  development_stage: string;
  status: string;
  decision_year: number;
  expected_completion_year: number;
  success_mode: string;
  success_probability: number;
  random_draw?: number | null;
  outcome: string;
  failure_reason_code?: string | null;
  assigned_asset_id?: string | null;
  extensions: ExtensionNamespace;
}

export interface PlanningEvent {
  schema_version: "value.planning-event/v2";
  event_id: string;
  project_id: string;
  year: number;
  event_type: string;
  event_sequence: number;
  reason_code?: string | null;
  from_stage?: string | null;
  to_stage?: string | null;
  capacity_mw?: number | null;
  region?: string | null;
  extensions: ExtensionNamespace;
}

export interface YearState {
  schema_version: "value.year-state/v2";
  year: number;
  assets: AssetStateV2[];
  planning_projects: PlanningProject[];
  cumulative_metrics: Record<string, number>;
  extensions: ExtensionNamespace;
}

export interface OperatingState {
  schema_version: "value.operating-state/v2";
  year: number;
  assets: AssetStateV2[];
  active_planning_projects: PlanningProject[];
  extensions: ExtensionNamespace;
}

export interface PlanningAdvanceResult {
  schema_version: "value.planning-advance-result/v2";
  year: number;
  operating_state: OperatingState;
  active_projects: PlanningProject[];
  commissioned_projects: PlanningProject[];
  failed_projects: PlanningProject[];
  deferred_projects: PlanningProject[];
  events: PlanningEvent[];
  artifacts: ArtifactReference[];
}

export interface PSMInputV2 {
  schema_version: "value.psm-input/v2";
  run_id: string;
  year: number;
  data_pack_id: string;
  operating_state: OperatingState;
  period_hours: number;
  parameters: Record<string, unknown>;
  units: Record<string, string>;
  extensions: ExtensionNamespace;
}

export interface PeriodSummary {
  schema_version: "value.period-summary/v2";
  period_id: string;
  year: number;
  period: number;
  market_stage: string;
  forecast_demand_mwh: number;
  real_demand_mwh: number;
  accepted_supply_mwh: number;
  storage_charge_mwh: number;
  storage_discharge_mwh: number;
  vre_available_mwh: number;
  vre_accepted_mwh: number;
  curtailed_mwh: number;
  import_mwh: number;
  clearing_price_gbp_per_mwh: number;
  physical_resource_cost_gbp: number;
  market_payment_gbp: number;
  blackout_mwh: number;
  energy_balance_residual_mwh: number;
  units: Record<string, string>;
}

export interface MarketYearResult {
  schema_version: "value.market-year-result/v2";
  result_id: string;
  year: number;
  module_id: string;
  module_version: string;
  generation_mwh_by_asset: Record<string, number>;
  market_income_gbp_by_agent: Record<string, number>;
  total_system_cost_gbp: number;
  total_operational_cost_gbp: number;
  total_levelized_capital_cost_gbp: number;
  total_demand_mwh: number;
  total_generation_mwh: number;
  total_blackout_mwh: number;
  total_excess_mwh: number;
  period_summaries: PeriodSummary[];
  artifacts: ArtifactReference[];
  units: Record<string, string>;
  extensions: ExtensionNamespace;
}

export interface ExpansionHeadroom {
  schema_version: "value.expansion-headroom/v2";
  headroom_id: string;
  year: number;
  module_id: string;
  allowed_additions_mw: Record<string, number>;
  method: string;
  evidence: Record<string, number>;
  units: Record<string, string>;
  extensions: ExtensionNamespace;
}

export interface InvestmentProposal {
  schema_version: "value.investment-proposal/v2";
  proposal_id: string;
  year: number;
  agent_id: string;
  technology: string;
  capacity_mw: number;
  region: string;
  expected_completion_year: number;
  evidence: Record<string, number>;
  extensions: ExtensionNamespace;
}

export interface InvestmentDecision {
  schema_version: "value.investment-decision/v2";
  decision_id: string;
  year: number;
  module_id: string;
  proposals: InvestmentProposal[];
  retirements_mw: Record<string, number>;
  artifacts: ArtifactReference[];
  extensions: ExtensionNamespace;
}

export interface PlanningAdmissionResult {
  schema_version: "value.planning-admission-result/v2";
  year: number;
  admitted_projects: PlanningProject[];
  rejected_proposals: InvestmentProposal[];
  next_pipeline: PlanningProject[];
  events: PlanningEvent[];
  artifacts: ArtifactReference[];
}

export interface YearResultV2 {
  schema_version: "value.year-result/v2";
  result_id: string;
  year: number;
  planning_advance: PlanningAdvanceResult;
  market: MarketYearResult;
  expansion_headroom: ExpansionHeadroom[];
  investment: InvestmentDecision;
  planning_admission: PlanningAdmissionResult;
  next_state: YearState;
  artifacts: ArtifactReference[];
}

export interface ModuleManifestV2 {
  schema_version: "value.module/v2";
  id: string;
  name: string;
  version: string;
  scientific_version?: string | null;
  slot: string;
  implementation: string;
  contract_version: string;
  inputs: DatasetRole[];
  outputs: string[];
  parameters: string[];
  state_reads: string[];
  state_writes: string[];
  determinism: "deterministic" | "seeded" | "stochastic";
  artifacts: string[];
  description: string;
  status: string;
  selection_required: boolean;
  provides_capabilities: string[];
  requires_capabilities: string[];
}

export type CanonicalVRETechnology =
  | "Solar"
  | "Onshore wind"
  | "Offshore wind";

export interface VRECounterfactualRow {
  asset_id: string;
  owner_id: string;
  canonical_technology: CanonicalVRETechnology;
  zone_id: string;
  bid_tranche_id: string;
  realised_available_vre_mwh: number;
  perfect_forecast_copperplate_dispatch_mwh: number;
  realised_copperplate_dispatch_mwh: number;
  zonal_final_dispatch_mwh: number;
}

export interface VRECounterfactualSnapshot {
  run_id: string;
  year: number;
  period: number;
  period_id: string;
  realised_input_sha256: string;
  rows: VRECounterfactualRow[];
  module_identities: Record<string, string>;
  schema: "value.vre-counterfactual-snapshot/v1";
}

export interface VREReferenceGroup {
  canonical_technology: CanonicalVRETechnology;
  bid_tranche_id: string;
  realised_available_vre_mwh: number;
  raw_perfect_forecast_copperplate_dispatch_mwh: number;
  raw_realised_copperplate_dispatch_mwh: number;
  perfect_reference_dispatch_mwh: number;
  copperplate_reference_dispatch_mwh: number;
}

export interface VRECurtailmentDetail {
  asset_id: string;
  owner_id: string;
  canonical_technology: CanonicalVRETechnology;
  zone_id: string;
  bid_tranche_id: string;
  realised_available_vre_mwh: number;
  perfect_reference_dispatch_mwh: number;
  copperplate_reference_dispatch_mwh: number;
  zonal_final_dispatch_mwh: number;
  economic_curtailment_mwh: number;
  forecast_added_curtailment_mwh: number;
  forecast_avoided_curtailment_mwh: number;
  forecast_net_impact_mwh: number;
  redispatch_added_curtailment_mwh: number;
  redispatch_avoided_curtailment_mwh: number;
  redispatch_net_impact_mwh: number;
  total_curtailment_mwh: number;
  identity_residual_mwh: number;
  attribution_method_id: "value.pro-rata-technology-bid-tranche/v1";
}

export interface VRECurtailmentPeriod {
  run_id: string;
  year: number;
  period: number;
  period_id: string;
  realised_input_sha256: string;
  realised_available_vre_mwh: number;
  perfect_reference_dispatch_mwh: number;
  copperplate_reference_dispatch_mwh: number;
  zonal_final_dispatch_mwh: number;
  economic_curtailment_mwh: number;
  forecast_added_curtailment_mwh: number;
  forecast_avoided_curtailment_mwh: number;
  forecast_net_impact_mwh: number;
  redispatch_added_curtailment_mwh: number;
  redispatch_avoided_curtailment_mwh: number;
  redispatch_net_impact_mwh: number;
  total_curtailment_mwh: number;
  curtailment_rate: number;
  identity_residual_mwh: number;
  tolerance_mwh: number;
  status: "reconciled";
  schema: "value.vre-curtailment-attribution/v2";
  attribution_method_id: "value.pro-rata-technology-bid-tranche/v1";
}

export interface VRECurtailmentAttribution {
  snapshot: VRECounterfactualSnapshot;
  details: VRECurtailmentDetail[];
  period: VRECurtailmentPeriod;
  reference_groups: VREReferenceGroup[];
  schema: "value.vre-curtailment-attribution/v2";
  attribution_method_id: "value.pro-rata-technology-bid-tranche/v1";
}

export interface ProjectV2 {
  schema_version: "value.project/v2";
  id: string;
  name: string;
  data_pack_id: string;
  start_year: number;
  end_year: number;
  modules: Record<string, string>;
  parameter_overrides: Record<string, unknown>;
  runtime_controls: Record<string, unknown>;
  migrated_from?: "value.project/v1" | null;
  extensions: ExtensionNamespace;
}

/** @deprecated Read-only shape retained for v1 saved runs and integrations. */
export interface ModelState {
  year: number;
  assets: AssetState[];
  planningPipeline: Record<string, unknown>[];
  cumulativeMetrics: Record<string, number>;
}

/** @deprecated Use AssetStateV2. */
export interface AssetState {
  id: string;
  technology: string;
  capacityMw: number;
  attributes: Record<string, unknown>;
}
