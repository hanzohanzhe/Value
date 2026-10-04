"""Live v2 adapter around the copied Scheme C bid-at-cost clearing functions."""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace
from typing import Mapping

import numpy as np
import pandas as pd

from ...asset_economics import primary_annual_asset_costs, validate_asset_economics
from ...market_ledger import (
    PhysicalDispatchRow,
    create_market_ledger,
    set_active_market_ledger,
)
from ...market_replay import canonical_technology
from ...v2.contracts import MarketYearResult, PSMInput, PeriodSummary
from .legacy_result_adapter import SchemeCLegacyResultAdapter
from .scheme_c_context import LegacyConfigSession, SchemeCRunContext


class _NativeParameterAdapter:
    def __init__(self, model_input: PSMInput) -> None:
        self.model_input = model_input

    def apply_config(self, config) -> None:
        config.simulation_parameters["periods"] = len(self.model_input.chronology.period_ids)
        config.simulation_parameters["bidding_factor"] = float(
            self.model_input.parameters.get("market.bid_multiplier", 1.0)
        )


class _StorageRuntime:
    def __init__(self, implementation: object, parameters: Mapping[str, object]) -> None:
        self.id = str(getattr(implementation, "id"))
        self.implementation = implementation
        if hasattr(implementation, "parameters"):
            implementation.parameters = dict(parameters)

    def create(self, **kwargs):
        return self.implementation.create(**kwargs)


class SchemeCNativePSM:
    """Execute the Scheme C market once for the current typed operating year."""

    id = "scheme-c-psm"
    version = "5.1.0"
    execution_kind = "live_module"

    def __init__(self) -> None:
        self._context: SchemeCRunContext | None = None
        self._storage_cost: object | None = None
        self._invocations: list[int] = []

    def configure_run(self, context: SchemeCRunContext, storage_cost: object) -> None:
        self._context = context
        self._storage_cost = storage_cost

    @staticmethod
    def _generator_technology(asset_id: str) -> str:
        lowered = asset_id.lower()
        if lowered.startswith("solar"):
            return "solar"
        if lowered.startswith("onshore"):
            return "onshore"
        if lowered.startswith("offshore"):
            return "offshore"
        return asset_id

    @staticmethod
    def _battery_target(technology: str) -> str | None:
        return {
            "pumped_hydro": "pumpedhydro_battery",
            "1c_battery": "1c_battery",
            "0.5c_battery": "0.5c_battery",
            "0.25c_battery": "0.25c_battery",
            "hydrogen_battery": "hydrogen_battery",
            "battery": "0.25c_battery",
        }.get(technology)

    @classmethod
    def _apply_state(
        cls,
        generators: dict[str, object],
        batteries: dict[str, object],
        model_input: PSMInput,
    ) -> dict[str, object]:
        """Aggregate all typed assets into the fixed FORCE market-agent topology."""

        generator_sources: dict[str, dict[str, float]] = {key: {} for key in generators}
        battery_sources: dict[str, dict[str, tuple[float, float]]] = {key: {} for key in batteries}
        deferred_generators = []
        mapped_asset_ids: set[str] = set()

        for asset in model_input.operating_state.assets:
            if asset.capacity_mw <= 0 or asset.status not in {"operating", "commissioned"}:
                continue
            if asset.asset_id in generators:
                generator_sources[asset.asset_id][asset.asset_id] = float(asset.capacity_mw)
                mapped_asset_ids.add(asset.asset_id)
                continue
            if asset.asset_id in batteries:
                energy = float(asset.energy_capacity_mwh or 0.0)
                battery_sources[asset.asset_id][asset.asset_id] = (float(asset.capacity_mw), energy)
                mapped_asset_ids.add(asset.asset_id)
                continue
            battery_target = cls._battery_target(asset.technology)
            if battery_target in batteries:
                energy = float(asset.energy_capacity_mwh or 0.0)
                battery_sources[battery_target][asset.asset_id] = (float(asset.capacity_mw), energy)
                mapped_asset_ids.add(asset.asset_id)
                continue
            technology = asset.technology
            if technology == "gas":
                candidates = [key for key in ("CCGT", "OCGT") if key in generators]
            else:
                candidates = [
                    key for key in generators
                    if cls._generator_technology(key) == technology
                ]
            if not candidates:
                raise ValueError(
                    f"Active asset {asset.asset_id} ({technology}) has no live FORCE market-agent target"
                )
            region_key = "".join(character for character in str(asset.region or "").lower() if character.isalnum())
            regional = [
                key for key in candidates
                if region_key and region_key in "".join(
                    character for character in key.lower() if character.isalnum()
                )
            ]
            deferred_generators.append((asset, regional or candidates))

        for asset, candidates in deferred_generators:
            weights = {
                key: sum(generator_sources[key].values()) for key in candidates
            }
            total_weight = sum(weights.values())
            if total_weight <= 0:
                weights = {}
                for key in candidates:
                    generator = generators[key]
                    if generator.__class__.__name__ == "ExpensiverenewableGenerator":
                        raw = float(getattr(generator, "capacity_multiplier", 0.0) or 0.0)
                        weights[key] = raw * 20.0 if key.startswith(("onshore", "offshore")) else raw
                    else:
                        weights[key] = float(getattr(generator, "capacity_limit", 0.0) or 0.0)
                total_weight = sum(weights.values())
            if total_weight <= 0:
                weights = {key: 1.0 for key in candidates}
                total_weight = float(len(candidates))
            for key in candidates:
                generator_sources[key][asset.asset_id] = (
                    float(asset.capacity_mw) * weights[key] / total_weight
                )
            mapped_asset_ids.add(asset.asset_id)

        generator_rows: dict[str, object] = {}
        for asset_id, generator in generators.items():
            capacity = sum(generator_sources[asset_id].values())
            if generator.__class__.__name__ == "ExpensiverenewableGenerator":
                generator.capacity_multiplier = (
                    capacity / 20.0
                    if asset_id.startswith(("onshore", "offshore")) else capacity
                )
            elif hasattr(generator, "capacity_limit"):
                generator.capacity_limit = capacity
            generator_rows[asset_id] = {
                "market_agent_id": str(getattr(generator, "name", asset_id)),
                "capacity_mw": capacity,
                "source_asset_capacity_mw": dict(generator_sources[asset_id]),
            }

        battery_rows: dict[str, object] = {}
        for asset_id, battery in batteries.items():
            power = sum(value[0] for value in battery_sources[asset_id].values())
            energy = sum(value[1] for value in battery_sources[asset_id].values())
            battery.resize_power_capacity(power, energy)
            battery_rows[asset_id] = {
                "market_agent_id": str(getattr(battery, "name", asset_id)),
                "capacity_mw": power,
                "energy_capacity_mwh": energy,
                "source_asset_capacity_mw": {
                    key: value[0] for key, value in battery_sources[asset_id].items()
                },
            }

        active_ids = {
            asset.asset_id for asset in model_input.operating_state.assets
            if asset.capacity_mw > 0 and asset.status in {"operating", "commissioned"}
        }
        unmapped = sorted(active_ids - mapped_asset_ids)
        if unmapped:
            raise ValueError(f"Live FORCE state coupling left assets unmapped: {unmapped[:5]}")
        return {
            "schema_version": "force.live-state-coupling/v1",
            "year": model_input.year,
            "generator_objects": generator_rows,
            "storage_objects": battery_rows,
            "active_asset_count": len(active_ids),
            "mapped_asset_count": len(mapped_asset_ids),
            "unmapped_asset_ids": unmapped,
        }

    @staticmethod
    def _allocate_runtime_income(
        raw_income: Mapping[str, object],
        coupling: Mapping[str, object],
    ) -> dict[str, float]:
        allocated: defaultdict[str, float] = defaultdict(float)
        consumed: set[str] = set()
        for group in ("generator_objects", "storage_objects"):
            for row_value in dict(coupling.get(group) or {}).values():
                row = dict(row_value or {})
                market_agent = str(row.get("market_agent_id") or "")
                if not market_agent or market_agent not in raw_income:
                    continue
                sources = {
                    str(key): float(value)
                    for key, value in dict(row.get("source_asset_capacity_mw") or {}).items()
                    if float(value) > 0
                }
                denominator = sum(sources.values())
                if denominator <= 0:
                    continue
                income = float(raw_income[market_agent])
                for asset_id, capacity in sources.items():
                    allocated[asset_id] += income * capacity / denominator
                consumed.add(market_agent)
        for key, value in raw_income.items():
            if str(key) not in consumed:
                allocated[str(key)] += float(value)
        return dict(allocated)

    @staticmethod
    def _restore_previous_observations(batteries: dict[str, object], model_input: PSMInput) -> None:
        observations = dict(
            model_input.operating_state.extensions.get("storage_cost_observations") or {}
        )
        for asset_id, battery in batteries.items():
            row = dict(observations.get(asset_id) or {})
            if not row:
                continue
            recovery = battery.cost_recovery
            previous = getattr(recovery, "previous", None)
            if previous is None:
                continue
            previous.year = row.get("prepared_year")
            previous.sold_energy_mwh = float(row.get("current_year_sold_mwh", 0.0) or 0.0)
            previous.dwell_weighted_sold_mwh_periods = (
                previous.sold_energy_mwh
                * float(row.get("current_year_average_dwell_periods", 0.0) or 0.0)
            )

    @staticmethod
    def _record_physical_dispatch(
        ledger,
        named,
        *,
        year: int,
        period_hours: float,
        forecast,
        real,
    ) -> None:
        """Materialise final physical rows without entering the clearing loop."""

        for period, raw_dispatch in enumerate(named.dispatch_by_period):
            combined: defaultdict[tuple[str, str, str, str], float] = defaultdict(float)
            for asset, power_mw in raw_dispatch:
                asset_id = str(getattr(asset, "name", asset.__class__.__name__))
                asset_type = asset.__class__.__name__
                if asset_type == "Battery":
                    flow_type = "storage_discharge"
                    scope = "final_storage_output"
                elif asset_type == "Connection":
                    flow_type = "import"
                    scope = "gb_boundary_import"
                else:
                    flow_type = "generation"
                    scope = "final_demand_serving_generation"
                technology = canonical_technology(
                    asset_id,
                    asset_type=asset_type,
                    declared_technology=str(getattr(asset, "battery_type", "") or ""),
                )
                combined[(asset_id, technology, flow_type, scope)] += (
                    float(power_mw) * period_hours
                )
            rows = [
                PhysicalDispatchRow(
                    year, period, asset_id, technology, flow_type, energy_mwh,
                    energy_mwh, scope,
                )
                for (asset_id, technology, flow_type, scope), energy_mwh in combined.items()
                if abs(energy_mwh) > 1e-12
            ]
            charge_mwh = float(named.storage_charge_by_period[period] or 0.0) * period_hours
            accounted_charge_mwh = min(
                charge_mwh,
                max((float(forecast[period]) - float(real[period])) * period_hours, 0.0),
            )
            context = (
                (
                    "__storage_charge_unallocated__", "storage_unallocated",
                    "storage_charge", charge_mwh, -accounted_charge_mwh,
                    "aggregate_input_charge; balance component includes only the retained final-dispatch boundary share",
                ),
                (
                    "__flexible_demand__", "flexible_demand", "flexible_demand",
                    float(named.flexible_demand_mwh_by_period[period] or 0.0) * period_hours,
                    0.0, "context flow outside the retained demand-serving balance",
                ),
                (
                    "__boundary_export__", "boundary_export", "export",
                    float(named.interconnector_exports_mwh_by_period[period] or 0.0) * period_hours,
                    0.0, "gb boundary export context flow",
                ),
                (
                    "__balancing_curtailment__", "vre_aggregate", "balancing_curtailment",
                    float(named.curtailed_electricity_mwh_by_period[period] or 0.0) * period_hours,
                    0.0, "reported balancing-stage curtailment",
                ),
                (
                    "__prebalancing_excess__", "inflexible_mixed", "excess_generation",
                    float(named.excess_electricity_mwh_by_period[period] or 0.0) * period_hours,
                    0.0, "pre-balancing excess may include VRE, nuclear or natural-flow hydro",
                ),
                (
                    "__blackout__", "unserved_energy", "blackout",
                    float(named.blackout_mwh_by_period[period] or 0.0) * period_hours,
                    float(named.blackout_mwh_by_period[period] or 0.0) * period_hours,
                    "unserved demand added to the physical balance",
                ),
            )
            rows.extend(
                PhysicalDispatchRow(year, period, asset_id, technology, flow_type, energy, balance, scope)
                for asset_id, technology, flow_type, energy, balance, scope in context
                if abs(energy) > 1e-12
            )
            ledger.record_physical_dispatch(rows)

    def run(self, model_input: PSMInput) -> MarketYearResult:
        if self._context is None or self._storage_cost is None:
            raise RuntimeError("SchemeCNativePSM was not configured from the frozen run context")
        if model_input.chronology is None:
            raise ValueError("Scheme C live PSM requires canonical chronological input")

        from .runtime_compat import config
        from .runtime_compat.modular_simulation_model import (
            Battery, BiomassGenerator, Connection, Electrolyzer,
            ExpensiverenewableGenerator, GasGenerator, NuclearGenerator,
            WaterGenerator, run_simulation,
        )

        parameters = dict(model_input.parameters)
        storage_runtime = _StorageRuntime(self._storage_cost, parameters)
        runtime = SimpleNamespace(storage_cost=storage_runtime)
        periods = len(model_input.chronology.period_ids)
        period_hours = float(model_input.period_hours)
        market_path = self._context.output_dir / "market" / "market.sqlite"
        trace_level = str(parameters.get("runtime.market_trace_level", "summary"))
        # The live adapter materialises the typed PeriodSummary contract from
        # this compact table after the copied session returns.  An explicit
        # request for no detailed trace therefore retains the minimum summary
        # layer, while still suppressing orders and declared auction payloads.
        ledger = create_market_ledger(
            market_path,
            "summary" if trace_level == "off" else trace_level,
            storage_cost_module_id=storage_runtime.id,
            export_format=str(parameters.get("runtime.market_export_format", "sqlite")),
            semantic_metadata={
                "psm_module_id": self.id,
                "psm_module_version": self.version,
                "period_hours": period_hours,
                "timezone": "Europe/London",
                "calendar": "fixed_365_day_local_periods",
                "requested_trace_level": trace_level,
                "dispatch_formulation": "bid_at_cost_continuous_no_commitment",
                "pricing_rule": "retained_bid_at_cost_pay_as_clear_agent_income",
                "period_price_semantics": "demand_normalised_total_period_cost; not a stage clearing-price proof",
                "excess_scope": "inflexible_mixed",
                "excess_relationship": "separate_prebalancing",
                "curtailment_semantics": "balancing_stage_down_regulation_after_storage_export_and_flexible_demand",
                "stage_order": ["ahead", "curtailment_or_balancing", "final_dispatch"],
            },
        )
        set_active_market_ledger(ledger)
        try:
            with LegacyConfigSession(
                self._context,
                _NativeParameterAdapter(model_input),
                runtime,
                environment_overrides={
                    "SIMULATION_YEAR": str(model_input.year),
                    "PHYSICAL_PERIOD_HOURS": str(period_hours),
                    "SAVE_MARKET_TRACE": "0",
                },
            ):
                fleet_generators = {}
                for name, raw in config.generators.items():
                    if name in {"CCGT", "OCGT"}:
                        value = GasGenerator(**raw)
                    elif name == "bio_and_waste":
                        value = BiomassGenerator(**raw)
                    elif name == "Hydro_natural_flow":
                        value = WaterGenerator(**raw)
                    elif name == "Nuclear":
                        value = NuclearGenerator(**raw)
                    else:
                        value = ExpensiverenewableGenerator(**raw)
                    fleet_generators[name] = value
                batteries = {name: Battery(**raw) for name, raw in config.batteries.items()}
                state_coupling = self._apply_state(fleet_generators, batteries, model_input)
                self._restore_previous_observations(batteries, model_input)
                for battery in batteries.values():
                    battery.prepare_operating_year(model_input.year)
                forecast = np.asarray(pd.read_csv(config.file_paths["forecast_demand"]), dtype=float).reshape(-1)[:periods]
                real = np.asarray(pd.read_csv(config.file_paths["real_demand"]), dtype=float).reshape(-1)[:periods]
                raw_result = run_simulation(
                    periods,
                    list(fleet_generators.values()),
                    list(batteries.values()),
                    forecast,
                    real,
                    [Connection(**raw) for raw in config.connections.values()],
                    Electrolyzer(**config.electrolyzer),
                )
                named = SchemeCLegacyResultAdapter.validate_and_convert(
                    raw_result, year=model_input.year, periods=periods,
                    period_hours=period_hours,
                )
                self._record_physical_dispatch(
                    ledger,
                    named,
                    year=model_input.year,
                    period_hours=period_hours,
                    forecast=forecast,
                    real=real,
                )
                storage_reports = {
                    asset_id: battery.storage_cost_report()
                    for asset_id, battery in batteries.items()
                }
        finally:
            metadata = ledger.close()
            set_active_market_ledger(None)

        with sqlite3.connect(market_path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT * FROM period_summary WHERE year=? ORDER BY period",
                (model_input.year,),
            ).fetchall()
        if len(rows) != periods:
            raise RuntimeError(
                f"Live Scheme C ledger contains {len(rows)} periods for {model_input.year}; expected {periods}"
            )
        summaries = tuple(PeriodSummary(
            period_id=str(model_input.chronology.period_ids[index]),
            year=model_input.year,
            period=int(row["period"]),
            market_stage=str(row["stage"]),
            forecast_demand_mwh=float(row["forecast_demand_mwh"]),
            real_demand_mwh=float(row["real_demand_mwh"]),
            accepted_supply_mwh=float(row["accepted_supply_mwh"]),
            storage_charge_mwh=float(row["storage_charge_mwh"]),
            storage_discharge_mwh=float(row["storage_discharge_mwh"]),
            vre_available_mwh=float(row["vre_available_mwh"]),
            vre_accepted_mwh=float(row["vre_accepted_mwh"]),
            curtailed_mwh=float(row["curtailed_mwh"]),
            import_mwh=float(row["import_mwh"]),
            clearing_price_gbp_per_mwh=float(row["clearing_price_gbp_per_mwh"]),
            physical_resource_cost_gbp=float(row["physical_resource_cost_gbp"]),
            market_payment_gbp=float(row["market_payment_gbp"]),
            blackout_mwh=float(row["blackout_mwh"]),
            energy_balance_residual_mwh=float(row["energy_balance_residual_mwh"]),
        ) for index, row in enumerate(rows))

        generation: defaultdict[str, float] = defaultdict(float)
        for period_dispatch in named.dispatch_by_period:
            for asset, power_mw in period_dispatch:
                if asset.__class__.__name__ == "Battery":
                    # Storage discharge is a separately conserved flow, not
                    # primary generation; including it here double-counts the
                    # electricity used to charge the store and corrupts carbon.
                    continue
                generation[str(getattr(asset, "name", asset.__class__.__name__))] += (
                    float(power_mw) * period_hours
                )
        for asset in model_input.operating_state.assets:
            validate_asset_economics(asset)
        primary_costs = tuple(
            primary_annual_asset_costs(asset)
            for asset in model_input.operating_state.assets
        )
        capital = sum(row[0] for row in primary_costs)
        fixed_om = sum(row[1] for row in primary_costs)
        cycle_wear = sum(
            float(report.get("current_cycle_depreciation_gbp", 0.0) or 0.0)
            for report in storage_reports.values()
        )
        operating = sum(row.physical_resource_cost_gbp for row in summaries) + cycle_wear
        allocated_market_income = self._allocate_runtime_income(
            named.market_income_gbp_by_agent,
            state_coupling,
        )
        self._invocations.append(model_input.year)
        return MarketYearResult(
            result_id=f"{model_input.run_id}:market:{model_input.year}",
            year=model_input.year,
            module_id=self.id,
            module_version=self.version,
            generation_mwh_by_asset=dict(generation),
            market_income_gbp_by_agent=allocated_market_income,
            total_system_cost_gbp=capital + fixed_om + operating,
            total_operational_cost_gbp=operating,
            total_levelized_capital_cost_gbp=capital + fixed_om,
            total_demand_mwh=sum(row.real_demand_mwh for row in summaries),
            total_generation_mwh=sum(generation.values()),
            total_blackout_mwh=sum(row.blackout_mwh for row in summaries),
            total_excess_mwh=sum(float(value) * period_hours for value in named.excess_electricity_mwh_by_period),
            period_summaries=summaries,
            extensions={
                "execution_kind": self.execution_kind,
                "live_scheme_c_clearing_invocation": True,
                "live_invocation_sequence": list(self._invocations),
                "storage_cost_module_id": storage_runtime.id,
                "storage_cost_observations": storage_reports,
                "state_coupling": state_coupling,
                "runtime_market_income_gbp_by_agent": {
                    str(key): float(value)
                    for key, value in named.market_income_gbp_by_agent.items()
                },
                "fleet_economics": {
                    "schema_version": "force.fleet-economics-summary/v1",
                    "active_asset_count": sum(
                        1 for asset in model_input.operating_state.assets
                        if asset.capacity_mw > 0 and asset.status in {"operating", "commissioned"}
                    ),
                    "annualized_capital_cost_gbp": capital,
                    "annual_fixed_opex_gbp": fixed_om,
                    "missing_economic_asset_count": 0,
                },
                "vre_expansion_headroom_mw_by_technology": dict(
                    model_input.chronology.extensions.get("vre_expansion_headroom_mw_by_technology") or {}
                ),
                "physical_operating_cost_components_gbp": {
                    "generation_import_and_reliability": operating - cycle_wear,
                    "storage_cycle_depreciation": cycle_wear,
                },
                "market_ledger": metadata,
            },
        )
