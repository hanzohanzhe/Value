"""Manifest-backed executable module registry for VALUE v2."""

from __future__ import annotations

import importlib
import importlib.metadata
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Sequence

from ..runtime_paths import activate_external_module_sources, external_modules_root
from ..module_quarantine import (
    ExternalImportError,
    ModuleQuarantinedError,
    QuarantinedEntry,
    cached_import_failure,
    import_cache_key,
    quarantine_entry,
    record_import_failure,
)
from ..extension_framework import (
    ExtensionManifest,
    ExtensionRegistry,
    ResolvedExtensionGraph,
    load_extension_manifests,
)


MODULE_SCHEMA = "value.module/v2"
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?$")
SUPPORTED_CONTRACTS = {
    "psm": "value.psm/v2",
    "investment": "value.investment/v2",
    "pipeline": "value.planning/v2",
    "vre_cap": "value.expansion-policy/v2",
    "storage_cap": "value.expansion-policy/v2",
    "transition": "value.state-transition/v2",
    "storage_cost": "value.storage-cost/v1",
    "network_expansion": "value.network-expansion/v1",
    "balancing": "value.balancing-module/v1",
    "weather_spatializer": "value.weather-spatializer/v1",
}


@dataclass(frozen=True)
class ModuleManifest:
    id: str
    name: str
    version: str
    slot: str
    implementation: str
    contract_version: str
    inputs: Sequence[str]
    outputs: Sequence[str]
    parameters: Sequence[str]
    state_reads: Sequence[str]
    state_writes: Sequence[str]
    determinism: str
    artifacts: Sequence[str]
    description: str
    schema_version: str = MODULE_SCHEMA
    status: str = "ready"
    selection_required: bool = True
    provides_capabilities: Sequence[str] = field(default_factory=tuple)
    requires_capabilities: Sequence[str] = field(default_factory=tuple)
    scientific_version: str | None = None
    units: Mapping[str, str] = field(default_factory=dict)
    execution_kind: str = "live_module"
    solver_contract: Mapping[str, object] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "ModuleManifest":
        sequence_fields = {
            "inputs", "outputs", "parameters", "state_reads", "state_writes",
            "artifacts", "provides_capabilities", "requires_capabilities",
        }
        values = dict(payload)
        for key in sequence_fields:
            values[key] = tuple(str(item) for item in values.get(key, ()))
        values["units"] = {
            str(key): str(value) for key, value in dict(values.get("units") or {}).items()
        }
        values["solver_contract"] = dict(values.get("solver_contract") or {})
        return cls(**values)  # type: ignore[arg-type]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "scientific_version": self.scientific_version,
            "slot": self.slot,
            "implementation": self.implementation,
            "contract_version": self.contract_version,
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "parameters": list(self.parameters),
            "state_reads": list(self.state_reads),
            "state_writes": list(self.state_writes),
            "determinism": self.determinism,
            "artifacts": list(self.artifacts),
            "description": self.description,
            "status": self.status,
            "selection_required": self.selection_required,
            "provides_capabilities": list(self.provides_capabilities),
            "requires_capabilities": list(self.requires_capabilities),
            "units": dict(self.units),
            "execution_kind": self.execution_kind,
            "solver_contract": dict(self.solver_contract),
        }


@dataclass(frozen=True)
class ResolvedModuleIdentity:
    slot: str
    module_id: str
    module_version: str
    contract_version: str
    entry_point: str
    source_sha256: str
    distribution: str
    scientific_version: str | None
    execution_kind: str

    def to_dict(self) -> dict[str, object]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class ResolvedModuleGraph:
    """One immutable resolution/instantiation result for a project run."""

    manifests_by_slot: Mapping[str, ModuleManifest]
    implementations_by_slot: Mapping[str, object]
    identities_by_slot: Mapping[str, ResolvedModuleIdentity]
    graph_sha256: str
    extension_graph: ResolvedExtensionGraph | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "manifests_by_slot", MappingProxyType(dict(self.manifests_by_slot))
        )
        object.__setattr__(
            self, "implementations_by_slot", MappingProxyType(dict(self.implementations_by_slot))
        )
        object.__setattr__(
            self, "identities_by_slot", MappingProxyType(dict(self.identities_by_slot))
        )

    def manifest(self, slot: str) -> ModuleManifest:
        try:
            return self.manifests_by_slot[slot]
        except KeyError as exc:
            raise ValueError(f"Resolved module graph has no slot: {slot}") from exc

    def implementation(self, slot: str) -> object:
        try:
            return self.implementations_by_slot[slot]
        except KeyError as exc:
            raise ValueError(f"Resolved module graph has no implementation for slot: {slot}") from exc

    def identity(self, slot: str) -> ResolvedModuleIdentity:
        try:
            return self.identities_by_slot[slot]
        except KeyError as exc:
            raise ValueError(f"Resolved module graph has no identity for slot: {slot}") from exc

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "schema_version": "value.module-resolution-graph/v1",
            "graph_sha256": self.graph_sha256,
            "modules": {
                slot: identity.to_dict()
                for slot, identity in sorted(self.identities_by_slot.items())
            },
        }
        if self.extension_graph is not None:
            result["extension_graph"] = self.extension_graph.to_dict()
        return result


def _source_identity(entry_point: str) -> tuple[str, str]:
    module_name = entry_point.split(":", 1)[0]
    module = importlib.import_module(module_name)
    raw = getattr(module, "__file__", None)
    if not raw or not Path(raw).is_file():
        raise ValueError(f"Module source is not a hashable file: {entry_point}")
    source_path = Path(raw).resolve()
    digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
    top_level = module_name.split(".", 1)[0]
    registry_path = Path(__file__).resolve()
    workspace_root = next(
        (
            parent
            for parent in registry_path.parents
            if (parent / "pyproject.toml").is_file()
            and (parent / "gridform_core").is_dir()
        ),
        None,
    )
    if workspace_root is not None and source_path.is_relative_to(workspace_root):
        distribution = "workspace-source"
    else:
        distributions = importlib.metadata.packages_distributions().get(top_level, [])
        distribution = distributions[0] if distributions else "workspace-source"
    return digest, distribution


class ModuleRegistryV2:
    def __init__(
        self,
        manifests: Sequence[ModuleManifest],
        extensions: Sequence[ExtensionManifest] = (),
    ) -> None:
        self._manifests: dict[str, ModuleManifest] = {}
        self.extension_registry = ExtensionRegistry(extensions)
        # External entries workspace_registry refused (P0-2); never on disk.
        self.quarantined: tuple[QuarantinedEntry, ...] = ()
        for manifest in manifests:
            self.register(manifest)

    def register(self, manifest: ModuleManifest) -> None:
        self.validate_manifest(manifest)
        if manifest.id in self._manifests:
            raise ValueError(f"Duplicate module ID: {manifest.id}")
        self._manifests[manifest.id] = manifest

    @staticmethod
    def validate_manifest(manifest: ModuleManifest) -> None:
        if manifest.schema_version != MODULE_SCHEMA:
            raise ValueError(
                f"Module {manifest.id} uses {manifest.schema_version}; expected {MODULE_SCHEMA}"
            )
        if manifest.slot not in SUPPORTED_CONTRACTS:
            raise ValueError(f"Module {manifest.id} declares unsupported slot {manifest.slot}")
        expected = SUPPORTED_CONTRACTS[manifest.slot]
        if manifest.contract_version != expected:
            raise ValueError(
                f"Module {manifest.id} in slot {manifest.slot} uses "
                f"{manifest.contract_version}; expected {expected}"
            )
        if not SEMVER.fullmatch(manifest.version):
            raise ValueError(f"Module {manifest.id} version is not semantic: {manifest.version}")
        if manifest.determinism not in {"deterministic", "seeded", "stochastic"}:
            raise ValueError(f"Module {manifest.id} has invalid determinism declaration")
        if manifest.execution_kind != "live_module":
            raise ValueError(
                f"Selectable module {manifest.id} must declare execution_kind=live_module"
            )
        if ":" not in manifest.implementation:
            raise ValueError(f"Module {manifest.id} has invalid implementation entry point")
        module_name, symbol_name = manifest.implementation.split(":", 1)
        try:
            module = importlib.import_module(module_name)
        except (Exception, SystemExit) as exc:
            # External code may raise anything (even SystemExit) at import time;
            # report the root cause instead of "missing" (G4-02).
            raise ExternalImportError(
                f"Module {manifest.id} implementation {module_name} failed to import: "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        if not hasattr(module, symbol_name):
            raise ValueError(
                f"Module {manifest.id} implementation symbol is missing: {manifest.implementation}"
            )
        declared_names = set(manifest.inputs) | set(manifest.outputs) | set(manifest.parameters)
        unknown_unit_names = sorted(set(manifest.units).difference(declared_names))
        if unknown_unit_names:
            raise ValueError(
                f"Module {manifest.id} declares units for unknown names: "
                + ", ".join(unknown_unit_names)
            )
        if any(not str(value).strip() for value in manifest.units.values()):
            raise ValueError(f"Module {manifest.id} contains an empty unit declaration")
        for field_name in ("provides_capabilities", "requires_capabilities"):
            capabilities = tuple(getattr(manifest, field_name))
            if any(not capability.strip() for capability in capabilities):
                raise ValueError(f"Module {manifest.id} contains an empty capability declaration")
            if len(set(capabilities)) != len(capabilities):
                raise ValueError(f"Module {manifest.id} repeats a capability declaration")

    def manifest(self, module_id: str, *, expected_slot: str | None = None) -> ModuleManifest:
        try:
            manifest = self._manifests[module_id]
        except KeyError as exc:
            raise ValueError(f"Module is not registered: {module_id}") from exc
        if expected_slot is not None and manifest.slot != expected_slot:
            raise ValueError(
                f"Module {module_id} cannot fill {expected_slot}; it provides {manifest.slot}"
            )
        return manifest

    def resolve(self, module_id: str, *, expected_slot: str) -> object:
        manifest = self.manifest(module_id, expected_slot=expected_slot)
        module_name, symbol_name = manifest.implementation.split(":", 1)
        implementation = getattr(importlib.import_module(module_name), symbol_name)
        return implementation()

    def resolve_selection(
        self,
        selected: Mapping[str, str],
        *,
        available_capabilities: Sequence[str] = (),
        selected_extensions: Sequence[str] = (),
        extension_parameters: Mapping[str, object] | None = None,
        available_data_roles: Sequence[str] = (),
    ) -> ResolvedModuleGraph:
        manifests = self.validate_selection(
            selected,
            available_capabilities=available_capabilities,
            selected_extensions=selected_extensions,
            extension_parameters=extension_parameters,
            available_data_roles=available_data_roles,
        )
        manifests_by_slot = {manifest.slot: manifest for manifest in manifests}
        implementations: dict[str, object] = {}
        identities: dict[str, ResolvedModuleIdentity] = {}
        for slot, module_id in sorted(selected.items()):
            manifest = manifests_by_slot[slot]
            source_sha256, distribution = _source_identity(manifest.implementation)
            module_name, symbol_name = manifest.implementation.split(":", 1)
            implementation_type = getattr(importlib.import_module(module_name), symbol_name)
            implementations[slot] = implementation_type()
            identities[slot] = ResolvedModuleIdentity(
                slot=slot,
                module_id=module_id,
                module_version=manifest.version,
                contract_version=manifest.contract_version,
                entry_point=manifest.implementation,
                source_sha256=source_sha256,
                distribution=distribution,
                scientific_version=manifest.scientific_version,
                execution_kind=manifest.execution_kind,
            )
        identity_payload: dict[str, object] = {
            slot: identity.to_dict() for slot, identity in sorted(identities.items())
        }
        extension_graph = None
        if selected_extensions:
            extension_graph = self.extension_registry.resolve(
                selected_extensions,
                available_capabilities=tuple(available_capabilities) + tuple(
                    capability
                    for manifest in manifests
                    for capability in manifest.provides_capabilities
                ),
                available_data_roles=available_data_roles,
                parameter_values=extension_parameters,
            )
            identity_payload["$extensions"] = extension_graph.to_dict()
        graph_sha256 = hashlib.sha256(
            json.dumps(identity_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return ResolvedModuleGraph(
            manifests_by_slot, implementations, identities, graph_sha256,
            extension_graph,
        )

    def validate_selection(
        self,
        selected: Mapping[str, str],
        *,
        available_capabilities: Sequence[str] = (),
        selected_extensions: Sequence[str] = (),
        extension_parameters: Mapping[str, object] | None = None,
        available_data_roles: Sequence[str] = (),
    ) -> tuple[ModuleManifest, ...]:
        required_slots = {
            manifest.slot for manifest in self._manifests.values() if manifest.selection_required
        }
        missing_slots = sorted(required_slots.difference(selected))
        if missing_slots:
            raise ValueError(f"Missing required module slots: {', '.join(missing_slots)}")
        psm_id = selected.get("psm")
        selected_psm = (
            self.manifest(psm_id, expected_slot="psm") if psm_id is not None else None
        )
        balancing_keys = tuple(
            slot for slot in selected if slot == "balancing" or slot.startswith("balancing_")
        )
        staged_market = bool(
            selected_psm is not None
            and "market.ahead-schedule/v1" in selected_psm.provides_capabilities
        )
        if staged_market and not balancing_keys:
            raise ValueError(
                f"Staged PSM {selected_psm.id} requires a balancing module"
            )
        if len(balancing_keys) > 1:
            raise ValueError("A staged Study cannot select more than one balancing module")
        if balancing_keys and not staged_market:
            raise ValueError("The balancing slot is only valid with a staged PSM")
        resolved = tuple(
            self.manifest(module_id, expected_slot=slot)
            for slot, module_id in selected.items()
        )
        psm = next((manifest for manifest in resolved if manifest.slot == "psm"), None)
        balancing = next((manifest for manifest in resolved if manifest.slot == "balancing"), None)
        if balancing is not None and "domain.network.zonal_redispatch" in balancing.provides_capabilities:
            missing_context: list[str] = []
            lifecycle = "value.module-context-lifecycle/v1"
            domain = "value.zonal-redispatch-domain/v2"
            if psm is None or lifecycle not in psm.provides_capabilities:
                missing_context.append(f"psm:{lifecycle}")
            if lifecycle not in balancing.provides_capabilities:
                missing_context.append(f"balancing:{lifecycle}")
            if domain not in balancing.provides_capabilities:
                missing_context.append(f"balancing:{domain}")
            if missing_context:
                raise ValueError(
                    "Module selection has incompatible capabilities; missing "
                    + ", ".join(missing_context)
                )
        if (
            psm is not None
            and "storage.central-cooptimization" in psm.provides_capabilities
            and "storage_cost" in selected
        ):
            raise ValueError(
                "Perfect-foresight co-optimization is incompatible with a storage offer rule; "
                "remove the storage_cost selection."
            )
        provided = set(available_capabilities)
        for manifest in resolved:
            provided.update(manifest.provides_capabilities)
        extension_graph = None
        if selected_extensions:
            extension_graph = self.extension_registry.resolve(
                selected_extensions,
                available_capabilities=tuple(provided),
                available_data_roles=available_data_roles,
                parameter_values=extension_parameters,
            )
            for extension in extension_graph.extensions:
                provided.update(extension.provided_capabilities)
        for manifest in resolved:
            missing = sorted(set(manifest.requires_capabilities).difference(provided))
            if missing:
                raise ValueError(
                    f"Module {manifest.id} has incompatible capabilities; missing "
                    f"{', '.join(missing)}"
                )
        if extension_graph is not None:
            selected_module_ids = set(selected.values())
            for extension in extension_graph.extensions:
                missing_modules = sorted(
                    set(extension.composed_module_ids).difference(selected_module_ids)
                )
                if missing_modules:
                    raise ValueError(
                        f"Extension {extension.id} requires selected modules: "
                        + ", ".join(missing_modules)
                    )
        return resolved

    def catalog(self) -> list[dict[str, object]]:
        return [
            manifest.to_dict()
            for manifest in sorted(self._manifests.values(), key=lambda item: (item.slot, item.id))
        ]

    def manifests(self) -> Mapping[str, ModuleManifest]:
        return dict(self._manifests)

    def extension_manifests(self) -> Mapping[str, ExtensionManifest]:
        return self.extension_registry.manifests()


def load_manifests(path: Path) -> tuple[ModuleManifest, ...]:
    manifests = []
    for manifest_path in sorted(path.glob("*.json")):
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifests.append(ModuleManifest.from_dict(payload))
    return tuple(manifests)


def builtin_registry() -> ModuleRegistryV2:
    path = Path(__file__).resolve().parents[1] / "manifests"
    extension_path = Path(__file__).resolve().parents[1] / "extension_manifests"
    return ModuleRegistryV2(load_manifests(path), load_extension_manifests(extension_path))


def _read_external_manifest(path: Path) -> tuple[bytes, object]:
    raw = path.read_bytes()
    return raw, json.loads(raw.decode("utf-8"))


def workspace_registry(
    modules_path: Path | None = None,
    *,
    include_internal_experimental: bool = False,
    strict: bool = False,
) -> ModuleRegistryV2:
    """Load built-ins plus explicitly installed local manifests.

    There is intentionally no browser upload path for executable modules.
    Researchers install code into their Python environment and place reviewed
    manifests under ``.gridform/modules``.

    Built-in manifests are fail-closed: any error still raises.  External
    manifests are fail-isolated in two passes (P0-2): pass one parses every
    file and counts IDs and namespaces (an external entry that collides with a
    built-in is quarantined alone, ``shadows_registered``; external entries
    that collide with each other are all quarantined - there is no implicit
    winner); pass two registers the survivors one by one in the original
    order, catching any exception including SystemExit.  Refused entries are
    listed in ``registry.quarantined``.  ``strict=True`` (release gates)
    raises ``ModuleQuarantinedError`` instead of isolating.
    """

    builtin_root = Path(__file__).resolve().parents[1]
    builtin_path = builtin_root / "manifests"
    manifests = list(load_manifests(builtin_path))
    extension_path = builtin_root / "extension_manifests"
    extensions = list(load_extension_manifests(extension_path))
    if include_internal_experimental:
        internal_root = builtin_root / "internal_experimental"
        manifests.extend(load_manifests(internal_root / "manifests"))
        extensions.extend(
            load_extension_manifests(internal_root / "extension_manifests")
        )
    registry = ModuleRegistryV2(tuple(manifests), tuple(extensions))
    local_path = modules_path or external_modules_root()
    activate_external_module_sources(local_path)
    if not local_path.is_dir():
        return registry
    roots = (local_path,)
    quarantined: list[QuarantinedEntry] = []

    # Pass one: parse every external file and collect IDs/namespaces.
    module_rows: list[tuple[Path, bytes, ModuleManifest | None, str | None]] = []
    for path in sorted(local_path.glob("*.json")):
        payload: object = None
        try:
            raw, payload = _read_external_manifest(path)
            module_rows.append((path, raw, ModuleManifest.from_dict(payload), None))  # type: ignore[arg-type]
        except Exception as exc:
            entry_id = str(payload.get("id")) if isinstance(payload, dict) and payload.get("id") else None
            module_rows.append((path, b"", None, entry_id))
            quarantined.append(quarantine_entry(
                "module", path.name, entry_id, "GF_MODULE_MANIFEST_INVALID", exc, roots=roots,
            ))
    extension_rows: list[tuple[Path, ExtensionManifest | None, str | None, str | None]] = []
    for path in sorted((local_path / "extensions").glob("*.json")):
        payload = None
        try:
            payload = json.loads(path.read_bytes().decode("utf-8"))
            extension_rows.append((path, ExtensionManifest.from_dict(payload), None, None))  # type: ignore[arg-type]
        except Exception as exc:
            entry_id = str(payload.get("id")) if isinstance(payload, dict) and payload.get("id") else None
            namespace = str(payload.get("namespace")) if isinstance(payload, dict) and payload.get("namespace") else None
            extension_rows.append((path, None, entry_id, namespace))
            quarantined.append(quarantine_entry(
                "extension", "extensions/" + path.name, entry_id, "GF_EXTENSION_MANIFEST_INVALID", exc,
                roots=roots,
            ))
    module_id_counts: dict[str, int] = {}
    for _, _, manifest, entry_id in module_rows:
        key = manifest.id if manifest is not None else entry_id
        if key:
            module_id_counts[key] = module_id_counts.get(key, 0) + 1
    extension_id_counts: dict[str, int] = {}
    namespace_counts: dict[str, int] = {}
    for _, manifest, entry_id, namespace in extension_rows:
        key = manifest.id if manifest is not None else entry_id
        space = manifest.namespace if manifest is not None else namespace
        if key:
            extension_id_counts[key] = extension_id_counts.get(key, 0) + 1
        if space:
            namespace_counts[space] = namespace_counts.get(space, 0) + 1
    builtin_ids = set(registry.manifests())
    builtin_extensions = registry.extension_manifests()
    builtin_namespaces = {item.namespace: item.id for item in builtin_extensions.values()}

    # Pass two: register survivors one by one, in the original order.
    for path, raw, manifest, _ in module_rows:
        if manifest is None:
            continue
        label = path.name
        if manifest.id in builtin_ids:
            quarantined.append(quarantine_entry(
                "module", label, manifest.id, "GF_MODULE_SHADOWS_BUILTIN",
                f"External module {manifest.id} uses the ID of a built-in module; the built-in stays active",
                roots=roots, shadows_registered=True,
            ))
            continue
        if module_id_counts[manifest.id] > 1:
            quarantined.append(quarantine_entry(
                "module", label, manifest.id, "GF_MODULE_ID_DUPLICATE",
                f"Module ID {manifest.id} is declared by {module_id_counts[manifest.id]} local manifests; "
                "all of them are quarantined",
                roots=roots,
            ))
            continue
        key = import_cache_key(path, raw)
        cached = cached_import_failure(key)
        if cached is not None:
            quarantined.append(QuarantinedEntry(
                "module", label, manifest.id, "GF_MODULE_IMPORT_FAILED", cached[0], cached[1],
            ))
            continue
        try:
            registry.register(manifest)
        except (Exception, SystemExit) as exc:
            if isinstance(exc, ExternalImportError):
                entry = quarantine_entry("module", label, manifest.id, "GF_MODULE_IMPORT_FAILED",
                                         exc, roots=roots)
                cause = exc.__cause__
                entry = QuarantinedEntry(entry.kind, entry.manifest_file, entry.entry_id, entry.code,
                                         type(cause).__name__ if cause is not None else entry.error_type,
                                         entry.message)
                record_import_failure(key, entry.error_type, entry.message)
            else:
                entry = quarantine_entry("module", label, manifest.id, "GF_MODULE_MANIFEST_INVALID",
                                         exc, roots=roots)
            quarantined.append(entry)
    for path, extension, _, _ in extension_rows:
        if extension is None:
            continue
        label = "extensions/" + path.name
        if extension.id in builtin_extensions:
            quarantined.append(quarantine_entry(
                "extension", label, extension.id, "GF_EXTENSION_SHADOWS_BUILTIN",
                f"External extension {extension.id} uses the ID of a built-in extension; the built-in stays active",
                roots=roots, shadows_registered=True,
            ))
            continue
        if extension.namespace in builtin_namespaces:
            quarantined.append(quarantine_entry(
                "extension", label, extension.id, "GF_EXTENSION_NAMESPACE_COLLISION",
                f"Extension namespace {extension.namespace} is owned by built-in extension "
                f"{builtin_namespaces[extension.namespace]}",
                roots=roots,
            ))
            continue
        if extension_id_counts[extension.id] > 1:
            quarantined.append(quarantine_entry(
                "extension", label, extension.id, "GF_EXTENSION_ID_DUPLICATE",
                f"Extension ID {extension.id} is declared by {extension_id_counts[extension.id]} local manifests; "
                "all of them are quarantined",
                roots=roots,
            ))
            continue
        if namespace_counts[extension.namespace] > 1:
            quarantined.append(quarantine_entry(
                "extension", label, extension.id, "GF_EXTENSION_NAMESPACE_COLLISION",
                f"Extension namespace {extension.namespace} is claimed by "
                f"{namespace_counts[extension.namespace]} enabled local extensions; all of them are quarantined",
                roots=roots,
            ))
            continue
        try:
            registry.extension_registry.register(extension)
        except (Exception, SystemExit) as exc:
            quarantined.append(quarantine_entry(
                "extension", label, extension.id, "GF_EXTENSION_MANIFEST_INVALID", exc, roots=roots,
            ))
    registry.quarantined = tuple(quarantined)
    if strict and quarantined:
        raise ModuleQuarantinedError(
            "GF_MODULE_QUARANTINED",
            "Local module entries are quarantined: " + "; ".join(
                f"{item.kind} {item.entry_id or item.manifest_file} ({item.code}: {item.message})"
                for item in quarantined
            ),
            entries=tuple(quarantined),
        )
    return registry
