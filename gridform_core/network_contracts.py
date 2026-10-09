"""Solver-neutral VALUE network data and PSM contract family."""

from __future__ import annotations

import json
import math
import csv
from pathlib import Path
from dataclasses import dataclass, field
from typing import Mapping, Sequence

from .clearing_inputs import ClearingInputRow
from .v2.contracts import ChronologicalPSMData, JsonContract, StorageDispatchResource


NETWORK_INPUT_SCHEMA = "value.network-psm-input/v1"
NETWORK_OUTPUT_SCHEMA = "value.network-psm-output/v1"
# Every mapped asset's bus shares must sum to one (P1-01).  The tolerance is
# the same as the zonal asset-map reconciliation (zonal_contracts.py).
SHARE_SUM_TOLERANCE = 1e-9


class MultiBusMappingError(ValueError):
    """An asset is split across several buses where one bus is required."""


@dataclass(frozen=True)
class NetworkBus(JsonContract):
    bus_id: str
    voltage_kv: float
    region: str
    reference_eligible: bool = False
    is_reference: bool = False
    base_mva: float | None = None
    voltage_min_pu: float | None = None
    voltage_max_pu: float | None = None
    bus_type: str | None = None
    shunt_conductance_pu: float = 0.0
    shunt_susceptance_pu: float = 0.0
    schema_version: str = "value.network-bus/v1"


@dataclass(frozen=True)
class NetworkBranch(JsonContract):
    branch_id: str
    from_bus: str
    to_bus: str
    branch_type: str
    in_service: bool
    thermal_rating_mw: float
    reactance_pu: float | None = None
    resistance_pu: float | None = None
    charging_susceptance_pu: float | None = None
    tap_ratio: float | None = None
    phase_shift_degrees: float | None = None
    apparent_power_rating_mva: float | None = None
    circuits: int = 1
    provenance: Mapping[str, object] = field(default_factory=dict)
    schema_version: str = "value.network-branch/v1"


@dataclass(frozen=True)
class AssetBusMapping(JsonContract):
    asset_id: str
    bus_id: str
    asset_class: str
    share: float = 1.0
    schema_version: str = "value.network-asset-bus-map/v1"


@dataclass(frozen=True)
class NetworkTopology(JsonContract):
    buses: Sequence[NetworkBus]
    branches: Sequence[NetworkBranch]
    asset_mappings: Sequence[AssetBusMapping]
    base_mva: float
    schema_version: str = "value.network-topology/v1"
    provenance: Mapping[str, object] = field(default_factory=dict)

    def bus_by_id(self) -> dict[str, NetworkBus]:
        return {item.bus_id: item for item in self.buses}

    def mappings_by_asset(self) -> dict[str, tuple[AssetBusMapping, ...]]:
        """Every bus share of every asset, in declared row order."""

        result: dict[str, list[AssetBusMapping]] = {}
        for item in self.asset_mappings:
            result.setdefault(item.asset_id, []).append(item)
        return {asset: tuple(rows) for asset, rows in result.items()}

    def mapping_by_asset(self) -> dict[str, AssetBusMapping]:
        """The single bus of each asset; a split asset is an error, never a guess.

        Before P0-8 this silently kept the last row of a multi-bus asset and
        solvers then injected the whole asset there (P1-01).
        """

        result: dict[str, AssetBusMapping] = {}
        split: list[str] = []
        for asset, rows in self.mappings_by_asset().items():
            if len(rows) != 1:
                split.append(asset)
                continue
            result[asset] = rows[0]
        if split:
            raise MultiBusMappingError(
                "Assets are split across several buses and need a share-aware "
                "solver: " + ", ".join(sorted(split))
            )
        return result

    def islands(self) -> tuple[tuple[str, ...], ...]:
        adjacency = {item.bus_id: set() for item in self.buses}
        for branch in self.branches:
            if branch.in_service:
                adjacency[branch.from_bus].add(branch.to_bus)
                adjacency[branch.to_bus].add(branch.from_bus)
        remaining = set(adjacency)
        result = []
        while remaining:
            start = min(remaining)
            component, stack = set(), [start]
            while stack:
                bus = stack.pop()
                if bus in component:
                    continue
                component.add(bus)
                stack.extend(adjacency[bus].difference(component))
            remaining.difference_update(component)
            result.append(tuple(sorted(component)))
        return tuple(result)

    def validate(self, *, capability: str) -> None:
        if not self.buses or not math.isfinite(self.base_mva) or self.base_mva <= 0:
            raise ValueError("Network topology requires buses and a positive base MVA")
        bus_ids = [item.bus_id for item in self.buses]
        branch_ids = [item.branch_id for item in self.branches]
        if len(bus_ids) != len(set(bus_ids)):
            raise ValueError("Network topology contains duplicate bus IDs")
        if len(branch_ids) != len(set(branch_ids)):
            raise ValueError("Network topology contains duplicate branch IDs")
        if any(not item.bus_id or item.voltage_kv <= 0 for item in self.buses):
            raise ValueError("Network bus ID/voltage is invalid")
        known = set(bus_ids)
        for branch in self.branches:
            if branch.from_bus not in known or branch.to_bus not in known:
                raise ValueError(f"Branch {branch.branch_id} has a dangling endpoint")
            if branch.from_bus == branch.to_bus:
                raise ValueError(f"Branch {branch.branch_id} is a self-loop")
            if branch.branch_type not in {"ac_line", "dc_link", "transformer"}:
                raise ValueError(f"Branch {branch.branch_id} has unknown type")
            if branch.circuits < 1 or branch.thermal_rating_mw <= 0:
                raise ValueError(f"Branch {branch.branch_id} has invalid circuits/rating")
            if capability == "domain.network.dc" and branch.in_service:
                if branch.branch_type in {"ac_line", "transformer"} and (
                    branch.reactance_pu is None or not math.isfinite(branch.reactance_pu)
                    or abs(branch.reactance_pu) < 1e-12
                ):
                    raise ValueError(f"Branch {branch.branch_id} has invalid DC reactance")
            if capability == "domain.network.ac" and branch.in_service:
                if branch.reactance_pu is None or branch.resistance_pu is None:
                    raise ValueError(f"Branch {branch.branch_id} lacks AC impedance")
                if (
                    not math.isfinite(branch.reactance_pu)
                    or not math.isfinite(branch.resistance_pu)
                    or abs(complex(branch.resistance_pu, branch.reactance_pu)) < 1e-8
                ):
                    raise ValueError(f"Branch {branch.branch_id} has invalid AC impedance")
                if (
                    branch.apparent_power_rating_mva is None
                    or not math.isfinite(branch.apparent_power_rating_mva)
                    or branch.apparent_power_rating_mva <= 0
                ):
                    raise ValueError(f"Branch {branch.branch_id} lacks an AC MVA rating")
                if branch.tap_ratio is not None and branch.tap_ratio <= 0:
                    raise ValueError(f"Transformer {branch.branch_id} has invalid tap")
        for mapping in self.asset_mappings:
            if mapping.bus_id not in known or not mapping.asset_id:
                raise ValueError(f"Network asset map has dangling bus for {mapping.asset_id}")
            if mapping.asset_class not in {"generator", "storage", "boundary_import", "demand"}:
                raise ValueError(f"Network asset {mapping.asset_id} has invalid class")
            if (
                isinstance(mapping.share, bool)
                or not math.isfinite(float(mapping.share))
                or mapping.share <= 0
                or mapping.share > 1
            ):
                raise ValueError(f"Network asset {mapping.asset_id} has invalid share")
        for asset, rows in self.mappings_by_asset().items():
            buses = [row.bus_id for row in rows]
            if len(buses) != len(set(buses)):
                raise ValueError(f"Network asset {asset} maps to the same bus twice")
            if len({row.asset_class for row in rows}) != 1:
                raise ValueError(f"Network asset {asset} declares conflicting classes")
            total = math.fsum(float(row.share) for row in rows)
            if abs(total - 1.0) > SHARE_SUM_TOLERANCE:
                raise ValueError(
                    f"Network asset {asset} bus shares sum to {total!r}; "
                    "every asset's shares must sum to 1"
                )
        by_bus = self.bus_by_id()
        for island in self.islands():
            references = [bus for bus in island if by_bus[bus].is_reference]
            if len(references) != 1:
                raise ValueError(
                    "Every connected island requires exactly one declared reference bus; "
                    f"{island} has {len(references)}"
                )
            if not by_bus[references[0]].reference_eligible:
                raise ValueError(f"Reference bus {references[0]} is not reference-eligible")
        if capability == "domain.network.ac":
            for bus in self.buses:
                if bus.bus_type not in {"slack", "pv", "pq"}:
                    raise ValueError(f"AC bus {bus.bus_id} requires slack, pv or pq type")
                if bus.is_reference != (bus.bus_type == "slack"):
                    raise ValueError(f"AC reference identity is inconsistent at {bus.bus_id}")
                if (
                    bus.voltage_min_pu is None
                    or bus.voltage_max_pu is None
                    or not 0 < bus.voltage_min_pu <= bus.voltage_max_pu
                ):
                    raise ValueError(f"AC bus {bus.bus_id} lacks valid voltage bounds")


@dataclass(frozen=True)
class NetworkPSMInput(JsonContract):
    run_id: str
    year: int
    period_hours: float
    chronology: ChronologicalPSMData
    topology: NetworkTopology
    demand_mwh_by_bus: Mapping[str, Sequence[float]]
    capability: str
    information_structure: str
    schema_version: str = NETWORK_INPUT_SCHEMA
    contingency_ids: Sequence[str] = field(default_factory=tuple)
    extensions: Mapping[str, object] = field(default_factory=dict)

    def validate(self) -> None:
        self.topology.validate(capability=self.capability)
        if self.capability not in {"domain.network.dc", "domain.network.ac"}:
            raise ValueError(f"Unsupported network capability: {self.capability}")
        periods = len(self.chronology.period_ids)
        if self.period_hours <= 0 or periods == 0:
            raise ValueError("Network PSM input has an invalid clock")
        buses = set(self.topology.bus_by_id())
        if set(self.demand_mwh_by_bus) != buses:
            raise ValueError("Nodal demand must name every and only canonical bus")
        for bus, values in self.demand_mwh_by_bus.items():
            if len(values) != periods or any(not math.isfinite(value) or value < 0 for value in values):
                raise ValueError(f"Nodal demand at {bus} has invalid chronology")
        for period in range(periods):
            nodal = sum(float(values[period]) for values in self.demand_mwh_by_bus.values())
            base = float(self.chronology.demand_mwh[period])
            if abs(nodal - base) > max(1e-8, abs(base) * 1e-9):
                raise ValueError(
                    f"Nodal demand mismatch at period {period}: {nodal} versus base {base}"
                )
        mappings = {
            asset: rows[0] for asset, rows in self.topology.mappings_by_asset().items()
        }
        required = {item.asset_id for item in self.chronology.resources} | {
            item.asset_id for item in self.chronology.storage
        }
        missing = sorted(required.difference(mappings))
        if missing:
            raise ValueError("Unmapped network assets: " + ", ".join(missing))
        for resource in self.chronology.resources:
            expected = "boundary_import" if resource.resource_type == "import" else "generator"
            if mappings[resource.asset_id].asset_class != expected:
                raise ValueError(
                    f"Resource {resource.asset_id} must map as {expected}; external imports are not internal branches"
                )
            if resource.asset_id in {item.branch_id for item in self.topology.branches}:
                raise ValueError(f"Boundary/resource {resource.asset_id} is also counted as a branch")
        for storage in self.chronology.storage:
            if mappings[storage.asset_id].asset_class != "storage":
                raise ValueError(f"Storage {storage.asset_id} is not mapped as storage")


@dataclass(frozen=True)
class NetworkPeriodResult(JsonContract):
    period_id: str
    nodal_injection_mwh: Mapping[str, float]
    nodal_withdrawal_mwh: Mapping[str, float]
    branch_flow_mw: Mapping[str, float]
    blackout_mwh_by_bus: Mapping[str, float]
    curtailment_mwh_by_bus: Mapping[str, float]
    voltage_angle_radians: Mapping[str, float] | None = None
    nodal_price_gbp_per_mwh: Mapping[str, float] | None = None
    network_losses_mwh: float | None = None
    voltage_magnitude_pu: Mapping[str, float] | None = None
    reactive_injection_mvarh: Mapping[str, float] | None = None
    unsupported: Mapping[str, str] = field(default_factory=dict)
    residuals: Mapping[str, float] = field(default_factory=dict)
    schema_version: str = "value.network-period-result/v1"

    def to_dict(self) -> dict[str, object]:
        result = {
            "schema_version": self.schema_version, "period_id": self.period_id,
            "nodal_injection_mwh": dict(self.nodal_injection_mwh),
            "nodal_withdrawal_mwh": dict(self.nodal_withdrawal_mwh),
            "branch_flow_mw": dict(self.branch_flow_mw),
            "blackout_mwh_by_bus": dict(self.blackout_mwh_by_bus),
            "curtailment_mwh_by_bus": dict(self.curtailment_mwh_by_bus),
            "unsupported": dict(self.unsupported), "residuals": dict(self.residuals),
        }
        for name in (
            "voltage_angle_radians", "nodal_price_gbp_per_mwh", "network_losses_mwh",
            "voltage_magnitude_pu", "reactive_injection_mvarh",
        ):
            value = getattr(self, name)
            if value is not None:
                result[name] = dict(value) if isinstance(value, Mapping) else value
        return result


@dataclass(frozen=True)
class NetworkPSMOutput(JsonContract):
    run_id: str
    year: int
    module_id: str
    module_version: str
    capability: str
    solver_status: str
    information_structure: str
    periods: Sequence[NetworkPeriodResult]
    objective_gbp: float
    maximum_residual: float
    optimality_class: str
    schema_version: str = NETWORK_OUTPUT_SCHEMA
    extensions: Mapping[str, object] = field(default_factory=dict)


def network_clearing_input_row(
    network_input: NetworkPSMInput, *, period: int, stage: str = "network_dispatch"
) -> ClearingInputRow:
    network_input.validate()
    shares = network_input.topology.mappings_by_asset()
    payload = {
        "network_schema_version": network_input.schema_version,
        "capability": network_input.capability,
        "period_hours": network_input.period_hours,
        "period_id": network_input.chronology.period_ids[period],
        "buses": [item.to_dict() for item in network_input.topology.buses],
        "branches": [item.to_dict() for item in network_input.topology.branches],
        # Single-bus assets keep the historical one-bus form; the complete
        # share list (P1-01) is recorded for every asset.
        "asset_to_bus": {
            asset: rows[0].bus_id for asset, rows in sorted(shares.items()) if len(rows) == 1
        },
        "asset_bus_shares": {
            asset: [
                [row.bus_id, float(row.share)]
                for row in sorted(rows, key=lambda item: item.bus_id)
            ]
            for asset, rows in sorted(shares.items())
        },
        "nodal_demand_mwh": {
            bus: values[period] for bus, values in sorted(network_input.demand_mwh_by_bus.items())
        },
        "reference_buses": [item.bus_id for item in network_input.topology.buses if item.is_reference],
        "information_structure": network_input.information_structure,
    }
    return ClearingInputRow.create(
        year=network_input.year, period=period, stage=stage,
        information_scope=network_input.information_structure, payload=payload,
    )


def topology_from_dict(payload: Mapping[str, object]) -> NetworkTopology:
    return NetworkTopology(
        buses=tuple(NetworkBus.from_dict(item) for item in payload.get("buses", ())),  # type: ignore[arg-type]
        branches=tuple(NetworkBranch.from_dict(item) for item in payload.get("branches", ())),  # type: ignore[arg-type]
        asset_mappings=tuple(AssetBusMapping.from_dict(item) for item in payload.get("asset_mappings", ())),  # type: ignore[arg-type]
        base_mva=float(payload.get("base_mva", 100.0)),
        provenance=dict(payload.get("provenance") or {}),
    )


def load_network_input_from_pack(
    pack_root: Path,
    manifest: Mapping[str, object],
    chronology: ChronologicalPSMData,
    *,
    run_id: str,
    year: int,
    period_hours: float,
    capability: str,
    information_structure: str,
) -> NetworkPSMInput:
    bindings = dict(manifest.get("bindings") or {})

    def path_for(role: str) -> Path:
        binding = bindings.get(role)
        if not isinstance(binding, Mapping):
            raise ValueError(f"Network data role is not bound: {role}")
        path = (pack_root / str(binding.get("uri") or "")).resolve()
        try:
            path.relative_to(pack_root.resolve())
        except ValueError as exc:
            raise ValueError(f"Network binding escapes pack root: {role}") from exc
        if not path.is_file():
            raise ValueError(f"Network binding is missing: {role}")
        return path

    def json_rows(role: str, key: str) -> list[Mapping[str, object]]:
        value = json.loads(path_for(role).read_text(encoding="utf-8"))
        rows = value.get(key) if isinstance(value, Mapping) else value
        if not isinstance(rows, list) or not all(isinstance(item, Mapping) for item in rows):
            raise ValueError(f"Network role {role} must contain a {key} array")
        return rows

    buses = tuple(
        NetworkBus.from_dict(item) for item in json_rows("value.network.buses", "buses")
    )
    branches = tuple(
        NetworkBranch.from_dict(item)
        for item in json_rows("value.network.branches", "branches")
    )
    mappings = tuple(
        AssetBusMapping.from_dict(item)
        for item in json_rows("value.network.asset-map", "asset_mappings")
    )
    demand_path = path_for("value.network.nodal-demand")
    by_bus = {bus.bus_id: {} for bus in buses}
    with demand_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            bus_id = str(row.get("bus_id") or "")
            period_id = str(row.get("period_id") or "")
            if bus_id not in by_bus:
                raise ValueError(f"Nodal demand has unknown bus {bus_id}")
            if period_id in by_bus[bus_id]:
                raise ValueError(f"Nodal demand duplicates {bus_id}/{period_id}")
            by_bus[bus_id][period_id] = float(row["demand_mwh"])
    nodal = {
        bus: tuple(values.get(period_id, float("nan")) for period_id in chronology.period_ids)
        for bus, values in by_bus.items()
    }
    base_mva = float(
        next((bus.base_mva for bus in buses if bus.base_mva is not None), 100.0)
    )
    model_input = NetworkPSMInput(
        run_id, year, period_hours, chronology,
        NetworkTopology(
            buses, branches, mappings, base_mva,
            provenance={
                "data_pack_id": manifest.get("id"),
                "roles": [
                    "value.network.buses", "value.network.branches",
                    "value.network.asset-map", "value.network.nodal-demand",
                ],
            },
        ),
        nodal, capability, information_structure,
    )
    model_input.validate()
    return model_input
