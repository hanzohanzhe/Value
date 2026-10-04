"""Canonical, append-only research-project revision identities."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Mapping

from .frontend_contract import validate_project_solver_contract
from .doctoral_weather import uses_doctoral_weather, weather_execution_identity
from .v2.module_manifest import ModuleRegistryV2
from .zonal_solver_contract import DEFAULT_ZONAL_SOLVER_SETTINGS


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def canonical_project_payload(project: Mapping[str, object], registry: ModuleRegistryV2, data_pack_manifest: Mapping[str, object]) -> dict[str, object]:
    modules = dict(project.get("modules") or {})  # type: ignore[arg-type]
    psm_id = str(modules.get("psm") or "")
    if psm_id:
        psm = registry.manifest(psm_id, expected_slot="psm")
        if "storage.bid-cost-function" in psm.requires_capabilities:
            modules.setdefault("storage_cost", "dynamic-annual-storage-cost")
    module_versions = {
        slot: {
            "module_id": module_id,
            "version": registry.manifest(module_id, expected_slot=slot).version,
            "contract_version": registry.manifest(module_id, expected_slot=slot).contract_version,
        }
        for slot, module_id in sorted(modules.items())
    }
    result = {
        "schema_version": "value.project-fingerprint/v1",
        "data_pack": {
            "id": data_pack_manifest.get("id"),
            "schema_version": data_pack_manifest.get("schema_version"),
            "content_sha256": hashlib.sha256(_canonical_bytes(data_pack_manifest)).hexdigest(),
        },
        "start_year": int(project.get("start_year", 2025)),
        "end_year": int(project.get("end_year", 2034)),
        "modules": module_versions,
        "scientific_parameters": dict(project.get("parameters") or project.get("parameter_overrides") or {}),
        "runtime_controls": dict(project.get("runtime_options") or project.get("runtime_controls") or {}),
    }
    if uses_doctoral_weather(data_pack_manifest):
        result["dispatch_weather_identity"] = weather_execution_identity()
    if "market_configuration" in project:
        result["market_configuration"] = dict(project.get("market_configuration") or {})
    selected_extensions = tuple(str(item) for item in project.get("selected_extensions", ()))
    if selected_extensions:
        graph = registry.resolve_selection(
            modules,
            selected_extensions=selected_extensions,
            available_data_roles=tuple(
                sorted(
                    str(role)
                    for role in dict(data_pack_manifest.get("bindings") or {})
                )
            ),
            extension_parameters=dict(project.get("extension_parameters") or {}),
        )
        result["module_resolution_graph"] = graph.to_dict()
    solver_contract = validate_project_solver_contract(
        project,
        registry,
        modules={str(slot): str(module_id) for slot, module_id in modules.items()},
        require_acknowledgement=False,
    )
    if solver_contract is not None:
        result["solver_contract"] = solver_contract
    acknowledgements = dict(project.get("maturity_acknowledgements") or {})
    if acknowledgements:
        result["maturity_acknowledgements"] = acknowledgements
    return result


def project_fingerprint(project: Mapping[str, object], registry: ModuleRegistryV2, data_pack_manifest: Mapping[str, object]) -> str:
    return hashlib.sha256(_canonical_bytes(canonical_project_payload(project, registry, data_pack_manifest))).hexdigest()


def attach_revision_identity(project: Mapping[str, object], registry: ModuleRegistryV2, data_pack_manifest: Mapping[str, object]) -> dict[str, object]:
    result = dict(project)
    result["revision_sha256"] = project_fingerprint(project, registry, data_pack_manifest)
    result.setdefault("revision_number", 0)
    result.setdefault("parent_revision_sha256", None)
    return result


def derive_zonal_execution_project(
    source_bytes: bytes,
    *,
    registry: ModuleRegistryV2,
    data_pack_manifest: Mapping[str, object],
) -> tuple[dict[str, object], dict[str, object]]:
    """Derive a VALUE v2 execution copy without changing retained source bytes."""

    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    try:
        decoded = json.loads(source_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Zonal source study is not valid UTF-8 JSON") from exc
    if not isinstance(decoded, Mapping):
        raise ValueError("Zonal source study must be a JSON object")
    candidate = dict(decoded)
    legacy_ids = {
        "force-staged-bid-at-cost-psm": "value-staged-bid-at-cost-psm",
        "force-zonal-redispatch-balancing": "value-zonal-redispatch-balancing",
        "force-representative-point-weather": "value-representative-point-weather",
        "storage-expansion-scheme-c": "value-storage-expansion-policy",
        "scheme-c-state-transition": "value-annual-state-transition",
        "force-zonal-redispatch-extension": "value-zonal-redispatch-extension",
    }

    # Prompt 104 is retained as immutable historical evidence.  Its execution
    # copy is renamed in memory so no FORCE identity can enter a current VALUE
    # Study, fingerprint or input snapshot.
    modules = {
        str(slot): legacy_ids.get(str(module_id), str(module_id))
        for slot, module_id in dict(candidate.get("modules") or {}).items()
    }
    candidate["modules"] = modules
    candidate["selected_extensions"] = [
        legacy_ids.get(str(extension_id), str(extension_id))
        for extension_id in candidate.get("selected_extensions", ())
    ]
    market_configuration = dict(candidate.get("market_configuration") or {})
    for field in (
        "ahead_market_module_id",
        "balancing_module_id",
        "weather_spatialisation_module_id",
    ):
        if field in market_configuration:
            value = str(market_configuration[field])
            market_configuration[field] = legacy_ids.get(value, value)
    candidate["market_configuration"] = market_configuration

    migrated_acknowledgements: dict[str, object] = {}
    for key, value in dict(candidate.get("maturity_acknowledgements") or {}).items():
        migrated_key = str(key)
        migrated_value = (
            "value.experimental-ack/v1"
            if value == "force.experimental-ack/v1"
            else value
        )
        for legacy_id, value_id in legacy_ids.items():
            migrated_key = migrated_key.replace(legacy_id, value_id)
        migrated_acknowledgements[migrated_key] = migrated_value
    candidate["maturity_acknowledgements"] = migrated_acknowledgements
    module_id = str(modules.get("balancing") or "")
    if module_id != "value-zonal-redispatch-balancing":
        raise ValueError("Zonal source study does not select the zonal balancing module")
    manifest = registry.manifest(module_id, expected_slot="balancing")
    if manifest.version != "3.0.0" or not manifest.solver_contract:
        raise ValueError("Zonal balancing module v3.0.0 solver contract is unavailable")
    if "solver_contract" in candidate:
        raise ValueError("Zonal source study already declares a solver contract")

    acknowledgements = dict(candidate.get("maturity_acknowledgements") or {})
    prefix = f"module:{module_id}@"
    old_keys = [key for key in acknowledgements if key.startswith(prefix)]
    new_key = f"{prefix}{manifest.version}"
    if new_key in acknowledgements or len(old_keys) != 1:
        raise ValueError("Zonal source study has an unexpected module acknowledgement identity")
    old_key = old_keys[0]
    if acknowledgements.get(old_key) != "value.experimental-ack/v1":
        raise ValueError("Zonal source study has an invalid experimental acknowledgement")
    acknowledgements[new_key] = acknowledgements.pop(old_key)
    candidate["maturity_acknowledgements"] = acknowledgements
    candidate["solver_contract"] = DEFAULT_ZONAL_SOLVER_SETTINGS.to_dict()
    candidate = attach_revision_identity(candidate, registry, data_pack_manifest)
    evidence = {
        "schema_version": "value.study-execution-derivation/v1",
        "source_sha256": source_sha256,
        "reason": "zonal-module-2.0-solver-contract-migration",
        "derived_revision_sha256": candidate["revision_sha256"],
    }
    return candidate, evidence


def _change_summary(previous: Mapping[str, object], current: Mapping[str, object]) -> list[str]:
    ignored = {"name", "updated_at", "revision_sha256", "revision_number", "parent_revision_sha256", "change_summary"}
    return sorted(key for key in set(previous) | set(current) if key not in ignored and previous.get(key) != current.get(key))


def save_project_revision(project_dir: Path, candidate: Mapping[str, object], registry: ModuleRegistryV2, data_pack_manifest: Mapping[str, object], *, expected_base_revision: str | None = None) -> dict[str, object]:
    current_path = project_dir / "project.json"
    previous: dict[str, object] = {}
    if current_path.is_file():
        previous = json.loads(current_path.read_text(encoding="utf-8"))
    previous_revision = str(previous.get("revision_sha256")) if previous.get("revision_sha256") else None
    if previous_revision and expected_base_revision != previous_revision:
        raise ValueError("Project revision conflict: reload the latest project before saving changes")
    result = attach_revision_identity(candidate, registry, data_pack_manifest)
    if result["revision_sha256"] == previous_revision:
        return previous
    result["parent_revision_sha256"] = previous_revision
    result["revision_number"] = int(previous.get("revision_number", 0)) + 1
    result["change_summary"] = _change_summary(previous, result)
    result["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    revisions = project_dir / "revisions"
    revisions.mkdir(parents=True, exist_ok=True)
    revision_path = revisions / f"{result['revision_sha256']}.json"
    if not revision_path.exists():
        revision_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    project_dir.mkdir(parents=True, exist_ok=True)
    temporary = current_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(current_path)
    return result
