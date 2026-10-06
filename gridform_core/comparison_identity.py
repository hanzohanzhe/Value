"""Recorded frozen identities for comparison, independent of today's registry.

This is an evidence review, not verification of a historical runtime or a causal
experiment. Missing or inconsistent records never establish controlled inputs.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from collections.abc import Mapping, Sequence

from .run_policy import scope_runs_extensions

DIMENSIONS = ("data", "method", "config", "years", "scope")
# The methodology profile is a scientific parameter but belongs to the method
# dimension only, so a profile-only change is an isolated method change
# (plan X0 3.5).
PROFILE_PARAMETER = "methodology.profile"


def _without_profile(values: object) -> object:
    if not isinstance(values, Mapping):
        return values
    return {key: value for key, value in values.items() if key != PROFILE_PARAMETER}


def recorded_methodology(root: Path, resolved: Mapping | None) -> tuple[dict | None, str | None]:
    """The method-dimension methodology of a run, or (None, reason).

    New runs carry ``extensions.methodology`` in resolved-run.json.  A run
    produced before methodology profiles existed is ``unrecorded`` and is
    identified by its execution bundle; without one the dimension is unknown.
    """

    extensions = resolved.get("extensions") if isinstance(resolved, Mapping) else None
    record = extensions.get("methodology") if isinstance(extensions, Mapping) else None
    if isinstance(record, Mapping):
        keys = ("profile_id", "profile_version", "profile_definition_sha256", "applied_corrections_sha256")
        if all(isinstance(record.get(key), str) and record.get(key) for key in keys):
            return {key: record[key] for key in keys}, None
        return None, "methodology_record_incomplete"
    bundle = _read(root / "execution-bundle.json")
    identity = bundle.get("identity_sha256") if isinstance(bundle, Mapping) else None
    if _sha(identity):
        return {"profile_id": "unrecorded", "execution_identity_sha256": str(identity).lower()}, None
    return None, "methodology_unrecorded_without_execution_bundle"


def _read(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _sha(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value.lower())


def build_comparison_identity(root: Path, status: Mapping, resolved: Mapping) -> dict:
    snapshot = _read(root / "input-snapshot/snapshot.json")
    project = _read(root / "input-snapshot/project.json")
    identity = {key: None for key in DIMENSIONS}
    reasons = {}
    # F-D2 (DECISIONS A16-3): a market-step-only scope (the one-day lesson)
    # never executes extension hooks.  Extensions recorded in such a Run are
    # kept as audit evidence but are not part of its method or configuration,
    # so they never make two otherwise identical lessons a method change.
    extensions_execute = scope_runs_extensions(status.get("mode"))
    non_executed_extensions: list[str] = []
    if not isinstance(snapshot, Mapping) or not isinstance(project, Mapping):
        return {"schema_version": "value.comparison-identity/v1", "dimensions": identity,
                "unknown_reasons": {key: "frozen_snapshot_or_project_missing" for key in DIMENSIONS}}
    conflicts = (
        (status.get("project_id") is not None and project.get("id") is not None and status["project_id"] != project["id"])
        or any(status.get(status_key) is not None and snapshot.get(snapshot_key) is not None
               and str(status[status_key]).lower() != str(snapshot[snapshot_key]).lower()
               for status_key, snapshot_key in (("input_snapshot_id", "snapshot_id"), ("input_tree_sha256", "input_tree_sha256")))
    )
    if conflicts or snapshot.get("state") != "ready" or _hash(project) != str(snapshot.get("project_sha256") or "").lower():
        return {"schema_version": "value.comparison-identity/v1", "dimensions": identity,
                "unknown_reasons": {key: "frozen_project_identity_invalid" for key in DIMENSIONS}}

    try:
        objects = snapshot.get("objects")
        if not isinstance(objects, list) or not objects:
            raise ValueError("frozen_objects_missing")
        data = {}
        for directory in ("pack", "network-pack"):
            rows = [row for row in objects if isinstance(row, Mapping) and row.get("pack_directory", "pack") == directory]
            required = directory == "pack" or snapshot.get("network_pack_manifest_sha256") is not None
            if not required and not rows:
                continue
            pack = _read(root / "input-snapshot" / directory / "manifest.json")
            manifest_key = "pack_manifest_sha256" if directory == "pack" else "network_pack_manifest_sha256"
            if not isinstance(pack, Mapping) or _hash(pack) != str(snapshot.get(manifest_key) or "").lower():
                raise ValueError("frozen_pack_manifest_identity_invalid")
            bindings = pack.get("bindings")
            if not isinstance(bindings, Mapping) or not bindings or len(rows) != len(bindings):
                raise ValueError("frozen_roles_incomplete")
            indexed = {row.get("role"): row for row in rows}
            if len(indexed) != len(rows) or set(indexed) != set(bindings):
                raise ValueError("frozen_roles_inconsistent")
            roles = {}
            for role, binding in bindings.items():
                row = indexed[role]
                if not isinstance(binding, Mapping) or not _sha(row.get("sha256")) or str(row.get("sha256") or "").lower() != str(binding.get("sha256") or "").lower():
                    raise ValueError("frozen_role_hash_missing_or_inconsistent")
                roles[role] = {"sha256": row["sha256"].lower(), **{key: binding.get(key) for key in ("format", "unit", "transformation_id")}}
            data[directory] = {"roles": roles, "metadata": {key: pack.get(key) for key in ("schema_version", "country", "timezone", "resolution", "calendar")}}
        if any(not isinstance(row, Mapping) or row.get("pack_directory", "pack") not in data for row in objects):
            raise ValueError("unrecognized_frozen_data_product")
        identity["data"] = data
    except (ValueError, TypeError) as exc:
        reasons["data"] = str(exc)

    try:
        modules = snapshot.get("modules")
        if not isinstance(modules, list) or not modules:
            raise ValueError("frozen_module_identity_missing")
        normalized = {}
        for row in modules:
            if not isinstance(row, Mapping) or any(not row.get(k) for k in ("slot", "module_id", "module_version", "contract_version", "entry_point")) or not _sha(row.get("source_sha256")):
                raise ValueError("frozen_module_identity_incomplete")
            slot = row["slot"]
            if slot in normalized:
                raise ValueError("duplicate_module_slot")
            normalized[slot] = {key: row[key] for key in ("module_id", "module_version", "contract_version", "entry_point", "source_sha256")}
        for row in normalized.values():
            row["source_sha256"] = row["source_sha256"].lower()
        declared = project.get("modules")
        if not isinstance(declared, Mapping) or any(normalized.get(slot, {}).get("module_id") != module_id for slot, module_id in declared.items()):
            raise ValueError("frozen_module_selection_inconsistent")
        # Resolved module selections cross-check execution when present; they do
        # not replace the source hashes recorded in the frozen manifest.
        actual = resolved.get("modules") if isinstance(resolved, Mapping) else None
        if isinstance(actual, Mapping):
            for slot, row in actual.items():
                if not isinstance(row, Mapping) or slot not in normalized or any(row.get(key) != normalized[slot][key] for key in ("module_id", "module_version", "contract_version")):
                    raise ValueError("resolved_module_selection_inconsistent")
        extensions = snapshot.get("extension_graph")
        if project.get("selected_extensions") and not isinstance(extensions, Mapping):
            raise ValueError("frozen_extension_identity_missing")
        if isinstance(extensions, Mapping):
            extension_rows = extensions.get("extensions")
            if not isinstance(extension_rows, list) or any(not isinstance(row, Mapping) or not row.get("id") or not row.get("version") or not _sha(row.get("manifest_sha256")) for row in extension_rows):
                raise ValueError("frozen_extension_identity_incomplete")
            if set(project.get("selected_extensions") or []) != {row["id"] for row in extension_rows}:
                raise ValueError("frozen_extension_selection_inconsistent")
            extensions = {key: value for key, value in extensions.items() if key != "graph_sha256"}
            extensions["extensions"] = sorted(({**row, "manifest_sha256": row["manifest_sha256"].lower()} for row in extension_rows), key=lambda row: row["id"])
            if not extensions_execute:
                non_executed_extensions = [row["id"] for row in extensions["extensions"]]
                extensions = None
        methodology, methodology_reason = recorded_methodology(root, resolved)
        if methodology is None:
            raise ValueError(str(methodology_reason))
        identity["method"] = {"modules": normalized, "extensions": extensions, "methodology": methodology}
    except (ValueError, TypeError) as exc:
        reasons["method"] = str(exc)

    if isinstance(resolved, Mapping) and isinstance(resolved.get("scientific_parameters"), Mapping) and isinstance(resolved.get("runtime_controls"), Mapping):
        raw_market = project.get("market_configuration")
        malformed = (raw_market is not None and not isinstance(raw_market, Mapping)) or any(
            project.get(key) is not None and not isinstance(project[key], Mapping)
            for key in ("parameters", "parameter_overrides", "runtime_options", "runtime_controls", "extension_parameters", "solver_contract")
        )
        market = dict(raw_market) if isinstance(raw_market, Mapping) else {}
        market.pop("network_pack_id", None)
        identity["config"] = {
            "parameters": _without_profile(project.get("parameters") or project.get("parameter_overrides") or {}),
            "runtime_options": project.get("runtime_options") or project.get("runtime_controls") or {},
            "scientific_parameters": _without_profile(dict(resolved["scientific_parameters"])),
            "runtime_controls": dict(resolved["runtime_controls"]),
            "extension_parameters": (project.get("extension_parameters") or {}) if extensions_execute else {},
            "market_configuration": market,
            "solver_contract": project.get("solver_contract"),
        }
        if malformed:
            identity["config"] = None
            reasons["config"] = "frozen_configuration_malformed"
    else:
        reasons["config"] = "resolved_effective_configuration_missing"
    policy = status.get("run_policy")
    if isinstance(policy, Mapping) and all(isinstance(policy.get(key), int) and not isinstance(policy.get(key), bool) for key in ("start_year", "end_year")) and policy["start_year"] <= policy["end_year"]:
        identity["years"] = {"start_year": policy["start_year"], "end_year": policy["end_year"]}
    else:
        reasons["years"] = "executed_year_range_missing"
    if isinstance(policy, Mapping) and status.get("mode") and isinstance(policy.get("periods_per_year"), int) and not isinstance(policy["periods_per_year"], bool) and policy["periods_per_year"] > 0:
        identity["scope"] = {"mode": status["mode"], "periods_per_year": policy["periods_per_year"], "annual_economics_candidate": policy.get("annual_economics_candidate"), "scientific_baseline_candidate": policy.get("scientific_baseline_candidate")}
    else:
        reasons["scope"] = "executed_scope_missing"
    record = {"schema_version": "value.comparison-identity/v1", "dimensions": identity, "unknown_reasons": reasons}
    if non_executed_extensions:
        record["non_executed_extensions"] = {
            "reason_code": "extensions_not_executed_in_scope",
            "extensions": non_executed_extensions,
        }
    return record


def review_comparison_identities(summaries: Sequence[Mapping]) -> dict:
    dimensions = {}
    for key in DIMENSIONS:
        values = []
        for row in summaries:
            record = row.get("comparison_identity")
            dims = record.get("dimensions") if isinstance(record, Mapping) and record.get("schema_version") == "value.comparison-identity/v1" else None
            values.append(dims.get(key) if isinstance(dims, Mapping) else None)
        state = "unknown" if any(value is None for value in values) else "same" if len({_hash(value) for value in values}) == 1 else "changed"
        dimensions[key] = {"status": state, "values": values}
    changed = [key for key, row in dimensions.items() if row["status"] == "changed"]
    unknown = [key for key, row in dimensions.items() if row["status"] == "unknown"]
    return {"schema_version": "value.comparison-review/v1", "status": "unknown" if unknown else "verified", "evidence_complete": not unknown,
            "isolated_change_allowed": not unknown and len(changed) == 1,
            "dimensions": dimensions, "changed_dimensions": changed, "unknown_dimensions": unknown,
            "warning": "Recorded frozen evidence is incomplete; isolated attribution is blocked." if unknown else "Multiple recorded dimensions differ; interpret differences jointly." if len(changed) > 1 else None}
