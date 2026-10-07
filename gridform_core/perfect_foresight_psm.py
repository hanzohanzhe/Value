"""Optional transparent perfect-foresight single-node dispatch module.

This module is deliberately separate from VALUE agent bidding.  It solves a
chronological resource-cost LP and therefore has no storage offer-price policy.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

from . import agent_cashflow
from .asset_economics import (
    CAPITAL_COST_COMPONENTS_KEY,
    FOM_IN_LEVELISED_CAPEX_TECHNOLOGIES,
    capital_cost_components,
)
from .methodology import methodology_scoped
from .v2.contracts import (
    ArtifactReference,
    ChronologicalPSMData,
    MarketYearResult,
    PSMInput,
    PeriodSummary,
)
from .market_ledger import (
    PeriodLedgerRow,
    PhysicalDispatchRow,
    StorageStateRow,
    create_market_ledger,
)
from .market_replay import canonical_technology


FORMULATION_ID = "value.perfect-foresight-single-node-lp/v1"
TOLERANCE_MWH = 1e-7


class PerfectForesightInputError(ValueError):
    """The declared LP cannot be formed without changing its assumptions."""


class PerfectForesightSolveError(RuntimeError):
    """The solver did not return a publishable optimum."""


@dataclass(frozen=True)
class _Layout:
    resource: Mapping[tuple[int, int], int]
    charge: Mapping[tuple[int, int], int]
    discharge: Mapping[tuple[int, int], int]
    soc: Mapping[tuple[int, int], int]
    blackout: Mapping[int, int]
    size: int


def _layout(data: ChronologicalPSMData) -> _Layout:
    cursor = 0
    resource: dict[tuple[int, int], int] = {}
    charge: dict[tuple[int, int], int] = {}
    discharge: dict[tuple[int, int], int] = {}
    soc: dict[tuple[int, int], int] = {}
    blackout: dict[int, int] = {}
    periods = len(data.period_ids)
    for resource_index in range(len(data.resources)):
        for period in range(periods):
            resource[resource_index, period] = cursor
            cursor += 1
    for storage_index in range(len(data.storage)):
        for target in (charge, discharge, soc):
            for period in range(periods):
                target[storage_index, period] = cursor
                cursor += 1
    for period in range(periods):
        blackout[period] = cursor
        cursor += 1
    return _Layout(resource, charge, discharge, soc, blackout, cursor)


def _availability(values: Sequence[float], periods: int, asset_id: str) -> np.ndarray:
    if len(values) == 1:
        result = np.repeat(float(values[0]), periods)
    elif len(values) == periods:
        result = np.asarray(values, dtype=float)
    else:
        raise PerfectForesightInputError(
            f"Resource {asset_id} has {len(values)} availability values; expected 1 or {periods}."
        )
    if not np.all(np.isfinite(result)) or np.any(result < 0) or np.any(result > 1):
        raise PerfectForesightInputError(
            f"Resource {asset_id} availability must be finite and between 0 and 1."
        )
    return result


def _marginal_costs(resource, periods: int) -> np.ndarray:
    values = resource.marginal_cost_profile_gbp_per_mwh
    if not values:
        result = np.repeat(float(resource.marginal_cost_gbp_per_mwh), periods)
    elif len(values) == 1:
        result = np.repeat(float(values[0]), periods)
    elif len(values) == periods:
        result = np.asarray(values, dtype=float)
    else:
        raise PerfectForesightInputError(
            f"Resource {resource.asset_id} has {len(values)} marginal-cost values; "
            f"expected 0, 1 or {periods}."
        )
    if not np.all(np.isfinite(result)) or np.any(result < 0):
        raise PerfectForesightInputError(
            f"Resource {resource.asset_id} has a negative or non-finite marginal-cost profile. "
            "Negative-cost regimes require a separately declared formulation."
        )
    return result


def validate_chronology(data: ChronologicalPSMData, period_hours: float) -> None:
    periods = len(data.period_ids)
    if periods == 0 or len(data.demand_mwh) != periods:
        raise PerfectForesightInputError("Period IDs and demand must have the same non-zero length.")
    if len(set(data.period_ids)) != periods:
        raise PerfectForesightInputError("Period IDs must be unique.")
    if not math.isfinite(period_hours) or period_hours <= 0:
        raise PerfectForesightInputError("period_hours must be positive.")
    demand = np.asarray(data.demand_mwh, dtype=float)
    if not np.all(np.isfinite(demand)) or np.any(demand < 0):
        raise PerfectForesightInputError("Demand must be finite and non-negative MWh/period.")
    if not math.isfinite(data.voll_gbp_per_mwh) or data.voll_gbp_per_mwh < 0:
        raise PerfectForesightInputError("VOLL must be finite and non-negative.")
    if data.terminal_soc_rule not in {"cyclic", "fixed", "free"}:
        raise PerfectForesightInputError("terminal_soc_rule must be cyclic, fixed or free.")
    resource_ids: set[str] = set()
    for resource in data.resources:
        if resource.asset_id in resource_ids:
            raise PerfectForesightInputError(f"Duplicate resource ID: {resource.asset_id}")
        resource_ids.add(resource.asset_id)
        if resource.resource_type not in {"thermal", "vre", "import", "hydro"}:
            raise PerfectForesightInputError(
                f"Resource {resource.asset_id} has unsupported type {resource.resource_type}."
            )
        for label, value in (
            ("capacity_mw", resource.capacity_mw),
            ("marginal_cost_gbp_per_mwh", resource.marginal_cost_gbp_per_mwh),
        ):
            if not math.isfinite(value) or value < 0:
                raise PerfectForesightInputError(
                    f"Resource {resource.asset_id} {label} must be finite and non-negative. "
                    "Negative-cost regimes require a separately declared formulation."
                )
        _availability(resource.availability, periods, resource.asset_id)
        _marginal_costs(resource, periods)
    storage_ids: set[str] = set()
    for storage in data.storage:
        if storage.asset_id in resource_ids or storage.asset_id in storage_ids:
            raise PerfectForesightInputError(f"Duplicate asset ID: {storage.asset_id}")
        storage_ids.add(storage.asset_id)
        for label, value in (
            ("charge_power_mw", storage.charge_power_mw),
            ("discharge_power_mw", storage.discharge_power_mw),
            ("energy_capacity_mwh", storage.energy_capacity_mwh),
            ("initial_soc_mwh", storage.initial_soc_mwh),
            ("variable_degradation_gbp_per_mwh_discharged", storage.variable_degradation_gbp_per_mwh_discharged),
        ):
            if not math.isfinite(value) or value < 0:
                raise PerfectForesightInputError(
                    f"Storage {storage.asset_id} {label} must be finite and non-negative."
                )
        if not 0 < storage.charge_efficiency <= 1 or not 0 < storage.discharge_efficiency <= 1:
            raise PerfectForesightInputError(
                f"Storage {storage.asset_id} efficiencies must be in (0, 1]."
            )
        if storage.initial_soc_mwh > storage.energy_capacity_mwh + TOLERANCE_MWH:
            raise PerfectForesightInputError(
                f"Storage {storage.asset_id} initial SOC exceeds energy capacity."
            )
        target = data.terminal_soc_mwh_by_asset.get(storage.asset_id)
        if data.terminal_soc_rule == "fixed" and target is None:
            raise PerfectForesightInputError(
                f"Fixed terminal SOC is missing for {storage.asset_id}."
            )
        if target is not None and (target < 0 or target > storage.energy_capacity_mwh):
            raise PerfectForesightInputError(
                f"Storage {storage.asset_id} terminal SOC is outside its energy capacity."
            )


def _artifact(
    model_input: PSMInput,
    payload: Mapping[str, object],
    arrays: Mapping[str, np.ndarray],
) -> tuple[ArtifactReference, ...]:
    raw_root = model_input.extensions.get("artifact_directory")
    if not raw_root:
        return ()
    root = Path(str(raw_root)).resolve()
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / f"perfect-foresight-{model_input.year}.json"
    npz_path = root / f"perfect-foresight-{model_input.year}.npz"
    json_bytes = json.dumps(payload, sort_keys=True, indent=2).encode("utf-8")
    json_path.write_bytes(json_bytes)
    np.savez_compressed(npz_path, **arrays)
    rows = []
    for path, kind, media_type in (
        (json_path, "solver-diagnostics", "application/json"),
        (npz_path, "chronological-dispatch", "application/x-npz"),
    ):
        content = path.read_bytes()
        rows.append(ArtifactReference(
            artifact_id=f"perfect-foresight/{path.name}",
            kind=kind,
            uri=f"solver/{path.name}",
            media_type=media_type,
            checksum_sha256=hashlib.sha256(content).hexdigest(),
            size_bytes=len(content),
        ))
    return tuple(rows)


class PerfectForesightPSM:
    """SciPy/HiGHS implementation of the public v2 PSM contract."""

    id = "value-perfect-foresight-lp"
    version = "1.1.0"

    @methodology_scoped
    def run(self, model_input: PSMInput) -> MarketYearResult:
        data = model_input.chronology
        if data is None:
            raise PerfectForesightInputError(
                "value-perfect-foresight-lp requires PSMInput.chronology; no live-file fallback is allowed."
            )
        validate_chronology(data, model_input.period_hours)
        try:
            import scipy
            from scipy.optimize import linprog
            from scipy.sparse import csr_matrix, lil_matrix, vstack
        except ImportError as exc:  # pragma: no cover - environment preflight owns this
            raise PerfectForesightSolveError(
                "The optional perfect-foresight solver requires SciPy with the HiGHS backend."
            ) from exc

        periods = len(data.period_ids)
        layout = _layout(data)
        objective = np.zeros(layout.size)
        throughput_objective = np.zeros(layout.size)
        bounds: list[tuple[float, float | None]] = [(0.0, None)] * layout.size

        resource_availability: list[np.ndarray] = []
        resource_marginal_costs: list[np.ndarray] = []
        for resource_index, resource in enumerate(data.resources):
            availability = _availability(resource.availability, periods, resource.asset_id)
            marginal_costs = _marginal_costs(resource, periods)
            resource_availability.append(availability)
            resource_marginal_costs.append(marginal_costs)
            for period in range(periods):
                index = layout.resource[resource_index, period]
                bounds[index] = (
                    0.0,
                    resource.capacity_mw * model_input.period_hours * availability[period],
                )
                objective[index] = marginal_costs[period]

        for storage_index, storage in enumerate(data.storage):
            for period in range(periods):
                charge = layout.charge[storage_index, period]
                discharge = layout.discharge[storage_index, period]
                soc = layout.soc[storage_index, period]
                bounds[charge] = (0.0, storage.charge_power_mw * model_input.period_hours)
                bounds[discharge] = (0.0, storage.discharge_power_mw * model_input.period_hours)
                bounds[soc] = (0.0, storage.energy_capacity_mwh)
                objective[discharge] = storage.variable_degradation_gbp_per_mwh_discharged
                throughput_objective[charge] = 1.0
                throughput_objective[discharge] = 1.0
            if data.terminal_soc_rule != "free":
                target = (
                    storage.initial_soc_mwh
                    if data.terminal_soc_rule == "cyclic"
                    else float(data.terminal_soc_mwh_by_asset[storage.asset_id])
                )
                bounds[layout.soc[storage_index, periods - 1]] = (target, target)
        for period in range(periods):
            bounds[layout.blackout[period]] = (
                0.0,
                float(data.demand_mwh[period]) if data.allow_blackout else 0.0,
            )
            objective[layout.blackout[period]] = data.voll_gbp_per_mwh

        equality_rows = periods + len(data.storage) * periods
        matrix = lil_matrix((equality_rows, layout.size), dtype=float)
        rhs = np.zeros(equality_rows)
        for period in range(periods):
            for resource_index in range(len(data.resources)):
                matrix[period, layout.resource[resource_index, period]] = 1.0
            for storage_index in range(len(data.storage)):
                matrix[period, layout.discharge[storage_index, period]] = 1.0
                matrix[period, layout.charge[storage_index, period]] = -1.0
            matrix[period, layout.blackout[period]] = 1.0
            rhs[period] = float(data.demand_mwh[period])
        row = periods
        for storage_index, storage in enumerate(data.storage):
            for period in range(periods):
                matrix[row, layout.soc[storage_index, period]] = 1.0
                if period:
                    matrix[row, layout.soc[storage_index, period - 1]] = -1.0
                    rhs[row] = 0.0
                else:
                    rhs[row] = storage.initial_soc_mwh
                matrix[row, layout.charge[storage_index, period]] = -storage.charge_efficiency
                matrix[row, layout.discharge[storage_index, period]] = 1.0 / storage.discharge_efficiency
                row += 1
        equality = csr_matrix(matrix)

        primary = linprog(
            objective,
            A_eq=equality,
            b_eq=rhs,
            bounds=bounds,
            method="highs",
            options={"primal_feasibility_tolerance": 1e-8, "dual_feasibility_tolerance": 1e-8},
        )
        if not primary.success or primary.status != 0 or not np.all(np.isfinite(primary.x)):
            raise PerfectForesightSolveError(
                f"HiGHS did not return an optimal solution (status={primary.status}): {primary.message}"
            )
        primary_tolerance = max(1e-7, abs(float(primary.fun)) * 1e-10)
        secondary = linprog(
            throughput_objective,
            A_ub=csr_matrix(objective.reshape(1, -1)),
            b_ub=np.asarray([float(primary.fun) + primary_tolerance]),
            A_eq=equality,
            b_eq=rhs,
            bounds=bounds,
            method="highs",
            options={"primal_feasibility_tolerance": 1e-8, "dual_feasibility_tolerance": 1e-8},
        )
        if not secondary.success or secondary.status != 0:
            raise PerfectForesightSolveError(
                f"HiGHS tie-break solve failed (status={secondary.status}): {secondary.message}"
            )
        solution = np.asarray(secondary.x, dtype=float)
        primary_value = float(objective @ solution)

        dispatch_by_asset: dict[str, float] = {}
        resource_period = np.zeros((len(data.resources), periods))
        for resource_index, resource in enumerate(data.resources):
            values = np.asarray(
                [solution[layout.resource[resource_index, period]] for period in range(periods)]
            )
            resource_period[resource_index] = values
            dispatch_by_asset[resource.asset_id] = float(values.sum())
        charge_period = np.zeros((len(data.storage), periods))
        discharge_period = np.zeros((len(data.storage), periods))
        soc_period = np.zeros((len(data.storage), periods))
        for storage_index, storage in enumerate(data.storage):
            charge_period[storage_index] = [
                solution[layout.charge[storage_index, period]] for period in range(periods)
            ]
            discharge_period[storage_index] = [
                solution[layout.discharge[storage_index, period]] for period in range(periods)
            ]
            soc_period[storage_index] = [
                solution[layout.soc[storage_index, period]] for period in range(periods)
            ]
            dispatch_by_asset[storage.asset_id] = float(discharge_period[storage_index].sum())
        blackout = np.asarray([solution[layout.blackout[p]] for p in range(periods)])
        residual = np.asarray(equality @ solution - rhs)
        simultaneous = float(
            max(
                (np.minimum(charge_period[index], discharge_period[index]).max(initial=0.0)
                 for index in range(len(data.storage))),
                default=0.0,
            )
        )
        if simultaneous > 1e-6:
            raise PerfectForesightSolveError(
                f"Lexicographic throughput minimisation left {simultaneous} MWh simultaneous operation."
            )

        resource_costs = np.asarray([
            float(sum(
                resource_period[index, period] * resource_marginal_costs[index][period]
                for index in range(len(data.resources))
            ))
            for period in range(periods)
        ])
        # P0-7 (A4): running cost by resource, as the MWh-weighted unit cost.
        running_cost_by_asset = {
            resource.asset_id: (
                float(np.dot(resource_period[index], resource_marginal_costs[index]))
                / float(resource_period[index].sum())
                if float(resource_period[index].sum()) > 0
                else float(np.mean(resource_marginal_costs[index]))
            )
            for index, resource in enumerate(data.resources)
        }
        degradation_costs = np.asarray([
            float(sum(
                discharge_period[index, period]
                * data.storage[index].variable_degradation_gbp_per_mwh_discharged
                for index in range(len(data.storage))
            ))
            for period in range(periods)
        ])
        reliability_costs = blackout * data.voll_gbp_per_mwh
        prices = np.asarray(primary.eqlin.marginals[:periods], dtype=float)
        available_vre = np.asarray([
            sum(
                resource.capacity_mw * model_input.period_hours
                * resource_availability[index][period]
                for index, resource in enumerate(data.resources)
                if resource.resource_type == "vre"
            )
            for period in range(periods)
        ])
        accepted_vre = np.asarray([
            sum(
                resource_period[index, period]
                for index, resource in enumerate(data.resources)
                if resource.resource_type == "vre"
            )
            for period in range(periods)
        ])
        imports = np.asarray([
            sum(
                resource_period[index, period]
                for index, resource in enumerate(data.resources)
                if resource.resource_type == "import"
            )
            for period in range(periods)
        ])
        charge = charge_period.sum(axis=0) if len(data.storage) else np.zeros(periods)
        discharge = discharge_period.sum(axis=0) if len(data.storage) else np.zeros(periods)
        supply = resource_period.sum(axis=0) + discharge
        summaries = tuple(
            PeriodSummary(
                str(data.period_ids[period]), model_input.year, period,
                "perfect_foresight", float(data.demand_mwh[period]),
                float(data.demand_mwh[period]), float(supply[period]),
                float(charge[period]), float(discharge[period]),
                float(available_vre[period]), float(accepted_vre[period]),
                float(max(available_vre[period] - accepted_vre[period], 0.0)),
                float(imports[period]), float(prices[period]),
                float(resource_costs[period] + degradation_costs[period] + reliability_costs[period]),
                float(prices[period] * max(float(data.demand_mwh[period]) - blackout[period], 0.0)),
                float(blackout[period]), float(residual[period]),
            )
            for period in range(periods)
        )

        market_ledger_metadata: dict[str, object] | None = None
        raw_artifact_root = model_input.extensions.get("artifact_directory")
        if raw_artifact_root:
            market_path = Path(str(raw_artifact_root)).resolve().parent / "market" / "market.sqlite"
            requested_trace_level = str(
                model_input.parameters.get("runtime.market_trace_level", "summary")
            )
            ledger = create_market_ledger(
                market_path,
                requested_trace_level,
                storage_cost_module_id="not_applicable",
                semantic_metadata={
                    "psm_module_id": self.id,
                    "psm_module_version": self.version,
                    "period_hours": float(model_input.period_hours),
                    # The ledger stamps the model clock (UTC, fixed 365-day year;
                    # gridform_core.model_clock, four-role test S-M1).
                    "requested_trace_level": requested_trace_level,
                    "dispatch_formulation": FORMULATION_ID,
                    "pricing_rule": "lp_balance_dual",
                    "period_price_semantics": "objective derivative with respect to the demand-balance right-hand side",
                    "excess_scope": "vre",
                    "excess_relationship": "alias_of_unused_vre",
                    "curtailment_semantics": "unused VRE is not split into ahead and balancing stages in the perfect-foresight formulation",
                    "stage_order": ["perfect_foresight_cooptimization"],
                },
            )
            for period, summary in enumerate(summaries):
                unused_vre = max(
                    float(summary.vre_available_mwh) - float(summary.vre_accepted_mwh),
                    0.0,
                )
                ledger.record_period(PeriodLedgerRow(
                    model_input.year, period, "perfect_foresight",
                    summary.forecast_demand_mwh, summary.real_demand_mwh,
                    summary.accepted_supply_mwh, summary.storage_charge_mwh,
                    summary.storage_discharge_mwh, 0.0, 0.0,
                    summary.vre_available_mwh, summary.vre_accepted_mwh,
                    unused_vre, summary.import_mwh,
                    summary.clearing_price_gbp_per_mwh,
                    summary.physical_resource_cost_gbp,
                    summary.market_payment_gbp, 0.0,
                    summary.blackout_mwh, unused_vre,
                    summary.energy_balance_residual_mwh, 0.0,
                    summary.energy_balance_residual_mwh,
                ))
                physical_rows: list[PhysicalDispatchRow] = []
                for resource_index, resource in enumerate(data.resources):
                    energy = float(resource_period[resource_index, period])
                    if energy > 1e-12:
                        flow_type = "import" if resource.resource_type == "import" else "generation"
                        physical_rows.append(PhysicalDispatchRow(
                            model_input.year, period, resource.asset_id,
                            canonical_technology(
                                resource.asset_id,
                                declared_technology=resource.technology,
                                asset_type=resource.resource_type,
                            ),
                            flow_type, energy, energy,
                            "solver_final_physical_dispatch",
                            "perfect_foresight",
                        ))
                    if resource.resource_type == "vre":
                        available = (
                            resource.capacity_mw * model_input.period_hours
                            * resource_availability[resource_index][period]
                        )
                        unused = max(float(available) - energy, 0.0)
                        if unused > 1e-12:
                            physical_rows.append(PhysicalDispatchRow(
                                model_input.year, period, resource.asset_id,
                                canonical_technology(
                                    resource.asset_id,
                                    declared_technology=resource.technology,
                                    asset_type="vre",
                                ),
                                "unused_vre", unused, 0.0,
                                "solver_availability_minus_dispatch",
                                "perfect_foresight",
                            ))
                for storage_index, storage in enumerate(data.storage):
                    charge_energy = float(charge_period[storage_index, period])
                    discharge_energy = float(discharge_period[storage_index, period])
                    technology = canonical_technology(
                        storage.asset_id,
                        declared_technology=storage.technology,
                        asset_type="storage",
                    )
                    if charge_energy > 1e-12:
                        physical_rows.append(PhysicalDispatchRow(
                            model_input.year, period, storage.asset_id, technology,
                            "storage_charge", charge_energy, -charge_energy,
                            "solver_storage_input", "perfect_foresight",
                        ))
                    if discharge_energy > 1e-12:
                        physical_rows.append(PhysicalDispatchRow(
                            model_input.year, period, storage.asset_id, technology,
                            "storage_discharge", discharge_energy, discharge_energy,
                            "solver_storage_output", "perfect_foresight",
                        ))
                    ledger.record_storage((StorageStateRow(
                        model_input.year, period, storage.asset_id,
                        float(soc_period[storage_index, period]), charge_energy,
                        discharge_energy, storage.discharge_power_mw,
                        storage.energy_capacity_mwh,
                    ),))
                if float(blackout[period]) > 1e-12:
                    physical_rows.append(PhysicalDispatchRow(
                        model_input.year, period, "__blackout__", "unserved_energy",
                        "blackout", float(blackout[period]), float(blackout[period]),
                        "solver_unserved_demand", "perfect_foresight",
                    ))
                ledger.record_physical_dispatch(physical_rows)
            market_ledger_metadata = ledger.close()

        capital = 0.0
        fixed_om = 0.0
        for asset in model_input.operating_state.assets:
            capital += float(asset.extensions.get("annualized_capital_cost_gbp", 0.0) or 0.0)
            # P0-7 S3: the economics key is annual_fixed_opex_gbp ("fixed_om_gbp"
            # never existed, so FOM was silently 0). DECISIONS A7: VRE and
            # storage FOM is folded into levelised CAPEX, so only thermal and
            # other FOM enters the headline.
            if asset.technology not in FOM_IN_LEVELISED_CAPEX_TECHNOLOGIES:
                fixed_om += float(asset.extensions.get("annual_fixed_opex_gbp", 0.0) or 0.0)
        diagnostics = {
            "schema_version": "value.perfect-foresight-diagnostics/v1",
            "formulation_id": FORMULATION_ID,
            "solver": {"modeler": "scipy.optimize.linprog", "backend": "HiGHS", "scipy_version": scipy.__version__},
            "termination": "optimal",
            "periods": periods,
            "terminal_soc_rule": data.terminal_soc_rule,
            "primary_objective_gbp": float(primary.fun),
            "reported_objective_gbp": primary_value,
            "tie_break": "minimise charge plus discharge subject to primary optimum tolerance",
            "primary_objective_tolerance_gbp": primary_tolerance,
            "max_energy_balance_residual_mwh": float(np.max(np.abs(residual[:periods]), initial=0.0)),
            "max_constraint_residual_mwh": float(np.max(np.abs(residual), initial=0.0)),
            "max_simultaneous_charge_discharge_mwh": simultaneous,
            "balance_duals_available": True,
            "balance_dual_sign": "d(objective)/d(demand_rhs)",
        }
        artifacts = _artifact(
            model_input,
            diagnostics,
            {
                "resource_dispatch_mwh": resource_period,
                "storage_charge_mwh": charge_period,
                "storage_discharge_mwh": discharge_period,
                "storage_soc_mwh": soc_period,
                "blackout_mwh": blackout,
                "balance_price_gbp_per_mwh": prices,
            },
        )
        operating = float(resource_costs.sum() + degradation_costs.sum() + reliability_costs.sum())
        market_income = {
            resource.asset_id: float(np.dot(resource_period[index], prices))
            for index, resource in enumerate(data.resources)
        }
        market_income.update({
            storage.asset_id: float(np.dot(discharge_period[index] - charge_period[index], prices))
            for index, storage in enumerate(data.storage)
        })
        return MarketYearResult(
            result_id=f"{model_input.run_id}:market:{model_input.year}",
            year=model_input.year,
            module_id=self.id,
            module_version=self.version,
            generation_mwh_by_asset=dispatch_by_asset,
            market_income_gbp_by_agent=market_income,
            total_system_cost_gbp=capital + fixed_om + operating,
            total_operational_cost_gbp=operating,
            total_levelized_capital_cost_gbp=capital + fixed_om,
            total_demand_mwh=float(np.sum(data.demand_mwh)),
            total_generation_mwh=float(resource_period.sum() + discharge_period.sum()),
            total_blackout_mwh=float(blackout.sum()),
            total_excess_mwh=float(np.maximum(available_vre - accepted_vre, 0.0).sum()),
            period_summaries=summaries,
            artifacts=artifacts,
            extensions={
                "market_formulation": "perfect_foresight_cooptimization",
                "storage_offer_rule": "not_applicable",
                "formulation_id": FORMULATION_ID,
                "solver_diagnostics": diagnostics,
                "physical_operating_cost_components_gbp": {
                    "generation_and_import_variable": float(resource_costs.sum()),
                    "storage_variable_degradation": float(degradation_costs.sum()),
                    "blackout_prevention_failure": float(reliability_costs.sum()),
                },
                "market_settlement_gbp": float(sum(market_income.values())),
                "chronology_hash": hashlib.sha256(
                    json.dumps(data.to_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")
                ).hexdigest(),
                "vre_expansion_headroom_mw_by_technology": dict(
                    data.extensions.get("vre_expansion_headroom_mw_by_technology") or {}
                ),
                "market_ledger": market_ledger_metadata,
                CAPITAL_COST_COMPONENTS_KEY: {
                    **capital_cost_components(model_input.operating_state.assets, included_fixed_opex_gbp=fixed_om),
                    "included_annualised_capital_gbp": capital,
                },
                agent_cashflow.EXTENSION_KEY: agent_cashflow.extension(
                    agent_cashflow.unit_cost_cashflow(
                        dispatch_by_asset, running_cost_by_asset,
                        {asset.asset_id: asset.technology for asset in model_input.operating_state.assets},
                        cost_basis="perfect_foresight_mwh_weighted_marginal_cost",
                    ),
                    psm_module_id=self.id,
                    cost_basis="perfect_foresight_mwh_weighted_marginal_cost",
                ),
            },
        )
