import { DEFAULT_ZONAL_SOLVER_CONTRACT, copyDefaultZonalSolverContract, isLegacyZonalSolverContract, type ZonalSolverContract } from "../network/networkRedispatch";
import type { StudyForm } from "./types";
import { tr } from "../../i18n/index.ts";

export const ZONAL_SOLVER_ACK_KEY = "solver-contract:value-zonal-redispatch-balancing@4.0.0";
export const LEGACY_ZONAL_SOLVER_ACK_KEY = "solver-contract:value-zonal-redispatch-balancing@2.0.0";
export const GBP1_ZONAL_SOLVER_ACK_KEY = "solver-contract:value-zonal-redispatch-balancing@3.0.0";
export const ZONAL_SOLVER_ACK = "value.solver-contract-ack/v1";
export function validateZonalSolverContract(contract: ZonalSolverContract | undefined): string {
  if (!contract) return tr("solverContract.required");
  if (isLegacyZonalSolverContract(contract)) {
    const generation = tr(contract.schema_version === "value.network-solver-contract/v2" ? "solverContract.v2" : "solverContract.v3");
    return tr("solverContract.historical", { generation });
  }
  const bounded = (
    label: string,
    value: number,
    minimum: number,
    maximum: number,
  ) => Number.isFinite(value) && value >= minimum && value <= maximum
    ? ""
    : tr("solverContract.between", { label, minimum, maximum });
  const toleranceError = bounded(tr("solverContract.primal"), contract.primal_feasibility_tolerance, 1e-10, 1e-7)
    || bounded(tr("solverContract.dual"), contract.dual_feasibility_tolerance, 1e-10, 1e-7)
    || bounded(tr("solverContract.ipm"), contract.ipm_optimality_tolerance, 1e-12, 1e-7);
  if (toleranceError) return toleranceError;
  if (!Number.isFinite(contract.warning_fraction) || contract.warning_fraction <= 0 || contract.warning_fraction > 1) {
    return tr("solverContract.warning");
  }
  const ceilings = [
    [tr("solverContract.bidCeiling"), "primary_bid_cost_gbp"],
    [tr("solverContract.scheduleCeiling"), "secondary_schedule_deviation_mwh"],
    [tr("solverContract.throughputCeiling"), "physical_throughput_mwh"],
  ] as const;
  for (const [label, key] of ceilings) {
    const value = contract.validated_ceilings[key];
    const absolute = DEFAULT_ZONAL_SOLVER_CONTRACT.absolute_ceilings[key];
    if (key === "primary_bid_cost_gbp" && value !== 1) return tr("solverContract.bidFixed");
    if (!Number.isFinite(value) || value <= 0 || (key !== "primary_bid_cost_gbp" && value >= absolute)) {
      return tr("solverContract.belowAbsolute", { label, absolute });
    }
    if (contract.absolute_ceilings[key] !== absolute) {
      return tr("solverContract.immutable");
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
  return {
    ...form,
    modules,
    maturity_acknowledgements: withoutZonalSolverAcknowledgements(maturity_acknowledgements),
    solver_contract: undefined,
  };
}


/** Every zonal solver-contract acknowledgement key, current and historical. */
export const ZONAL_SOLVER_ACK_KEYS = [ZONAL_SOLVER_ACK_KEY, GBP1_ZONAL_SOLVER_ACK_KEY, LEGACY_ZONAL_SOLVER_ACK_KEY] as const;

/** A copy of the acknowledgements without any zonal solver-contract key (v2, v3 or v4). */
export function withoutZonalSolverAcknowledgements(acknowledgements: Record<string, string>): Record<string, string> {
  const remaining = { ...acknowledgements };
  for (const key of ZONAL_SOLVER_ACK_KEYS) delete remaining[key];
  return remaining;
}

export function upgradeZonalSolverContract(form: StudyForm): StudyForm {
  return {
    ...form,
    solver_contract: copyDefaultZonalSolverContract(),
    maturity_acknowledgements: withoutZonalSolverAcknowledgements(form.maturity_acknowledgements),
  };
}
