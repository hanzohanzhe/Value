"""Explicit v1-to-v2 project parsing; saved projects are never reinterpreted."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

from .module_manifest import ModuleRegistryV2
from ..frontend_contract import validate_maturity_acknowledgements
from ..study_market_config import resolve_market_configuration


@dataclass(frozen=True)
class ProjectV2:
    id: str
    name: str
    data_pack_id: str
    start_year: int
    end_year: int
    modules: Mapping[str, str]
    parameter_overrides: Mapping[str, object]
    runtime_controls: Mapping[str, object]
    selected_extensions: Sequence[str] = field(default_factory=tuple)
    extension_parameters: Mapping[str, object] = field(default_factory=dict)
    maturity_acknowledgements: Mapping[str, str] = field(default_factory=dict)
    market_configuration: Mapping[str, object] = field(default_factory=dict)
    schema_version: str = "value.project/v2"
    migrated_from: str | None = None
    extensions: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "name": self.name,
            "data_pack_id": self.data_pack_id,
            "start_year": self.start_year,
            "end_year": self.end_year,
            "modules": dict(self.modules),
            "parameter_overrides": dict(self.parameter_overrides),
            "runtime_controls": dict(self.runtime_controls),
            "selected_extensions": list(self.selected_extensions),
            "extension_parameters": dict(self.extension_parameters),
            "maturity_acknowledgements": dict(self.maturity_acknowledgements),
            "market_configuration": dict(self.market_configuration),
            "migrated_from": self.migrated_from,
            "extensions": dict(self.extensions),
        }


def migrate_project_v1(payload: Mapping[str, object]) -> dict[str, object]:
    version = str(payload.get("schema_version") or "value.project/v1")
    if version != "value.project/v1":
        raise ValueError(f"Expected a v1 project, received {version}")
    known = {
        "schema_version", "id", "name", "data_pack_id", "start_year", "end_year",
        "modules", "parameters", "runtime_options", "updated_at",
        "selected_extensions", "extension_parameters", "maturity_acknowledgements",
        "market_configuration", "extensions",
    }
    explicit_extensions = payload.get("extensions") or {}
    if not isinstance(explicit_extensions, Mapping):
        raise ValueError("Project extensions must be an object")
    extensions = dict(explicit_extensions)
    extensions.update({key: value for key, value in payload.items() if key not in known})
    if "updated_at" in payload:
        extensions["v1_updated_at"] = payload["updated_at"]
    modules = dict(payload.get("modules") or {})  # type: ignore[arg-type]
    parameters = dict(payload.get("parameters") or {})  # type: ignore[arg-type]
    runtime = dict(payload.get("runtime_options") or {})  # type: ignore[arg-type]
    return {
        "schema_version": "value.project/v2",
        "id": str(payload.get("id") or "project"),
        "name": str(payload.get("name") or payload.get("id") or "Project"),
        "data_pack_id": str(payload.get("data_pack_id") or ""),
        "start_year": int(payload.get("start_year", 2025)),
        "end_year": int(payload.get("end_year", 2034)),
        "modules": modules,
        "parameter_overrides": parameters,
        "runtime_controls": runtime,
        "selected_extensions": list(payload.get("selected_extensions") or ()),
        "extension_parameters": dict(payload.get("extension_parameters") or {}),  # type: ignore[arg-type]
        "maturity_acknowledgements": dict(payload.get("maturity_acknowledgements") or {}),  # type: ignore[arg-type]
        "market_configuration": resolve_market_configuration(
            modules,
            parameters,
            runtime,
            dict(payload.get("market_configuration") or {}),  # type: ignore[arg-type]
        ),
        "migrated_from": "value.project/v1",
        "extensions": extensions,
    }


def parse_project(payload: Mapping[str, object], registry: ModuleRegistryV2) -> ProjectV2:
    version = str(payload.get("schema_version") or "value.project/v1")
    values = migrate_project_v1(payload) if version == "value.project/v1" else dict(payload)
    if values.get("schema_version") != "value.project/v2":
        raise ValueError(f"Unsupported project schema: {values.get('schema_version')}")
    modules = dict(values.get("modules") or {})  # type: ignore[arg-type]
    parameter_overrides = dict(values.get("parameter_overrides") or {})  # type: ignore[arg-type]
    runtime_controls = dict(values.get("runtime_controls") or {})  # type: ignore[arg-type]
    market_configuration = resolve_market_configuration(
        modules,
        parameter_overrides,
        runtime_controls,
        dict(values.get("market_configuration") or {}),  # type: ignore[arg-type]
    )
    project = ProjectV2(
        id=str(values["id"]),
        name=str(values["name"]),
        data_pack_id=str(values["data_pack_id"]),
        start_year=int(values["start_year"]),
        end_year=int(values["end_year"]),
        modules=modules,
        parameter_overrides=parameter_overrides,
        runtime_controls=runtime_controls,
        selected_extensions=tuple(str(item) for item in values.get("selected_extensions", ())),
        extension_parameters=dict(values.get("extension_parameters") or {}),  # type: ignore[arg-type]
        maturity_acknowledgements={
            str(key): str(value)
            for key, value in dict(values.get("maturity_acknowledgements") or {}).items()  # type: ignore[arg-type]
        },
        market_configuration=market_configuration,
        migrated_from=(str(values["migrated_from"]) if values.get("migrated_from") else None),
        extensions=dict(values.get("extensions") or {}),  # type: ignore[arg-type]
    )
    if project.end_year < project.start_year:
        raise ValueError("The end year cannot be earlier than the start year")
    registry.validate_selection(
        project.modules,
        selected_extensions=project.selected_extensions,
        extension_parameters=project.extension_parameters,
        # Full data readiness is enforced against the chosen pack at preflight.
        available_data_roles=tuple(
            role
            for extension_id in project.selected_extensions
            for role in (
                item.role
                for item in registry.extension_registry.manifest(extension_id).data_roles
            )
        ),
    )
    validate_maturity_acknowledgements(
        registry,
        project.modules,
        project.selected_extensions,
        project.maturity_acknowledgements,
    )
    return project
