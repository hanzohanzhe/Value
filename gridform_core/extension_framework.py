"""Versioned, fail-closed VALUE domain-extension contracts.

This module deliberately contains no power-system equations.  It extends the
single workspace registry with typed capability, conditional-data, parameter,
state, artifact and lifecycle declarations while preserving the v2 path when no
extension is selected.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping, Sequence

from .module_quarantine import (
    ExtensionHookImportError,
    cached_hook_failure,
    record_hook_failure,
    record_hook_quarantine,
)


EXTENSION_SCHEMA = "value.extension-bundle/v1"
EXTENSION_STATE_SCHEMA = "value.extension-state/v1"
EXTENSION_ARTIFACT_SCHEMA = "value.extension-artifact/v1"
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?$")
NAMESPACE = re.compile(r"^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)+$")
HOOKS = (
    "preflight", "initialize", "before_psm", "after_psm", "before_cem",
    "after_cem", "transition", "finalize",
)
SAFE_JSON_TYPES = {"boolean", "integer", "number", "string"}


def canonical_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class ConditionalDataRole:
    role: str
    capability: str
    group: str
    label: str
    formats: Sequence[str]
    required: bool = True
    unit: str | None = None
    time_semantics: str | None = None
    coordinate_semantics: str | None = None
    adapter_contract: str = "value.data-adapter/v1"
    validation_rules: Mapping[str, object] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "ConditionalDataRole":
        payload = dict(value)
        if "extension_role" in payload:
            if payload.pop("extension_role") is not True:
                raise ValueError("extension_role projection marker must be true")
        payload["formats"] = tuple(str(item) for item in value.get("formats", ()))
        payload["validation_rules"] = dict(value.get("validation_rules") or {})
        return cls(**payload)  # type: ignore[arg-type]

    def to_dataset_slot(self) -> dict[str, object]:
        result: dict[str, object] = {
            "role": self.role, "capability": self.capability, "group": self.group,
            "label": self.label, "formats": list(self.formats), "required": self.required,
            "extension_role": True, "adapter_contract": self.adapter_contract,
            "validation_rules": dict(self.validation_rules),
        }
        if self.unit is not None:
            result["unit"] = self.unit
        if self.time_semantics is not None:
            result["time_semantics"] = self.time_semantics
        if self.coordinate_semantics is not None:
            result["coordinate_semantics"] = self.coordinate_semantics
        return result


@dataclass(frozen=True)
class ParameterDeclaration:
    name: str
    value_type: str
    default: object
    title: str
    description: str
    visibility: str = "advanced"
    unit: str | None = None
    minimum: float | None = None
    maximum: float | None = None
    enum: Sequence[object] = field(default_factory=tuple)

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "ParameterDeclaration":
        payload = dict(value)
        payload["enum"] = tuple(value.get("enum") or ())
        return cls(**payload)  # type: ignore[arg-type]

    def validate_schema(self) -> None:
        if not NAMESPACE.fullmatch(self.name):
            raise ValueError(f"Unsafe extension parameter name: {self.name}")
        if self.value_type not in SAFE_JSON_TYPES:
            raise ValueError(f"Parameter {self.name} has unsupported JSON type {self.value_type}")
        if self.visibility not in {"basic", "advanced"}:
            raise ValueError(f"Parameter {self.name} has invalid visibility")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError(f"Parameter {self.name} has minimum above maximum")
        self.validate_value(self.default)

    def validate_value(self, value: object) -> object:
        valid_type = {
            "boolean": isinstance(value, bool),
            "integer": isinstance(value, int) and not isinstance(value, bool),
            "number": isinstance(value, (int, float)) and not isinstance(value, bool),
            "string": isinstance(value, str),
        }[self.value_type]
        if not valid_type:
            raise ValueError(f"Parameter {self.name} expects {self.value_type}")
        if self.enum and value not in self.enum:
            raise ValueError(f"Parameter {self.name} is not in its declared enum")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if self.minimum is not None and value < self.minimum:
                raise ValueError(f"Parameter {self.name} is below {self.minimum}")
            if self.maximum is not None and value > self.maximum:
                raise ValueError(f"Parameter {self.name} is above {self.maximum}")
        return value

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name, "value_type": self.value_type, "default": self.default,
            "title": self.title, "description": self.description,
            "visibility": self.visibility, "unit": self.unit, "minimum": self.minimum,
            "maximum": self.maximum, "enum": list(self.enum),
        }


@dataclass(frozen=True)
class ArtifactDeclaration:
    artifact_type: str
    media_type: str
    schema_version: str
    summary_fields: Sequence[str] = field(default_factory=tuple)

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "ArtifactDeclaration":
        payload = dict(value)
        payload["summary_fields"] = tuple(str(item) for item in value.get("summary_fields", ()))
        return cls(**payload)  # type: ignore[arg-type]


@dataclass(frozen=True)
class HookDeclaration:
    hook: str
    implementation: str
    before: Sequence[str] = field(default_factory=tuple)
    after: Sequence[str] = field(default_factory=tuple)

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "HookDeclaration":
        payload = dict(value)
        payload["before"] = tuple(str(item) for item in value.get("before", ()))
        payload["after"] = tuple(str(item) for item in value.get("after", ()))
        return cls(**payload)  # type: ignore[arg-type]


@dataclass(frozen=True)
class ExtensionManifest:
    id: str
    name: str
    version: str
    licence: str
    namespace: str
    provided_capabilities: Sequence[str]
    required_capabilities: Sequence[str] = field(default_factory=tuple)
    composed_module_ids: Sequence[str] = field(default_factory=tuple)
    data_roles: Sequence[ConditionalDataRole] = field(default_factory=tuple)
    parameters: Sequence[ParameterDeclaration] = field(default_factory=tuple)
    artifacts: Sequence[ArtifactDeclaration] = field(default_factory=tuple)
    hooks: Sequence[HookDeclaration] = field(default_factory=tuple)
    state_schema_version: str | None = None
    state_migrations: Mapping[str, str] = field(default_factory=dict)
    required_value_version: str = ">=0.5.0"
    required_contract_versions: Mapping[str, str] = field(default_factory=dict)
    member_inventory: Sequence[Mapping[str, object]] = field(default_factory=tuple)
    schema_version: str = EXTENSION_SCHEMA
    maturity: str = "experimental"

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "ExtensionManifest":
        payload = dict(value)
        for key in ("provided_capabilities", "required_capabilities", "composed_module_ids"):
            payload[key] = tuple(str(item) for item in value.get(key, ()))
        payload["data_roles"] = tuple(
            ConditionalDataRole.from_dict(item) for item in value.get("data_roles", ())  # type: ignore[arg-type]
        )
        payload["parameters"] = tuple(
            ParameterDeclaration.from_dict(item) for item in value.get("parameters", ())  # type: ignore[arg-type]
        )
        payload["artifacts"] = tuple(
            ArtifactDeclaration.from_dict(item) for item in value.get("artifacts", ())  # type: ignore[arg-type]
        )
        payload["hooks"] = tuple(
            HookDeclaration.from_dict(item) for item in value.get("hooks", ())  # type: ignore[arg-type]
        )
        payload["state_migrations"] = dict(value.get("state_migrations") or {})
        payload["required_contract_versions"] = dict(value.get("required_contract_versions") or {})
        payload["member_inventory"] = tuple(dict(item) for item in value.get("member_inventory", ()))  # type: ignore[arg-type]
        return cls(**payload)  # type: ignore[arg-type]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version, "id": self.id, "name": self.name,
            "version": self.version, "licence": self.licence, "namespace": self.namespace,
            "provided_capabilities": list(self.provided_capabilities),
            "required_capabilities": list(self.required_capabilities),
            "composed_module_ids": list(self.composed_module_ids),
            "data_roles": [item.to_dataset_slot() for item in self.data_roles],
            "parameters": [item.to_dict() for item in self.parameters],
            "artifacts": [dict(item.__dict__) for item in self.artifacts],
            "hooks": [dict(item.__dict__) for item in self.hooks],
            "state_schema_version": self.state_schema_version,
            "state_migrations": dict(self.state_migrations),
            "required_value_version": self.required_value_version,
            "required_contract_versions": dict(self.required_contract_versions),
            "member_inventory": [dict(item) for item in self.member_inventory],
            "maturity": self.maturity,
        }


@dataclass(frozen=True)
class ResolvedExtensionGraph:
    extensions: Sequence[ExtensionManifest]
    parameters: Mapping[str, object]
    parameter_schema_hashes: Mapping[str, str]
    hook_order: Mapping[str, Sequence[str]]
    graph_sha256: str
    hook_source_identities: Mapping[str, Sequence[Mapping[str, object]]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        payload = {
            "schema_version": "value.resolved-extension-graph/v1",
            "graph_sha256": self.graph_sha256,
            "extensions": [
                {"id": item.id, "version": item.version, "namespace": item.namespace,
                 "manifest_sha256": canonical_hash(item.to_dict())}
                for item in self.extensions
            ],
            "manifests": {item.id: item.to_dict() for item in self.extensions},
            "hook_source_identities": {key: [dict(item) for item in values] for key, values in self.hook_source_identities.items()},
            "parameters": dict(self.parameters),
            "parameter_schema_hashes": dict(self.parameter_schema_hashes),
            "hook_order": {key: list(value) for key, value in self.hook_order.items()},
        }

        # Nested declaration tuples must survive checkpoint JSON round trips.
        return json.loads(json.dumps(payload, ensure_ascii=False))

def hook_source_identity(hook: HookDeclaration, *, extension_id: str | None = None) -> dict[str, object]:
    module_name, symbol_name = hook.implementation.split(":", 1)
    # A hook that failed to import is not imported again for the same
    # sys.path (negative cache); the failure is a coded ValueError so every
    # resolution path reports it, and the extension is runtime-quarantined.
    key = (module_name, tuple(sys.path))
    cached = cached_hook_failure(key)
    if cached is not None:
        error = ExtensionHookImportError(
            f"Extension hook {hook.implementation} failed to import: {cached[0]}: {cached[1]}",
            extension_id=extension_id, error_type=cached[0],
        )
        if extension_id:
            record_hook_quarantine(extension_id, error)
        raise error
    try:
        module = importlib.import_module(module_name)
    except (Exception, SystemExit) as exc:
        record_hook_failure(key, type(exc).__name__, str(exc))
        error = ExtensionHookImportError(
            f"Extension hook {hook.implementation} failed to import: {type(exc).__name__}: {exc}",
            extension_id=extension_id, error_type=type(exc).__name__,
        )
        if extension_id:
            record_hook_quarantine(extension_id, error)
        raise error from exc
    filename = getattr(module, "__file__", None)
    if not filename or not Path(filename).is_file() or Path(filename).suffix != ".py":
        raise ValueError("Extension hook has no readable Python source: " + hook.implementation)
    symbol = getattr(module, symbol_name, None)
    if not callable(getattr(symbol, hook.hook, None)):
        raise ValueError("Extension hook is not callable: " + hook.implementation + ":" + hook.hook)
    digest = hashlib.sha256(Path(filename).read_bytes()).hexdigest()
    loaded_hash = getattr(module, "__value_extension_source_sha256__", digest)
    if loaded_hash != digest:
        raise ValueError("Extension source changed after module load: " + hook.implementation)
    module.__value_extension_source_sha256__ = digest
    return {"hook": hook.hook, "implementation": hook.implementation, "source_sha256": digest, "distribution": "workspace-source" if Path(filename).resolve().is_relative_to(Path(__file__).resolve().parent) else "installed-source"}


def probe_extension_hooks(manifests: Mapping[str, ExtensionManifest]) -> dict[str, list[str]]:
    """Import every hook of the given registered extensions now (R4 F-中3).

    Rescan calls this after it purged the installed sources and rebuilt the
    catalogue, so an extension whose hook no longer imports is quarantined at
    once (``hook_source_identity`` records the runtime hook quarantine), as a
    broken module is, instead of at the next Study resolution.  Returns the
    extension ids whose hooks imported and those that were quarantined.
    """

    imported: list[str] = []
    quarantined: list[str] = []
    for extension_id, manifest in sorted(manifests.items()):
        try:
            for hook in manifest.hooks:
                hook_source_identity(hook, extension_id=extension_id)
        except ExtensionHookImportError:
            quarantined.append(extension_id)
        except ValueError:
            # Not an import failure (for example a hook that is not callable):
            # Study resolution reports it with its own message.
            imported.append(extension_id)
        else:
            imported.append(extension_id)
    return {"imported": imported, "quarantined": quarantined}


def _hook_order(manifests: Sequence[ExtensionManifest]) -> dict[str, tuple[str, ...]]:
    result: dict[str, tuple[str, ...]] = {}
    by_id = {item.id: item for item in manifests}
    for hook_name in HOOKS:
        declarations = {
            extension.id: declaration
            for extension in manifests
            for declaration in extension.hooks
            if declaration.hook == hook_name
        }
        edges: dict[str, set[str]] = {item: set() for item in declarations}
        for extension_id, declaration in declarations.items():
            for predecessor in declaration.after:
                if predecessor in declarations:
                    edges[extension_id].add(predecessor)
            for successor in declaration.before:
                if successor in declarations:
                    edges[successor].add(extension_id)
        ordered: list[str] = []
        remaining = {key: set(value) for key, value in edges.items()}
        while remaining:
            ready = sorted(key for key, dependencies in remaining.items() if not dependencies)
            if not ready:
                raise ValueError(f"Cyclic extension hook order for {hook_name}")
            for key in ready:
                ordered.append(key)
                remaining.pop(key)
                for dependencies in remaining.values():
                    dependencies.discard(key)
        result[hook_name] = tuple(ordered)
    return result


class ExtensionRegistry:
    def __init__(self, manifests: Sequence[ExtensionManifest] = ()) -> None:
        self._manifests: dict[str, ExtensionManifest] = {}
        self._namespaces: dict[str, str] = {}
        for manifest in manifests:
            self.register(manifest)

    def register(self, manifest: ExtensionManifest) -> None:
        if manifest.schema_version != EXTENSION_SCHEMA:
            raise ValueError(f"Extension {manifest.id} uses unsupported schema {manifest.schema_version}")
        if not SEMVER.fullmatch(manifest.version):
            raise ValueError(f"Extension {manifest.id} version is not semantic")
        if not NAMESPACE.fullmatch(manifest.namespace) or manifest.namespace.startswith("value.core"):
            raise ValueError(f"Extension {manifest.id} has an unsafe or reserved namespace")
        if manifest.id in self._manifests:
            raise ValueError(f"Duplicate extension ID: {manifest.id}")
        if manifest.namespace in self._namespaces:
            raise ValueError(
                f"Extension namespace collision: {manifest.namespace} is owned by {self._namespaces[manifest.namespace]}"
            )
        if manifest.maturity not in {"ready", "experimental", "not_evaluated"}:
            raise ValueError(f"Extension {manifest.id} has invalid maturity")
        parameter_names = [item.name for item in manifest.parameters]
        if len(parameter_names) != len(set(parameter_names)):
            raise ValueError(f"Extension {manifest.id} has duplicate parameters")
        role_names = [item.role for item in manifest.data_roles]
        if len(role_names) != len(set(role_names)):
            raise ValueError(f"Extension {manifest.id} has duplicate data roles")
        for parameter in manifest.parameters:
            parameter.validate_schema()
            if not parameter.name.startswith(manifest.namespace + "."):
                raise ValueError(f"Parameter {parameter.name} is outside {manifest.namespace}")
        for role in manifest.data_roles:
            if not role.role.startswith(manifest.namespace + "."):
                raise ValueError(f"Data role {role.role} is outside {manifest.namespace}")
            if role.capability not in manifest.provided_capabilities:
                raise ValueError(f"Data role {role.role} activates an undeclared capability")
        for hook in manifest.hooks:
            if hook.hook not in HOOKS or ":" not in hook.implementation:
                raise ValueError(f"Extension {manifest.id} has an invalid lifecycle hook")
        self._manifests[manifest.id] = manifest
        self._namespaces[manifest.namespace] = manifest.id

    def manifest(self, extension_id: str) -> ExtensionManifest:
        try:
            return self._manifests[extension_id]
        except KeyError as exc:
            raise ValueError(f"Extension is not registered: {extension_id}") from exc

    def manifests(self) -> Mapping[str, ExtensionManifest]:
        return dict(self._manifests)

    def resolve(
        self,
        selected: Sequence[str],
        *,
        available_capabilities: Sequence[str] = (),
        available_data_roles: Sequence[str] = (),
        parameter_values: Mapping[str, object] | None = None,
    ) -> ResolvedExtensionGraph:
        manifests = tuple(self.manifest(item) for item in selected)
        capabilities = set(available_capabilities)
        for item in manifests:
            capabilities.update(item.provided_capabilities)
        for item in manifests:
            missing = sorted(set(item.required_capabilities).difference(capabilities))
            if missing:
                raise ValueError(f"Extension {item.id} is missing capabilities: {', '.join(missing)}")
        active_roles = set(available_data_roles)
        required_roles = {
            role.role for item in manifests for role in item.data_roles if role.required
        }
        missing_roles = sorted(required_roles.difference(active_roles))
        if missing_roles:
            raise ValueError("Extension data roles are not ready: " + ", ".join(missing_roles))
        supplied = dict(parameter_values or {})
        declarations = {parameter.name: parameter for item in manifests for parameter in item.parameters}
        unknown = sorted(set(supplied).difference(declarations))
        if unknown:
            raise ValueError("Unknown extension parameters: " + ", ".join(unknown))
        resolved_parameters = {
            name: declaration.validate_value(supplied.get(name, declaration.default))
            for name, declaration in sorted(declarations.items())
        }
        schema_hashes = {
            item.id: canonical_hash([parameter.to_dict() for parameter in item.parameters])
            for item in manifests
        }
        order = _hook_order(manifests)
        source_identities = {
            item.id: tuple(hook_source_identity(hook, extension_id=item.id) for hook in item.hooks)
            for item in manifests
        }
        payload = {
            "extensions": [item.to_dict() for item in manifests],
            "hook_source_identities": source_identities,
            "parameters": resolved_parameters,
            "parameter_schema_hashes": schema_hashes,
            "hook_order": order,
        }
        return ResolvedExtensionGraph(
            manifests, resolved_parameters, schema_hashes, order, canonical_hash(payload), source_identities
        )

    def conditional_dataset_slots(self, selected: Sequence[str]) -> tuple[dict[str, object], ...]:
        return tuple(
            role.to_dataset_slot()
            for extension_id in selected
            for role in self.manifest(extension_id).data_roles
        )


def load_extension_manifests(path: Path) -> tuple[ExtensionManifest, ...]:
    if not path.is_dir():
        return ()
    return tuple(
        ExtensionManifest.from_dict(json.loads(item.read_text(encoding="utf-8")))
        for item in sorted(path.glob("*.json"))
    )


def validate_extension_state(
    state: Mapping[str, object], graph: ResolvedExtensionGraph
) -> dict[str, object]:
    allowed = {item.namespace: item for item in graph.extensions}
    unknown = sorted(set(state).difference(allowed))
    if unknown:
        raise ValueError("Orphaned extension state: " + ", ".join(unknown))
    result: dict[str, object] = {}
    for namespace, payload in state.items():
        if not isinstance(payload, Mapping):
            raise ValueError(f"Extension state {namespace} must be a JSON object")
        manifest = allowed[namespace]
        if payload.get("owner") != manifest.id:
            raise ValueError(f"Extension state {namespace} has the wrong owner")
        if payload.get("schema_version") != manifest.state_schema_version:
            raise ValueError(f"Extension state {namespace} has an incompatible schema")
        result[namespace] = dict(payload)
    return result


def validate_extension_artifact(
    artifact: Mapping[str, object], extension: ExtensionManifest
) -> dict[str, object]:
    declared = {item.artifact_type: item for item in extension.artifacts}
    artifact_type = str(artifact.get("artifact_type") or "")
    if artifact_type not in declared:
        raise ValueError(f"Undeclared extension artifact: {artifact_type}")
    specification = declared[artifact_type]
    if artifact.get("schema_version") != specification.schema_version:
        raise ValueError(f"Artifact {artifact_type} uses an incompatible schema")
    if artifact.get("producer_extension") != extension.id:
        raise ValueError(f"Artifact {artifact_type} has the wrong producer")
    if not artifact.get("source_inputs_sha256"):
        raise ValueError(f"Artifact {artifact_type} has no source identity")
    return dict(artifact)


class ExtensionRuntime:
    """Invoke only hooks frozen by a resolved graph, in deterministic order."""

    def __init__(self, graph: ResolvedExtensionGraph) -> None:
        self.graph = graph
        self._instances: dict[tuple[str, str], Callable[..., object]] = {}
        for manifest in graph.extensions:
            for hook in manifest.hooks:
                observed = hook_source_identity(hook, extension_id=manifest.id)
                frozen = self.graph.hook_source_identities.get(manifest.id, ())
                if not any(dict(identity) == observed for identity in frozen):
                    raise ValueError("Extension hook source does not match frozen graph: " + hook.implementation)
                module_name, symbol_name = hook.implementation.split(":", 1)
                symbol = getattr(importlib.import_module(module_name), symbol_name)
                instance = symbol() if isinstance(symbol, type) else symbol
                callback = getattr(instance, hook.hook, None)
                if not callable(callback):
                    raise ValueError(
                        f"Extension hook {manifest.id}:{hook.hook} is not callable"
                    )
                self._instances[(manifest.id, hook.hook)] = callback

    def invoke(self, hook: str, payload: Mapping[str, object]) -> tuple[dict[str, object], ...]:
        if hook not in HOOKS:
            raise ValueError(f"Unknown extension lifecycle hook: {hook}")
        immutable_input = json.loads(json.dumps(dict(payload), ensure_ascii=False))
        outputs = []
        for extension_id in self.graph.hook_order.get(hook, ()):
            result = self._instances[(extension_id, hook)](immutable_input)
            if not isinstance(result, Mapping):
                raise ValueError(f"Extension {extension_id}:{hook} returned an untyped value")
            value = dict(result)
            if "artifact_type" in value:
                extension = next(
                    item for item in self.graph.extensions if item.id == extension_id
                )
                value = validate_extension_artifact(value, extension)
            outputs.append(value)
        return tuple(outputs)
