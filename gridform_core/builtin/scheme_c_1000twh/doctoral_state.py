"""Serializable physical memory for the restored national doctoral model.

Source: simulation_model.py Battery/decay_func and generator mutable fields.
Declared correction D1-age: batch creation uses a monotonically increasing
half-hour index, never the annually reset array index. Stored energy here is
MWh; only the explicit source-boundary helpers use the source's MW-period
quantity. This is NOT the existing zonal runtime/checkpoint schema.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Mapping, Sequence

from ...v2.contracts import YearState

PHYSICAL_STATE_KEY = "doctoral_physical_state"
SCHEMA = "value.doctoral-national-physical-state/v1"
STORAGE_TECHNOLOGIES = frozenset({"battery", "1c_battery", "0.5c_battery",
                                 "0.25c_battery", "pumped_hydro", "hydrogen_battery"})
_DECAY = {"pumped_hydro": 0.000001, "hydrogen_battery": 0.000005}


def _nonnegative(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite nonnegative number")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"{name} must be a finite nonnegative number")
    return result


def _index(value: object, name: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return value


@dataclass(frozen=True)
class StorageBatch:
    charged_absolute_period: int
    stored_energy_mwh: float

    def __post_init__(self) -> None:
        _index(self.charged_absolute_period, "charged_absolute_period")
        _nonnegative(self.stored_energy_mwh, "stored_energy_mwh")

    def to_dict(self) -> dict[str, object]:
        return {"charged_absolute_period": self.charged_absolute_period,
                "stored_energy_mwh": self.stored_energy_mwh}

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> StorageBatch:
        if not isinstance(payload, Mapping) or set(payload) != {"charged_absolute_period", "stored_energy_mwh"}:
            raise ValueError("Incomplete or unsupported storage batch")
        return cls(**payload)


def decay_batches(batches: Sequence[StorageBatch], technology: str) -> tuple[StorageBatch, ...]:
    if technology not in STORAGE_TECHNOLOGIES:
        raise ValueError(f"Unknown doctoral storage technology {technology!r}")
    return tuple(replace(batch, stored_energy_mwh=batch.stored_energy_mwh *
                         (1 - _DECAY.get(technology, 0.000021))) for batch in batches)


def batch_bid_price(batch: StorageBatch, absolute_period: int, *, storage_fee: float,
                    per_storage_fee: float, bid_multiplier: float = 1.0) -> float:
    _index(absolute_period, "absolute_period")
    age = absolute_period - batch.charged_absolute_period
    if age < 0:
        raise ValueError("Cannot bid a future storage batch")
    return (age * _nonnegative(per_storage_fee, "per_storage_fee") +
            _nonnegative(storage_fee, "storage_fee")) * _nonnegative(bid_multiplier, "bid_multiplier")


def _half_hour(period_hours: float) -> float:
    if period_hours != 0.5:
        raise ValueError("Doctoral source quantity contract requires period_hours=0.5")
    return 0.5


def batches_from_source(stored_energy: Mapping[int, float], *, period_hours: float) -> tuple[StorageBatch, ...]:
    dt = _half_hour(period_hours)
    return tuple(StorageBatch(index, _nonnegative(energy, "source stored energy") * dt)
                 for index, energy in sorted(stored_energy.items()))


def batches_to_source(batches: Sequence[StorageBatch], *, period_hours: float) -> dict[int, float]:
    dt = _half_hour(period_hours)
    result = {batch.charged_absolute_period: batch.stored_energy_mwh / dt for batch in batches}
    if len(result) != len(batches):
        raise ValueError("Duplicate storage batch clock")
    return result


# Fields are the cross-period read/write set of the source classes. Static
# capacities, fees and ramp rates belong to the independently hashed fleet.
_GENERATOR_FIELDS = {
    "GasGenerator": {"real_gen_energy", "run_time", "if_curtail"},
    "NuclearGenerator": {"real_gen_energy", "run_time"},
    "WaterGenerator": {"real_gen_energy", "run_time", "energy_limit", "have_gen_energy"},
    "BiomassGenerator": {"real_gen_energy", "run_time", "energy_limit", "have_gen_energy"},
    "ExpensiverenewableGenerator": {"real_gen_energy", "run_time", "if_curtail"},
}


@dataclass(frozen=True)
class DoctoralRuntimeState:
    year: int
    next_period_index: int
    next_absolute_period: int
    storage_capacities_mwh: Mapping[str, float]
    storage_batches: Mapping[str, Sequence[StorageBatch]]
    generator_memory: Mapping[str, Mapping[str, object]]
    accepted_generator_ids: Sequence[str]
    schema_version: str = SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA:
            raise ValueError("Unsupported doctoral physical state schema; old checkpoints cannot be upgraded by editing JSON")
        _index(self.year, "year")
        _index(self.next_period_index, "next_period_index")
        _index(self.next_absolute_period, "next_absolute_period")
        if self.next_absolute_period < self.next_period_index:
            raise ValueError("Absolute clock precedes year-local clock")
        capacities = dict(self.storage_capacities_mwh)
        if set(capacities) != set(self.storage_batches):
            raise ValueError("Storage batches and capacities must contain exactly the same assets")
        batches = {}
        for asset_id, capacity in capacities.items():
            if not isinstance(asset_id, str) or not asset_id:
                raise ValueError("Invalid storage asset identity")
            _nonnegative(capacity, f"{asset_id} capacity")
            rows = tuple(self.storage_batches[asset_id])
            if any(not isinstance(row, StorageBatch) for row in rows):
                raise ValueError("Storage state requires typed batches")
            clocks = [row.charged_absolute_period for row in rows]
            if len(clocks) != len(set(clocks)):
                raise ValueError("Duplicate storage batch clock")
            if any(clock >= self.next_absolute_period for clock in clocks):
                raise ValueError("Uncommitted or future storage batch")
            if sum(row.stored_energy_mwh for row in rows) > float(capacity) + 1e-9:
                raise ValueError(f"Storage {asset_id} exceeds capacity; explicit energy disposition required")
            batches[asset_id] = tuple(sorted(rows, key=lambda row: row.charged_absolute_period))
        memory = {}
        for asset_id, fields in self.generator_memory.items():
            fields = dict(fields)
            kind = fields.get("kind")
            expected = _GENERATOR_FIELDS.get(kind)
            if expected is None or set(fields) != expected | {"kind"}:
                raise ValueError(f"Incomplete generator memory for {asset_id}: {kind}")
            for name, value in fields.items():
                if name == "kind":
                    continue
                if name == "if_curtail":
                    if type(value) is not bool:
                        raise ValueError("if_curtail must be boolean")
                else:
                    _nonnegative(value, f"{asset_id}.{name}")
            memory[asset_id] = MappingProxyType(fields)
        accepted = tuple(self.accepted_generator_ids)
        if len(accepted) != len(set(accepted)) or any(not isinstance(item, str) or not item for item in accepted):
            raise ValueError("Invalid accepted generator identities")
        object.__setattr__(self, "storage_capacities_mwh", MappingProxyType(capacities))
        object.__setattr__(self, "storage_batches", MappingProxyType(batches))
        object.__setattr__(self, "generator_memory", MappingProxyType(memory))
        object.__setattr__(self, "accepted_generator_ids", accepted)

    def storage_energy_mwh(self, asset_id: str) -> float:
        return sum(batch.stored_energy_mwh for batch in self.storage_batches[asset_id])

    def batch_age(self, batch: StorageBatch) -> int:
        return self.next_absolute_period - batch.charged_absolute_period

    def commit_period(self, *, storage_batches: Mapping[str, Sequence[StorageBatch]],
                      generator_memory: Mapping[str, Mapping[str, object]],
                      accepted_generator_ids: Sequence[str]) -> DoctoralRuntimeState:
        if self.next_period_index >= 17520:
            raise ValueError("Model year is complete at 17520 periods; advance the validated annual boundary")
        return replace(self, next_period_index=self.next_period_index + 1,
                       next_absolute_period=self.next_absolute_period + 1,
                       storage_batches=storage_batches, generator_memory=generator_memory,
                       accepted_generator_ids=accepted_generator_ids)

    def start_year(self, year: int, *, storage_capacities_mwh: Mapping[str, float]) -> DoctoralRuntimeState:
        if year != self.year + 1:
            raise ValueError("Physical state can advance exactly one year at a time")
        if self.next_period_index != 17520:
            raise ValueError("Cannot advance an incomplete model year: expected 17520 committed periods")
        for asset_id in set(self.storage_batches) - set(storage_capacities_mwh):
            if self.storage_energy_mwh(asset_id) > 1e-9:
                raise ValueError(f"Retired storage {asset_id} requires an explicit energy disposition")
        return replace(self, year=year, next_period_index=0,
                       storage_capacities_mwh=storage_capacities_mwh,
                       storage_batches={asset_id: self.storage_batches.get(asset_id, ())
                                        for asset_id in storage_capacities_mwh},
                       accepted_generator_ids=())

    def to_dict(self) -> dict[str, object]:
        return {"schema_version": self.schema_version, "year": self.year,
                "next_period_index": self.next_period_index, "next_absolute_period": self.next_absolute_period,
                "storage_capacities_mwh": dict(self.storage_capacities_mwh),
                "storage_batches": {key: [row.to_dict() for row in value] for key, value in self.storage_batches.items()},
                "generator_memory": {key: dict(value) for key, value in self.generator_memory.items()},
                "accepted_generator_ids": list(self.accepted_generator_ids)}

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> DoctoralRuntimeState:
        expected = {"schema_version", "year", "next_period_index", "next_absolute_period", "storage_capacities_mwh",
                    "storage_batches", "generator_memory", "accepted_generator_ids"}
        if not isinstance(payload, Mapping) or set(payload) != expected:
            raise ValueError("Incomplete or unsupported doctoral physical state")
        return cls(**{**payload, "storage_batches": {
            key: tuple(StorageBatch.from_dict(row) for row in rows)
            for key, rows in payload["storage_batches"].items()}})


def initialise_doctoral_state(state: YearState, *, initial_year: int = 2025) -> DoctoralRuntimeState:
    capacities = {asset.asset_id: float(asset.energy_capacity_mwh or 0)
                  for asset in state.assets if asset.technology in STORAGE_TECHNOLOGIES and asset.status != "retired"}
    payload = state.extensions.get(PHYSICAL_STATE_KEY)
    if payload is not None:
        restored = DoctoralRuntimeState.from_dict(payload)
        if restored.year != state.year or dict(restored.storage_capacities_mwh) != capacities:
            raise ValueError("Restored physical state does not match current year/fleet")
        if restored.next_absolute_period > 0:
            expected_generators = {asset.asset_id for asset in state.assets
                                   if asset.technology not in STORAGE_TECHNOLOGIES
                                   and asset.status != "retired" and asset.capacity_mw > 0}
            if set(restored.generator_memory) != expected_generators:
                raise ValueError("Incomplete generator memory for restored operating fleet")
            if not set(restored.accepted_generator_ids) <= expected_generators:
                raise ValueError("Unknown accepted generator identity")
        return restored
    if state.year != initial_year:
        raise ValueError("Later year is missing validated doctoral physical state")
    return DoctoralRuntimeState(state.year, 0, 0, capacities,
                               {asset_id: () for asset_id in capacities}, {}, ())
