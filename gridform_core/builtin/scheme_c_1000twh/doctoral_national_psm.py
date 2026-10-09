"""Live typed national doctoral PSM with independent monthly JSON recovery.

This explicit experimental entry is not the staged/zonal model, a legacy main
import, or a claim of final9.6 CEM equivalence. It exposes source-rule cashflow
and complete physical memory to the annual lifecycle; unresolved scientific
cost/settlement/expansion decisions remain separately gated.
"""
from __future__ import annotations

import json
import math
import hashlib
import importlib
from pathlib import Path
from types import FunctionType
from typing import Mapping

from ...methodology import methodology_scoped
from ...doctoral_checkpoint import DoctoralCheckpointStore, month_end_periods
from ...doctoral_contract import thesis96_contract_identity
from ...v2.contracts import MarketYearResult, PeriodSummary
from .doctoral_market import DoctoralPeriodEngine, _hash, _code_identity, COST_PROFILE, SETTLEMENT_RULE
from .doctoral_market_factory import from_doctoral_psm_input
from .doctoral_period_ledger import DoctoralPeriodLedger
from .doctoral_settlement import publish_settlement_report, verify_settlement_files

PROFILE = "value.doctoral-national/v1"


def _runtime_identity() -> dict:
    """Bind persisted interpretation as well as the separate physical kernel.

    Both disk bytes and loaded callables are retained: changing a .py file does
    not hot-reload an existing process. No identity is copied from a checkpoint.
    """
    result = {"profile": PROFILE, "module": DoctoralNationalPSM.id,
              "version": DoctoralNationalPSM.version}
    for name in (__name__, from_doctoral_psm_input.__module__, DoctoralPeriodLedger.__module__,
                 DoctoralCheckpointStore.__module__, thesis96_contract_identity.__module__,
                 PeriodSummary.__module__, publish_settlement_report.__module__):
        module = importlib.import_module(name)
        code = {}
        for key, value in vars(module).items():
            if isinstance(value, FunctionType) and value.__module__ == name:
                code[key] = _hash(_code_identity(value.__code__))
            elif isinstance(value, type) and value.__module__ == name:
                for method, fn in vars(value).items():
                    if isinstance(fn, (staticmethod, classmethod)):
                        fn = fn.__func__
                    if isinstance(fn, FunctionType):
                        code[key + "." + method] = _hash(_code_identity(fn.__code__))
        result[name] = {"file_sha256": hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest(),
                        "loaded_rules_sha256": _hash(code)}
    return result


def _annual_costs(state) -> tuple[float, float]:
    totals = {"annual_fixed_opex_gbp": 0.0, "annualized_capital_cost_gbp": 0.0}
    for asset in state.assets:
        if (asset.status == "retired" or asset.capacity_mw <= 0
                or asset.extensions.get("primary_cost_ledger_included") is False):
            continue
        for field in totals:
            value = asset.extensions.get(field)
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value) or value < 0):
                raise ValueError(f"Complete national year requires explicit nonnegative {asset.asset_id}.{field}")
            totals[field] += float(value)
    return totals["annual_fixed_opex_gbp"], totals["annualized_capital_cost_gbp"]


def _validate_summaries(summaries, model_input, totals) -> None:
    """Reconcile the cumulative public output with the authenticated ledger.

    The checkpoint bundle hash binds every price/row. These checks additionally
    reject producer mistakes in time, units, inputs and aggregate quantities;
    they do not recreate the entire original period outcomes from summaries.
    """
    expected = {
        "forecast_demand_mwh": totals["forecast_demand_mwh"],
        "real_demand_mwh": totals["actual_demand_mwh"],
        "accepted_supply_mwh": sum(totals["generation_mwh_by_asset"].values()),
        "storage_charge_mwh": totals["storage_charge_mwh"],
        "storage_discharge_mwh": totals["storage_discharge_mwh"],
        "vre_available_mwh": totals["vre_available_mwh"],
        "vre_accepted_mwh": totals["vre_available_mwh"] - totals["vre_curtailed_mwh"],
        "curtailed_mwh": totals["vre_curtailed_mwh"],
        "import_mwh": totals["import_mwh"],
        "physical_resource_cost_gbp": sum(totals["operating_cost_gbp_by_asset"].values()),
        "market_payment_gbp": sum(totals["ahead_income_gbp_by_asset"].values())
                              + sum(totals["balancing_income_gbp_by_asset"].values()),
        "blackout_mwh": totals["blackout_mwh"],
        "energy_balance_residual_mwh": totals["energy_balance_residual_mwh"],
    }
    for index, row in enumerate(summaries):
        if (type(row.period) is not int or row.period != index or row.year != model_input.year
                or row.period_id != model_input.chronology.period_ids[index]
                or row.schema_version != "value.period-summary/v2"
                or row.market_stage != "doctoral_final_physical_with_ahead_generator_price"
                or row.units != {"energy": "MWh/period", "price": "GBP/MWh", "cost": "GBP"}):
            raise ValueError("Cumulative summary period identity/units mismatch")
        for field in (*expected, "clearing_price_gbp_per_mwh"):
            value = getattr(row, field)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"Invalid cumulative summary {field}")
        if (row.forecast_demand_mwh != float(model_input.chronology.extensions["forecast_demand_mwh"][index])
                or row.real_demand_mwh != float(model_input.chronology.demand_mwh[index])):
            raise ValueError("Cumulative summary demand differs from frozen input")
    for field, value in expected.items():
        actual = math.fsum(getattr(row, field) for row in summaries)
        if not math.isclose(actual, value, rel_tol=1e-10, abs_tol=1e-7):
            raise ValueError(f"Cumulative summary {field} differs from authenticated ledger")


class DoctoralNationalPSM:
    id, version = "value-doctoral-national-psm", "0.3.0"
    execution_kind = "live_module"

    def configure_run(self, *, output_dir: Path, fleet_parameters: Mapping,
                      battery_parameters: Mapping, frozen_data_identity: Mapping) -> None:
        # Defensive JSON copies make subsequent caller mutation harmless.
        self._fleet = json.loads(json.dumps(fleet_parameters, allow_nan=False))
        self._batteries = json.loads(json.dumps(battery_parameters, allow_nan=False))
        self._data_identity = dict(frozen_data_identity)
        required = {"data_pack_sha256", "weather_sha256", "nuclear_policy_sha256"}
        if not required <= set(self._data_identity):
            raise ValueError("National PSM requires frozen data/weather/nuclear identities")
        self._output_dir = Path(output_dir)

    @methodology_scoped
    def run(self, model_input, *, stop_after_period: int | None = None) -> MarketYearResult:
        if not hasattr(self, "_fleet"):
            raise ValueError("Doctoral national PSM must be configured with frozen constructor inputs")
        if model_input.extensions.get("doctoral_alignment_profile") != PROFILE:
            raise ValueError("Explicit doctoral national input profile required")
        cost_profile = model_input.extensions.get('doctoral_cost_profile', COST_PROFILE)
        if cost_profile != COST_PROFILE:
            raise ValueError('Unsupported or uncalibrated doctoral cost profile')
        chronology = model_input.chronology
        if chronology is None:
            raise ValueError("Doctoral national PSM requires a typed chronology")
        count = len(chronology.period_ids)
        if not 0 < count <= 17520 or len(set(chronology.period_ids)) != count:
            raise ValueError("Doctoral chronology requires 1..17520 unique periods")
        forecast = chronology.extensions.get("forecast_demand_mwh")
        if forecast is None or len(forecast) != count or any(
                isinstance(v, bool) or not math.isfinite(float(v)) or float(v) < 0 for v in forecast):
            raise ValueError("Explicit complete forecast demand MWh is required")
        end = count if stop_after_period is None else stop_after_period
        if type(end) is not int or not 0 < end <= count:
            raise ValueError("Invalid requested diagnostic stopping period")
        # Fail before a costly full-year run or any accepted checkpoint if an
        # annual result could not be accounted for. Partial diagnostics do not
        # silently prorate or fabricate these annual amounts.
        annual_costs = _annual_costs(model_input.operating_state) if end == 17520 else (0.0, 0.0)
        runtime_identity = _hash(_runtime_identity())
        multiplier = float(model_input.parameters.get("market.bid_multiplier", 1.0))
        if not math.isfinite(multiplier) or multiplier < 0:
            raise ValueError("Invalid doctoral bid multiplier")
        generators, batteries, connections = from_doctoral_psm_input(model_input, self._fleet, self._batteries)
        prior = model_input.operating_state.extensions.get("doctoral_runtime")
        if prior is not None:
            if _hash(prior) != model_input.operating_state.extensions.get("doctoral_runtime_sha256"):
                raise ValueError("Parent annual doctoral runtime hash mismatch")
            old_identity = prior["identity"]
            if old_identity.get("runtime_implementation_sha256") != runtime_identity:
                raise ValueError("Parent annual doctoral runtime implementation identity mismatch")
            previous_ledger = DoctoralPeriodLedger.from_snapshot(prior["ledger"],
                expected_input_sha256=old_identity["engine_input_sha256"],
                expected_source_rule_sha256=old_identity["source_rule_sha256"],
                expected_weather_sha256=old_identity["weather_sha256"],
                expected_prefix_sha256=prior["ledger"]["prefix_sha256"])
            if (not previous_ledger.coverage["annual_complete"] or old_identity["run_id"] != model_input.run_id
                    or previous_ledger.current_state.to_dict() != prior["engine"]["state"]):
                raise ValueError("Incomplete or inconsistent parent annual doctoral runtime")
            # The outer YearState was authenticated by the annual checkpoint
            # loader. Its full runtime hash binds the child engine and prefix.
            engine = DoctoralPeriodEngine.from_prior_year_snapshot(generators, batteries,
                year=model_input.year, connections=connections, prior_snapshot=prior["engine"],
                expected_prior_snapshot_sha256=_hash(prior["engine"]))
        else:
            engine = DoctoralPeriodEngine(generators, batteries, year=model_input.year, connections=connections)
        annual_state = model_input.operating_state.to_dict()
        identity = {**self._data_identity, "run_id": model_input.run_id, "year": model_input.year,
            "cost_profile": cost_profile, "settlement_rule": SETTLEMENT_RULE,
            "runtime_implementation_sha256": runtime_identity,
            "engine_input_sha256": engine.input_sha256, "source_rule_sha256": _hash(engine.rule_identity),
            "parameters_sha256": _hash({"input": model_input.to_dict(), "fleet": self._fleet, "batteries": self._batteries}),
            "planning_state_sha256": _hash(annual_state),
            "thesis_contract_sha256": thesis96_contract_identity()["contract_sha256"]}
        store = DoctoralCheckpointStore(self._output_dir / "doctoral-checkpoints" / str(model_input.year),
                                        frozen_identity=identity)
        payload = store.load_latest()
        asset_ids = tuple(item.name for item in (*generators, *batteries, *connections))
        summaries = []
        detail_root = self._output_dir / 'doctoral-settlement-details' / str(model_input.year)
        detail_records = []
        if payload is None:
            ledger = DoctoralPeriodLedger(run_id=model_input.run_id, input_sha256=engine.input_sha256,
                source_rule_sha256=identity["source_rule_sha256"], weather_sha256=identity["weather_sha256"],
                initial_state=engine.state, asset_ids=asset_ids)
        else:
            engine = DoctoralPeriodEngine(generators, batteries, year=model_input.year,
                                          connections=connections, checkpoint=payload["engine"])
            ledger = DoctoralPeriodLedger.from_snapshot(payload["ledger"],
                expected_input_sha256=engine.input_sha256,
                expected_source_rule_sha256=identity["source_rule_sha256"],
                expected_weather_sha256=identity["weather_sha256"],
                expected_prefix_sha256=store.latest_record()["ledger_prefix_sha256"])
            raw_summaries = payload.get("runtime_artifacts", {}).get("period_summaries")
            if not isinstance(raw_summaries, list) or len(raw_summaries) != ledger.period_count:
                raise ValueError("Checkpoint is missing the cumulative PSM period summaries")
            summaries = [PeriodSummary.from_dict(row) for row in raw_summaries]
            _validate_summaries(summaries, model_input, ledger.totals)
            detail_records = payload.get('runtime_artifacts', {}).get('settlement_details')
            if not isinstance(detail_records, list):
                raise ValueError('Checkpoint is missing settlement details')
            verify_settlement_files(detail_root, detail_records, ledger.period_count)
        if engine.state.next_period_index > end:
            raise ValueError("Requested stopping period would rewind a committed national checkpoint")
        for index in range(engine.state.next_period_index, end):
            plan = engine.plan_period(float(forecast[index]) / 0.5, bid_multiplier=multiplier)
            # Explicitly AHEAD generator settlement price, never relabelled as
            # an all-stage price or fed into the unimplemented thesis storage cap.
            ahead_price = max((float(row[1]) for row in plan._calculation[3][0]), default=0.0)
            outcome = engine.realise_period(plan, float(chronology.demand_mwh[index]) / 0.5)
            ledger.append(outcome)
            detail_records.append(publish_settlement_report(detail_root, outcome))
            engine.commit(outcome)
            summary = PeriodSummary(chronology.period_ids[index], model_input.year, index,
                "doctoral_final_physical_with_ahead_generator_price",
                outcome.forecast_demand_mwh, outcome.actual_demand_mwh,
                sum(outcome.generation_mwh_by_asset.values()), outcome.storage_charge_mwh,
                outcome.storage_discharge_mwh, outcome.vre_available_mwh,
                outcome.vre_available_mwh - outcome.vre_curtailed_mwh,
                outcome.vre_curtailed_mwh, outcome.import_mwh, ahead_price,
                sum(outcome.operating_cost_gbp_by_asset.values()),
                sum(outcome.ahead_income_gbp_by_asset.values()) + sum(outcome.balancing_income_gbp_by_asset.values()),
                outcome.blackout_mwh, outcome.energy_balance_residual_mwh)
            summaries.append(summary)
            position = engine.state.next_period_index
            if position in month_end_periods() or position == end:
                if _hash(_runtime_identity()) != runtime_identity:
                    raise ValueError("Doctoral runtime implementation identity changed before checkpoint publication")
                _validate_summaries(summaries, model_input, ledger.totals)
                boundary = "annual" if ledger.coverage["annual_complete"] else (
                    "monthly" if position in month_end_periods() else "diagnostic")
                store.publish(engine, ledger, annual_state=annual_state, boundary=boundary,
                              runtime_artifacts={"period_summaries": [row.to_dict() for row in summaries],
                                                 "settlement_details": detail_records})
        totals = ledger.totals
        complete = ledger.coverage["annual_complete"]
        fixed, capital = annual_costs if complete else (0.0, 0.0)
        variable = sum(totals["operating_cost_gbp_by_asset"].values())
        cash = ledger.doctoral_cashflow_inputs()
        runtime = {"engine": engine.export_state(), "ledger": ledger.snapshot(),
                   "identity": identity, "period_coverage": ledger.coverage}
        return MarketYearResult(f"{model_input.run_id}:doctoral:{model_input.year}", model_input.year,
            self.id, self.version, totals["generation_mwh_by_asset"], cash["total_market_income_gbp_by_asset"],
            variable + fixed + capital + totals["blackout_mwh"] * chronology.voll_gbp_per_mwh,
            variable + fixed, capital, totals["actual_demand_mwh"],
            sum(totals["generation_mwh_by_asset"].values()), totals["blackout_mwh"], totals["vre_curtailed_mwh"],
            period_summaries=tuple(summaries), extensions={
                "doctoral_alignment_profile": PROFILE, "doctoral_cashflow_inputs": cash,
                "doctoral_cost_profile": cost_profile, "doctoral_settlement_rule": SETTLEMENT_RULE,
                "settlement_details_directory": f'doctoral-settlement-details/{model_input.year}',
                "settlement_detail_records": detail_records,
                "doctoral_runtime": runtime, "doctoral_runtime_sha256": _hash(runtime),
                "doctoral_national_operating_state": annual_state,
                "scientific_release_eligible": False,
                "doctoral_annual_cem_ready": False,
                "validation_scope": "live_national_psm_only_not_thesis96_annual_CEM_release",
                "annual_costs_included": complete,
                "cost_basis": "explicit_variable_plus_complete_year_fixed_and_annual_capital_plus_VOLL_no_policy_levies",
                "period_price_basis": "ahead_generator_settlement_only_not_all_stage_storage_arbitrage",
                "physical_totals": totals,
                "unresolved_scientific_gates": ["thesis96_storage_price_profit_cap", "downward_price_unit_calibration_and_legacy_nuclear_reconciliation",
                    "mixed_equity_loan_annual_capital", "full_annual_and_multiyear_comparison"],
            })
