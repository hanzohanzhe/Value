import { DEFAULT_ZONAL_SOLVER_CONTRACT, copyDefaultZonalSolverContract, isLegacyZonalSolverContract, type ZonalSolverContract } from "../network/networkRedispatch";
import type { StudyForm } from "./types";

export const ZONAL_SOLVER_ACK_KEY = "solver-contract:value-zonal-redispatch-balancing@4.0.0";
export const LEGACY_ZONAL_SOLVER_ACK_KEY = "solver-contract:value-zonal-redispatch-balancing@2.0.0";
export const GBP1_ZONAL_SOLVER_ACK_KEY = "solver-contract:value-zonal-redispatch-balancing@3.0.0";
export const ZONAL_SOLVER_ACK = "value.solver-contract-ack/v1";
export function validateZonalSolverContract(contract: ZonalSolverContract | undefined): string {
  if (!contract) return "The selected zonal module requires a solver contract.";
  if (isLegacyZonalSolverContract(contract)) {
    const generation = contract.schema_version === "value.network-solver-contract/v2" ? "v2" : "v3 GBP 1 lock";
    return `This draft retains the historical ${generation} policy. Explicitly choose the current v4 policy (shed lock, numerical bid-cost lock, GBP 1 acceptance ceiling) and review its changed method before saving a new revision.`;
  }
  const bounded = (
    label: string,
    value: number,
    minimum: number,
    maximum: number,
  ) => Number.isFinite(value) && value >= minimum && value <= maximum
    ? ""
    : `${label} must be between ${minimum} and ${maximum}.`;
  const toleranceError = bounded("Primal feasibility tolerance", contract.primal_feasibility_tolerance, 1e-10, 1e-7)
    || bounded("Dual feasibility tolerance", contract.dual_feasibility_tolerance, 1e-10, 1e-7)
    || bounded("IPM optimality tolerance", contract.ipm_optimality_tolerance, 1e-12, 1e-7);
  if (toleranceError) return toleranceError;
  if (!Number.isFinite(contract.warning_fraction) || contract.warning_fraction <= 0 || contract.warning_fraction > 1) {
    return "Numerical warning threshold must be greater than 0 and no greater than 1.";
  }
  const ceilings = [
    ["Redispatch bid cost validated ceiling", "primary_bid_cost_gbp"],
    ["Schedule deviation validated ceiling", "secondary_schedule_deviation_mwh"],
    ["Physical throughput validated ceiling", "physical_throughput_mwh"],
  ] as const;
  for (const [label, key] of ceilings) {
    const value = contract.validated_ceilings[key];
    const absolute = DEFAULT_ZONAL_SOLVER_CONTRACT.absolute_ceilings[key];
    if (key === "primary_bid_cost_gbp" && value !== 1) return "The current primary bid-cost objective is fixed at GBP 1 total per solved half-hour period.";
    if (!Number.isFinite(value) || value <= 0 || (key !== "primary_bid_cost_gbp" && value >= absolute)) {
      return `${label} must be greater than 0 and below the immutable ${absolute} execution ceiling.`;
    }
    if (contract.absolute_ceilings[key] !== absolute) {
      return "Immutable platform execution ceilings cannot be changed.";
    }
  }
  return "";
}

export function alignZonalSolverContract(form: StudyForm, modules: Record<string, string>): StudyForm {
  const maturity_acknowledgements = { ...form.maturity_acknowledgements };
  if (modules.balancing === "value-zonal-redispatch-balancing") {
    return {
      ...form,
      modules,
      maturity_acknowledgements,
      solver_contract: form.solver_contract ?? copyDefaultZonalSolverContract(),
    };
  }
  delete maturity_acknowledgements[ZONAL_SOLVER_ACK_KEY];
  delete maturity_acknowledgements[LEGACY_ZONAL_SOLVER_ACK_KEY];
  delete maturity_acknowledgements[GBP1_ZONAL_SOLVER_ACK_KEY];
  return {
    ...form,
    modules,
    maturity_acknowledgements,
    solver_contract: undefined,
  };
}


export function upgradeZonalSolverContract(form: StudyForm): StudyForm {
  const maturity_acknowledgements = { ...form.maturity_acknowledgements };
  delete maturity_acknowledgements[ZONAL_SOLVER_ACK_KEY];
  delete maturity_acknowledgements[LEGACY_ZONAL_SOLVER_ACK_KEY];
  delete maturity_acknowledgements[GBP1_ZONAL_SOLVER_ACK_KEY];
  return { ...form, solver_contract: copyDefaultZonalSolverContract(), maturity_acknowledgements };
}
