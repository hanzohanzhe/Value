"""Create independent Studies only from identity-verified saved revisions."""

from __future__ import annotations

import copy
import json
import os
import re
import shutil
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable, Mapping

from gridform_core.project_revision import project_fingerprint, save_project_revision
from gridform_core.data_import import sha256_file
from gridform_core.frontend_contract import solver_contract_acknowledgement_key

from backend.module_authoring import module_candidate_identity


SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
REVISION = re.compile(r"^[0-9a-f]{64}$")
DERIVED_FIELDS = {
    "revision_sha256", "revision_number", "parent_revision_sha256",
    "base_revision_sha256", "change_summary", "module_resolution_graph",
    "linked_run_count", "derivation",
}


class StudyDerivationError(ValueError):
    def __init__(self, code: str, message: str, status: int = 409,
                 validation: Mapping[str, object] | None = None):
        self.code, self.status, self.validation = code, status, validation
        super().__init__(message)


def _method_candidate(source: Mapping[str, object], request: Mapping[str, object],
                      registry: object) -> tuple[str, str, dict[str, object]]:
    """Accept one reviewed replacement and only its explicit acknowledgements."""
    slot, module_id = request.get("slot"), request.get("module_id")
    identity = request.get("candidate_identity_sha256")
    modules = dict(source.get("modules") or {})
    if (not isinstance(slot, str) or slot not in modules
            or not isinstance(module_id, str) or not SAFE_ID.fullmatch(module_id)
            or not isinstance(identity, str) or not REVISION.fullmatch(identity)
            or modules[slot] == module_id):
        raise StudyDerivationError(
            "GF_STUDY_METHOD_REQUEST_INVALID",
            "Choose a different module for one existing slot and review its exact identity.", 400,
        )
    try:
        manifest = registry.manifest(module_id, expected_slot=slot)
        current_identity = module_candidate_identity(registry, module_id, expected_slot=slot)
    except (KeyError, TypeError, ValueError, OSError) as exc:
        raise StudyDerivationError("GF_STUDY_METHOD_UNAVAILABLE", str(exc), 400) from exc
    if current_identity != identity:
        raise StudyDerivationError(
            "GF_STUDY_METHOD_IDENTITY_CHANGED",
            "The candidate module changed after review; reload its manifest and source before saving.",
        )
    supplied = request.get("maturity_acknowledgements", {})
    acknowledgements = copy.deepcopy(dict(source.get("maturity_acknowledgements") or {}))
    allowed_keys = {
        f"module:{manifest.id}@{manifest.version}",
        solver_contract_acknowledgement_key(manifest.id, manifest.version),
    }
    # A source Study may retain acknowledgements for previously selected
    # modules. The replacement must be acknowledged in this request again.
    for key in allowed_keys:
        acknowledgements.pop(key, None)
    if (not isinstance(supplied, dict)
            or any(not isinstance(key, str) or not isinstance(value, str)
                   or key not in allowed_keys and acknowledgements.get(key) != value
                   for key, value in supplied.items())):
        raise StudyDerivationError(
            "GF_STUDY_METHOD_ACK_INVALID",
            "Only the new module's explicit acknowledgements can change in this method comparison.", 400,
        )
    acknowledgements.update(supplied)
    return slot, module_id, acknowledgements


def _verify_method_graph(saved: Mapping[str, object], graph: object,
                         slot: str, module_id: str) -> None:
    if not isinstance(graph, dict):
        raise StudyDerivationError("GF_STUDY_DERIVATION_METHOD_DRIFT", "The new method has no resolved graph.")
    previous = saved.get("modules")
    current = graph.get("modules")
    if (not isinstance(previous, dict) or not isinstance(current, dict)
            or set(previous) != set(current)
            or any(current[key] != previous[key] for key in previous if key != slot)
            or not isinstance(current.get(slot), dict)
            or current[slot].get("module_id") != module_id
            or {key: value for key, value in saved.items() if key not in {"modules", "graph_sha256"}}
            != {key: value for key, value in graph.items() if key not in {"modules", "graph_sha256"}}):
        raise StudyDerivationError(
            "GF_STUDY_METHOD_SCOPE_CHANGED",
            "This replacement also changes another module or extension identity. Create a separate multi-method Study instead.", 400,
        )


def _read(path: Path, label: str) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("expected an object")
        return value
    except (OSError, ValueError) as exc:
        raise StudyDerivationError(
            "GF_STUDY_DERIVATION_EVIDENCE_MISSING",
            f"Cannot verify {label}; restore or review its saved evidence.",
        ) from exc


def _verify_bound_inputs(manifest: Mapping[str, object], pack_root: Path) -> None:
    overlay = dict(manifest.get("network_overlay") or {})
    overlay_bindings = dict(overlay.get("bindings") or {})
    for role, binding in dict(manifest.get("bindings") or {}).items():
        if not isinstance(binding, Mapping):
            raise ValueError(f"Source role {role} has invalid binding evidence")
        root = pack_root
        if role in overlay_bindings:
            network_id = str(overlay.get("id") or "")
            if not SAFE_ID.fullmatch(network_id):
                raise ValueError("Invalid source network-pack identity")
            root = pack_root.parent.parent / "data-workbench" / "installed-packs" / network_id
        root = root.resolve()
        uri = str(binding.get("uri") or "")
        if not uri:
            raise ValueError(f"Source role {role} has no file URI")
        path = (root / uri).resolve()
        path.relative_to(root)
        if sha256_file(path) != binding.get("sha256"):
            raise ValueError(f"Source role {role} does not match its recorded checksum")


def derive_study(
    source_id: str,
    request: Mapping[str, object],
    *,
    projects_root: Path,
    packs_root: Path,
    registry: object,
    validate_project: Callable,
    revision_manifest: Callable,
    is_reserved: Callable[[str], bool],
    save_revision: Callable = save_project_revision,
    suffix_factory: Callable[[], str] = lambda: uuid.uuid4().hex[:10],
) -> dict[str, object]:
    """Caller holds the Study lifecycle lock. Never runs or mutates the source."""

    intent = request.get("intent")
    name = request.get("name")
    pack_id = request.get("data_pack_id")
    expected = request.get("source_revision_sha256")
    if (not isinstance(intent, str) or intent not in {"reproduce", "data", "edit_module"}
            or not isinstance(name, str) or not name.strip()
            or not isinstance(pack_id, str) or not SAFE_ID.fullmatch(pack_id)
            or not isinstance(expected, str) or not REVISION.fullmatch(expected)
            or not SAFE_ID.fullmatch(source_id)):
        raise StudyDerivationError(
            "GF_STUDY_DERIVATION_REQUEST_INVALID",
            "Provide an intent, name, safe data-pack ID and exact source revision.", 400,
        )
    source_path = projects_root / source_id / "project.json"
    if not source_path.is_file():
        raise StudyDerivationError(
            "GF_STUDY_DERIVATION_SOURCE_NOT_FOUND",
            "Select an active saved Study; restore a trashed Study first.", 404,
        )
    source = _read(source_path, "source Study")
    if source.get("id") != source_id or source.get("revision_sha256") != expected:
        raise StudyDerivationError(
            "GF_STUDY_DERIVATION_STALE_REVISION",
            "The source Study revision changed; reload it before deriving a Study.",
        )
    record = _read(projects_root / source_id / "revisions" / f"{expected}.json",
                   "immutable source revision")
    if record.get("id") != source_id or record.get("revision_sha256") != expected:
        raise StudyDerivationError(
            "GF_STUDY_DERIVATION_EVIDENCE_MISSING", "Source revision identity is inconsistent.",
        )
    source_pack_id = source.get("data_pack_id")
    if not isinstance(source_pack_id, str) or not SAFE_ID.fullmatch(source_pack_id):
        raise StudyDerivationError("GF_STUDY_DERIVATION_EVIDENCE_MISSING", "Source data-pack identity is invalid.")
    if (intent in {"reproduce", "edit_module"} and pack_id != source_pack_id
            or intent == "data" and pack_id == source_pack_id):
        raise StudyDerivationError(
            "GF_STUDY_DERIVATION_PACK_MISMATCH",
            "Reproduction and method comparisons keep the source pack; adding data requires a different pack.", 400,
        )
    if not (packs_root / pack_id / "manifest.json").is_file():
        raise StudyDerivationError("GF_DATA_PACK_UNKNOWN", "The selected data pack is not installed.", 404)
    source_pack = _read(packs_root / source_pack_id / "manifest.json", "source data pack")
    selected_pack = _read(packs_root / pack_id / "manifest.json", "selected data pack")
    if source_pack.get("id") != source_pack_id or selected_pack.get("id") != pack_id:
        raise StudyDerivationError("GF_STUDY_DERIVATION_EVIDENCE_MISSING", "Data-pack manifest identity is inconsistent.")
    try:
        source_manifest = revision_manifest(source, source_pack)
        if (project_fingerprint(source, registry, source_manifest) != expected
                or project_fingerprint(record, registry, source_manifest) != expected):
            raise StudyDerivationError(
                "GF_STUDY_DERIVATION_SOURCE_DRIFT",
                "Source inputs or scientific configuration drifted from the saved revision; review and save a new revision first.",
            )
        saved_graph = record.get("module_resolution_graph")
        if not isinstance(saved_graph, dict) or not saved_graph.get("graph_sha256"):
            raise StudyDerivationError(
                "GF_STUDY_DERIVATION_EVIDENCE_MISSING",
                "The saved revision has no module identity evidence; review and save a new revision first.",
            )
        current_graph = registry.resolve_selection(
            dict(record.get("modules") or {}),
            selected_extensions=tuple(record.get("selected_extensions") or ()),
            extension_parameters=dict(record.get("extension_parameters") or {}),
            available_data_roles=tuple(sorted(dict(source_manifest.get("bindings") or {}))),
        ).to_dict()
        if current_graph != saved_graph or source.get("module_resolution_graph") != saved_graph:
            raise StudyDerivationError(
                "GF_STUDY_DERIVATION_METHOD_DRIFT",
                "Current module identities differ from the source revision; review and save a new revision first.",
            )
        _verify_bound_inputs(source_manifest, packs_root / source_pack_id)
    except StudyDerivationError:
        raise
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise StudyDerivationError("GF_STUDY_DERIVATION_SOURCE_DRIFT", f"Cannot verify the source method and inputs: {exc}") from exc

    stem = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")[:100] or "study"
    new_id = f"{stem}-{suffix_factory()}"
    if not SAFE_ID.fullmatch(new_id) or (projects_root / new_id).exists() or is_reserved(new_id):
        raise StudyDerivationError("GF_STUDY_DERIVATION_ID_CONFLICT", "Generated Study ID is reserved; retry with a new ID.")
    candidate = {key: copy.deepcopy(value) for key, value in source.items() if key not in DERIVED_FIELDS}
    candidate.update(id=new_id, name=name.strip(), data_pack_id=pack_id,
                     updated_at=datetime.now().astimezone().isoformat(timespec="seconds"))
    slot = module_id = None
    if intent == "edit_module":
        slot, module_id, acknowledgements = _method_candidate(source, request, registry)
        candidate["modules"][slot] = module_id
        candidate["maturity_acknowledgements"] = acknowledgements
    before_validation = copy.deepcopy(candidate)
    validation = validate_project(candidate)
    if not validation.get("valid"):
        raise StudyDerivationError(
            "GF_STUDY_DERIVATION_INVALID",
            str((validation.get("errors") or ["The derived Study is invalid."])[0]),
            400, validation,
        )
    candidate.update(copy.deepcopy(validation.get("normalised_project") or {}))
    graph = candidate.get("module_resolution_graph")
    if intent == "edit_module":
        if ({key: value for key, value in candidate.items() if key != "module_resolution_graph"}
                != before_validation):
            raise StudyDerivationError(
                "GF_STUDY_METHOD_SCOPE_CHANGED",
                "The replacement requires other configuration changes. Keep this comparison to one slot, or create a separate multi-method Study.", 400,
            )
        _verify_method_graph(saved_graph, graph, slot, module_id)
        # Validation can resolve implementations. Re-check the reviewed identity
        # immediately before saving, so a changed source cannot be accepted.
        _method_candidate(source, request, registry)
    elif not isinstance(graph, dict) or graph != saved_graph:
        raise StudyDerivationError("GF_STUDY_DERIVATION_METHOD_DRIFT", "The new pack must preserve the source module graph.")
    # Metadata such as teaching origin remains available, even if a validator
    # returns only its normalised scientific fields.
    candidate["derivation"] = {
        "schema_version": "value.study-derivation/v1", "intent": intent,
        "source_study_id": source_id, "source_revision_sha256": expected,
        "source_data_pack_id": source_pack_id,
        "source_module_graph_sha256": saved_graph["graph_sha256"],
        "created_at": candidate["updated_at"],
    }
    if intent == "edit_module":
        candidate["derivation"]["method_change"] = {
            "slot": slot, "source_module_id": source["modules"][slot],
            "module_id": module_id,
            "candidate_identity_sha256": request["candidate_identity_sha256"],
        }
    destination = projects_root / new_id
    staging: Path | None = None
    owns_destination = False
    try:
        manifest = revision_manifest(candidate, selected_pack)
        projects_root.mkdir(parents=True, exist_ok=True)
        # Exclusive reservation prevents overwriting any pre-existing Study.
        destination.mkdir()
        owns_destination = True
        staging = Path(tempfile.mkdtemp(prefix=".study-derive-", dir=projects_root.parent))
        saved = save_revision(staging, candidate, registry, manifest)
        if intent == "edit_module":
            # The lifecycle lock excludes API writes, but authors can still edit
            # local source files. Do not promote evidence that changed while
            # validation and revision persistence were in progress.
            fresh_pack = _read(packs_root / source_pack_id / "manifest.json", "source data pack")
            fresh_manifest = revision_manifest(source, fresh_pack)
            if _read(source_path, "source Study") != source or fresh_manifest != source_manifest:
                raise StudyDerivationError("GF_STUDY_DERIVATION_SOURCE_DRIFT", "Source Study or inputs changed while saving; reload and review.")
            _verify_bound_inputs(fresh_manifest, packs_root / source_pack_id)
            resolution_args = {
                "selected_extensions": tuple(record.get("selected_extensions") or ()),
                "extension_parameters": dict(record.get("extension_parameters") or {}),
                "available_data_roles": tuple(sorted(dict(fresh_manifest.get("bindings") or {}))),
            }
            if registry.resolve_selection(dict(record.get("modules") or {}), **resolution_args).to_dict() != saved_graph:
                raise StudyDerivationError("GF_STUDY_DERIVATION_METHOD_DRIFT", "A source module changed while saving; reload and review.")
            _method_candidate(source, request, registry)
            fresh_graph = registry.resolve_selection(dict(candidate["modules"]), **resolution_args).to_dict()
            if fresh_graph != graph or saved.get("module_resolution_graph") != graph:
                raise StudyDerivationError("GF_STUDY_DERIVATION_METHOD_DRIFT", "The candidate method graph changed while saving; reload and review.")
        os.replace(staging, destination)
        staging = None
    except (OSError, KeyError, TypeError, ValueError) as exc:
        if staging is not None:
            shutil.rmtree(staging)
        if owns_destination:
            destination.rmdir()
        if isinstance(exc, StudyDerivationError):
            raise
        raise StudyDerivationError("GF_STUDY_DERIVATION_SAVE_FAILED", f"The derived Study was not saved: {exc}") from exc
    return {"ok": True, "project": saved, "validation": validation, "run_started": False}
