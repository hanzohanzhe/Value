"""Canonical, append-only research-project revision identities."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Mapping

from .frontend_contract import validate_project_solver_contract
from .legacy_module_ids import LEGACY_MODULE_IDS
from .doctoral_weather import uses_doctoral_weather, weather_execution_identity
from .v2.module_manifest import ModuleRegistryV2
from .zonal_solver_contract import (
    DEFAULT_ZONAL_SOLVER_SETTINGS,
    solver_contract_generation,
    validate_recorded_solver_settings,
)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


FINGERPRINT_BASIS_SCHEMA = "value.project-fingerprint-basis/v1"
# Why a revision was appended (X0 S11, Q13).  Code-only changes are appended
# automatically; method or data changes only after the user confirmed the diff.
REVISION_REASONS = (
    "user-save",
    "code-identity-upgrade",
    "environment-reidentify",
    "method-upgrade-confirmed",
    "data-change-confirmed",
    "basis-reestablished-confirmed",
)
# Bookkeeping fields of a saved revision; never part of the Study content.
REVISION_BOOKKEEPING_FIELDS = (
    "revision_sha256", "revision_number", "parent_revision_sha256", "change_summary",
    "fingerprint_basis", "revision_reason",
)


def canonical_project_payload(
    project: Mapping[str, object],
    registry: ModuleRegistryV2,
    data_pack_manifest: Mapping[str, object],
    *,
    module_version_overrides: Mapping[str, tuple[str, str]] | None = None,
    include_methodology: bool = True,
    module_resolution_graph: Mapping[str, object] | None = None,
    recorded_solver_contract: bool = False,
) -> dict[str, object]:
    """The canonical identity payload of a Study revision.

    ``module_version_overrides`` (module id -> (version, contract version))
    ``include_methodology=False``, ``module_resolution_graph`` (the graph
    stored in project.json, used instead of resolving the current one) and
    ``recorded_solver_contract=True`` (a historical v2/v3 zonal solver
    contract is read as recorded instead of being refused, P0-8 S5) exist
    only to reconstruct the payload of a revision saved before X0 S11
    (pre-profile, 35aadb3 module versions and module source hashes); see
    :mod:`gridform_core.revision_migration`.  A payload built that way is an
    identity record only: it is never saved or executed.
    """

    modules = dict(project.get("modules") or {})  # type: ignore[arg-type]
    psm_id = str(modules.get("psm") or "")
    if psm_id:
        psm = registry.manifest(psm_id, expected_slot="psm")
        if "storage.bid-cost-function" in psm.requires_capabilities:
            modules.setdefault("storage_cost", "dynamic-annual-storage-cost")
    overrides = dict(module_version_overrides or {})
    module_versions = {
        slot: {
            "module_id": module_id,
            "version": overrides[module_id][0] if module_id in overrides else registry.manifest(module_id, expected_slot=slot).version,
            "contract_version": overrides[module_id][1] if module_id in overrides else registry.manifest(module_id, expected_slot=slot).contract_version,
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
    if selected_extensions and module_resolution_graph is not None:
        result["module_resolution_graph"] = json.loads(json.dumps(dict(module_resolution_graph)))
    elif selected_extensions:
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
    stored_contract = project.get("solver_contract")
    if (
        recorded_solver_contract
        and isinstance(stored_contract, Mapping)
        and solver_contract_generation(stored_contract) in {"v2", "v3"}
    ):
        # The hash a v2/v3 revision was saved with (X0 S11 reconstruction
        # after the P0-8 v4 contract): the historical contract as recorded,
        # which its own generation canonicalised to the same values.
        solver_contract = validate_recorded_solver_settings(stored_contract)
    else:
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
    if include_methodology:
        # The methodology profile decides how the Study is computed, so it is
        # part of the revision identity (X0 S11, Q13): a Study saved before
        # profiles existed, or under another catalogue, no longer matches and
        # is classified by revision_migration instead of re-identified.
        from .methodology import resolve_project_methodology

        result["methodology"] = resolve_project_methodology(project).identity()
    return result


def fingerprint_basis(project: Mapping[str, object], registry: ModuleRegistryV2, data_pack_manifest: Mapping[str, object]) -> dict[str, object]:
    """What a revision hash was computed from, stored with the revision (X0 S11)."""

    from .methodology import resolve_project_methodology

    payload = canonical_project_payload(project, registry, data_pack_manifest)
    return {
        "schema_version": FINGERPRINT_BASIS_SCHEMA,
        "revision_sha256": hashlib.sha256(_canonical_bytes(payload)).hexdigest(),
        "payload": payload,
        "applied_correction_ids": list(resolve_project_methodology(project).applied_correction_ids),
        # Semantic records (id, track, scope, affects) so a later catalogue can
        # tell a redefined correction from a presentation-only edit.
        "applied_corrections": resolve_project_methodology(project).applied_correction_records(),
    }


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
    legacy_ids = LEGACY_MODULE_IDS

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
    # The derivation always targets the registered module and its current
    # solver contract (v4 since P0-8); historical contracts are never minted.
    if not manifest.solver_contract:
        raise ValueError(
            f"Zonal balancing module v{manifest.version} solver contract is unavailable"
        )
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
    ignored = {"name", "updated_at", *REVISION_BOOKKEEPING_FIELDS}
    return sorted(key for key in set(previous) | set(current) if key not in ignored and previous.get(key) != current.get(key))


def save_project_revision(project_dir: Path, candidate: Mapping[str, object], registry: ModuleRegistryV2, data_pack_manifest: Mapping[str, object], *, expected_base_revision: str | None = None, revision_reason: str = "user-save") -> dict[str, object]:
    if revision_reason not in REVISION_REASONS:
        raise ValueError(f"Unknown revision reason {revision_reason!r}")
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
    # Every revision written from now on records what its hash was computed
    # from and why it was appended (X0 S11), so a later code or method change
    # can be classified instead of guessed.
    result["fingerprint_basis"] = fingerprint_basis(candidate, registry, data_pack_manifest)
    result["revision_reason"] = revision_reason
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
