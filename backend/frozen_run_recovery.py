"""Review and publish independent Studies from verified canonical Run inputs.

The caller serializes publication with the existing Study lifecycle lock. This
service never starts a worker and never uses a mutable source Study as input.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Callable

from backend.frozen_input_recovery import stage_recovered_inputs
from gridform_core.frozen_input_integrity import verify_frozen_input_integrity
from gridform_core.frontend_contract import (
    EXPERIMENTAL_ACK, maturity_acknowledgement_requirements, resolve_study_draft,
)
from gridform_core.project_revision import save_project_revision
from gridform_core.run_policy import resolve_run_policy
from gridform_core.zonal_solver_contract import DEFAULT_ZONAL_SOLVER_SETTINGS


class FrozenRecoveryError(ValueError):
    def __init__(self, message: str, *, code: str = "GF_FROZEN_RECOVERY_BLOCKED", status: int = 409):
        super().__init__(message)
        self.code, self.status = code, status


def json_hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def read_object(path: Path) -> dict:
    if path.is_symlink():
        raise FrozenRecoveryError("Recovery metadata must be a regular local file")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise FrozenRecoveryError("Recovery metadata must be an object")
    return value


def configuration_identity(project: dict) -> str:
    # Names and bookkeeping are editable; data, method and scope are fixed by
    # the accepted review. Project revisions alone omit some recovery metadata.
    return json_hash({key: project.get(key) for key in (
        "data_pack_id", "start_year", "end_year", "modules", "parameters", "parameter_overrides",
        "runtime_options", "runtime_controls", "selected_extensions", "extension_parameters",
        "maturity_acknowledgements", "market_configuration", "solver_contract",
    )})


def recovery_guard(project: dict) -> dict | None:
    value = dict(project.get("extensions") or {}).get("frozen_recovery")
    if value is None:
        return None
    if not isinstance(value, dict) or value.get("schema_version") != "value.frozen-recovery-constraint/v1":
        raise FrozenRecoveryError("Invalid frozen-input recovery constraints")
    return value


def verify_recovered_configuration(project: dict, *, mode: str | None = None,
                                   execution_identity: str | None = None) -> None:
    guard = recovery_guard(project)
    if guard is None:
        return
    if configuration_identity(project) != guard.get("configuration_sha256"):
        raise FrozenRecoveryError("Recovered data, method and scope are fixed by the accepted review. Create a separate Study to change them.")
    if mode is not None and mode != guard.get("required_mode"):
        raise FrozenRecoveryError("Choose the recorded Run scope for this recovered Study")
    if execution_identity is not None and execution_identity != guard.get("accepted_execution_identity_sha256"):
        raise FrozenRecoveryError("The execution source or environment changed after recovery review. Review the source Run again.")


def verify_recovered_inputs(project: dict, base_root: Path, network_root: Path | None,
                            *, frozen: bool = False) -> None:
    guard = recovery_guard(project)
    if guard is None:
        return
    for product, root in (("base", base_root), ("network", network_root)):
        expected = dict(guard.get("products") or {}).get(product)
        if expected is None:
            if root is not None and product == "network":
                raise FrozenRecoveryError("Unexpected network product in recovered Study")
            continue
        if root is None:
            raise FrozenRecoveryError("Recovered input product is missing")
        manifest = read_object(root / "manifest.json")
        if not frozen and json_hash(manifest) != expected["manifest_sha256"]:
            raise FrozenRecoveryError("Recovered input manifest changed after review")
        bindings = manifest.get("bindings") or {}
        if set(bindings) != set(expected["roles"]):
            raise FrozenRecoveryError("Recovered input role coverage changed")
        for role, digest in expected["roles"].items():
            binding = bindings[role]
            uri = str(binding.get("uri") or "")
            path = root / uri
            if (not uri or path.is_symlink() or not path.is_file()
                    or not path.resolve().is_relative_to(root.resolve())
                    or hashlib.sha256(path.read_bytes()).hexdigest() != digest):
                raise FrozenRecoveryError(f"Recovered canonical input changed: {role}")


def _scope(status: dict, project: dict) -> dict:
    policy = resolve_run_policy(str(status.get("mode") or ""))
    declared = status.get("run_policy")
    actual = policy.to_dict(project)
    if not isinstance(declared, dict):
        raise FrozenRecoveryError("The source Run has no recorded execution scope")
    for key in ("mode", "start_year", "end_year", "periods_per_year", "total_periods"):
        if declared.get(key) != actual.get(key):
            raise FrozenRecoveryError(f"Recorded scope differs from the supported Run policy: {key}")
    return {key: actual[key] for key in ("mode", "start_year", "end_year", "periods_per_year")}


def _candidate(integrity: dict, scope: dict, recovery_mode: str, *, registry, module_catalog, dataset_slots) -> tuple[dict, dict, list]:
    source = integrity["project"]
    candidate = copy.deepcopy(source)
    for key in ("revision_sha256", "revision_number", "parent_revision_sha256", "base_revision_sha256",
                "change_summary", "module_resolution_graph", "linked_run_count", "derivation",
                "fingerprint_basis", "revision_reason"):
        candidate.pop(key, None)
    extensions = dict(candidate.get("extensions") or {})
    extensions.pop("frozen_recovery", None)
    extensions.pop("execution_bundle", None)
    candidate["extensions"] = extensions
    candidate.update(start_year=scope["start_year"], end_year=scope["end_year"])
    changes = []
    if recovery_mode == "migration":
        # Only a declared installed solver contract may replace historical
        # settings, and the entire old/new setting is exposed before consent.
        if dict(candidate.get("modules") or {}).get("balancing") == "value-zonal-redispatch-balancing":
            candidate["solver_contract"] = DEFAULT_ZONAL_SOLVER_SETTINGS.to_dict()
        acknowledgements = dict(candidate.get("maturity_acknowledgements") or {})
        for requirement in maturity_acknowledgement_requirements(registry, candidate.get("modules") or {}, candidate.get("selected_extensions") or ()):
            acknowledgements[requirement["key"]] = EXPERIMENTAL_ACK
        candidate["maturity_acknowledgements"] = acknowledgements
    for key in ("solver_contract", "maturity_acknowledgements"):
        if candidate.get(key) != source.get(key):
            changes.append({"field": key, "recorded": source.get(key), "current": candidate.get(key)})
    draft = resolve_study_draft(candidate, registry=registry, module_catalog=module_catalog,
                                base_dataset_slots=dataset_slots,
                                available_data_roles=tuple(sorted({r["role"] for r in integrity["canonical_roles"]})))
    candidate = dict(draft["normalised_project"])
    previous_graph = integrity["snapshot"].get("module_resolution_graph")
    current_graph = candidate.get("module_resolution_graph")
    if previous_graph != current_graph:
        changes.append({"field": "module_resolution_graph", "recorded": previous_graph, "current": current_graph})
    return candidate, draft, changes


def review_frozen_recovery(source_run_root: Path, recovery_mode: str, *, registry, module_catalog,
                           dataset_slots, current_execution: Callable[[], dict],
                           verify_archive: Callable[[dict], None]) -> tuple[dict, dict | None]:
    if recovery_mode not in {"strict", "migration"}:
        raise FrozenRecoveryError("Choose strict or migration recovery", status=400)
    report = {
        "schema_version": "value.frozen-recovery-review/v1", "source_run_id": source_run_root.name,
        "source_snapshot_id": None, "recovery_mode": recovery_mode, "allowed": False,
        "input_integrity": "blocked", "scope": None, "canonical_role_count": 0,
        "source_execution_identity_sha256": None, "current_execution_identity_sha256": None,
        "missing_evidence": [], "changes": [], "blocking_reasons": [],
        "limitations": ["Creates independent canonical input products and a Study only; run readiness and launch remain separate.",
                        "Recomputation starts from opening inputs. No historical checkpoint is transplanted.",
                        "Identity agreement does not imply scientific validation or bitwise numerical reproducibility."],
    }
    context = None
    try:
        integrity = verify_frozen_input_integrity(source_run_root / "input-snapshot")
        status = read_object(source_run_root / "status.json")
        if (status.get("id") != source_run_root.name or status.get("project_id") != integrity["project"].get("id")
                or status.get("input_snapshot_id") != integrity["snapshot_id"]
                or status.get("input_tree_sha256") != integrity["input_tree_sha256"]):
            raise FrozenRecoveryError("The Run status and frozen input identity do not agree")
        if status.get("status") not in {"completed", "failed", "cancelled", "archived"}:
            raise FrozenRecoveryError("Wait for the source Run to stop before reviewing recovery")
        scope = _scope(status, integrity["project"])
        report.update(input_integrity="verified", source_snapshot_id=integrity["snapshot_id"],
                      scope=scope, canonical_role_count=len(integrity["canonical_roles"]))
        current = current_execution()
        report["current_execution_identity_sha256"] = current["identity_sha256"]
        report["limitations"].extend(current.get("limitations") or [])
        if not current.get("identity_complete"):
            report["blocking_reasons"].append("The current execution has source or runtime paths that cannot be fully identified.")
        recorded_ref = dict(integrity["project"].get("extensions") or {}).get("execution_bundle")
        recorded = None
        if not isinstance(recorded_ref, dict):
            report["missing_evidence"].append("The historical Run did not bind a complete execution source and environment archive.")
        else:
            try:
                recorded = read_object(source_run_root / "execution-bundle.json")
                if json_hash(recorded) != recorded_ref.get("record_sha256") or recorded.get("identity_sha256") != recorded_ref.get("identity_sha256"):
                    raise FrozenRecoveryError("Recorded execution bundle does not match the frozen project")
                verify_archive(recorded)
                if not recorded.get("identity_complete"):
                    raise FrozenRecoveryError("The recorded execution identity has uncovered source or runtime paths")
                report["source_execution_identity_sha256"] = recorded["identity_sha256"]
                if not recorded.get("archive_complete"):
                    report["limitations"].extend(recorded.get("limitations") or [])
                    report["limitations"].append("Strict matching uses this compatible local environment; the archive has not been proved independently runnable.")
            except (OSError, ValueError) as exc:
                recorded = None
                report["missing_evidence"].append(str(exc))
        if not integrity["declaration_evidence"]["complete"]:
            report["missing_evidence"].extend(integrity["limitations"])
        candidate, draft, changes = _candidate(integrity, scope, recovery_mode, registry=registry,
                                               module_catalog=module_catalog, dataset_slots=dataset_slots)
        report["changes"] = changes
        if recorded and recorded["identity_sha256"] != current["identity_sha256"]:
            for field in ("source_sha256", "environment_sha256"):
                if recorded[field] != current[field]:
                    changes.append({"field": field, "recorded": recorded[field], "current": current[field]})
        report["blocking_reasons"].extend(str(row["message"]) for row in draft["errors"])
        if recovery_mode == "strict":
            report["blocking_reasons"].extend(report["missing_evidence"])
            if changes:
                report["blocking_reasons"].append("Recorded method or environment differs from the current execution. Use explicit migration or restore the recorded environment.")
        report["allowed"] = not report["blocking_reasons"]
        context = {"integrity": integrity, "candidate": candidate, "current_execution": current,
                   "source_status_identity": {key: status.get(key) for key in ("id", "project_id", "mode", "status", "input_snapshot_id", "input_tree_sha256", "run_policy")}}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        report["blocking_reasons"].append(str(exc))
    report["review_sha256"] = json_hash({"report": report, "candidate": context["candidate"] if context else None,
                                        "status": context["source_status_identity"] if context else None})
    return report, context


def publish_frozen_recovery(source_run_root: Path, request: dict, *, review: Callable,
                            projects_root: Path, packs_root: Path, network_packs_root: Path,
                            staging_root: Path, registry, validate_project: Callable,
                            revision_manifest: Callable, is_reserved: Callable[[str], bool],
                            save_revision: Callable = save_project_revision) -> dict:
    """Publish under the Study lock; rollback every newly owned path on error."""
    name = request.get("name")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 160 or request.get("acknowledge") is not True:
        raise FrozenRecoveryError("Review and acknowledge the changes, then provide a Study name (1–160 characters)", status=400)
    report, context = review(source_run_root, str(request.get("recovery_mode") or ""))
    if not report["allowed"] or context is None:
        raise FrozenRecoveryError("; ".join(report["blocking_reasons"]) or "Recovery review is blocked")
    if request.get("review_sha256") != report["review_sha256"]:
        raise FrozenRecoveryError("The source or execution changed since review. Review again.", code="GF_FROZEN_RECOVERY_REVIEW_STALE")
    suffix = uuid.uuid4().hex[:16]
    project_id, base_id = f"recovered-{suffix}", f"recovered-base-{suffix}"
    network_id = f"recovered-network-{suffix}" if context["integrity"]["network_manifest"] else None
    if is_reserved(project_id):
        raise FrozenRecoveryError("Recovery Study ID is reserved")
    stage = stage_recovered_inputs(source_run_root, staging_root, base_pack_id=base_id,
                                   network_pack_id=network_id, source_snapshot_id=report["source_snapshot_id"])
    owned = []
    try:
        # The staging helper copied verified bytes, never hardlinks to history.
        for relative, entry in stage["inventory"].items():
            path = stage["stage_root"] / relative
            if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
                raise FrozenRecoveryError("Staged recovery inputs changed before publication")
        candidate = copy.deepcopy(context["candidate"])
        candidate.update(id=project_id, name=name.strip(), data_pack_id=base_id)
        if network_id:
            candidate.setdefault("market_configuration", {})["network_pack_id"] = network_id
        for product, source, destination in (("base", stage["base_root"], packs_root / base_id),
                                               ("network", stage["network_root"], network_packs_root / str(network_id))):
            if source is None:
                continue
            if destination.exists():
                raise FrozenRecoveryError("An independent recovery product already exists")
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.rename(source, destination)
            owned.append(destination)
        validation = validate_project(candidate)
        if not validation["valid"]:
            raise FrozenRecoveryError("; ".join(validation["errors"]))
        if configuration_identity(candidate) != configuration_identity(validation["normalised_project"]):
            raise FrozenRecoveryError("Validation changed the reviewed method or scope. Review the source Run again.")
        candidate = dict(validation["normalised_project"])
        guard = {"schema_version": "value.frozen-recovery-constraint/v1",
                 "source_run_id": source_run_root.name, "source_snapshot_id": report["source_snapshot_id"],
                 "source_input_tree_sha256": context["integrity"]["input_tree_sha256"],
                 "recovery_mode": report["recovery_mode"], "review_sha256": report["review_sha256"],
                 "required_mode": report["scope"]["mode"], "scope": report["scope"],
                 "accepted_execution_identity_sha256": report["current_execution_identity_sha256"],
                 "source_execution_identity_sha256": report["source_execution_identity_sha256"],
                 "missing_evidence": report["missing_evidence"], "changes": report["changes"],
                 "products": {}}
        for product, manifest in (("base", stage["base_manifest"]), ("network", stage["network_manifest"])):
            if manifest is not None:
                guard["products"][product] = {"manifest_sha256": json_hash(manifest),
                                               "roles": {role: row["sha256"] for role, row in manifest["bindings"].items()}}
        guard["configuration_sha256"] = configuration_identity(candidate)
        candidate.setdefault("extensions", {})["frozen_recovery"] = guard
        project_stage = stage["stage_root"] / "study"
        saved = save_revision(project_stage, candidate, registry, revision_manifest(candidate, stage["base_manifest"]))
        # Final source check also notices byte mutation during long validation.
        final = verify_frozen_input_integrity(source_run_root / "input-snapshot")
        if final["snapshot_id"] != report["source_snapshot_id"]:
            raise FrozenRecoveryError("Source snapshot changed while publishing recovery")
        destination = projects_root / project_id
        if destination.exists():
            raise FrozenRecoveryError("Independent recovery Study already exists")
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.rename(project_stage, destination)
        owned.append(destination)
        return {"schema_version": "value.frozen-recovery-created/v1", "source_run_id": source_run_root.name,
                "source_snapshot_id": report["source_snapshot_id"], "project": saved, "run_started": False,
                "mode": report["scope"]["mode"]}
    except Exception:
        for path in reversed(owned):
            shutil.rmtree(path, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(stage["stage_root"], ignore_errors=True)
