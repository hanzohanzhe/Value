"""Run-scoped boundary for the preserved Scheme C compatibility session."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import threading
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from ...data import load_data_pack, required_uri
from ...errors import CompatibilityError
from ...parameters import SchemeCLegacyParameterAdapter


ROLE_TO_CONFIG_KEY = {
    "demand.forecast": "forecast_demand",
    "demand.real": "real_demand",
    "market.france.profile": "france_profile",
    "market.france.price": "france_price",
    "market.belgium.profile": "belgium_profile",
    "market.belgium.price": "belgium_price",
    "market.netherlands.profile": "netherlands_profile",
    "market.netherlands.price": "netherlands_price",
    "market.norway.profile": "norway_profile",
    "market.norway.price": "norway_price",
    "market.ireland.profile": "ireland_profile",
    "market.ireland.price": "ireland_price",
    "profiles.vre_solar": "vre_solar_profile",
    "profiles.vre_onshore": "vre_onshore_profile",
    "profiles.vre_offshore": "vre_offshore_profile",
    "weather.solar": "solar_weather",
    "weather.wind": "wind_weather",
}

REFERENCE_NAMED_INPUTS = {
    "source.repd_raw": "repd-q2-jul-2025.csv",
    "policy.support": "mechansim cost.xlsx",
    "planning.success_rates": "regional_technology_success_rates.csv",
}

CONFIG_ATTRIBUTES = (
    "generators",
    "batteries",
    "connections",
    "electrolyzer",
    "locations",
    "investment_parameters",
    "investment_methodology_external",
    "capital_costs_per_mw",
    "simulation_parameters",
    "file_paths",
)

_LEGACY_SESSION_LOCK = threading.Lock()


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return copy.deepcopy(value)


def _identity_hash(payload: Mapping[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class SchemeCRunContext:
    run_id: str
    project_id: str
    start_year: int
    end_year: int
    periods: int
    scenario_id: str
    pack_root: Path
    output_dir: Path
    reference_work_dir: Path
    module_ids: Mapping[str, str]
    data_bindings: Mapping[str, str]
    legacy_config: Mapping[str, object]
    environment: Mapping[str, str]
    scientific_parameters: Mapping[str, object]
    runtime_options: Mapping[str, object]
    context_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "pack_root", self.pack_root.resolve())
        object.__setattr__(self, "output_dir", self.output_dir.resolve())
        object.__setattr__(self, "reference_work_dir", self.reference_work_dir.resolve())
        object.__setattr__(self, "module_ids", _freeze(self.module_ids))
        object.__setattr__(self, "data_bindings", _freeze(self.data_bindings))
        object.__setattr__(self, "legacy_config", _freeze(self.legacy_config))
        object.__setattr__(self, "environment", _freeze(self.environment))
        object.__setattr__(self, "scientific_parameters", _freeze(self.scientific_parameters))
        object.__setattr__(self, "runtime_options", _freeze(self.runtime_options))
        object.__setattr__(self, "context_sha256", _identity_hash(self.identity_payload()))

    def identity_payload(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "project_id": self.project_id,
            "years": [self.start_year, self.end_year],
            "periods": self.periods,
            "scenario_id": self.scenario_id,
            "pack_root": str(self.pack_root),
            "output_dir": str(self.output_dir),
            "reference_work_dir": str(self.reference_work_dir),
            "module_ids": _thaw(self.module_ids),
            "data_bindings": _thaw(self.data_bindings),
            "legacy_config": _thaw(self.legacy_config),
            "environment": _thaw(self.environment),
            "scientific_parameters": _thaw(self.scientific_parameters),
            "runtime_options": _thaw(self.runtime_options),
        }

    def to_manifest(self) -> dict[str, object]:
        return {
            "schema_version": "force.scheme-c-run-context/v1",
            "context_sha256": self.context_sha256,
            **self.identity_payload(),
        }


def stage_reference_named_inputs(pack_root: Path, output_dir: Path) -> Path:
    """Stage fixed legacy names only inside a reference session directory."""

    pack = load_data_pack(pack_root)
    work = output_dir.resolve() / "reference-session-inputs"
    work.mkdir(parents=True, exist_ok=True)
    for role, filename in REFERENCE_NAMED_INPUTS.items():
        shutil.copy2(required_uri(pack, role), work / filename)
    return work


def build_scheme_c_run_context(
    *,
    run_id: str,
    project_id: str,
    start_year: int,
    end_year: int,
    periods: int,
    scenario_id: str,
    pack_root: Path,
    output_dir: Path,
    reference_work_dir: Path,
    module_ids: Mapping[str, str],
    scientific_parameters: Mapping[str, object],
    runtime_options: Mapping[str, object],
    environment: Mapping[str, str],
) -> SchemeCRunContext:
    pack = load_data_pack(pack_root)
    bindings = {role: required_uri(pack, role) for role in sorted(pack.datasets)}
    # Weather bindings are resolved before any compatibility module import.
    for role in ("weather.solar", "weather.wind"):
        required_uri(pack, role)
    fleet = json.loads(Path(required_uri(pack, "fleet.generators")).read_text(encoding="utf-8"))
    model = json.loads(Path(required_uri(pack, "config.model_parameters")).read_text(encoding="utf-8"))
    costs = json.loads(Path(required_uri(pack, "costs.capital")).read_text(encoding="utf-8"))
    file_paths = {
        key: required_uri(pack, role) for role, key in ROLE_TO_CONFIG_KEY.items()
    }
    simulation_parameters = dict(model["simulation_parameters"])
    simulation_parameters.update({
        "periods": int(periods),
        "solar_data": required_uri(pack, "weather.solar"),
        "wind_data": required_uri(pack, "weather.wind"),
    })
    config = {
        "generators": fleet["generators"],
        "batteries": fleet["batteries"],
        "connections": fleet["connections"],
        "electrolyzer": fleet["electrolyzer"],
        "locations": fleet["locations"],
        "investment_parameters": model["investment_parameters"],
        "investment_methodology_external": model["investment_methodology_external"],
        "capital_costs_per_mw": costs["capital_costs_per_mw"],
        "simulation_parameters": simulation_parameters,
        "file_paths": file_paths,
    }
    return SchemeCRunContext(
        run_id=run_id,
        project_id=project_id,
        start_year=start_year,
        end_year=end_year,
        periods=periods,
        scenario_id=scenario_id,
        pack_root=pack_root,
        output_dir=output_dir,
        reference_work_dir=reference_work_dir,
        module_ids=module_ids,
        data_bindings=bindings,
        legacy_config=config,
        environment=environment,
        scientific_parameters=scientific_parameters,
        runtime_options=runtime_options,
    )


def persist_or_verify_context(context: SchemeCRunContext) -> Path:
    """Write the frozen context once and reject changed resume inputs."""

    path = context.output_dir / "scheme-c-run-context.json"
    if path.is_file():
        previous = json.loads(path.read_text(encoding="utf-8"))
        if previous.get("context_sha256") != context.context_sha256:
            raise CompatibilityError(
                "Scheme C run context changed after the run/checkpoint was created. "
                "Resume requires the original frozen project, data, modules and parameters."
            )
        return path
    temporary = path.with_suffix(".json.incomplete")
    temporary.write_text(
        json.dumps(context.to_manifest(), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    os.replace(temporary, path)
    return path


class LegacyConfigSession:
    """The only allowlisted mutable-global boundary for compatibility execution."""

    def __init__(
        self,
        context: SchemeCRunContext,
        parameter_adapter: SchemeCLegacyParameterAdapter,
        runtime: object,
        environment_overrides: Mapping[str, str] | None = None,
    ) -> None:
        self.context = context
        self.parameter_adapter = parameter_adapter
        self.runtime = runtime
        self.environment = {
            **{str(key): str(value) for key, value in context.environment.items()},
            **{
                str(key): str(value)
                for key, value in (environment_overrides or {}).items()
            },
        }
        self._entered = False
        self._config_before: dict[str, object] = {}
        self._environment_before: dict[str, str | None] = {}
        self._cwd_before: Path | None = None
        self._runtime_before: object | None = None

    def __enter__(self) -> "LegacyConfigSession":
        if self._entered or not _LEGACY_SESSION_LOCK.acquire(blocking=False):
            raise CompatibilityError(
                "A Scheme C legacy config session is already active in this interpreter. "
                "Reference runs must use isolated processes."
            )
        self._entered = True
        try:
            from .runtime_compat import config, module_context

            self._cwd_before = Path.cwd()
            self._environment_before = {
                key: os.environ.get(key) for key in self.environment
            }
            self._config_before = {
                name: copy.deepcopy(getattr(config, name)) for name in CONFIG_ATTRIBUTES
            }
            self._runtime_before = getattr(module_context, "_runtime", None)
            for key, value in self.environment.items():
                os.environ[key] = value
            os.chdir(self.context.reference_work_dir)
            for name, value in self.context.legacy_config.items():
                setattr(config, name, _thaw(value))
            self.parameter_adapter.apply_config(config)
            module_context.configure_runtime(self.runtime)
            return self
        except Exception:
            self._restore()
            raise

    def _restore(self) -> None:
        try:
            from .runtime_compat import config, module_context

            for name, value in self._config_before.items():
                setattr(config, name, value)
            setattr(module_context, "_runtime", self._runtime_before)
            for key, value in self._environment_before.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            if self._cwd_before is not None:
                os.chdir(self._cwd_before)
        finally:
            if self._entered:
                self._entered = False
                _LEGACY_SESSION_LOCK.release()

    def __exit__(self, exc_type, exc, traceback) -> None:
        self._restore()
        manifest = {
            "schema_version": "force.legacy-config-session/v1",
            "context_sha256": self.context.context_sha256,
            "mutated_config_attributes": list(CONFIG_ATTRIBUTES),
            "mutated_environment_keys": sorted(self.environment),
            "private_working_directory": str(self.context.reference_work_dir),
            "restored": True,
            "outcome": "failed" if exc_type else "completed",
        }
        (self.context.output_dir / "legacy-config-session.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )
