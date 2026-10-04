"""Selected-graph resource estimates for staged VALUE zonal runs.

This module is operational protection.  It reads immutable contexts and never
changes a Study, a model state, the selected trace profile or the official RNG.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import random
import sqlite3
import tempfile
import time
import uuid
from contextlib import contextmanager
from dataclasses import replace
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence

from .module_context import RunStaticContext, YearContext, canonical_context_sha256
from .run_quota import QuotaUsage, RunQuotaPolicy, global_quota_reasons


GIB = 1024**3
CALIBRATION_KEY_SCHEMA_VERSION = "value.resource-calibration-key/v1"
CALIBRATION_SCHEMA_VERSION = "value.resource-calibration/v1"
PERSISTED_SAFETY_MULTIPLIER = 1.5
MAX_CALIBRATION_PERIODS = 48


@dataclass(frozen=True)
class ResourceHeadroomBounds:
    """Frozen expansion-policy cardinality bounds for resource protection.

    Values are maximum new commissioned rows admitted in each model year by
    the selected expansion/investment policy graph.  They are derived before
    calibration and are intentionally not editable Study fields.
    """

    source_modules: tuple[str, ...]
    annual_asset_additions: tuple[int, ...]
    annual_storage_additions: tuple[int, ...]

    def __post_init__(self) -> None:
        if len(self.annual_asset_additions) != len(self.annual_storage_additions):
            raise ValueError("Asset and storage headroom must cover the same years")
        if any(int(value) < 0 for value in (
            *self.annual_asset_additions, *self.annual_storage_additions
        )):
            raise ValueError("Resource headroom additions cannot be negative")

    @classmethod
    def empty(cls, years: int) -> "ResourceHeadroomBounds":
        return cls((), (0,) * years, (0,) * years)

    def to_dict(self) -> dict[str, object]:
        return {
            "source_modules": list(self.source_modules),
            "annual_asset_additions": list(self.annual_asset_additions),
            "annual_storage_additions": list(self.annual_storage_additions),
        }


def build_frozen_resource_contexts(
    *,
    project: Mapping[str, object],
    policy: Mapping[str, object],
    run_id: str,
    pack_root: Path,
    network_pack_root: Path,
    registry: object,
) -> tuple[RunStaticContext, YearContext, ResourceHeadroomBounds]:
    """Rebuild readiness solely from frozen production inputs and pure builders."""

    from .application import (
        DEFAULT_STORAGE_COST,
        DEFAULT_TRANSITION,
        _network_period_ids_for_year,
        _resolved_run,
        build_run_static_context,
    )
    from .canonical_psm_data import build_chronology, native_initial_state
    from .cem_investment_policy import investment_mode
    from .parameters import resolve_scheme_c_parameters
    from .v2.contracts import OperatingState, PSMInput
    from .v2.orchestrator import build_year_context, contract_hash
    from .zonal_contracts import load_zonal_network_pack
    from .zonal_pack_selection import resolve_zonal_pack_selection
    from .zonal_redispatch import ZonalRedispatchBalancing
    from .zonal_solver_contract import validate_solver_settings

    frozen_project = copy.deepcopy(dict(project))
    pack_root = Path(pack_root).resolve()
    network_pack_root = Path(network_pack_root).resolve()
    selected = dict(frozen_project.get("modules") or {})
    selected.setdefault("transition", DEFAULT_TRANSITION)
    psm_manifest = registry.manifest(str(selected["psm"]), expected_slot="psm")
    if "storage.bid-cost-function" in psm_manifest.requires_capabilities:
        selected.setdefault("storage_cost", DEFAULT_STORAGE_COST)
    runtime = dict(
        frozen_project.get("runtime_options")
        or frozen_project.get("runtime_controls") or {}
    )
    resolved_parameters = resolve_scheme_c_parameters(
        pack_root,
        frozen_project.get("parameters")
        or frozen_project.get("parameter_overrides") or {},
        runtime,
        periods_per_year=int(policy["periods_per_year"]),
    )
    pack_selection = resolve_zonal_pack_selection(
        frozen_project,
        base_pack_root=pack_root,
        explicit_network_pack_root=network_pack_root,
    )
    resolution_graph = registry.resolve_selection(
        selected,
        selected_extensions=tuple(
            str(item) for item in frozen_project.get("selected_extensions", ())
        ),
        extension_parameters=dict(frozen_project.get("extension_parameters") or {}),
        available_data_roles=pack_selection.available_data_roles,
    )
    balancing_manifest = resolution_graph.manifests_by_slot.get("balancing")
    solver = validate_solver_settings(
        frozen_project.get("solver_contract")
        or (balancing_manifest.solver_contract if balancing_manifest else {})
    )
    implementations = dict(resolution_graph.implementations_by_slot)
    implementations["balancing"] = ZonalRedispatchBalancing(solver)
    resolution_graph = replace(
        resolution_graph, implementations_by_slot=implementations
    )
    start_year = int(frozen_project.get("start_year") or 0)
    end_year = int(frozen_project.get("end_year") or start_year)
    resolved = _resolved_run(
        frozen_project, run_id, resolution_graph,
        resolved_parameters.scientific.values,
        resolved_parameters.runtime.values,
        {key: dict(value) for key, value in resolved_parameters.sources.items()},
        start_year, end_year,
    )
    pack_manifest_path = pack_root / "manifest.json"
    pack_manifest = json.loads(pack_manifest_path.read_text(encoding="utf-8"))
    network_manifest = json.loads(
        (network_pack_root / "manifest.json").read_text(encoding="utf-8")
    )
    network_pack = load_zonal_network_pack(network_pack_root, network_manifest)
    run_context = build_run_static_context(
        resolved=resolved,
        project=frozen_project,
        pack_manifest=pack_manifest,
        pack_manifest_sha256=hashlib.sha256(
            pack_manifest_path.read_bytes()
        ).hexdigest(),
        resolution_graph=resolution_graph,
        network_pack=network_pack,
    )
    initial = native_initial_state(
        pack_root, start_year,
        capital_discount_rate=float(
            resolved.scientific_parameters.get("cost.capital_discount_rate", 0.05)
            or 0.05
        ),
        scientific_parameters=resolved.scientific_parameters,
    )
    advanced = implementations["pipeline"].advance_year(resolved, initial)
    opening = advanced.operating_state
    chronology = build_chronology(
        pack_root, pack_manifest, opening,
        periods=int(policy["periods_per_year"]),
        period_hours=float(resolved.scientific_parameters["clock.period_hours"]),
        terminal_soc_rule=str(resolved.scientific_parameters.get(
            "market.perfect_foresight_terminal_soc_rule", "cyclic"
        )),
        voll_gbp_per_mwh=float(resolved.scientific_parameters.get(
            "market.voll_gbp_per_mwh", 10_000.0
        )),
    )
    chronology = replace(
        chronology,
        period_ids=_network_period_ids_for_year(
            network_pack.zonal_demand.period_ids,
            year=start_year,
            periods=int(policy["periods_per_year"]),
        ),
    )
    model_input = PSMInput(
        run_id, start_year, resolved.data_pack_id, opening,
        float(resolved.scientific_parameters["clock.period_hours"]),
        {**dict(resolved.scientific_parameters), **dict(resolved.runtime_controls)},
        chronology=chronology,
        extensions={"artifact_directory": "resource-readiness-only"},
    )
    balancing_identity = resolution_graph.identity("balancing")
    psm = implementations["psm"]
    psm.configure_run(
        output_dir=None,
        storage_cost=implementations["storage_cost"],
        balancing=implementations["balancing"],
        expected_balancing_identity=(
            balancing_identity.module_id, balancing_identity.module_version
        ),
        network_pack=network_pack,
        zonal_demand_mode=str(dict(
            frozen_project.get("market_configuration") or {}
        ).get("zonal_demand_mode") or ""),
        weather_spatializer_identity=(
            (
                resolution_graph.identity("weather_spatializer").module_id,
                resolution_graph.identity("weather_spatializer").module_version,
            ) if "weather_spatializer" in selected else None
        ),
        ledger_detail=run_context.trace_profile,
    )
    prepared, annual_metadata = psm.prepare_year_context(model_input)
    year_context = build_year_context(
        run_context=run_context,
        model_input=prepared,
        transition_lineage={
            "annual_input_state_sha256": contract_hash(initial),
            "planning_advance_sha256": contract_hash(advanced),
            "commissioned_project_ids": [
                item.project_id for item in advanced.commissioned_projects
            ],
            "active_project_ids": [
                item.project_id for item in advanced.active_projects
            ],
        },
        annual_metadata=annual_metadata,
    )
    groups: set[tuple[str, str, str]] = set()
    for asset in opening.assets:
        if asset.capacity_mw <= 0 or asset.status == "retired":
            continue
        extensions = dict(asset.extensions)
        owner = str(
            extensions.get("investment_owner_id")
            or extensions.get("source_agent_id")
            or ("" if asset.asset_id.startswith("commissioned:") else asset.asset_id)
        )
        if not owner or extensions.get("investment_eligible") is False:
            continue
        if investment_mode(asset.technology) in {"denied", "site_data_required"}:
            continue
        groups.add((owner, asset.technology, asset.region or "GB"))
    storage_technologies = {
        "1c_battery", "0.5c_battery", "0.25c_battery", "hydrogen_battery"
    }
    years = int(policy["years"])
    annual_assets = len(groups)
    annual_storage = sum(1 for _owner, tech, _region in groups if tech in storage_technologies)
    bounds = ResourceHeadroomBounds(
        source_modules=tuple(sorted(str(selected.get(slot) or "") for slot in (
            "vre_cap", "storage_cap", "investment"
        ) if selected.get(slot))),
        annual_asset_additions=(annual_assets,) * years,
        annual_storage_additions=(annual_storage,) * years,
    )
    return run_context, year_context, bounds


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        _json_plain(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _json_plain(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _json_plain(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_plain(item) for item in value]
    return value


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _require_sha256(value: str, field: str) -> str:
    text = str(value).lower()
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise ValueError(f"{field} must be a lowercase SHA-256")
    return text


@dataclass(frozen=True)
class ResourceCalibrationKey:
    data_fingerprint: str
    module_fingerprint: str
    solver_fingerprint: str
    clock_fingerprint: str
    trace_profile: str
    headroom_fingerprint: str = "0" * 64
    schema_version: str = CALIBRATION_KEY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != CALIBRATION_KEY_SCHEMA_VERSION:
            raise ValueError("Unsupported resource calibration-key schema")
        for field in (
            "data_fingerprint", "module_fingerprint", "solver_fingerprint",
            "clock_fingerprint",
            "headroom_fingerprint",
        ):
            object.__setattr__(self, field, _require_sha256(getattr(self, field), field))
        if self.trace_profile not in {"off", "summary", "full"}:
            raise ValueError("trace_profile must be off, summary or full")

    @classmethod
    def from_inputs(
        cls,
        *,
        project: Mapping[str, object],
        policy: Mapping[str, object],
        run_context: RunStaticContext,
        trace_profile: str,
        headroom_bounds: ResourceHeadroomBounds | None = None,
    ) -> "ResourceCalibrationKey":
        clock = {
            "start_year": run_context.start_year,
            "end_year": run_context.end_year,
            "period_hours": run_context.period_hours,
            "periods_per_year": int(policy.get("periods_per_year") or 0),
            "total_periods": int(policy.get("total_periods") or 0),
        }
        data = {
            "data_pack": run_context.data_pack,
            "network_pack": run_context.network_pack,
            "market_configuration": run_context.market_configuration,
        }
        modules = {
            "selected": dict(project.get("modules") or {}),
            "resolution_graph": run_context.module_graph,
        }
        return cls(
            data_fingerprint=_sha256(data),
            module_fingerprint=_sha256(modules),
            solver_fingerprint=_sha256(run_context.solver_contract),
            clock_fingerprint=_sha256(clock),
            trace_profile=str(trace_profile),
            headroom_fingerprint=_sha256(
                (headroom_bounds or ResourceHeadroomBounds.empty(
                    int(policy.get("years") or 0)
                )).to_dict()
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "data_fingerprint": self.data_fingerprint,
            "module_fingerprint": self.module_fingerprint,
            "solver_fingerprint": self.solver_fingerprint,
            "clock_fingerprint": self.clock_fingerprint,
            "trace_profile": self.trace_profile,
            "headroom_fingerprint": self.headroom_fingerprint,
        }

    @property
    def digest(self) -> str:
        return _sha256(self.to_dict())

    @property
    def cache_filename(self) -> str:
        return f"{self.digest}.json"


@dataclass(frozen=True)
class ResourceEstimate:
    persisted_bytes: int
    temporary_bytes: int
    reserve_bytes: int
    runtime_seconds: float
    trace_profile: str
    calibration_basis: Mapping[str, object]
    row_cardinality: Mapping[str, int]

    @property
    def required_bytes(self) -> int:
        return self.persisted_bytes + self.temporary_bytes + self.reserve_bytes

    def to_dict(self) -> dict[str, object]:
        return {
            "persisted_bytes": self.persisted_bytes,
            "temporary_bytes": self.temporary_bytes,
            "reserve_bytes": self.reserve_bytes,
            "required_bytes": self.required_bytes,
            "runtime_seconds": self.runtime_seconds,
            "trace_profile": self.trace_profile,
            "calibration_basis": dict(self.calibration_basis),
            "row_cardinality": dict(self.row_cardinality),
        }


def build_resource_estimation_contexts(
    *,
    project: Mapping[str, object],
    policy: Mapping[str, object],
    run_id: str,
    pack_manifest: Mapping[str, object],
    module_graph: Mapping[str, object],
    solver_contract: Mapping[str, object],
    network_pack: Mapping[str, object],
    scientific_parameters: Mapping[str, object],
    runtime_controls: Mapping[str, object],
) -> tuple[RunStaticContext, YearContext]:
    """Build deterministic estimate-only contexts from the selected graph.

    These objects are never published as official run/year contexts.  Their
    hashes bind the readiness calculation to the exact selected input graph.
    """

    requested_runtime = dict(
        project.get("runtime_options") or project.get("runtime_controls") or {}
    )
    trace = str(
        requested_runtime.get("runtime.market_trace_level")
        or dict(project.get("market_configuration") or {}).get("ledger_detail")
        or runtime_controls.get("runtime.market_trace_level")
        or "summary"
    )
    start_year = int(project.get("start_year") or 0)
    end_year = int(project.get("end_year") or start_year)
    period_hours = float(scientific_parameters.get("clock.period_hours") or 0.5)
    revision = str(project.get("revision_sha256") or "")
    if len(revision) != 64 or any(character not in "0123456789abcdef" for character in revision):
        revision = _sha256(project)
    run_context = RunStaticContext(
        run_id=str(run_id),
        study_revision_sha256=revision,
        start_year=start_year,
        end_year=end_year,
        period_hours=period_hours,
        data_pack={
            "data_pack_id": pack_manifest.get("id"),
            "manifest_sha256": _sha256(pack_manifest),
            "scientific_sha256": pack_manifest.get("scientific_sha256"),
        },
        module_graph=dict(module_graph),
        scientific_parameters=dict(scientific_parameters),
        runtime_controls=dict(runtime_controls),
        trace_profile=trace,
        solver_contract=dict(solver_contract),
        market_configuration=dict(project.get("market_configuration") or {}),
        network_pack=dict(network_pack),
    )
    assets: dict[str, dict[str, object]] = {}
    storage: dict[str, dict[str, object]] = {}
    zone_shares: dict[str, dict[str, float]] = {}
    resource_classes: dict[str, str] = {}
    mappings = network_pack.get("asset_mappings") or ()
    if isinstance(mappings, Sequence) and not isinstance(mappings, (str, bytes, bytearray)):
        for raw in mappings:
            if not isinstance(raw, Mapping):
                continue
            asset_id = str(raw.get("asset_id") or "")
            zone_id = str(raw.get("zone_id") or "")
            if not asset_id or not zone_id:
                continue
            asset_class = str(raw.get("asset_class") or "generator")
            technology = str(raw.get("technology") or asset_class)
            row = {
                "asset_id": asset_id,
                "asset_class": asset_class,
                "technology": technology,
                "zone": zone_id,
            }
            target = storage if asset_class == "storage" else assets
            target[asset_id] = row
            resource_classes[asset_id] = "storage" if asset_class == "storage" else technology
            zone_shares.setdefault(asset_id, {})[zone_id] = (
                zone_shares.setdefault(asset_id, {}).get(zone_id, 0.0)
                + float(raw.get("share") or 0.0)
            )
    year_context = YearContext(
        run_id=run_context.run_id,
        year=start_year,
        run_context_sha256=canonical_context_sha256(run_context),
        operating_state={
            "assets": assets,
            "storage": storage,
            "resource_class_by_asset": resource_classes,
            "resource_estimate_only": True,
        },
        frozen_zone_shares=zone_shares,
        opening_soc_mwh_by_asset={asset_id: 0.0 for asset_id in storage},
        transition_lineage={
            "resource_estimate_only": True,
            "policy": {
                "years": int(policy.get("years") or 0),
                "periods_per_year": int(policy.get("periods_per_year") or 0),
            },
        },
    )
    return run_context, year_context


def _cardinality(value: object) -> int:
    if isinstance(value, Mapping):
        return len(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return len(value)
    return 0


def _network_rows(network_pack: Mapping[str, object]) -> tuple[int, int]:
    zones = _cardinality(network_pack.get("zones"))
    boundaries = 0
    for key in ("boundaries", "corridors", "cutsets"):
        boundaries = max(boundaries, _cardinality(network_pack.get(key)))
    return zones, boundaries


def _selected_graph_cardinality(
    *,
    project: Mapping[str, object],
    policy: Mapping[str, object],
    run_context: RunStaticContext,
    year_context: YearContext,
    headroom_bounds: ResourceHeadroomBounds,
) -> dict[str, int]:
    network = dict(run_context.network_pack or {})
    zones, boundaries = _network_rows(network)
    state = dict(year_context.operating_state)
    assets = _cardinality(state.get("assets"))
    storage = _cardinality(state.get("storage"))
    if storage == 0:
        storage = len(year_context.opening_soc_mwh_by_asset)
    resource_classes = {
        str(value) for value in dict(state.get("resource_class_by_asset") or {}).values()
    }
    technologies = max(1, len(resource_classes))
    expansion_assets = sum(headroom_bounds.annual_asset_additions)
    expansion_storage = sum(headroom_bounds.annual_storage_additions)
    assets_max = assets + expansion_assets
    storage_max = storage + expansion_storage
    periods = int(policy.get("total_periods") or 0)
    years = int(policy.get("years") or (run_context.end_year - run_context.start_year + 1))
    if periods <= 0 or years <= 0:
        raise ValueError("Run policy must declare positive periods and years")
    if zones <= 0:
        raise ValueError("Selected zonal graph declares no zones")
    trace = run_context.trace_profile
    common = trace != "off"
    full = trace == "full"
    offers_per_period = assets_max * 3 + storage_max * 4
    return {
        "periods": periods,
        "years": years,
        "zones": zones,
        "boundaries": boundaries,
        "current_assets": assets,
        "expansion_headroom_assets": expansion_assets,
        "assets": assets_max,
        "current_storage_assets": storage,
        "expansion_headroom_storage_assets": expansion_storage,
        "storage_assets": storage_max,
        "technologies": technologies,
        "offers_per_period": offers_per_period if full else 0,
        "period_summary": periods if common else 0,
        "zone_period_summary": periods * zones if common else 0,
        "boundary_period_summary": periods * boundaries if common else 0,
        "dispatch_summary": periods * zones * technologies * 2 if common else 0,
        "storage_summary": periods * storage_max if common else 0,
        "redispatch_summary": periods * zones * technologies * 2 if common else 0,
        "orders": periods * offers_per_period if full else 0,
        "physical_dispatch": periods * assets_max * 2 if full else 0,
        "storage_state": periods * storage_max if full else 0,
        "redispatch_settlement": periods * offers_per_period if full else 0,
    }


def _valid_calibration(
    payload: object, key: ResourceCalibrationKey
) -> dict[str, object] | None:
    if not isinstance(payload, Mapping):
        return None
    if payload.get("schema_version") != CALIBRATION_SCHEMA_VERSION:
        return None
    if payload.get("calibration_key") != key.to_dict():
        return None
    try:
        periods = int(payload["periods"])
        persisted = float(payload["persisted_bytes_per_period"])
        temporary = float(payload["temporary_bytes_per_period"])
        seconds = float(payload["seconds_per_period"])
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    if not 1 <= periods <= MAX_CALIBRATION_PERIODS:
        return None
    if not all(math.isfinite(value) and value >= 0 for value in (persisted, temporary, seconds)):
        return None
    return dict(payload)


def _read_cache(path: Path, key: ResourceCalibrationKey) -> dict[str, object] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return _valid_calibration(payload, key)


def _default_calibration(request: Mapping[str, object]) -> dict[str, object]:
    """Measure isolated v8-shaped persistence without touching run state.

    The callback boundary permits the application to substitute its selected
    module/solver executor.  This fallback still measures real SQLite bytes and
    time in the isolated ledger instead of publishing a guessed Run artifact.
    """

    ledger_path = Path(request["ledger_path"])
    periods = int(request["periods"])
    rows = dict(request.get("row_cardinality") or {})
    started = time.perf_counter()
    with sqlite3.connect(ledger_path) as connection:
        connection.execute(
            "CREATE TABLE calibration_period(period INTEGER PRIMARY KEY, payload TEXT NOT NULL)"
        )
        per_period = {
            key: int(value) // max(1, int(rows.get("periods") or periods))
            for key, value in rows.items()
            if key not in {"periods", "years"}
        }
        payload = json.dumps(per_period, sort_keys=True, separators=(",", ":"))
        connection.executemany(
            "INSERT INTO calibration_period(period, payload) VALUES (?, ?)",
            ((period, payload) for period in range(periods)),
        )
        connection.commit()
    elapsed = max(time.perf_counter() - started, 1e-6)
    persisted = ledger_path.stat().st_size
    return {
        "periods": periods,
        "persisted_bytes": persisted,
        "temporary_bytes": persisted,
        "runtime_seconds": elapsed,
    }


def selected_staged_zonal_calibration_runner(
    *,
    project: Mapping[str, object],
    pack_root: Path,
    network_pack_root: Path,
    registry: object,
    isolation_executor: Callable[..., Mapping[str, object]] | None = None,
) -> Callable[[dict[str, object]], Mapping[str, object]]:
    """Return an isolated selected-module/solver 48-period calibration.

    It reuses the existing production PSM-only execution boundary.  That path
    constructs fresh state from frozen pack bytes, runs no CEM/transition and
    creates no checkpoint or official Run record.
    """

    frozen_project = copy.deepcopy(dict(project))
    frozen_pack_root = Path(pack_root).resolve()
    frozen_network_root = Path(network_pack_root).resolve()

    def run(request: dict[str, object]) -> Mapping[str, object]:
        for field in ("publish_run", "create_checkpoint", "advance_cem"):
            if request.get(field) is not False:
                raise ValueError(f"Selected calibration must deny {field}")
        opening = request.get("opening_state")
        private_rng = request.get("rng")
        if not isinstance(opening, Mapping):
            raise ValueError("Selected calibration requires a cloned opening state")
        if not isinstance(private_rng, random.Random):
            raise ValueError("Selected calibration requires a private RNG")
        cloned_opening = copy.deepcopy(dict(opening))
        rng_nonce = private_rng.getrandbits(64)
        if isolation_executor is not None:
            return isolation_executor(
                opening_state=cloned_opening,
                private_rng=private_rng,
                rng_nonce=rng_nonce,
                periods=int(request["periods"]),
                isolated_root=Path(request["isolated_root"]),
                publish_run=False,
                create_checkpoint=False,
                advance_cem=False,
            )
        from .application import (
            DEFAULT_STORAGE_COST,
            DEFAULT_TRANSITION,
            _network_period_ids_for_year,
        )
        from .canonical_psm_data import build_chronology
        from .module_context import ImmutableContextResolver
        from .parameters import resolve_scheme_c_parameters
        from .v2.contracts import OperatingState, PSMInput
        from .zonal_contracts import load_zonal_network_pack
        from .zonal_pack_selection import resolve_zonal_pack_selection
        from .zonal_redispatch import ZonalRedispatchBalancing
        from .zonal_solver_contract import validate_solver_settings

        calibration_project = copy.deepcopy(frozen_project)
        trace = str(dict(request["calibration_key"])["trace_profile"])
        runtime = dict(
            calibration_project.get("runtime_options")
            or calibration_project.get("runtime_controls")
            or {}
        )
        runtime["runtime.market_trace_level"] = trace
        calibration_project["runtime_options"] = runtime
        market = dict(calibration_project.get("market_configuration") or {})
        market["ledger_detail"] = trace
        calibration_project["market_configuration"] = market
        periods = int(request["periods"])
        start_year = int(calibration_project.get("start_year") or 0)
        selected = dict(calibration_project.get("modules") or {})
        selected.setdefault("transition", DEFAULT_TRANSITION)
        psm_manifest = registry.manifest(str(selected["psm"]), expected_slot="psm")
        if "storage.bid-cost-function" in psm_manifest.requires_capabilities:
            selected.setdefault("storage_cost", DEFAULT_STORAGE_COST)
        resolved_parameters = resolve_scheme_c_parameters(
            frozen_pack_root,
            calibration_project.get("parameters")
            or calibration_project.get("parameter_overrides")
            or {},
            runtime,
            periods_per_year=periods,
        )
        pack_selection = resolve_zonal_pack_selection(
            calibration_project,
            base_pack_root=frozen_pack_root,
            explicit_network_pack_root=frozen_network_root,
        )
        selected_extensions = tuple(
            str(item) for item in calibration_project.get("selected_extensions", ())
        )
        resolution_graph = registry.resolve_selection(
            selected,
            selected_extensions=selected_extensions,
            extension_parameters=dict(
                calibration_project.get("extension_parameters") or {}
            ),
            available_data_roles=pack_selection.available_data_roles,
        )
        balancing_manifest = resolution_graph.manifests_by_slot.get("balancing")
        if (
            balancing_manifest is None
            or balancing_manifest.id != "value-zonal-redispatch-balancing"
        ):
            raise ValueError("Calibration graph is not the selected zonal balancing graph")
        implementations = dict(resolution_graph.implementations_by_slot)
        implementations["balancing"] = ZonalRedispatchBalancing(
            validate_solver_settings(calibration_project.get("solver_contract"))
        )
        resolution_graph = replace(
            resolution_graph, implementations_by_slot=implementations
        )
        run_payload = request.get("run_context")
        if not isinstance(run_payload, Mapping):
            raise ValueError("Selected calibration requires the frozen run context")
        run_context = RunStaticContext.from_dict(copy.deepcopy(dict(run_payload)))
        year_context = YearContext.from_dict(cloned_opening)
        if year_context.run_context_sha256 != canonical_context_sha256(run_context):
            raise ValueError("Calibration opening state is not bound to its run context")
        state_payload = dict(year_context.operating_state)
        operating_state = OperatingState.from_dict({
            key: state_payload[key]
            for key in (
                "schema_version", "year", "assets",
                "active_planning_projects", "extensions",
            )
            if key in state_payload
        })
        pack_manifest = json.loads(
            (frozen_pack_root / "manifest.json").read_text(encoding="utf-8")
        )
        network_manifest = json.loads(
            (frozen_network_root / "manifest.json").read_text(encoding="utf-8")
        )
        network_pack = load_zonal_network_pack(
            frozen_network_root, network_manifest
        )
        chronology = build_chronology(
            frozen_pack_root, pack_manifest, operating_state,
            periods=periods,
            period_hours=run_context.period_hours,
            terminal_soc_rule=str(resolved_parameters.scientific.values.get(
                "market.perfect_foresight_terminal_soc_rule", "cyclic"
            )),
            voll_gbp_per_mwh=float(resolved_parameters.scientific.values.get(
                "market.voll_gbp_per_mwh", 10_000.0
            )),
        )
        chronology = replace(
            chronology,
            period_ids=_network_period_ids_for_year(
                network_pack.zonal_demand.period_ids,
                year=year_context.year,
                periods=periods,
            ),
        )
        model_input = PSMInput(
            run_context.run_id, year_context.year,
            str(run_context.data_pack["data_pack_id"]), operating_state,
            run_context.period_hours,
            {
                **dict(resolved_parameters.scientific.values),
                **dict(resolved_parameters.runtime.values),
                "resource_calibration_rng_nonce": rng_nonce,
            },
            chronology=chronology,
            extensions={"artifact_directory": "resource-calibration-only"},
        )
        output_dir = Path(request["isolated_root"]) / "selected-graph-output"
        output_dir.mkdir(parents=True, exist_ok=False)
        balancing_identity = resolution_graph.identity("balancing")
        psm = implementations["psm"]
        psm.configure_run(
            output_dir=output_dir,
            storage_cost=implementations["storage_cost"],
            balancing=implementations["balancing"],
            expected_balancing_identity=(
                balancing_identity.module_id, balancing_identity.module_version
            ),
            network_pack=network_pack,
            zonal_demand_mode=str(market.get("zonal_demand_mode") or ""),
            weather_spatializer_identity=(
                (
                    resolution_graph.identity("weather_spatializer").module_id,
                    resolution_graph.identity("weather_spatializer").module_version,
                ) if "weather_spatializer" in selected else None
            ),
            ledger_detail=trace,
        )
        resolver = ImmutableContextResolver(
            run_contexts=(run_context,), year_contexts=(year_context,),
            modules_by_slot=implementations,
        )
        psm.configure(run_context, resolver)
        psm.start_year(year_context)
        started = time.perf_counter()
        psm.run(model_input)
        runtime_seconds = time.perf_counter() - started
        if (output_dir / "checkpoints-v2").exists() or (
            output_dir / "partial-year-results"
        ).exists():
            raise RuntimeError("Isolated PSM calibration created annual recovery state")
        persisted_bytes = sum(
            path.stat().st_size for path in output_dir.rglob("*") if path.is_file()
        )
        database = output_dir / "market" / "market.sqlite"
        temporary_bytes = database.stat().st_size if database.is_file() else 0
        return {
            "periods": periods,
            "persisted_bytes": persisted_bytes,
            "temporary_bytes": temporary_bytes,
            "runtime_seconds": runtime_seconds,
        }

    return run


def _calibrate(
    *,
    key: ResourceCalibrationKey,
    run_context: RunStaticContext,
    year_context: YearContext,
    row_cardinality: Mapping[str, int],
    periods: int,
    calibration_root: Path,
    calibration_runner: Callable[[dict[str, object]], Mapping[str, object]] | None,
) -> dict[str, object]:
    runner = calibration_runner or _default_calibration
    with tempfile.TemporaryDirectory(
        prefix=".resource-calibration-", dir=calibration_root
    ) as folder:
        isolated_root = Path(folder)
        ledger_path = isolated_root / "market.sqlite"
        request: dict[str, object] = {
            "schema_version": "value.resource-calibration-request/v1",
            "calibration_key": key.to_dict(),
            "periods": periods,
            "run_context": copy.deepcopy(run_context.to_dict()),
            "opening_state": copy.deepcopy(year_context.to_dict()),
            "ledger_path": ledger_path,
            "isolated_root": isolated_root,
            "row_cardinality": dict(row_cardinality),
            "rng": random.Random(key.digest),
            "publish_run": False,
            "create_checkpoint": False,
            "advance_cem": False,
        }
        result = dict(runner(request))
        measured_periods = int(result.get("periods") or 0)
        if measured_periods != periods or measured_periods > MAX_CALIBRATION_PERIODS:
            raise ValueError("Calibration must measure exactly the bounded requested periods")
        persisted = int(result.get("persisted_bytes") or 0)
        temporary = int(result.get("temporary_bytes") or 0)
        runtime = float(result.get("runtime_seconds") or 0.0)
        if persisted < 0 or temporary < 0 or not math.isfinite(runtime) or runtime < 0:
            raise ValueError("Calibration returned invalid byte/time evidence")
        return {
            "schema_version": CALIBRATION_SCHEMA_VERSION,
            "calibration_key": key.to_dict(),
            "periods": periods,
            "persisted_bytes_per_period": persisted / periods,
            "temporary_bytes_per_period": temporary / periods,
            "seconds_per_period": runtime / periods,
        }


def _publish_cache(path: Path, payload: Mapping[str, object]) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    encoded = json.dumps(payload, indent=2, sort_keys=True, allow_nan=False)
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def _cache_lock(root: Path, key: ResourceCalibrationKey):
    lock_path = root / f".{key.digest}.lock"
    deadline = time.monotonic() + 10.0
    descriptor = None
    while descriptor is None:
        try:
            descriptor = os.open(
                lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
            )
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise RuntimeError("Timed out acquiring the resource calibration lock")
            time.sleep(0.01)
    try:
        os.write(descriptor, str(os.getpid()).encode("ascii"))
        os.fsync(descriptor)
        yield
    finally:
        os.close(descriptor)
        lock_path.unlink(missing_ok=True)


def _append_synthetic_rows(value: object, rows: Sequence[Mapping[str, object]]) -> object:
    if isinstance(value, Mapping):
        result = copy.deepcopy(dict(value))
        for row in rows:
            result[str(row["asset_id"])] = dict(row)
        return result
    existing = list(value) if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ) else []
    return [*copy.deepcopy(existing), *(dict(row) for row in rows)]


def _year_context_upper_bound_bytes(
    opening: YearContext,
    bounds: ResourceHeadroomBounds,
    *,
    years: int,
) -> list[int]:
    """Encode opening and annual fleet-growth upper contexts as publishers do."""

    sizes: list[int] = []
    cumulative_assets = 0
    cumulative_storage = 0
    for index in range(years):
        if index:
            cumulative_assets += int(bounds.annual_asset_additions[index - 1])
            cumulative_storage += int(bounds.annual_storage_additions[index - 1])
        payload = copy.deepcopy(opening.to_dict())
        payload["year"] = opening.year + index
        state = dict(payload.get("operating_state") or {})
        asset_rows = [
            {
                "asset_id": f"resource-headroom-asset-{item:08d}",
                "technology": "declared-expansion-upper-bound",
                "capacity_mw": 0.0,
                "status": "operational",
                "region": "declared-upper-bound-zone",
                "extensions": {"resource_estimate_only": True},
            }
            for item in range(cumulative_assets)
        ]
        storage_rows = [
            {
                "asset_id": f"resource-headroom-storage-{item:08d}",
                "technology": "declared-storage-upper-bound",
                "charge_power_mw": 0.0,
                "discharge_power_mw": 0.0,
                "energy_capacity_mwh": 0.0,
                "bid_contract": "convex_net_power_v1",
            }
            for item in range(cumulative_storage)
        ]
        state["assets"] = _append_synthetic_rows(state.get("assets"), asset_rows)
        state["storage"] = _append_synthetic_rows(state.get("storage"), storage_rows)
        classes = dict(state.get("resource_class_by_asset") or {})
        classes.update({str(row["asset_id"]): "expansion" for row in asset_rows})
        classes.update({str(row["asset_id"]): "storage" for row in storage_rows})
        state["resource_class_by_asset"] = classes
        payload["operating_state"] = state
        zone_shares = dict(payload.get("frozen_zone_shares") or {})
        zone_shares.update({
            str(row["asset_id"]): {"declared-upper-bound-zone": 1.0}
            for row in (*asset_rows, *storage_rows)
        })
        payload["frozen_zone_shares"] = zone_shares
        opening_soc = dict(payload.get("opening_soc_mwh_by_asset") or {})
        opening_soc.update({str(row["asset_id"]): 0.0 for row in storage_rows})
        payload["opening_soc_mwh_by_asset"] = opening_soc
        sizes.append(len(json.dumps(
            payload, indent=2, ensure_ascii=False, sort_keys=True
        ).encode("utf-8")))
    return sizes


def _production_run_context_bytes(
    context: RunStaticContext, calibration_root: Path
) -> int:
    """Measure the actual production run-context publisher byte stream once."""

    from .application import _atomic_json_artifact

    with tempfile.TemporaryDirectory(
        prefix=".resource-context-bytes-", dir=calibration_root
    ) as folder:
        path = _atomic_json_artifact(
            Path(folder) / "run-context.json", context.to_dict()
        )
        return len(path.read_bytes())


def estimate_run_resources(
    *,
    project: Mapping[str, object],
    policy: Mapping[str, object],
    run_context: RunStaticContext,
    year_context: YearContext,
    calibration_root: Path,
    free_bytes: int,
    quota_policy: RunQuotaPolicy,
    target_volume_bytes: int | None = None,
    calibration_runner: Callable[[dict[str, object]], Mapping[str, object]] | None = None,
    official_rng: object | None = None,
    headroom_bounds: ResourceHeadroomBounds | None = None,
) -> ResourceEstimate:
    """Estimate one selected staged/zonal graph without mutating its inputs."""

    del official_rng  # Deliberately never inspected or advanced.
    requested_runtime = dict(
        project.get("runtime_options") or project.get("runtime_controls") or {}
    )
    trace = str(
        requested_runtime.get("runtime.market_trace_level")
        or dict(project.get("market_configuration") or {}).get("ledger_detail")
        or run_context.trace_profile
    )
    if trace != run_context.trace_profile:
        raise ValueError("Requested trace profile does not match the immutable run context")
    modules = dict(project.get("modules") or {})
    if modules.get("psm") != "value-staged-bid-at-cost-psm" or modules.get(
        "balancing"
    ) != "value-zonal-redispatch-balancing":
        raise ValueError("Prompt122 resource estimates apply only to selected staged/zonal runs")
    years = int(policy.get("years") or (run_context.end_year - run_context.start_year + 1))
    headroom_bounds = headroom_bounds or ResourceHeadroomBounds.empty(years)
    if len(headroom_bounds.annual_asset_additions) != years:
        raise ValueError("Frozen expansion headroom must cover every model year")
    rows = _selected_graph_cardinality(
        project=project, policy=policy, run_context=run_context,
        year_context=year_context, headroom_bounds=headroom_bounds,
    )
    key = ResourceCalibrationKey.from_inputs(
        project=project, policy=policy, run_context=run_context, trace_profile=trace,
        headroom_bounds=headroom_bounds,
    )
    calibration_root = Path(calibration_root)
    calibration_root.mkdir(parents=True, exist_ok=True)
    cache_path = calibration_root / key.cache_filename
    source = "matching_cache"
    with _cache_lock(calibration_root, key):
        calibration = _read_cache(cache_path, key)
        if calibration is None:
            calibration_periods = min(MAX_CALIBRATION_PERIODS, rows["periods"])
            calibration = _calibrate(
                key=key,
                run_context=run_context,
                year_context=year_context,
                row_cardinality=rows,
                periods=calibration_periods,
                calibration_root=calibration_root,
                calibration_runner=calibration_runner,
            )
            _publish_cache(cache_path, calibration)
            source = "isolated_calibration"
    run_context_bytes = _production_run_context_bytes(run_context, calibration_root)
    year_context_bytes_by_year = _year_context_upper_bound_bytes(
        year_context, headroom_bounds, years=rows["years"]
    )
    year_context_bytes = year_context_bytes_by_year[0]
    fixed_context_bytes = run_context_bytes + sum(year_context_bytes_by_year)
    annual_artifact_bytes = years * 64 * 1024
    measured_persisted = math.ceil(
        float(calibration["persisted_bytes_per_period"]) * rows["periods"]
    )
    opening_assets = max(1, rows["current_assets"])
    opening_storage = rows["current_storage_assets"]
    opening_offers = opening_assets * 3 + opening_storage * 4
    maximum_offers = rows["assets"] * 3 + rows["storage_assets"] * 4
    growth_ratio = max(0.0, (maximum_offers - opening_offers) / max(1, opening_offers))
    headroom_persisted_delta = math.ceil(measured_persisted * growth_ratio)
    calibrated_temporary = math.ceil(
        float(calibration["temporary_bytes_per_period"])
        * min(MAX_CALIBRATION_PERIODS, rows["periods"])
    )
    headroom_temporary_delta = math.ceil(calibrated_temporary * growth_ratio)
    persisted = math.ceil(
        (fixed_context_bytes + annual_artifact_bytes + measured_persisted
         + headroom_persisted_delta)
        * PERSISTED_SAFETY_MULTIPLIER
    )
    temporary = calibrated_temporary + headroom_temporary_delta
    capacity = int(
        target_volume_bytes
        if target_volume_bytes is not None
        else project.get("target_volume_capacity_bytes") or max(int(free_bytes), 0)
    )
    reserve = max(10 * GIB, math.ceil(max(0, capacity) * 0.05))
    runtime = float(calibration["seconds_per_period"]) * rows["periods"]
    basis = {
        "schema_version": "value.resource-estimate-basis/v1",
        "source": source,
        "calibration_key": key.to_dict(),
        "calibration_periods": int(calibration["periods"]),
        "context_copies": 1,
        "run_context_bytes": run_context_bytes,
        "year_context_bytes": year_context_bytes,
        "year_context_bytes_by_year": year_context_bytes_by_year,
        "fixed_context_bytes": fixed_context_bytes,
        "headroom_bounds": headroom_bounds.to_dict(),
        "headroom_persisted_delta_bytes": headroom_persisted_delta,
        "headroom_temporary_delta_bytes": headroom_temporary_delta,
        "persisted_safety_multiplier": PERSISTED_SAFETY_MULTIPLIER,
        "quota_policy": {
            "schema_version": quota_policy.schema_version,
            "global_quota_bytes": quota_policy.global_quota_bytes,
            "per_run_quota_bytes": quota_policy.per_run_quota_bytes,
            "minimum_free_bytes": quota_policy.minimum_free_bytes,
        },
    }
    return ResourceEstimate(
        persisted_bytes=persisted,
        temporary_bytes=temporary,
        reserve_bytes=reserve,
        runtime_seconds=runtime,
        trace_profile=trace,
        calibration_basis=basis,
        row_cardinality=rows,
    )


def resource_readiness_from_snapshot(
    *,
    project: Mapping[str, object],
    policy: Mapping[str, object],
    run_id: str,
    snapshot_root: Path,
    registry: object,
    calibration_root: Path,
    selected_output_root: Path,
    free_bytes: int,
    quota_policy: RunQuotaPolicy,
    target_volume_bytes: int | None = None,
    calibration_runner: Callable[[dict[str, object]], Mapping[str, object]] | None = None,
    usage: QuotaUsage | None = None,
) -> tuple[ResourceEstimate, dict[str, object], dict[str, object]]:
    """Build authoritative readiness from the promoted immutable snapshot.

    ``usage`` (run_quota.quota_usage) applies the shared global quota rule.
    """

    from .run_snapshot import verify_run_input_snapshot

    snapshot_root = Path(snapshot_root).resolve()
    verify_run_input_snapshot(snapshot_root, registry)
    frozen_project = json.loads(
        (snapshot_root / "project.json").read_text(encoding="utf-8")
    )
    if frozen_project != dict(project):
        raise ValueError("Frozen project differs from the readiness project")
    network_root = snapshot_root / "network-pack"
    if not (network_root / "manifest.json").is_file():
        raise ValueError("Staged/zonal resource snapshot has no frozen network pack")
    run_context, year_context, headroom = build_frozen_resource_contexts(
        project=frozen_project,
        policy=policy,
        run_id=run_id,
        pack_root=snapshot_root / "pack",
        network_pack_root=network_root,
        registry=registry,
    )
    estimate = estimate_run_resources(
        project=frozen_project,
        policy=policy,
        run_context=run_context,
        year_context=year_context,
        calibration_root=calibration_root,
        free_bytes=free_bytes,
        quota_policy=quota_policy,
        target_volume_bytes=target_volume_bytes,
        calibration_runner=calibration_runner,
        headroom_bounds=headroom,
    )
    decision = evaluate_resource_gate(
        estimate,
        free_bytes=free_bytes,
        quota_policy=quota_policy,
        existing_run_bytes=usage.existing_run_bytes if usage is not None else 0,
        already_reserved_bytes=usage.outstanding_reserved_bytes if usage is not None else 0,
    )
    evidence = {
        "trace_profile": estimate.trace_profile,
        "run_context_sha256": canonical_context_sha256(run_context),
        "year_context_sha256": canonical_context_sha256(year_context),
        "calibration_key": dict(estimate.calibration_basis["calibration_key"]),
        "calibration_basis": dict(estimate.calibration_basis),
        "free_space_observation": {
            "free_bytes": int(free_bytes),
            "target_volume_capacity_bytes": target_volume_bytes,
        },
        "quota_decision": decision,
        "selected_output_root": str(Path(selected_output_root)),
        "estimate": estimate.to_dict(),
    }
    return estimate, decision, evidence


def evaluate_resource_gate(
    estimate: ResourceEstimate,
    *,
    free_bytes: int,
    quota_policy: RunQuotaPolicy,
    existing_run_bytes: int = 0,
    already_reserved_bytes: int = 0,
) -> dict[str, object]:
    """Return the hard, non-mutating quota/free-space decision."""

    estimated_output = estimate.persisted_bytes + estimate.temporary_bytes
    required_free = estimated_output + estimate.reserve_bytes
    reasons: list[str] = global_quota_reasons(
        QuotaUsage(int(existing_run_bytes), int(already_reserved_bytes), ()),
        estimated_output,
        quota_policy,
    )
    if int(free_bytes) < required_free or int(free_bytes) - required_free < quota_policy.minimum_free_bytes:
        reasons.append("free_space_reserve_not_satisfied")
    errors = []
    if reasons:
        errors.append({
            "code": "VALUE_PREFLIGHT_DISK_SPACE",
            "severity": "error",
            "scope": "output",
            "message": "Selected staged/zonal output does not fit the configured quota and free-space reserve.",
            "corrective_actions": ["Choose Summary", "Move output root", "Free space"],
        })
    return {
        "schema_version": "value.resource-gate-decision/v1",
        "accepted": not reasons,
        "required_bytes": required_free,
        "estimated_output_bytes": estimated_output,
        "required_free_bytes": required_free,
        "free_bytes": int(free_bytes),
        "trace_profile": estimate.trace_profile,
        "reason_codes": reasons,
        "errors": errors,
    }
