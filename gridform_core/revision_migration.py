"""Classify and migrate saved Study revisions after code or method changes (X0 S11, Q13).

A saved Study carries ``revision_sha256``.  When the installed code computes a
different hash for the same Study, :func:`classify_revision_mismatch` explains
why, by comparing the revision's recorded ``fingerprint_basis`` (written by
every save since X0 S11) with the current canonical payload:

=========================  ===============================================  =========================
classification             cause                                            handling
=========================  ===============================================  =========================
code_identity_upgrade      module version bumps without
                           ``requires_user_opt_in`` (VERSION_LEDGER), same
                           contract; identity-only corrections             appended automatically
environment_reidentify     dispatch weather adapter identity only           appended automatically
method_upgrade_required    opt-in module upgrade, contract or solver
                           contract change, methodology first written or
                           changed, numeric corrections added               explicit UI confirmation
data_changed               same data pack id, different content            explicit UI confirmation
content_changed            the Study's own fields no longer match           refused: save normally
unverifiable               no basis and the 35aadb3 payload cannot be
                           reconstructed                                    explicit UI confirmation
=========================  ===============================================  =========================

A revision saved before X0 S11 has no basis.  It is reconstructed from the
35aadb3 module versions (VERSION_LEDGER ``baseline_version``) without a
methodology record; when that reproduces the declared hash, the revision is
classified like any other, and the first explicit methodology is a method
change that needs confirmation (Q13).  GET requests only classify; nothing is
written unless :func:`migrate_project_revision` is called.
"""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

from .methodology import PROFILE_PARAMETER, default_profile_id, load_catalogue, resolve_project_methodology
from .project_revision import (
    FINGERPRINT_BASIS_SCHEMA,
    _canonical_bytes,
    canonical_project_payload,
    save_project_revision,
)
from .v2.module_manifest import ModuleRegistryV2

CLASSIFICATION_SCHEMA = "value.revision-classification/v1"
LEDGER_PATH = Path(__file__).resolve().parents[1] / "docs" / "release" / "VERSION_LEDGER.json"
AUTOMATIC = {"code_identity_upgrade": "code-identity-upgrade", "environment_reidentify": "environment-reidentify"}
CONFIRMABLE = {
    "method_upgrade_required": "method-upgrade-confirmed",
    "data_changed": "data-change-confirmed",
    "unverifiable": "basis-reestablished-confirmed",
}
# Worst first: the reported classification is the worst difference found.
PRECEDENCE = ("content_changed", "method_upgrade_required", "data_changed", "code_identity_upgrade", "environment_reidentify")
ERROR_CODES = {
    "code_identity_upgrade": "GF_PREFLIGHT_REVISION_REIDENTIFY",
    "environment_reidentify": "GF_PREFLIGHT_REVISION_REIDENTIFY",
    "method_upgrade_required": "GF_PREFLIGHT_METHOD_UPGRADE_REQUIRED",
    "data_changed": "GF_PREFLIGHT_DATA_CHANGED",
    "content_changed": "GF_PREFLIGHT_PROJECT_REVISION",
    "unverifiable": "GF_PREFLIGHT_PROJECT_REVISION",
}
SOLVER_CONTRACT_UPGRADE = "GF_SOLVER_CONTRACT_UPGRADE_REQUIRED"
CONTENT_KEYS = ("start_year", "end_year", "scientific_parameters", "runtime_controls",
                "market_configuration", "maturity_acknowledgements")
NUMERIC_AFFECTS = {"trajectory", "accounting"}


class RevisionMigrationError(ValueError):
    def __init__(self, code: str, message: str, classification: Mapping[str, Any] | None = None) -> None:
        self.code = code
        self.classification = dict(classification or {})
        super().__init__(message)


@lru_cache(maxsize=1)
def _ledger() -> dict[str, Any]:
    try:
        payload = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    modules = payload.get("modules") if isinstance(payload, Mapping) else None
    return dict(modules) if isinstance(modules, Mapping) else {}


def _version_tuple(text: object) -> tuple[int, ...]:
    core = str(text).split("-", 1)[0].split("+", 1)[0]
    try:
        return tuple(int(part) for part in core.split("."))
    except ValueError:
        return ()


def _module_change_kind(module_id: str, old: str, new: str) -> tuple[str, str]:
    """(classification, reason) of a module version change."""

    entry = _ledger().get(module_id)
    old_v, new_v = _version_tuple(old), _version_tuple(new)
    if not old_v or not new_v or new_v < old_v:
        return "method_upgrade_required", "the module version moved backwards or is not a version"
    if isinstance(entry, Mapping):
        bumps = [row for row in entry.get("bumps") or [] if isinstance(row, Mapping)]
        between = [row for row in bumps if old_v < _version_tuple(row.get("to")) <= new_v]
        if not between:
            return "method_upgrade_required", "the version change is not recorded in VERSION_LEDGER"
        opt_in = [row for row in between if row.get("requires_user_opt_in")]
        if opt_in:
            ids = sorted({str(item) for row in opt_in for item in (row.get("correction_ids") or [])})
            return "method_upgrade_required", "method upgrade " + ", ".join(
                f"{row.get('from')}->{row.get('to')}" for row in opt_in
            ) + (f" ({', '.join(ids)})" if ids else "")
        return "code_identity_upgrade", "code-only upgrade recorded in VERSION_LEDGER"
    # Not a ledger module (external): only a patch release is code-only.
    if old_v[:2] == new_v[:2]:
        return "code_identity_upgrade", "patch release"
    return "method_upgrade_required", "minor or major release of a module outside VERSION_LEDGER"


def _baseline_overrides(registry: ModuleRegistryV2, modules: Mapping[str, str]) -> dict[str, tuple[str, str]]:
    overrides: dict[str, tuple[str, str]] = {}
    for slot, module_id in modules.items():
        entry = _ledger().get(str(module_id))
        if not isinstance(entry, Mapping) or not entry.get("baseline_version"):
            continue
        try:
            contract = registry.manifest(str(module_id), expected_slot=str(slot)).contract_version
        except (KeyError, ValueError):
            continue
        overrides[str(module_id)] = (str(entry["baseline_version"]), contract)
    return overrides


def _recorded_basis(project: Mapping[str, Any], declared: str) -> dict[str, Any] | None:
    basis = project.get("fingerprint_basis")
    if not isinstance(basis, Mapping) or basis.get("schema_version") != FINGERPRINT_BASIS_SCHEMA:
        return None
    payload = basis.get("payload")
    if not isinstance(payload, Mapping) or hashlib.sha256(_canonical_bytes(payload)).hexdigest() != declared:
        return None
    records = basis.get("applied_corrections")
    return {"source": "recorded", "payload": dict(payload),
            "applied_correction_ids": list(basis.get("applied_correction_ids") or []),
            "applied_corrections": [dict(item) for item in records if isinstance(item, Mapping)]
            if isinstance(records, list) else None}


def _reconstructed_basis(project: Mapping[str, Any], registry: ModuleRegistryV2, manifest: Mapping[str, Any], declared: str) -> dict[str, Any] | None:
    modules = dict(project.get("modules") or {})
    attempts = (
        ("reconstructed_35aadb3", _baseline_overrides(registry, modules)),
        ("reconstructed_current_versions", {}),
    )
    # A Study with extensions hashed its module resolution graph, which records
    # every module's source sha256: any code change moves it, so the graph is
    # never reproducible from the current sources.  project.json stores the
    # graph the revision was saved with; it is tried as recorded.
    stored_graph = project.get("module_resolution_graph")
    graphs: list[tuple[str, Mapping[str, Any] | None]] = [("", None)]
    if isinstance(stored_graph, Mapping) and project.get("selected_extensions"):
        graphs.append(("_stored_graph", stored_graph))
    for source, overrides in attempts:
        for suffix, graph in graphs:
            try:
                payload = canonical_project_payload(
                    project, registry, manifest, module_version_overrides=overrides, include_methodology=False,
                    module_resolution_graph=graph,
                )
            except (KeyError, ValueError):
                continue
            if hashlib.sha256(_canonical_bytes(payload)).hexdigest() == declared:
                return {"source": source + suffix, "payload": payload, "applied_correction_ids": None}
    return None


def _unverifiable_rows(current: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """What the user reviews when the saved basis cannot be reconstructed: the Study as it stands."""

    rows: list[dict[str, Any]] = [{
        "dimension": "basis", "key": "fingerprint_basis", "old": None, "new": None,
        "classification": "unverifiable",
        "effect": "The saved revision records no basis and cannot be reconstructed; review the Study and confirm to re-establish it.",
    }]
    if not current:
        return rows
    effect = "Current value (the saved revision cannot be reconstructed for comparison)."
    for key in CONTENT_KEYS:
        if key in current:
            rows.append({"dimension": "study", "key": key, "old": None, "new": current.get(key),
                         "classification": "unverifiable", "effect": effect})
    modules = {slot: f"{row.get('module_id')}@{row.get('version')}"
               for slot, row in dict(current.get("modules") or {}).items() if isinstance(row, Mapping)}
    rows.append({"dimension": "study", "key": "modules", "old": None, "new": modules,
                 "classification": "unverifiable", "effect": effect})
    pack = dict(current.get("data_pack") or {})
    rows.append({"dimension": "data", "key": "data_pack", "old": None,
                 "new": {"id": pack.get("id"), "content_sha256": pack.get("content_sha256")},
                 "classification": "unverifiable", "effect": effect})
    for key in ("solver_contract", "methodology"):
        if key in current:
            rows.append({"dimension": key, "key": key, "old": None, "new": current.get(key),
                         "classification": "unverifiable", "effect": effect})
    return rows


def _solver_contract_upgrade(project: Mapping[str, Any], registry: ModuleRegistryV2) -> dict[str, Any] | None:
    balancing = str(dict(project.get("modules") or {}).get("balancing") or "")
    stored = project.get("solver_contract")
    if not balancing or not isinstance(stored, Mapping):
        return None
    try:
        declaration = dict(registry.manifest(balancing, expected_slot="balancing").solver_contract or {})
    except (KeyError, ValueError):
        return None
    defaults = declaration.get("defaults") if isinstance(declaration.get("defaults"), Mapping) else None
    if not defaults:
        return None
    old, new = stored.get("contract_version"), defaults.get("contract_version")
    if old == new:
        return None
    return {
        "dimension": "solver_contract", "key": "contract_version", "old": old, "new": new,
        "classification": "method_upgrade_required", "error_code": SOLVER_CONTRACT_UPGRADE,
        "effect": "The zonal solver contract changed; the Study must adopt the installed contract explicitly.",
        "custom_settings_replaced": not bool(stored.get("is_builtin_default", False)),
    }


def _methodology_differences(old_basis: Mapping[str, Any], current: Mapping[str, Any], project: Mapping[str, Any]) -> list[dict[str, Any]]:
    old = old_basis["payload"].get("methodology")
    new = current.get("methodology")
    explicit = PROFILE_PARAMETER in dict(project.get("parameters") or project.get("parameter_overrides") or {})
    if old is None:
        return [{
            "dimension": "methodology", "key": "profile_id", "old": None, "new": (new or {}).get("profile_id"),
            "classification": "method_upgrade_required",
            "effect": ("The Study predates methodology profiles; confirming records the "
                       + ("selected" if explicit else "default") + " methodology explicitly (Q13)."),
        }]
    if old == new:
        return []
    rows: list[dict[str, Any]] = []
    for key in ("profile_id", "profile_version", "profile_definition_sha256"):
        if old.get(key) != (new or {}).get(key):
            rows.append({"dimension": "methodology", "key": key, "old": old.get(key), "new": (new or {}).get(key),
                         "classification": "method_upgrade_required",
                         "effect": "The methodology profile or its definition changed."})
    if old.get("applied_corrections_sha256") != (new or {}).get("applied_corrections_sha256"):
        rows.append(_applied_corrections_row(old_basis, project))
    return rows


def _applied_corrections_row(old_basis: Mapping[str, Any], project: Mapping[str, Any]) -> dict[str, Any]:
    """Classify a change of the applied-correction identity.

    Only corrections that change computed numbers (affects trajectory or
    accounting) make a method upgrade: added, removed, or redefined with a
    numeric ``affects`` before or after.  Identity/presentation corrections
    and redefinitions that stay non-numeric are code-only.
    """

    catalogue = load_catalogue()
    resolved = resolve_project_methodology(project)
    before = old_basis.get("applied_correction_ids")
    after = list(resolved.applied_correction_ids)
    row: dict[str, Any] = {"dimension": "methodology", "key": "applied_corrections", "old": before, "new": after}
    if not isinstance(before, list):
        row.update(changed_correction_ids=None, classification="method_upgrade_required",
                   effect="The applied corrections changed and the saved revision does not record which; review them.")
        return row
    before_records = {
        str(item.get("id")): dict(item) for item in old_basis.get("applied_corrections") or [] if isinstance(item, Mapping)
    } if isinstance(old_basis.get("applied_corrections"), list) else None
    after_records = {str(item["id"]): item for item in resolved.applied_correction_records()}

    def affects(correction_id: str) -> set[str]:
        values: set[str] = set()
        if correction_id in after_records:
            values.update(after_records[correction_id]["affects"])  # type: ignore[arg-type]
        if before_records is not None and correction_id in before_records:
            values.update(str(item) for item in before_records[correction_id].get("affects") or [])
        if not values and correction_id in catalogue.corrections:
            values.update(catalogue.corrections[correction_id].affects)
        # A removed correction whose record is unknown may have changed numbers.
        return values or set(NUMERIC_AFFECTS)

    added_removed = sorted(set(before).symmetric_difference(after))
    redefined = sorted(
        item for item in set(before).intersection(after)
        if before_records is not None and item in before_records and before_records[item] != after_records.get(item)
    )
    numeric = sorted(item for item in [*added_removed, *redefined] if NUMERIC_AFFECTS.intersection(affects(item)))
    row["changed_correction_ids"] = added_removed
    row["redefined_correction_ids"] = redefined
    row["numeric_correction_ids"] = numeric
    if numeric:
        row.update(classification="method_upgrade_required",
                   effect="Corrections that change computed numbers were added, removed or redefined: " + ", ".join(numeric) + ".")
    elif added_removed or redefined:
        row.update(classification="code_identity_upgrade",
                   effect="Only identity or presentation corrections were added, removed or redefined: "
                   + ", ".join([*added_removed, *redefined]) + ".")
    else:
        row.update(classification="code_identity_upgrade",
                   effect="The applied correction set is unchanged; only correction records outside the computed numbers changed.")
    return row


def _differences(old_basis: Mapping[str, Any], current: Mapping[str, Any], project: Mapping[str, Any]) -> list[dict[str, Any]]:
    old = old_basis["payload"]
    rows: list[dict[str, Any]] = []
    for key in CONTENT_KEYS:
        if old.get(key) != current.get(key):
            rows.append({"dimension": "study", "key": key, "old": old.get(key), "new": current.get(key),
                         "classification": "content_changed",
                         "effect": "The Study content differs from its saved revision."})
    old_modules = dict(old.get("modules") or {})
    new_modules = dict(current.get("modules") or {})
    for slot in sorted(set(old_modules) | set(new_modules)):
        before, after = old_modules.get(slot) or {}, new_modules.get(slot) or {}
        if before.get("module_id") != after.get("module_id"):
            rows.append({"dimension": "study", "key": f"modules.{slot}", "old": before.get("module_id"),
                         "new": after.get("module_id"), "classification": "content_changed",
                         "effect": "The selected module differs from the saved revision."})
            continue
        if before.get("contract_version") != after.get("contract_version"):
            rows.append({"dimension": "module", "key": f"{slot}:{after.get('module_id')}.contract_version",
                         "old": before.get("contract_version"), "new": after.get("contract_version"),
                         "classification": "method_upgrade_required",
                         "effect": "The module's contract changed."})
        if before.get("version") != after.get("version"):
            kind, reason = _module_change_kind(str(after.get("module_id")), str(before.get("version")), str(after.get("version")))
            rows.append({"dimension": "module", "key": f"{slot}:{after.get('module_id')}", "old": before.get("version"),
                         "new": after.get("version"), "classification": kind, "effect": reason})
    old_pack, new_pack = dict(old.get("data_pack") or {}), dict(current.get("data_pack") or {})
    if old_pack.get("id") != new_pack.get("id"):
        rows.append({"dimension": "study", "key": "data_pack.id", "old": old_pack.get("id"), "new": new_pack.get("id"),
                     "classification": "content_changed", "effect": "The Study selects another data pack."})
    elif old_pack != new_pack:
        rows.append({"dimension": "data", "key": "data_pack.content_sha256", "old": old_pack.get("content_sha256"),
                     "new": new_pack.get("content_sha256"), "classification": "data_changed",
                     "effect": "The installed data pack with this id has different content."})
    if old.get("dispatch_weather_identity") != current.get("dispatch_weather_identity"):
        rows.append({"dimension": "environment", "key": "dispatch_weather_identity",
                     "old": old.get("dispatch_weather_identity"), "new": current.get("dispatch_weather_identity"),
                     "classification": "environment_reidentify",
                     "effect": "The dispatch weather adapter identity changed."})
    if old.get("solver_contract") != current.get("solver_contract"):
        rows.append({"dimension": "solver_contract", "key": "solver_contract", "old": old.get("solver_contract"),
                     "new": current.get("solver_contract"), "classification": "method_upgrade_required",
                     "error_code": SOLVER_CONTRACT_UPGRADE, "effect": "The solver contract changed."})
    old_graph, new_graph = old.get("module_resolution_graph"), current.get("module_resolution_graph")
    if old_graph != new_graph:
        def extensions(graph: object) -> object:
            if not isinstance(graph, Mapping):
                return graph
            ext = graph.get("extension_graph") or graph.get("$extensions") or {}
            rows_ = ext.get("extensions") if isinstance(ext, Mapping) else None
            return sorted((str(row.get("id")), str(row.get("version"))) for row in rows_ or [] if isinstance(row, Mapping))
        same_extensions = extensions(old_graph) == extensions(new_graph)
        rows.append({"dimension": "module", "key": "module_resolution_graph", "old": None, "new": None,
                     "classification": "code_identity_upgrade" if same_extensions else "method_upgrade_required",
                     "effect": ("Module source identities changed." if same_extensions
                                else "Extension versions changed.")})
    rows.extend(_methodology_differences(old_basis, current, project))
    known = {"schema_version", "data_pack", "modules", "dispatch_weather_identity", "solver_contract",
             "module_resolution_graph", "methodology", *CONTENT_KEYS}
    for key in sorted((set(old) | set(current)) - known):
        if old.get(key) != current.get(key):
            rows.append({"dimension": "other", "key": key, "old": old.get(key), "new": current.get(key),
                         "classification": "method_upgrade_required", "effect": "An unclassified identity field changed."})
    return rows


def _finish(record: dict[str, Any]) -> dict[str, Any]:
    classification = record["classification"]
    record["error_code"] = next(
        (row["error_code"] for row in record.get("differences", []) if row.get("error_code")
         and row.get("classification") == classification),
        ERROR_CODES.get(classification),
    )
    record["automatic"] = classification in AUTOMATIC
    record["confirmable"] = classification in CONFIRMABLE
    record["revision_reason"] = AUTOMATIC.get(classification) or CONFIRMABLE.get(classification)
    record["diff_sha256"] = hashlib.sha256(_canonical_bytes({
        key: record.get(key) for key in ("classification", "declared_sha256", "calculated_sha256", "differences")
    })).hexdigest()
    return record


def classify_revision_mismatch(project: Mapping[str, Any], registry: ModuleRegistryV2, data_pack_manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Why the installed code computes another revision hash for this Study.  Read-only."""

    declared = project.get("revision_sha256")
    record: dict[str, Any] = {"schema_version": CLASSIFICATION_SCHEMA, "declared_sha256": declared,
                              "calculated_sha256": None, "basis_source": None, "differences": []}
    solver = _solver_contract_upgrade(project, registry)
    if solver is not None:
        record.update(classification="method_upgrade_required", differences=[solver])
        return _finish(record)
    current = canonical_project_payload(project, registry, data_pack_manifest)
    calculated = hashlib.sha256(_canonical_bytes(current)).hexdigest()
    record["calculated_sha256"] = calculated
    if not declared:
        record["classification"] = "unsaved"
        return _finish(record)
    if declared == calculated:
        record["classification"] = "none"
        return _finish(record)
    basis = _recorded_basis(project, str(declared)) or _reconstructed_basis(project, registry, data_pack_manifest, str(declared))
    if basis is None:
        record.update(classification="unverifiable", basis_source="none", differences=_unverifiable_rows(current))
        return _finish(record)
    record["basis_source"] = basis["source"]
    differences = _differences(basis, current, project)
    record["differences"] = differences
    kinds = {row["classification"] for row in differences}
    record["classification"] = next((kind for kind in PRECEDENCE if kind in kinds), "code_identity_upgrade")
    return _finish(record)


def migration_candidate(project: Mapping[str, Any], registry: ModuleRegistryV2) -> dict[str, Any]:
    """The Study content a confirmed migration saves.

    The methodology is written explicitly when absent (first write, Q13) and a
    superseded zonal solver contract is replaced by the installed default.
    """

    from .zonal_solver_contract import DEFAULT_ZONAL_SOLVER_SETTINGS

    candidate = json.loads(json.dumps(dict(project)))
    key = "parameters" if "parameters" in candidate or "parameter_overrides" not in candidate else "parameter_overrides"
    parameters = dict(candidate.get(key) or {})
    parameters.setdefault(PROFILE_PARAMETER, default_profile_id())
    candidate[key] = parameters
    if _solver_contract_upgrade(candidate, registry) is not None:
        candidate["solver_contract"] = DEFAULT_ZONAL_SOLVER_SETTINGS.to_dict()
    return candidate


def migrate_project_revision(
    project_dir: Path,
    registry: ModuleRegistryV2,
    data_pack_manifest: Mapping[str, Any],
    *,
    confirm_diff_sha256: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Append the revision a classification calls for; returns (project, classification).

    Code-only classifications are appended without confirmation.  Method,
    data and unverifiable classifications need ``confirm_diff_sha256`` equal
    to the classification the user reviewed (stale confirmations are
    refused).  A content change is never migrated here.
    """

    project = json.loads((project_dir / "project.json").read_text(encoding="utf-8"))
    classification = classify_revision_mismatch(project, registry, data_pack_manifest)
    kind = classification["classification"]
    if kind in {"none", "unsaved"}:
        return project, classification
    if kind == "content_changed":
        raise RevisionMigrationError(
            "GF_PREFLIGHT_PROJECT_REVISION",
            "The Study content differs from its saved revision; review and save it as a new revision.",
            classification,
        )
    if kind in CONFIRMABLE:
        if not confirm_diff_sha256:
            raise RevisionMigrationError(
                "GF_REVISION_MIGRATION_CONFIRMATION_REQUIRED",
                "This Study needs your confirmation before it runs: review the listed changes.",
                classification,
            )
        if confirm_diff_sha256 != classification["diff_sha256"]:
            raise RevisionMigrationError(
                "GF_REVISION_MIGRATION_STALE",
                "The changes you confirmed are no longer current; review them again.",
                classification,
            )
        candidate = migration_candidate(project, registry)
    else:
        candidate = json.loads(json.dumps(project))
    saved = save_project_revision(
        project_dir, candidate, registry, data_pack_manifest,
        expected_base_revision=str(project.get("revision_sha256") or "") or None,
        revision_reason=str(classification["revision_reason"]),
    )
    return saved, classification
