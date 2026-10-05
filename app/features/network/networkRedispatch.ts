export type ZonalRun = {
  id: string;
  status: string;
  archived_from_status?: string;
  error?: string;
  error_code?: string;
  modules?: Record<string, string>;
  comparison_parent_run_id?: string;
};

export type ZonalSolverContract = {
  schema_version: "value.network-solver-contract/v2" | "value.network-solver-contract/v3" | "value.network-solver-contract/v4";
  contract_version: "value.zonal-lexicographic/v2" | "value.zonal-lexicographic-gbp1/v3" | "value.zonal-lexicographic-shed-lock/v4";
  method: "highs-ds" | "highs-ipm" | "highs";
  presolve: true;
  primal_feasibility_tolerance: number;
  dual_feasibility_tolerance: number;
  ipm_optimality_tolerance: number;
  warning_fraction: number;
  validated_ceilings: Record<string, number>;
  absolute_ceilings: Record<string, number>;
  is_builtin_default: boolean;
  requires_acknowledgement: boolean;
};

// Solver contract v4 (P0-8): shed lock first, then a numerical bid-cost lock;
// GBP 1 per period is only its acceptance ceiling.
export const DEFAULT_ZONAL_SOLVER_CONTRACT: ZonalSolverContract = {
  schema_version: "value.network-solver-contract/v4",
  contract_version: "value.zonal-lexicographic-shed-lock/v4",
  method: "highs-ds",
  presolve: true,
  primal_feasibility_tolerance: 1e-9,
  dual_feasibility_tolerance: 1e-9,
  ipm_optimality_tolerance: 1e-9,
  warning_fraction: 0.1,
  validated_ceilings: {
    primary_bid_cost_gbp: 1,
    secondary_schedule_deviation_mwh: 0.001,
    physical_throughput_mwh: 0.001,
  },
  absolute_ceilings: {
    primary_bid_cost_gbp: 1,
    secondary_schedule_deviation_mwh: 0.01,
    physical_throughput_mwh: 0.01,
  },
  is_builtin_default: true,
  requires_acknowledgement: false,
};

export const LEGACY_ZONAL_SOLVER_CONTRACT: ZonalSolverContract = {
  ...DEFAULT_ZONAL_SOLVER_CONTRACT,
  schema_version: "value.network-solver-contract/v2",
  contract_version: "value.zonal-lexicographic/v2",
  validated_ceilings: { ...DEFAULT_ZONAL_SOLVER_CONTRACT.validated_ceilings, primary_bid_cost_gbp: 0.01 },
  absolute_ceilings: { ...DEFAULT_ZONAL_SOLVER_CONTRACT.absolute_ceilings, primary_bid_cost_gbp: 0.1 },
};

// v3 used GBP 1 as the primary lock allowance (P2-01); its built-in values are
// the same as v4's, only the identity differs.  Readable, never executable.
export const HISTORICAL_GBP1_ZONAL_SOLVER_CONTRACT: ZonalSolverContract = {
  ...DEFAULT_ZONAL_SOLVER_CONTRACT,
  schema_version: "value.network-solver-contract/v3",
  contract_version: "value.zonal-lexicographic-gbp1/v3",
};

export type ZonalSolverContractGeneration = "v2" | "v3" | "v4";

export function zonalSolverContractGeneration(contract: ZonalSolverContract): ZonalSolverContractGeneration {
  if (contract.schema_version === "value.network-solver-contract/v2") return "v2";
  if (contract.schema_version === "value.network-solver-contract/v3") return "v3";
  return "v4";
}

/** A historical (v2 or v3) contract: readable, but a run needs an explicit upgrade. */
export function isLegacyZonalSolverContract(contract: ZonalSolverContract): boolean {
  return zonalSolverContractGeneration(contract) !== "v4";
}

function generationDefaults(contract: ZonalSolverContract): ZonalSolverContract {
  const generation = zonalSolverContractGeneration(contract);
  if (generation === "v2") return LEGACY_ZONAL_SOLVER_CONTRACT;
  if (generation === "v3") return HISTORICAL_GBP1_ZONAL_SOLVER_CONTRACT;
  return DEFAULT_ZONAL_SOLVER_CONTRACT;
}

export function copyDefaultZonalSolverContract(): ZonalSolverContract {
  return {
    ...DEFAULT_ZONAL_SOLVER_CONTRACT,
    validated_ceilings: { ...DEFAULT_ZONAL_SOLVER_CONTRACT.validated_ceilings },
    absolute_ceilings: { ...DEFAULT_ZONAL_SOLVER_CONTRACT.absolute_ceilings },
  };
}

const solverCeilingKeys = [
  "primary_bid_cost_gbp",
  "secondary_schedule_deviation_mwh",
  "physical_throughput_mwh",
] as const;
const solverContractKeys = [
  "schema_version",
  "contract_version",
  "method",
  "presolve",
  "primal_feasibility_tolerance",
  "dual_feasibility_tolerance",
  "ipm_optimality_tolerance",
  "warning_fraction",
  "validated_ceilings",
  "absolute_ceilings",
  "is_builtin_default",
  "requires_acknowledgement",
] as const;
const solverMethods = ["highs-ds", "highs-ipm", "highs"] as const;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasExactKeys(value: Record<string, unknown>, keys: readonly string[]): boolean {
  return Object.keys(value).length === keys.length
    && keys.every((key) => Object.hasOwn(value, key));
}

function hasBuiltinZonalSolverValues(contract: ZonalSolverContract): boolean {
  const defaults = generationDefaults(contract);
  return contract.schema_version === defaults.schema_version
    && contract.contract_version === defaults.contract_version
    && contract.method === defaults.method
    && contract.presolve === defaults.presolve
    && contract.primal_feasibility_tolerance === defaults.primal_feasibility_tolerance
    && contract.dual_feasibility_tolerance === defaults.dual_feasibility_tolerance
    && contract.ipm_optimality_tolerance === defaults.ipm_optimality_tolerance
    && contract.warning_fraction === defaults.warning_fraction
    && Object.keys(defaults.validated_ceilings).every(
      (key) => contract.validated_ceilings[key] === defaults.validated_ceilings[key],
    )
    && Object.keys(defaults.absolute_ceilings).every(
      (key) => contract.absolute_ceilings[key] === defaults.absolute_ceilings[key],
    );
}

export function withZonalSolverContractFlags(contract: ZonalSolverContract): ZonalSolverContract {
  const builtin = hasBuiltinZonalSolverValues(contract);
  return { ...contract, is_builtin_default: builtin, requires_acknowledgement: !builtin };
}

export function isZonalSolverContract(value: unknown): value is ZonalSolverContract {
  if (!isRecord(value)
    || !hasExactKeys(value, solverContractKeys)
    || !((value.schema_version === "value.network-solver-contract/v2" && value.contract_version === "value.zonal-lexicographic/v2")
      || (value.schema_version === "value.network-solver-contract/v3" && value.contract_version === "value.zonal-lexicographic-gbp1/v3")
      || (value.schema_version === "value.network-solver-contract/v4" && value.contract_version === "value.zonal-lexicographic-shed-lock/v4"))
    || !solverMethods.includes(value.method as (typeof solverMethods)[number])
    || value.presolve !== true
    || typeof value.is_builtin_default !== "boolean"
    || typeof value.requires_acknowledgement !== "boolean"
    || !isRecord(value.validated_ceilings)
    || !isRecord(value.absolute_ceilings)
    || !hasExactKeys(value.validated_ceilings, solverCeilingKeys)
    || !hasExactKeys(value.absolute_ceilings, solverCeilingKeys)) return false;
  const finite = (candidate: unknown): candidate is number => typeof candidate === "number" && Number.isFinite(candidate);
  if (!finite(value.primal_feasibility_tolerance)
    || !finite(value.dual_feasibility_tolerance)
    || !finite(value.ipm_optimality_tolerance)
    || !finite(value.warning_fraction)
    || value.primal_feasibility_tolerance < 1e-10
    || value.primal_feasibility_tolerance > 1e-7
    || value.dual_feasibility_tolerance < 1e-10
    || value.dual_feasibility_tolerance > 1e-7
    || value.ipm_optimality_tolerance < 1e-12
    || value.ipm_optimality_tolerance > 1e-7
    || value.warning_fraction <= 0
    || value.warning_fraction > 1) return false;
  const legacy = value.schema_version === "value.network-solver-contract/v2";
  const defaults = legacy ? LEGACY_ZONAL_SOLVER_CONTRACT : DEFAULT_ZONAL_SOLVER_CONTRACT;
  for (const key of solverCeilingKeys) {
    const validated = value.validated_ceilings[key];
    const absolute = value.absolute_ceilings[key];
    if (!finite(validated) || !finite(absolute)
      || absolute !== defaults.absolute_ceilings[key]
      || validated <= 0 || validated > absolute) return false;
    if (!legacy && key === "primary_bid_cost_gbp" && validated !== 1) return false;
    if ((legacy || key !== "primary_bid_cost_gbp") && validated >= absolute) return false;
  }
  const contract = value as ZonalSolverContract;
  const builtin = hasBuiltinZonalSolverValues(contract);
  return contract.is_builtin_default === builtin
    && contract.requires_acknowledgement === !builtin;
}

export function isBuiltinZonalSolverContract(contract: unknown): contract is ZonalSolverContract {
  return isZonalSolverContract(contract) && hasBuiltinZonalSolverValues(contract);
}

export type SolverValidationSummary = {
  schema_version: string;
  annual_status: string;
  study_status: string;
  solver_validated: boolean;
  solver_stack_validation_status: "builtin_validated_baseline" | "solver_stack_not_yet_validated" | string;
  inherited_unvalidated: boolean;
  first_causal_period: Record<string, unknown> | null;
  row_count: number;
  warning_periods: number;
  unvalidated_periods: number;
  maximum_validated_ceiling_use: number;
  method?: string;
  solver_contract_version?: string;
  scipy_version?: string;
  highs_identity?: string;
  phases: Record<string, unknown>;
  detail_view: "solver-diagnostics" | string;
  evidence_status: "valid" | "invalid" | "not_recorded" | string;
  evidence_errors: string[];
};

const annualSolverStatuses = [
  "GO",
  "GO_WITH_NUMERICAL_WARNING",
  "COMPLETED_WITH_NUMERICAL_WARNING",
  "NOT_RECORDED",
] as const;
const studySolverStatuses = [
  ...annualSolverStatuses,
  "solver_stack_not_yet_validated",
  "solver_evidence_invalid",
] as const;
const stackValidationStatuses = [
  "builtin_validated_baseline",
  "solver_stack_not_yet_validated",
] as const;
const evidenceStatuses = ["valid", "invalid", "not_recorded"] as const;

function isNonnegativeInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value >= 0;
}

function isOptionalNonemptyString(value: unknown): boolean {
  return value === undefined || (typeof value === "string" && value.length > 0);
}

export function isSolverValidationSummary(value: unknown): value is SolverValidationSummary {
  if (!isRecord(value)
    || value.schema_version !== "value.solver-validation-summary/v1"
    || !annualSolverStatuses.includes(value.annual_status as (typeof annualSolverStatuses)[number])
    || !studySolverStatuses.includes(value.study_status as (typeof studySolverStatuses)[number])
    || typeof value.solver_validated !== "boolean"
    || !stackValidationStatuses.includes(value.solver_stack_validation_status as (typeof stackValidationStatuses)[number])
    || typeof value.inherited_unvalidated !== "boolean"
    || !(value.first_causal_period === null || isRecord(value.first_causal_period))
    || !isNonnegativeInteger(value.row_count)
    || !isNonnegativeInteger(value.warning_periods)
    || !isNonnegativeInteger(value.unvalidated_periods)
    || typeof value.maximum_validated_ceiling_use !== "number"
    || !Number.isFinite(value.maximum_validated_ceiling_use)
    || value.maximum_validated_ceiling_use < 0
    || !isRecord(value.phases)
    || !evidenceStatuses.includes(value.evidence_status as (typeof evidenceStatuses)[number])
    || !Array.isArray(value.evidence_errors)
    || !value.evidence_errors.every((error) => typeof error === "string")
    || !isOptionalNonemptyString(value.method)
    || !isOptionalNonemptyString(value.solver_contract_version)
    || !isOptionalNonemptyString(value.scipy_version)
    || !isOptionalNonemptyString(value.highs_identity)
    || !(value.detail_view === undefined || value.detail_view === "solver-diagnostics")) return false;
  if (value.row_count > 0) {
    return solverMethods.includes(value.method as (typeof solverMethods)[number])
      && ["value.zonal-lexicographic/v2", "value.zonal-lexicographic-gbp1/v3", "value.zonal-lexicographic-shed-lock/v4"].includes(value.solver_contract_version as string)
      && typeof value.scipy_version === "string"
      && value.scipy_version.length > 0
      && typeof value.highs_identity === "string"
      && value.highs_identity.length > 0
      && value.detail_view === "solver-diagnostics";
  }
  return true;
}

export type ZonalCapabilities = {
  trace_level: "off" | "summary" | "full";
  years: number[];
  network_pack_id: string;
  data_pack_id: string;
  available_views: string[];
  row_counts: Record<string, number>;
  bid_replay_available: boolean;
  network_semantics: string;
  boundary_value_semantics: string;
  reliability_semantics: string;
  security_scope: string;
  unsupported_scope: string[];
  solver_validation_summary?: SolverValidationSummary | null;
  demand_alignment: {
    mode: "scenario_scaled_zonal_shares" | "network_pack_absolute_demand" | "mixed_invalid";
    period_count: number;
    research_real_demand_mwh: number;
    research_forecast_demand_mwh: number;
    network_national_demand_mwh: number;
    aligned_zonal_total_mwh: number;
    scale_factor_min: number;
    scale_factor_max: number;
    scale_factor_mean: number;
    maximum_absolute_conservation_residual_mwh: number;
    detail_location: string;
  } | null;
};

export type VRECurtailmentValues = {
  available_mwh: number | null;
  economic_mwh: number | null;
  forecast_added_mwh: number | null;
  forecast_avoided_mwh: number | null;
  redispatch_added_mwh: number | null;
  redispatch_avoided_mwh: number | null;
  redispatch_net_mwh: number | null;
  total_mwh: number | null;
};

export type VRECurtailmentTechnology = VRECurtailmentValues & {
  year: number;
  technology: string;
};

export type VRECurtailmentZoneTechnology = VRECurtailmentTechnology & {
  zone_id: string;
};

export type VRECurtailmentAnnual = VRECurtailmentValues & {
  attribution_status: "reconciled" | "legacy_partial" | "unavailable" | "not_recorded" | "incomplete" | "invalid";
  reason_code: string | null;
  period_count?: number;
  rate: number | null;
  maximum_absolute_residual_mwh?: number | null;
  aggregate_tolerance_mwh?: number | null;
  attribution_method_id?: string | null;
  by_technology: VRECurtailmentTechnology[];
  by_zone_technology: VRECurtailmentZoneTechnology[];
};

export type VRECurtailmentDetailRow = {
  year: number;
  period: number;
  period_id: string;
  asset_id: string;
  owner_id: string;
  zone_id: string;
  technology: string;
  bid_tranche_id: string;
  realised_available_vre_mwh: number;
  perfect_reference_dispatch_mwh: number;
  copperplate_reference_dispatch_mwh: number;
  zonal_final_dispatch_mwh: number;
  economic_curtailment_mwh: number;
  forecast_added_curtailment_mwh: number;
  forecast_avoided_curtailment_mwh: number;
  redispatch_added_curtailment_mwh: number;
  redispatch_avoided_curtailment_mwh: number;
  redispatch_net_impact_mwh: number;
  total_curtailment_mwh: number;
  evidence_level: string;
};

export type AnnualNetworkRow = {
  year: number;
  period_count: number;
  system_resource_cost_gbp: number;
  network_constraint_cost_gbp: number;
  national_settlement_gbp: number;
  redispatch_settlement_gbp: number;
  policy_transfer_gbp: number;
  forecast_error_cost_gbp: number;
  total_deviation_cost_gbp: number;
  vre_curtailment: VRECurtailmentAnnual;
  unserved_energy_mwh: number;
  congested_boundary_periods: number;
  maximum_boundary_utilisation_fraction: number;
  observed_loss_of_load_hours: number;
  observed_loss_of_load_events: number;
  affected_load_shedding_zones: number;
  solver_validation_summary?: SolverValidationSummary;
};

export type AnnualBrief = {
  schema_version?: string;
  ledger_schema_version?: string;
  years: AnnualNetworkRow[];
  reliability_semantics: string;
  security_scope: string;
  solver_validation_summary?: SolverValidationSummary | null;
};

export type ResultPage<T = Record<string, unknown>> = {
  view: string;
  total: number;
  count?: number;
  limit: number;
  offset: number;
  has_more: boolean;
  items: T[];
};

export type BoundedPeriodSelection = {
  year: number;
  periodFrom: number;
  periodTo: number;
  limit: number;
  offset: number;
};

export function boundedPeriodQuery(selection: BoundedPeriodSelection): URLSearchParams {
  return new URLSearchParams({
    year: String(selection.year),
    period_from: String(selection.periodFrom),
    period_to: String(selection.periodTo),
    limit: String(selection.limit),
    offset: String(selection.offset),
  });
}

export async function fetchNetworkJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { cache: "no-store" });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "Network results request failed");
  return payload as T;
}

export function numberValue(row: Record<string, unknown>, key: string): number {
  const value = Number(row[key] ?? 0);
  return Number.isFinite(value) ? value : 0;
}

export function formatNetworkNumber(value: number, digits = 2): string {
  return new Intl.NumberFormat("en-GB", { maximumFractionDigits: digits }).format(value);
}

export function formatOptionalNetworkNumber(
  value: number | null | undefined,
  digits = 2,
): string | null {
  return typeof value === "number" && Number.isFinite(value)
    ? formatNetworkNumber(value, digits)
    : null;
}

export function formatNetworkMoney(value: number): string {
  const absolute = Math.abs(value);
  if (absolute >= 1e9) return `£${formatNetworkNumber(value / 1e9, 3)}bn`;
  if (absolute >= 1e6) return `£${formatNetworkNumber(value / 1e6, 3)}m`;
  if (absolute >= 1e3) return `£${formatNetworkNumber(value / 1e3, 2)}k`;
  return `£${formatNetworkNumber(value, 2)}`;
}
