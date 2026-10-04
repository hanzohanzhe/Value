"""Transactional adapter for one restored national half-hour.

This boundary does not launch a model, read weather, write a ledger or publish
a checkpoint. The caller commits its ledger before applying an outcome. Raw
doctoral objects are cloned for calculation; rejected/failed trials cannot
mutate the accepted physical state. Full-year integration is a separate gate.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import sys
from collections import defaultdict
from dataclasses import dataclass, fields, replace
from pathlib import Path
from types import CodeType, FunctionType, MappingProxyType
from typing import Mapping, Sequence

from . import doctoral_market_kernel as k
from . import doctoral_state as state_module
from .doctoral_state import (DoctoralRuntimeState, _GENERATOR_FIELDS,
                             batches_from_source, batches_to_source)

ENGINE_SCHEMA = "value.doctoral-national-period-engine/v2"
SETTLEMENT_RULE = "thesis96-signed-downward/v1"
COST_PROFILE = "thesis96_base"


def _code_identity(code):
    # marshal's object-reference flags can vary as strings become interned.
    # Serialize immutable instruction/constant content rather than object ids.
    def constant(value):
        if isinstance(value, CodeType):
            return _code_identity(value)
        if isinstance(value, bytes):
            return {"bytes": value.hex()}
        if isinstance(value, (tuple, list)):
            return [constant(item) for item in value]
        if isinstance(value, frozenset):
            return {"frozenset": sorted((constant(item) for item in value), key=repr)}
        if value is Ellipsis:
            return {"ellipsis": True}
        return value
    return {"bytecode": code.co_code.hex(), "constants": constant(code.co_consts),
            "names": code.co_names, "variables": code.co_varnames,
            "freevars": code.co_freevars, "cellvars": code.co_cellvars,
            "argcount": code.co_argcount, "posonly": code.co_posonlyargcount,
            "kwonly": code.co_kwonlyargcount, "flags": code.co_flags}


def _rule_identity() -> dict[str, str]:
    """Bind file bytes AND loaded rules: editing a file is not hot reloading it.

    This is a local continuation guard, not the run/weather/ledger-prefix
    certificate required by the separately gated monthly publisher.
    """
    result = {}
    for label, module in (("kernel", k), ("physical_state", state_module),
                          ("period_adapter", sys.modules[__name__])):
        result[label + "_file_sha256"] = hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
        code = {}
        for name, value in vars(module).items():
            if isinstance(value, FunctionType) and value.__module__ == module.__name__:
                code[name] = _hash(_code_identity(value.__code__))
            elif isinstance(value, type) and value.__module__ == module.__name__:
                for method, fn in vars(value).items():
                    if isinstance(fn, (staticmethod, classmethod)):
                        fn = fn.__func__
                    if isinstance(fn, FunctionType):
                        code[name + "." + method] = _hash(_code_identity(fn.__code__))
        # Kernel public callable assignments also detect wrappers from tests or
        # another module; filtering by __module__ alone would miss those.
        if module is k:
            for name, fn in vars(module).items():
                if isinstance(fn, FunctionType):
                    code[name] = _hash(_code_identity(fn.__code__))
        result[label + "_loaded_rules_sha256"] = _hash(code)
    result["python_cache_tag"] = sys.implementation.cache_tag
    return result


def _hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def _number(value: float, name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be finite and nonnegative")
    return value


def _observable(value):
    if isinstance(value, Mapping):
        return {str(key): _observable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_observable(item) for item in value]
    if hasattr(value, "name"):
        return value.name
    return value


def _memory(generators) -> dict[str, dict[str, object]]:
    return {item.name: {"kind": type(item).__name__,
                       **{name: getattr(item, name) for name in _GENERATOR_FIELDS[type(item).__name__]}}
            for item in generators}


def _quantities(rows) -> dict[str, float]:
    result = defaultdict(float)
    for asset, quantity in rows:
        result[asset.name] += float(quantity)
    return dict(result)


@dataclass(frozen=True)
class DoctoralAheadPlan:
    state_sha256: str
    input_sha256: str
    ahead_sha256: str
    forecast_mw: float
    bid_multiplier: float
    _calculation: tuple


@dataclass(frozen=True)
class DoctoralPeriodOutcome:
    state_sha256: str
    input_sha256: str
    ahead_sha256: str
    next_state: DoctoralRuntimeState
    forecast_demand_mwh: float
    actual_demand_mwh: float
    generation_mwh_by_asset: Mapping[str, float]
    ahead_income_gbp_by_asset: Mapping[str, float]
    balancing_income_gbp_by_asset: Mapping[str, float]
    operating_cost_gbp_by_asset: Mapping[str, float]
    storage_charge_mwh: float
    storage_discharge_mwh: float
    export_mwh: float
    import_mwh: float
    vre_available_mwh: float
    vre_curtailed_mwh: float
    non_vre_spill_mwh: float
    storage_decay_loss_mwh: float
    storage_conversion_loss_mwh: float
    storage_numerical_discard_mwh: float
    blackout_mwh: float
    energy_balance_residual_mwh: float
    raw_source_cost_components: Mapping[str, float]
    ahead_scheduled_mwh_by_asset: Mapping[str, float]
    upward_accepted_mwh_by_asset: Mapping[str, float]
    downward_accepted_mwh_by_asset: Mapping[str, float]
    upward_income_gbp_by_asset: Mapping[str, float]
    downward_cash_gbp_by_asset: Mapping[str, float]
    legacy_downward_fee_gbp_by_asset: Mapping[str, float]
    fuel_cost_gbp_by_asset: Mapping[str, float]
    carbon_cost_gbp_by_asset: Mapping[str, float]
    other_operating_cost_gbp_by_asset: Mapping[str, float]
    export_mwh_by_asset: Mapping[str, float]
    export_receipt_gbp_by_asset: Mapping[str, float]

    def __post_init__(self):
        for field in fields(self):
            value = getattr(self, field.name)
            if isinstance(value, Mapping):
                object.__setattr__(self, field.name, MappingProxyType(dict(value)))

    def to_dict(self) -> dict[str, object]:
        result = {item.name: _observable(getattr(self, item.name)) for item in fields(self)}
        result["next_state"] = self.next_state.to_dict()
        return result


class DoctoralPeriodEngine:
    """Use explicit source-quantity templates, never the legacy simulation main.

    For a Battery template, pool_limit is energy_capacity_mwh / 0.5 and
    per_pool_limit is charging power MW. This states the actually-used source
    variable convention, not the misleading pumped-hydro table column names.
    The separate canonical factory must prove that conversion before release.
    """

    def __init__(self, generators: Sequence[object], batteries: Sequence[object], *,
                 year: int, connections: Sequence[object] = (), period_hours: float = 0.5,
                 checkpoint: Mapping[str, object] | None = None, cost_profile: str = COST_PROFILE) -> None:
        if cost_profile == "thermal_extra_costs":
            raise ValueError("thermal_extra_costs is uncalibrated; explicit extra-cost parameters and event rules required")
        if cost_profile != COST_PROFILE:
            raise ValueError("Unsupported doctoral cost profile")
        if period_hours != 0.5:
            raise ValueError("Doctoral period engine requires period_hours=0.5")
        if not generators:
            raise ValueError("Doctoral market requires an explicit generator offer set")
        self._generators, self._batteries, self._connections = copy.deepcopy((list(generators), list(batteries), list(connections)))
        all_assets = self._generators + self._batteries + self._connections
        names = [item.name for item in all_assets]
        if len(names) != len(set(names)) or any(not str(name) for name in names):
            raise ValueError("Doctoral market asset names must be unique")
        for generator in self._generators:
            if type(generator).__name__ not in _GENERATOR_FIELDS:
                raise ValueError("Unsupported doctoral generator class")
            if isinstance(generator, k.ExpensiverenewableGenerator) and (
                generator.electrolyzer_limit != 0 or generator.rampup_rate != 0 or generator.real_energy != 0
                or generator.stored_energy
            ):
                raise ValueError("Direct VRE electrolyzer loads must be explicitly disabled")
        for battery in self._batteries:
            if type(battery) is not k.Battery or not 0 < battery.n_1 <= 1 or not 0 < battery.n_2 <= 1:
                raise ValueError("Unsupported storage or nonphysical efficiency")
            if battery.stored_energy:
                raise ValueError("Opening charge must come from a validated state, not mutable templates")
            _number(battery.pool_limit, "storage energy bound")
            _number(battery.per_pool_limit, "storage charging bound")
        self.rule_identity = _rule_identity()
        self._issued_plans = set()
        self._issued_outcomes = set()
        self.input_sha256 = _hash({"schema": ENGINE_SCHEMA, "year": year, "rule_identity": self.rule_identity,
                                  "cost_profile": cost_profile, "settlement_rule": SETTLEMENT_RULE,
                                  "units": "MW * 0.5h * GBP/MWh; legacy startup bid adder unchanged",
                                  "templates": [{"kind": type(item).__name__, **vars(item)} for item in all_assets]})
        capacities = {item.name: float(item.pool_limit) * .5 for item in self._batteries}
        if checkpoint is None:
            self.state = DoctoralRuntimeState(year, 0, 0, capacities,
                         {name: () for name in capacities}, _memory(self._generators), ())
        else:
            expected = {"schema_version", "input_sha256", "rule_identity", "state_sha256", "state"}
            if set(checkpoint) != expected or checkpoint["schema_version"] != ENGINE_SCHEMA:
                raise ValueError("Unsupported national engine snapshot")
            if checkpoint["rule_identity"] != self.rule_identity:
                raise ValueError("National engine rule identity mismatch")
            if checkpoint["input_sha256"] != self.input_sha256:
                raise ValueError("National engine input identity mismatch")
            if checkpoint["state_sha256"] != _hash(checkpoint["state"]):
                raise ValueError("National engine state hash mismatch")
            self.state = DoctoralRuntimeState.from_dict(checkpoint["state"])
            if self.state.year != year or dict(self.state.storage_capacities_mwh) != capacities:
                raise ValueError("National engine year/storage identity mismatch")
            if set(self.state.generator_memory) != {item.name for item in self._generators}:
                raise ValueError("Incomplete generator memory in national engine state")
            if not set(self.state.accepted_generator_ids) <= set(self.state.generator_memory):
                raise ValueError("Unknown accepted generator identity")

    def export_state(self) -> dict[str, object]:
        payload = self.state.to_dict()
        return {"schema_version": ENGINE_SCHEMA, "input_sha256": self.input_sha256,
                "rule_identity": dict(self.rule_identity), "state_sha256": _hash(payload), "state": payload}

    def advance_year(self, generators: Sequence[object], batteries: Sequence[object], *,
                     year: int, connections: Sequence[object] = ()) -> DoctoralPeriodEngine:
        """Create a new, independently input-bound engine at a complete boundary.

        Never edit the old snapshot's hashes to fit new templates. Surviving
        generator memory and storage batch clocks continue; new assets receive
        their explicitly supplied initial state. Source main constructs its
        generator objects once, outside the year loop (lines 1579-1596), so
        natural-resource budgets are not silently replenished at New Year.
        Shrinking/removing nonempty storage still needs an explicit disposition
        rule; this API cannot infer one. Full annual ledger approval belongs to
        the caller, separately from this physical-state boundary check.
        """
        if self.rule_identity != _rule_identity():
            raise ValueError("Cannot cross year after national engine rule identity changed")
        new = type(self)(generators, batteries, year=year, connections=connections)
        return new._continue_prior_year(self.state, self.input_sha256)

    @classmethod
    def from_prior_year_snapshot(cls, generators: Sequence[object], batteries: Sequence[object], *,
                                 year: int, prior_snapshot: Mapping, expected_prior_snapshot_sha256: str,
                                 connections: Sequence[object] = ()) -> DoctoralPeriodEngine:
        """Annual recovery after a separately authenticated parent checkpoint.

        The expected hash must come from the validated parent annual state, not
        a user-edited copy of this snapshot. This permits changed *new-year*
        templates without pretending the previous input hash has changed.
        """
        if _hash(prior_snapshot) != expected_prior_snapshot_sha256:
            raise ValueError("Prior national annual snapshot hash mismatch")
        expected = {"schema_version", "input_sha256", "rule_identity", "state_sha256", "state"}
        if set(prior_snapshot) != expected or prior_snapshot["schema_version"] != ENGINE_SCHEMA:
            raise ValueError("Unsupported prior national annual snapshot")
        if (prior_snapshot["rule_identity"] != _rule_identity()
                or _hash(prior_snapshot["state"]) != prior_snapshot["state_sha256"]):
            raise ValueError("Prior national annual rule/state hash mismatch")
        prior = DoctoralRuntimeState.from_dict(prior_snapshot["state"])
        new = cls(generators, batteries, year=year, connections=connections)
        return new._continue_prior_year(prior, prior_snapshot["input_sha256"])

    def _continue_prior_year(self, prior: DoctoralRuntimeState, prior_input_sha256: str) -> DoctoralPeriodEngine:
        opening = prior.start_year(self.state.year, storage_capacities_mwh=self.state.storage_capacities_mwh)
        memory = {}
        for name, initial in self.state.generator_memory.items():
            previous = prior.generator_memory.get(name)
            if previous is not None and previous["kind"] != initial["kind"]:
                raise ValueError(f"Generator class changed across annual transition: {name}")
            memory[name] = dict(previous if previous is not None else initial)
        self.state = replace(opening, generator_memory=memory)
        self.annual_transition_evidence = {
            "schema_version": "value.doctoral-engine-year-transition/v1",
            "prior_engine_input_sha256": prior_input_sha256,
            "prior_state_sha256": _hash(prior.to_dict()),
            "new_engine_input_sha256": self.input_sha256,
            "new_state_sha256": _hash(self.state.to_dict()),
            "retired_generator_ids": sorted(set(prior.generator_memory) - set(memory)),
            "new_generator_ids": sorted(set(memory) - set(prior.generator_memory)),
            "storage_disposition": "none; nonempty retired or over-capacity inventory rejected",
        }
        return self

    def _restore_objects(self):
        generators, batteries, connections = copy.deepcopy((self._generators, self._batteries, self._connections))
        for generator in generators:
            memory = self.state.generator_memory[generator.name]
            if memory["kind"] != type(generator).__name__:
                raise ValueError("Generator class changed across continuation")
            for name, value in memory.items():
                if name != "kind":
                    setattr(generator, name, value)
        for battery in batteries:
            battery.stored_energy = batches_to_source(self.state.storage_batches[battery.name], period_hours=.5)
        return generators, batteries, connections

    @staticmethod
    def _plan_hash(state_sha256, forecast, multiplier, calculation):
        generators, batteries, connections, result = calculation
        return _hash({"state": state_sha256, "forecast_mw": forecast, "bid_multiplier": multiplier,
                      "objects": [vars(item) for item in generators + batteries + connections],
                      "ahead_result": _observable(result)})

    def plan_period(self, forecast_mw: float, *, available_mw_by_vre: Mapping[str, float] | None = None,
                    bid_multiplier: float = 1.0) -> DoctoralAheadPlan:
        forecast = _number(forecast_mw, "forecast")
        multiplier = _number(bid_multiplier, "bid multiplier")
        generators, batteries, connections = self._restore_objects()
        for generator in generators:
            values = getattr(generator, "doctoral_capacity_mw_by_period", None)
            if values is not None:
                if self.state.next_period_index >= len(values):
                    raise ValueError("Doctoral generator profile does not cover this period")
                generator.capacity_limit = _number(values[self.state.next_period_index], "capacity profile")
        for connection in connections:
            names = ("doctoral_transfer_constraint_mw_by_period", "doctoral_external_price_gbp_per_mwh_by_period")
            present = [hasattr(connection, name) for name in names]
            if any(present):
                if not all(present):
                    raise ValueError("Incomplete doctoral connection profile")
                values = [getattr(connection, name) for name in names]
                if len(values[0]) != len(values[1]) or self.state.next_period_index >= len(values[0]):
                    raise ValueError("Doctoral connection profile does not cover this period")
                constraint, price = (float(value[self.state.next_period_index]) for value in values)
                if not math.isfinite(constraint) or not math.isfinite(price):
                    raise ValueError("Nonfinite doctoral connection profile")
                connection.transfer_constraint, connection.external_price = constraint, price
        if available_mw_by_vre is not None:
            expected = {item.name for item in generators if type(item) is k.ExpensiverenewableGenerator}
            if set(available_mw_by_vre) != expected:
                raise ValueError("VRE availability must explicitly cover every VRE agent")
            for item in generators:
                if item.name in expected:
                    item.capacity_limit = _number(available_mw_by_vre[item.name], "VRE availability")
        accepted = [[item] for item in generators if item.name in self.state.accepted_generator_ids]
        result = k.ahead_market_bidding(generators, batteries, forecast, self.state.next_absolute_period,
                    accepted, defaultdict(float), defaultdict(float), defaultdict(float), defaultdict(float), multiplier)
        calculation = (generators, batteries, connections, result)
        state_sha256 = _hash(self.state.to_dict())
        plan = DoctoralAheadPlan(state_sha256, self.input_sha256,
                    self._plan_hash(state_sha256, forecast, multiplier, calculation), forecast, multiplier, calculation)
        self._issued_plans.add(plan.ahead_sha256)
        return plan

    def realise_period(self, plan: DoctoralAheadPlan, actual_mw: float) -> DoctoralPeriodOutcome:
        if plan.input_sha256 != self.input_sha256 or plan.state_sha256 != _hash(self.state.to_dict()):
            raise ValueError("Stale national ahead plan")
        if plan.ahead_sha256 != self._plan_hash(plan.state_sha256, plan.forecast_mw, plan.bid_multiplier, plan._calculation):
            raise ValueError("National ahead plan was mutated")
        if plan.ahead_sha256 not in self._issued_plans:
            raise ValueError("National ahead plan was not issued by this engine")
        actual = _number(actual_mw, "actual demand")
        generators, batteries, connections, ahead = copy.deepcopy(plan._calculation)
        period = self.state.next_absolute_period
        electrolyzer = k.Electrolyzer("off", 0, 0, .6, 0, 0, 0, 0)
        # Record income before curtailment mutates the accepted bid quantities.
        income_ahead = dict(ahead[14])
        scheduled = defaultdict(float)
        for asset, price, quantity, *_ in ahead[0]:
            scheduled[asset.name] += float(quantity)
        for asset, quantity in ahead[10]:
            if type(asset) is k.Battery:
                scheduled[asset.name] += float(quantity)
        down_actions, up_actions = [], []
        # D1-shortfall: a shortage in the forecast clearance is not a scheduled
        # delivery. Curtailing forecast-actual in that case would cut already
        # insufficient generation. Balance the actual accepted load instead.
        already_generated_surplus = sum(float(amount) for generator, amount in ahead[15]
                                        if type(generator) is not k.ExpensiverenewableGenerator)
        scheduled_load = sum(float(amount) for generator, amount in ahead[10]) - already_generated_surplus
        non_vre_spill = 0.0
        if actual < scheduled_load:
            before_curtailment = _quantities(ahead[10])
            result = k.curtailment_market_bidding(period, actual, scheduled_load,
                       ahead[0], ahead[5], ahead[6], ahead[10], connections, electrolyzer, batteries,
                       actions=down_actions)
            generation_list, remaining_excess = result[4], result[6]
            after_curtailment = _quantities(generation_list)
            reductions = [before_curtailment.get(name, 0.0) - after_curtailment.get(name, 0.0)
                          for name in sorted(before_curtailment.keys() | after_curtailment.keys())]
            if any(amount < -1e-7 for amount in reductions):
                raise ValueError("Source downward curtailment increased generation; outcome not committed")
            # store_service_three records result[5] after charging/export, but
            # BEFORE generator curtailment. Compare that explicit request with
            # the physical reductions in gen_list, not accepted_bids (whose
            # fully curtailed VRE quantities are not consistently updated).
            # Ramp-limited output left by this request is additional spill;
            # it is absent from the original ahead[15] surplus pool.
            non_vre_spill = max(0.0, float(result[5]) - sum(reductions))
            charge, income_balance = float(result[1]), {}
            balance_fee, storage_balance, curtail_fee, bought_fee = 0.0, 0.0, sum(result[0]), 0.0
        else:
            result = k.balancing_market_bidding(generators, period, actual, scheduled_load,
                       ahead[0], ahead[6], defaultdict(float), defaultdict(float), defaultdict(float),
                       ahead[10], defaultdict(float), connections, ahead[12], ahead[13], electrolyzer,
                       ahead[15], batteries, plan.bid_multiplier, actions=up_actions)
            generation_list, remaining_excess = result[8], result[10]
            charge, income_balance = float(result[3]), dict(result[15])
            balance_fee, storage_balance, curtail_fee, bought_fee = sum(result[0]), result[1], 0.0, sum(result[12])
        generation = _quantities(generation_list)  # NOT duplicated legacy real_list.
        # The source gen_list records load-serving generation but omits VRE
        # surplus actually sent to storage/export. Allocate only that observed
        # surplus consumption, retaining the source's proportional VRE rule.
        remaining_pool = sum(float(row[1]) for row in ahead[15])
        consumed_surplus = max(0.0, remaining_pool - float(remaining_excess))
        if remaining_pool > 0:
            for generator, amount in ahead[15]:
                consumed = consumed_surplus * amount / remaining_pool
                if type(generator) is k.ExpensiverenewableGenerator:
                    generation[generator.name] = generation.get(generator.name, 0) + consumed
                else:
                    # Nuclear minimum output is already in gen_list. Retain
                    # unused physical output as spill, not VRE curtailment or
                    # another sale/generation event.
                    non_vre_spill += max(0.0, amount - consumed)
        available_vre = {item.name: float(item.capacity_limit) for item in generators if type(item) is k.ExpensiverenewableGenerator}
        vre_curtailed = sum(available - generation.get(name, 0) for name, available in available_vre.items())
        if vre_curtailed < -1e-7:
            raise ValueError("Source dispatch exceeds available VRE; outcome not committed")
        for generator in generators:
            quantity = generation.get(generator.name, 0.0)
            if quantity < -1e-7:
                raise ValueError("Source dispatch produced negative generation; outcome not committed")
            generator.real_gen_energy = max(0.0, quantity)
        all_assets = generators + batteries + connections
        generation = {item.name: float(generation.get(item.name, 0)) for item in all_assets}
        discharge = sum(generation[item.name] for item in batteries)
        imported = sum(generation[item.name] for item in connections)
        exported = sum(float(item.sold_energy) for item in connections)
        total = sum(generation.values())
        missing = actual + charge + exported + non_vre_spill - total
        blackout = max(0.0, missing)
        residual = (total + blackout - actual - charge - exported - non_vre_spill) * .5
        if abs(residual) > 1e-7:
            raise ValueError(f"Source physical balance residual {residual} MWh; outcome not committed")
        next_state = self.state.commit_period(
            storage_batches={item.name: batches_from_source(item.stored_energy, period_hours=.5) for item in batteries},
            generator_memory=_memory(generators), accepted_generator_ids=tuple(row[0].name for row in ahead[0]))
        decay_loss, conversion_loss, numerical_discard, measured_charge = 0.0, 0.0, 0.0, 0.0
        for battery in batteries:
            opening = self.state.storage_energy_mwh(battery.name)
            decayed = batches_to_source(self.state.storage_batches[battery.name], period_hours=.5)
            k.decay_func(decayed, battery.battery_type)
            decay = opening - sum(decayed.values()) * .5
            charged = float(battery.stored_energy.get(period, 0.0)) * .5 / battery.n_1
            delivered = generation[battery.name] * .5
            conversion = charged * (1 - battery.n_1) + delivered * (1 / battery.n_2 - 1)
            discard = opening + charged - delivered - decay - conversion - next_state.storage_energy_mwh(battery.name)
            # Source clr_stored_energy_var drops residual batches <0.001 raw
            # units. Account for that separately; never absorb an arbitrary
            # state mismatch into a supposed conversion loss.
            bound = len(self.state.storage_batches[battery.name]) * .0005
            if discard < -1e-7 or discard > bound + 1e-7:
                raise ValueError("Doctoral storage SOC reconciliation failed; outcome not committed")
            decay_loss += max(0.0, decay)
            conversion_loss += conversion
            numerical_discard += max(0.0, discard) if abs(discard) > 1e-10 else 0.0
            measured_charge += charged
        if not math.isclose(measured_charge, charge * .5, rel_tol=1e-10, abs_tol=1e-7):
            raise ValueError("Doctoral reported charging differs from committed batches")
        income_ahead = {item.name: float(income_ahead.get(item.name, 0)) for item in all_assets}
        income_up = {item.name: float(income_balance.get(item.name, 0)) for item in all_assets}
        down_mwh = {item.name: 0.0 for item in all_assets}
        down_cash, legacy_down = dict(down_mwh), dict(down_mwh)
        for name, kind, quantity, price in down_actions:
            down_mwh[name] += quantity * .5
            raw_gbp = quantity * .5 * price
            # Frozen configured price retains its sign. Do not silently replace
            # the unresolved thesis startup/fuel formula with a new calibration.
            if kind in {"NuclearGenerator", "ExpensiverenewableGenerator", "Battery"}:
                legacy_down[name] += raw_gbp
            else:
                down_cash[name] += raw_gbp
        income_balance = {item.name: income_up[item.name] + down_cash[item.name] for item in all_assets}
        operational = {item.name: (generation[item.name] * .5 * float(item.gen_cost)
                                   if hasattr(item, "gen_cost") else
                                   generation[item.name] * .5 * float(item.external_price)
                                   if type(item) is k.Connection else 0.0) for item in all_assets}
        fuel = {item.name: generation[item.name] * .5 * float(getattr(item, "fuel_cost", 0)) for item in all_assets}
        carbon = {item.name: generation[item.name] * .5 * float(getattr(item, "carbon_price", 0)) for item in all_assets}
        # Residual is already included in gen_cost: never add the components to
        # the old total again. For connections it is external procurement cost.
        other = {name: operational[name] - fuel[name] - carbon[name] for name in operational}
        up_mw = defaultdict(float)
        for name, quantity in up_actions:
            up_mw[name] += quantity
        export_by_asset = {item.name: (float(item.sold_energy) * .5 if type(item) is k.Connection else 0.0) for item in all_assets}
        export_receipts = {item.name: (export_by_asset[item.name] * float(item.external_price)
                            if type(item) is k.Connection else 0.0) for item in all_assets}
        outcome = DoctoralPeriodOutcome(plan.state_sha256, self.input_sha256, plan.ahead_sha256,
            next_state, plan.forecast_mw * .5, actual * .5,
            {name: quantity * .5 for name, quantity in generation.items()}, income_ahead, income_balance, operational,
            charge * .5, discharge * .5, exported * .5, imported * .5,
            sum(available_vre.values()) * .5, max(0.0, vre_curtailed) * .5, non_vre_spill * .5,
            decay_loss, conversion_loss, numerical_discard, blackout * .5, residual,
            {"ahead_generator_price_times_source_quantity": sum(row[1] * row[2] for row in ahead[0]),
             "ahead_storage": float(ahead[1]), "balancing": float(balance_fee),
             "balancing_storage": float(storage_balance), "curtailment": float(curtail_fee),
             "imports_included_in_balancing": float(bought_fee)},
            {item.name: scheduled.get(item.name, 0.0) * .5 for item in all_assets},
            {item.name: up_mw.get(item.name, 0.0) * .5 for item in all_assets},
            down_mwh, income_up, down_cash, legacy_down, fuel, carbon, other,
            export_by_asset, export_receipts)
        self._issued_outcomes.add(_hash(outcome.to_dict()))
        return outcome

    def commit(self, outcome: DoctoralPeriodOutcome) -> None:
        if outcome.input_sha256 != self.input_sha256 or outcome.state_sha256 != _hash(self.state.to_dict()):
            raise ValueError("Outcome is stale or already committed")
        if (outcome.next_state.year != self.state.year
            or outcome.next_state.next_period_index != self.state.next_period_index + 1
            or outcome.next_state.next_absolute_period != self.state.next_absolute_period + 1):
            raise ValueError("Outcome does not advance exactly one period")
        if _hash(outcome.to_dict()) not in self._issued_outcomes:
            raise ValueError("Outcome was not issued by this engine or was modified")
        self.state = outcome.next_state
        self._issued_outcomes.clear()
        self._issued_plans.clear()
