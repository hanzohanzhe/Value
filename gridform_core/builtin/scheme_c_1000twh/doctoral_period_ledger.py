"""In-memory national period ledger with externally anchored JSON continuation.

This bounded accumulator is not a disk publisher or a legacy/zonal checkpoint
adapter. It authenticates a committed prefix against the caller's trusted hash;
a content hash supplied alongside an untrusted snapshot is never its own trust
anchor. Compact entries bind time, physical-state hashes, outcome hashes and
the complete cumulative accounts without retaining every historical SOC object.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Mapping, Sequence

from .doctoral_state import DoctoralRuntimeState


SCHEMA = "value.doctoral-national-period-ledger/v2"
CHAIN_SCHEMA = "value.doctoral-national-ledger-prefix/v2"
PERIOD_HOURS = 0.5
PERIODS_PER_YEAR = 17520
BALANCE_TOLERANCE_MWH = 1e-7
ASSET_MAP_FIELDS = (
    "generation_mwh_by_asset", "ahead_income_gbp_by_asset",
    "balancing_income_gbp_by_asset", "operating_cost_gbp_by_asset",
    "ahead_scheduled_mwh_by_asset", "upward_accepted_mwh_by_asset",
    "downward_accepted_mwh_by_asset", "upward_income_gbp_by_asset",
    "downward_cash_gbp_by_asset", "legacy_downward_fee_gbp_by_asset",
    "fuel_cost_gbp_by_asset", "carbon_cost_gbp_by_asset",
    "other_operating_cost_gbp_by_asset", "export_mwh_by_asset",
    "export_receipt_gbp_by_asset",
)
SCALAR_FIELDS = (
    "forecast_demand_mwh", "actual_demand_mwh", "storage_charge_mwh",
    "storage_discharge_mwh", "export_mwh", "import_mwh", "vre_available_mwh",
    "vre_curtailed_mwh", "non_vre_spill_mwh", "storage_decay_loss_mwh",
    "storage_conversion_loss_mwh", "storage_numerical_discard_mwh",
    "blackout_mwh", "energy_balance_residual_mwh",
)
RAW_SOURCE_COMPONENTS = (
    "ahead_generator_price_times_source_quantity", "ahead_storage", "balancing",
    "balancing_storage", "curtailment", "imports_included_in_balancing",
)
OUTCOME_FIELDS = frozenset((*ASSET_MAP_FIELDS, *SCALAR_FIELDS,
    "state_sha256", "input_sha256", "ahead_sha256", "next_state", "raw_source_cost_components"))
ENTRY_FIELDS = frozenset(("ordinal", "year", "period_index", "absolute_period",
    "state_sha256", "next_state_sha256", "outcome_sha256", "accumulator_sha256",
    "previous_prefix_sha256", "prefix_sha256"))


def _hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False,
        separators=(",", ":")).encode("utf-8")).hexdigest()


def _copy(value):
    return json.loads(json.dumps(value, allow_nan=False, separators=(",", ":")))


def _sha(value, label):
    if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{label} must be a canonical SHA-256 identity")
    return value


def _index(value, label):
    if type(value) is not int or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _number(value, label, *, nonnegative=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result) or nonnegative and result < 0:
        raise ValueError(f"{label} must be finite" + (" and nonnegative" if nonnegative else ""))
    return result


def _amounts(value, keys, label, *, nonnegative=False):
    if not isinstance(value, Mapping) or set(value) != set(keys):
        raise ValueError(f"{label} requires exact asset/component coverage")
    return {key: _number(value[key], f"{label}[{key}]", nonnegative=nonnegative) for key in keys}


def _state(value):
    if isinstance(value, DoctoralRuntimeState):
        return value
    return DoctoralRuntimeState.from_dict(value)


def _stock(state):
    return _number(sum(state.storage_energy_mwh(name) for name in state.storage_batches),
                   "aggregate storage stock", nonnegative=True)


def _entry_hash(entry):
    return _hash({"schema_version": CHAIN_SCHEMA,
                  **{key: value for key, value in entry.items() if key != "prefix_sha256"}})


def _accumulator_hash(cumulative, current_state_sha256, period_count):
    return _hash({"cumulative": cumulative, "current_state_sha256": current_state_sha256,
                  "period_count": period_count})


class DoctoralPeriodLedger:
    """Accumulate one explicitly bounded segment of one national model year.

    ``asset_ids`` covers every actor in a period outcome, including storage and
    external connections. The explicit initial state may start at any valid
    local/absolute period; no earlier ledger history is fabricated. All mutations
    are computed and validated before append changes the accepted prefix.
    """

    def __init__(self, *, run_id: str, input_sha256: str, source_rule_sha256: str,
                 weather_sha256: str, initial_state: DoctoralRuntimeState,
                 asset_ids: Sequence[str], period_hours: float = PERIOD_HOURS):
        if not isinstance(run_id, str) or not run_id:
            raise ValueError("ledger requires a nonempty run identity")
        if period_hours != PERIOD_HOURS:
            raise ValueError("doctoral ledger requires period_hours=0.5")
        if isinstance(asset_ids, str):
            raise ValueError("asset_ids must be an explicit sequence")
        assets = tuple(asset_ids)
        if not assets or len(set(assets)) != len(assets) or any(not isinstance(name, str) or not name for name in assets):
            raise ValueError("ledger asset identities must be unique and nonempty")
        opening = _state(initial_state)
        if opening.next_period_index > PERIODS_PER_YEAR:
            raise ValueError("initial local period is beyond the model year")
        self._asset_ids = assets
        self._validate_state_assets(opening, opening)
        self._initial_state = self._current_state = opening
        self._header = {
            "run_id": run_id, "input_sha256": _sha(input_sha256, "input_sha256"),
            "source_rule_sha256": _sha(source_rule_sha256, "source_rule_sha256"),
            "weather_sha256": _sha(weather_sha256, "weather_sha256"),
            "asset_ids": list(assets), "period_hours": PERIOD_HOURS,
            "initial_state": opening.to_dict(), "initial_state_sha256": _hash(opening.to_dict()),
        }
        self._entries: list[dict] = []
        self._cumulative = self._zero_totals()
        self._prefix_sha256 = _hash({"schema_version": CHAIN_SCHEMA, "header": self._header})

    @property
    def current_state(self) -> DoctoralRuntimeState:
        return self._current_state

    @property
    def period_count(self) -> int:
        return len(self._entries)

    @property
    def prefix_sha256(self) -> str:
        return self._prefix_sha256

    @property
    def totals(self) -> dict:
        return _copy(self._cumulative)

    @property
    def coverage(self) -> dict:
        start, end = self._initial_state, self._current_state
        return {"year": start.year, "start_period_index": start.next_period_index,
            "end_period_index_exclusive": end.next_period_index,
            "start_absolute_period": start.next_absolute_period,
            "end_absolute_period_exclusive": end.next_absolute_period,
            "period_count": self.period_count,
            "annual_complete": start.next_period_index == 0 and end.next_period_index == PERIODS_PER_YEAR}

    def _zero_totals(self):
        return {**{key: {name: 0.0 for name in self._asset_ids} for key in ASSET_MAP_FIELDS},
            **{key: 0.0 for key in SCALAR_FIELDS},
            "raw_source_cost_components": {key: 0.0 for key in RAW_SOURCE_COMPONENTS},
            "source_cost_components_gbp": {key: 0.0 for key in RAW_SOURCE_COMPONENTS},
            "max_abs_energy_balance_residual_mwh": 0.0,
            "max_abs_storage_balance_residual_mwh": 0.0}

    def _validate_state_assets(self, state, original):
        if (not set(state.generator_memory) <= set(self._asset_ids)
            or not set(state.storage_capacities_mwh) <= set(self._asset_ids)
            or set(state.generator_memory) & set(state.storage_capacities_mwh)
            or not set(state.accepted_generator_ids) <= set(state.generator_memory)):
            raise ValueError("physical state has invalid ledger asset identities")
        if (dict(state.storage_capacities_mwh) != dict(original.storage_capacities_mwh)
            or set(state.generator_memory) != set(original.generator_memory)
            or any(state.generator_memory[name]["kind"] != original.generator_memory[name]["kind"]
                   for name in original.generator_memory)):
            raise ValueError("physical fleet identity changed within a ledger segment")

    def _asset_amounts(self, raw, key):
        amounts = _amounts(raw, self._asset_ids, key, nonnegative=key.endswith("mwh_by_asset"))
        if key == "operating_cost_gbp_by_asset":
            # Signed import prices are source-valid expenditure credits. Only
            # connections (outside both physical-state sets) may have them;
            # domestic generation/storage cost is still explicitly nonnegative.
            domestic = set(self._initial_state.generator_memory) | set(self._initial_state.storage_capacities_mwh)
            for name in domestic:
                _number(amounts[name], f"{key}[{name}]", nonnegative=True)
        return amounts

    def append(self, outcome) -> str:
        """Validate and append a typed DoctoralPeriodOutcome or its JSON payload."""
        raw = outcome.to_dict() if hasattr(outcome, "to_dict") else outcome
        if not isinstance(raw, Mapping) or set(raw) != OUTCOME_FIELDS:
            raise ValueError("incomplete or unsupported doctoral period outcome")
        before = self._current_state
        if raw["input_sha256"] != self._header["input_sha256"]:
            raise ValueError("period outcome input identity mismatch")
        if raw["state_sha256"] != _hash(before.to_dict()):
            raise ValueError("period outcome state is stale, duplicated or discontinuous")
        _sha(raw["ahead_sha256"], "ahead_sha256")
        after = _state(raw["next_state"])
        if (after.year != before.year or after.next_period_index != before.next_period_index + 1
            or after.next_absolute_period != before.next_absolute_period + 1
            or after.next_period_index > PERIODS_PER_YEAR):
            raise ValueError("period outcome year/local/absolute clock is discontinuous")
        self._validate_state_assets(after, self._initial_state)
        normalized = {"state_sha256": raw["state_sha256"], "input_sha256": raw["input_sha256"],
                      "ahead_sha256": raw["ahead_sha256"], "next_state": after.to_dict()}
        for key in ASSET_MAP_FIELDS:
            normalized[key] = self._asset_amounts(raw[key], key)
        for name in self._asset_ids:
            cash_residual = (normalized['balancing_income_gbp_by_asset'][name]
                - normalized['upward_income_gbp_by_asset'][name] - normalized['downward_cash_gbp_by_asset'][name])
            cost_residual = (normalized['operating_cost_gbp_by_asset'][name]
                - normalized['fuel_cost_gbp_by_asset'][name] - normalized['carbon_cost_gbp_by_asset'][name]
                - normalized['other_operating_cost_gbp_by_asset'][name])
            if abs(cash_residual) > 1e-7 or abs(cost_residual) > 1e-7:
                raise ValueError('period cash/cost components do not reconcile')
        for key in SCALAR_FIELDS:
            normalized[key] = _number(raw[key], key, nonnegative=key != "energy_balance_residual_mwh")
        normalized["raw_source_cost_components"] = _amounts(raw["raw_source_cost_components"],
            RAW_SOURCE_COMPONENTS, "raw_source_cost_components")
        generation = normalized["generation_mwh_by_asset"]
        storage_ids = set(before.storage_capacities_mwh)
        connection_ids = set(self._asset_ids) - set(before.generator_memory) - storage_ids
        vre_ids = {name for name, memory in before.generator_memory.items()
                   if memory["kind"] == "ExpensiverenewableGenerator"}
        for label, reported, ids in (
            ("storage discharge", normalized["storage_discharge_mwh"], storage_ids),
            ("imports", normalized["import_mwh"], connection_ids),
            ("available minus curtailed VRE", normalized["vre_available_mwh"] - normalized["vre_curtailed_mwh"], vre_ids),
        ):
            residual = _number(reported - sum(generation[name] for name in ids), f"{label} identity balance")
            if abs(residual) > BALANCE_TOLERANCE_MWH:
                raise ValueError(f"period {label} differs from identified asset generation")
        # Import and delivered storage discharge are already members of the
        # generation map. Adding their scalar totals again would double-count.
        physical_balance = _number(sum(generation.values()) + normalized["blackout_mwh"]
            - normalized["actual_demand_mwh"] - normalized["storage_charge_mwh"]
            - normalized["export_mwh"] - normalized["non_vre_spill_mwh"], "physical energy balance")
        if (abs(physical_balance) > BALANCE_TOLERANCE_MWH
            or abs(normalized["energy_balance_residual_mwh"]) > BALANCE_TOLERANCE_MWH
            or abs(physical_balance - normalized["energy_balance_residual_mwh"]) > BALANCE_TOLERANCE_MWH):
            raise ValueError("period physical energy balance does not reconcile")
        storage_balance = _number(_stock(before) + normalized["storage_charge_mwh"] - normalized["storage_discharge_mwh"]
            - normalized["storage_decay_loss_mwh"] - normalized["storage_conversion_loss_mwh"]
            - normalized["storage_numerical_discard_mwh"] - _stock(after), "storage stock/loss balance")
        if abs(storage_balance) > BALANCE_TOLERANCE_MWH:
            raise ValueError("period storage stock/loss balance does not reconcile")
        cumulative = self.totals
        for key in ASSET_MAP_FIELDS:
            for name in self._asset_ids:
                cumulative[key][name] = _number(cumulative[key][name] + normalized[key][name], f"cumulative {key}[{name}]")
        for key in SCALAR_FIELDS:
            cumulative[key] = _number(cumulative[key] + normalized[key], f"cumulative {key}")
        for key in RAW_SOURCE_COMPONENTS:
            amount = _number(cumulative["raw_source_cost_components"][key]
                             + normalized["raw_source_cost_components"][key], f"cumulative raw {key}")
            cumulative["raw_source_cost_components"][key] = amount
            cumulative["source_cost_components_gbp"][key] = amount * PERIOD_HOURS
        # These price-times-source-quantity diagnostics overlap: imports are
        # included in balancing. Never create a blindly summed source-cost total
        # or add them to the independently supplied physical operating GBP map.
        cumulative["max_abs_energy_balance_residual_mwh"] = max(
            cumulative["max_abs_energy_balance_residual_mwh"], abs(physical_balance))
        cumulative["max_abs_storage_balance_residual_mwh"] = max(
            cumulative["max_abs_storage_balance_residual_mwh"], abs(storage_balance))
        next_hash = _hash(after.to_dict())
        entry = {"ordinal": self.period_count, "year": before.year,
            "period_index": before.next_period_index, "absolute_period": before.next_absolute_period,
            "state_sha256": raw["state_sha256"], "next_state_sha256": next_hash,
            "outcome_sha256": _hash(normalized),
            "accumulator_sha256": _accumulator_hash(cumulative, next_hash, self.period_count + 1),
            "previous_prefix_sha256": self._prefix_sha256}
        entry["prefix_sha256"] = _entry_hash(entry)
        self._entries.append(entry)
        self._cumulative, self._current_state, self._prefix_sha256 = cumulative, after, entry["prefix_sha256"]
        return self._prefix_sha256

    def snapshot(self) -> dict:
        """Export complete cumulative/state evidence without publishing to disk."""
        payload = {"schema_version": SCHEMA, "header": _copy(self._header),
            "current_state": self._current_state.to_dict(), "cumulative": self.totals,
            "period_count": self.period_count, "entries": _copy(self._entries),
            "prefix_sha256": self._prefix_sha256}
        return {**payload, "content_sha256": _hash(payload)}

    def _validate_cumulative(self, raw):
        if not isinstance(raw, Mapping) or set(raw) != set(self._zero_totals()):
            raise ValueError("snapshot accumulator is incomplete")
        result = {}
        for key in ASSET_MAP_FIELDS:
            result[key] = self._asset_amounts(raw[key], key)
        for key in (*SCALAR_FIELDS, "max_abs_energy_balance_residual_mwh", "max_abs_storage_balance_residual_mwh"):
            result[key] = _number(raw[key], key, nonnegative=key != "energy_balance_residual_mwh")
        for key in ("raw_source_cost_components", "source_cost_components_gbp"):
            result[key] = _amounts(raw[key], RAW_SOURCE_COMPONENTS, key)
        for key in RAW_SOURCE_COMPONENTS:
            if result["source_cost_components_gbp"][key] != result["raw_source_cost_components"][key] * PERIOD_HOURS:
                raise ValueError("snapshot source fee conversion must apply the half hour exactly once")
        return result

    @classmethod
    def from_snapshot(cls, snapshot, *, expected_input_sha256: str, expected_source_rule_sha256: str,
                      expected_weather_sha256: str, expected_prefix_sha256: str):
        """Restore only against identities and a prefix obtained outside this JSON.

        Passing a snapshot's own prefix back as its trusted anchor only checks
        accidental corruption. The persistence caller must retain/verify the
        accepted prefix independently; this class creates no external anchor.
        """
        expected = {"schema_version", "header", "current_state", "cumulative", "period_count",
                    "entries", "prefix_sha256", "content_sha256"}
        if not isinstance(snapshot, Mapping) or set(snapshot) != expected or snapshot["schema_version"] != SCHEMA:
            raise ValueError("incomplete or unsupported doctoral period ledger snapshot")
        _sha(expected_prefix_sha256, "expected_prefix_sha256")
        if snapshot["prefix_sha256"] != expected_prefix_sha256:
            raise ValueError("snapshot prefix differs from the independently trusted prefix")
        content = {key: value for key, value in snapshot.items() if key != "content_sha256"}
        if snapshot["content_sha256"] != _hash(content):
            raise ValueError("snapshot content hash mismatch")
        header = snapshot["header"]
        if not isinstance(header, Mapping) or set(header) != {"run_id", "input_sha256", "source_rule_sha256",
            "weather_sha256", "asset_ids", "period_hours", "initial_state", "initial_state_sha256"}:
            raise ValueError("incomplete snapshot ledger identity")
        for field, anchor in (("input_sha256", expected_input_sha256),
                              ("source_rule_sha256", expected_source_rule_sha256),
                              ("weather_sha256", expected_weather_sha256)):
            if header[field] != _sha(anchor, f"expected_{field}"):
                raise ValueError(f"snapshot {field} identity mismatch")
        result = cls(run_id=header["run_id"], input_sha256=header["input_sha256"],
            source_rule_sha256=header["source_rule_sha256"], weather_sha256=header["weather_sha256"],
            initial_state=_state(header["initial_state"]), asset_ids=header["asset_ids"], period_hours=header["period_hours"])
        if dict(header) != result._header:
            raise ValueError("snapshot initial physical state identity mismatch")
        count = _index(snapshot["period_count"], "snapshot period_count")
        entries = snapshot["entries"]
        if not isinstance(entries, list) or len(entries) != count:
            raise ValueError("snapshot ledger prefix entries are incomplete")
        opening = result._initial_state
        previous_prefix = result.prefix_sha256
        previous_state_hash = result._header["initial_state_sha256"]
        for ordinal, entry in enumerate(entries):
            if not isinstance(entry, Mapping) or set(entry) != ENTRY_FIELDS:
                raise ValueError("snapshot prefix entry is incomplete")
            if (entry["ordinal"] != ordinal or type(entry["ordinal"]) is not int
                or entry["year"] != opening.year or type(entry["year"]) is not int
                or entry["period_index"] != opening.next_period_index + ordinal or type(entry["period_index"]) is not int
                or entry["absolute_period"] != opening.next_absolute_period + ordinal or type(entry["absolute_period"]) is not int
                or entry["state_sha256"] != previous_state_hash
                or entry["previous_prefix_sha256"] != previous_prefix):
                raise ValueError("snapshot prefix clock or physical-state chain is discontinuous")
            for key in ("next_state_sha256", "outcome_sha256", "accumulator_sha256", "prefix_sha256"):
                _sha(entry[key], f"prefix {key}")
            if entry["prefix_sha256"] != _entry_hash(entry):
                raise ValueError("snapshot ledger prefix hash mismatch")
            previous_prefix, previous_state_hash = entry["prefix_sha256"], entry["next_state_sha256"]
        current = _state(snapshot["current_state"])
        result._validate_state_assets(current, opening)
        if (current.year != opening.year or current.next_period_index != opening.next_period_index + count
            or current.next_absolute_period != opening.next_absolute_period + count
            or current.next_period_index > PERIODS_PER_YEAR or _hash(current.to_dict()) != previous_state_hash):
            raise ValueError("snapshot latest state does not match its committed prefix")
        cumulative = result._validate_cumulative(snapshot["cumulative"])
        if previous_prefix != snapshot["prefix_sha256"]:
            raise ValueError("snapshot final prefix mismatch")
        if entries:
            if entries[-1]["accumulator_sha256"] != _accumulator_hash(cumulative, previous_state_hash, count):
                raise ValueError("snapshot accumulator does not match its authenticated prefix")
        elif cumulative != result._zero_totals():
            raise ValueError("empty ledger cannot contain a nonzero accumulator")
        result._entries, result._cumulative = _copy(entries), cumulative
        result._current_state, result._prefix_sha256 = current, previous_prefix
        return result

    def doctoral_cashflow_inputs(self, *, asset_ids: Sequence[str] | None = None) -> dict:
        """Export complete sums for an explicit financial-asset view of this span.

        The full ledger retains connection payments/costs even when the supplied
        OperatingState contains only domestic financial assets. No absent asset
        is synthesized as zero. Coverage identifies a bounded span, not a claim
        that a complete annual investment boundary has been reached.
        """
        requested = self._asset_ids if asset_ids is None else tuple(asset_ids)
        if (len(set(requested)) != len(requested) or not set(requested) <= set(self._asset_ids)):
            raise ValueError("cashflow view requests unknown or duplicated ledger assets")
        fields = ("ahead_income_gbp_by_asset", "balancing_income_gbp_by_asset", "operating_cost_gbp_by_asset")
        result = {key: {name: self._cumulative[key][name] for name in requested} for key in fields}
        result["total_market_income_gbp_by_asset"] = {
            name: _number(result["ahead_income_gbp_by_asset"][name] + result["balancing_income_gbp_by_asset"][name],
                          f"total market income [{name}]") for name in requested}
        result["ledger_prefix_sha256"] = self._prefix_sha256
        result["period_coverage"] = self.coverage
        result["period_hours"] = PERIOD_HOURS
        return result

    def build_asset_accounts(self, state, policy: Mapping) -> dict:
        """Pass actual cumulative cashflow through the explicit policy gates.

        CM/decarbonization scenarios cannot obtain an implicit transfer amount;
        the existing source-grounded cashflow builder validates the policy maps.
        """
        from ...doctoral_ledgers import build_asset_accounts
        assets = state.get("assets") if isinstance(state, Mapping) else state.assets
        year = state.get("year") if isinstance(state, Mapping) else state.year
        if year is not None and year != self._initial_state.year:
            raise ValueError("cashflow state year differs from ledger year")
        ids = tuple(asset.get("asset_id") if isinstance(asset, Mapping) else asset.asset_id for asset in assets)
        return build_asset_accounts(self.doctoral_cashflow_inputs(asset_ids=ids), state, policy)
