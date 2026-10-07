"""Server-owned semantic contract for the expanded browser workspace.

This module contains no scientific equations and no second registry.  It turns
the existing module/extension manifests and the one registry resolution into a
bounded JSON response that browser clients can render without reimplementing
compatibility logic.
"""

from __future__ import annotations

from itertools import combinations
from typing import Mapping, Sequence

from .extension_framework import canonical_hash
from .methodology import (
    COMBINATION_ERROR_CODE,
    ProfileCombinationError,
    UnknownProfileError,
    module_supported,
    reference_deviations,
    resolve_project_methodology,
    selection_combination_violations,
)
from .module_quarantine import all_quarantine_entries, selection_blockers
from .data_contract_templates import runtime_supported_formats, template_available
from .v2.module_manifest import ModuleRegistryV2, ResolvedModuleGraph
from .study_market_config import resolve_market_configuration
from .zonal_solver_contract import (
    DEFAULT_ZONAL_SOLVER_SETTINGS,
    ZonalSolverContractError,
    solver_contract_generation,
    validate_solver_settings,
)


FRONTEND_CONTRACT_VERSION = "value.expanded-frontend/v1"
DRAFT_SCHEMA_VERSION = "value.study-draft/v1"
DRAFT_RESOLUTION_VERSION = "value.study-draft-resolution/v1"
EXPERIMENTAL_ACK = "value.experimental-ack/v1"
SOLVER_CONTRACT_ACK = "value.solver-contract-ack/v1"
VRE_SNAPSHOT_CAPABILITY = "evidence.vre-counterfactual-snapshot/v1"
FINAL_ZONAL_DISPATCH_CONTRACT = "network.zonal-redispatch-result/v1"
VRE_ATTRIBUTION_RESULT_CAPABILITY = "results.vre-curtailment-attribution/v2"
VRE_ATTRIBUTION_UNAVAILABLE_REASON = (
    "module_does_not_provide_counterfactual_snapshot"
)
VRE_ATTRIBUTION_BALANCING_UNAVAILABLE_REASON = (
    "selected_balancing_does_not_provide_final_zonal_dispatch"
)

ALLOWED_DRAFT_FIELDS = {
    "derivation",  # Server-recorded cross-Study provenance; not a scientific override.
    "schema_version", "id", "name", "purpose", "data_pack_id", "start_year",
    "end_year", "modules", "parameters", "parameter_overrides",
    "runtime_options", "runtime_controls", "selected_extensions",
    "extension_parameters", "maturity_acknowledgements", "updated_at",
    "base_revision_sha256", "revision_sha256", "revision_number",
    "parent_revision_sha256", "change_summary", "module_resolution_graph",
    "fingerprint_basis", "revision_reason",  # revision bookkeeping (X0 S11)
    "market_configuration", "extensions",
    "solver_contract",
}


class ProjectSolverContractError(ValueError):
    """Stable project-validation error for solver-contract identity."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def solver_contract_acknowledgement_key(module_id: str, version: str) -> str:
    return f"solver-contract:{module_id}@{version}"


def maturity_acknowledgement_key(kind: str, item_id: str, version: str) -> str:
    """The one place that spells a maturity acknowledgement key."""

    if kind not in {"module", "extension"}:
        raise ValueError(f"Unknown acknowledgement kind: {kind}")
    return f"{kind}:{item_id}@{version}"


def builtin_maturity_acknowledgement_key(
    kind: str, item_id: str, registry: ModuleRegistryV2 | None = None
) -> str:
    """Acknowledgement key for a module/extension at its registered version.

    Built-in Study templates (VALUE 101 network lesson, VALUE UK suite) derive
    their keys here so a module version bump cannot leave a stale key behind.
    """

    if registry is None:
        from .v2.module_manifest import builtin_registry

        registry = builtin_registry()
    if kind == "module":
        version = registry.manifest(item_id).version
    elif kind == "extension":
        version = registry.extension_registry.manifest(item_id).version
    else:
        raise ValueError(f"Unknown acknowledgement kind: {kind}")
    return maturity_acknowledgement_key(kind, item_id, version)


def _canonical_solver_settings(payload: object) -> dict[str, object]:
    if not isinstance(payload, Mapping):
        raise ProjectSolverContractError(
            "GF_SOLVER_CONTRACT_INVALID", "solver_contract must be an object"
        )
    expected_fields = set(DEFAULT_ZONAL_SOLVER_SETTINGS.to_dict())
    if set(payload) != expected_fields:
        raise ProjectSolverContractError(
            "GF_SOLVER_CONTRACT_INVALID",
            "solver_contract must contain exactly the declared v1 fields",
        )
    candidate = dict(payload)
    default = DEFAULT_ZONAL_SOLVER_SETTINGS.to_dict()
    identity_fields = expected_fields.difference(
        {"is_builtin_default", "requires_acknowledgement"}
    )
    is_builtin_default = all(
        candidate[field] == default[field] for field in identity_fields
    )
    candidate["is_builtin_default"] = is_builtin_default
    candidate["requires_acknowledgement"] = not is_builtin_default
    try:
        return validate_solver_settings(candidate).to_dict()
    except ZonalSolverContractError as exc:
        # A v2/v3 Study is never silently rewritten (P0-8 S5, Q13): the user
        # upgrades it explicitly, which saves a new revision.
        raise ProjectSolverContractError(exc.code, str(exc)) from exc
    except ValueError as exc:
        raise ProjectSolverContractError(
            "GF_SOLVER_CONTRACT_INVALID", str(exc)
        ) from exc


def solver_contract_upgrade_preview(project: Mapping[str, object]) -> dict[str, object] | None:
    """Describe the explicit v2/v3 -> current upgrade without applying it.

    Returns ``None`` when the Study already declares the current contract or
    declares none.  The preview lists every changed field with its recorded
    and current value so the UI can show the method difference before the
    user saves a new revision (Q13 ``method_upgrade_required``).
    """

    recorded = project.get("solver_contract")
    generation = solver_contract_generation(recorded if isinstance(recorded, Mapping) else None)
    if generation in {"v4", "unknown"}:
        return None
    assert isinstance(recorded, Mapping)
    current = DEFAULT_ZONAL_SOLVER_SETTINGS.to_dict()
    changes = [
        {"field": key, "recorded": recorded.get(key), "current": current.get(key)}
        for key in sorted(set(recorded) | set(current))
        if recorded.get(key) != current.get(key)
    ]
    return {
        "schema_version": "value.solver-contract-upgrade-preview/v1",
        "error_code": "GF_SOLVER_CONTRACT_UPGRADE_REQUIRED",
        "classification": "method_upgrade_required",
        "recorded_generation": generation,
        "current_generation": "v4",
        "recorded_was_builtin_default": recorded.get("is_builtin_default") is True,
        "changes": changes,
        "proposed_solver_contract": current,
    }


def validate_project_solver_contract(
    project: Mapping[str, object],
    registry: ModuleRegistryV2,
    *,
    modules: Mapping[str, str] | None = None,
    require_acknowledgement: bool = True,
) -> dict[str, object] | None:
    """Return canonical settings for the selected module or reject the pairing."""

    selected = dict(modules or _normalise_modules(project, registry))
    balancing_id = str(selected.get("balancing") or "")
    manifest = None
    if balancing_id:
        try:
            manifest = registry.manifest(balancing_id, expected_slot="balancing")
        except (KeyError, ValueError):
            manifest = None
    declaration = dict(manifest.solver_contract) if manifest is not None else {}
    supplied = "solver_contract" in project and project.get("solver_contract") is not None
    if declaration and not supplied:
        raise ProjectSolverContractError(
            "GF_SOLVER_CONTRACT_REQUIRED",
            f"Solver contract required for {balancing_id}",
        )
    if supplied and not declaration:
        raise ProjectSolverContractError(
            "GF_SOLVER_CONTRACT_MODULE_MISMATCH",
            "The selected balancing module does not declare this solver contract",
        )
    if not declaration:
        return None
    if manifest is None or manifest.id != "value-zonal-redispatch-balancing":
        raise ProjectSolverContractError(
            "GF_SOLVER_CONTRACT_MODULE_MISMATCH",
            "The zonal solver contract belongs to value-zonal-redispatch-balancing",
        )
    try:
        manifest_defaults = _canonical_solver_settings(declaration.get("defaults"))
    except ProjectSolverContractError as exc:
        raise ProjectSolverContractError(
            "GF_SOLVER_CONTRACT_MANIFEST_INVALID",
            f"Selected module solver contract is invalid: {exc}",
        ) from exc
    if manifest_defaults != DEFAULT_ZONAL_SOLVER_SETTINGS.to_dict():
        raise ProjectSolverContractError(
            "GF_SOLVER_CONTRACT_MANIFEST_INVALID",
            "Selected module defaults do not match the installed solver policy",
        )
    canonical = _canonical_solver_settings(project.get("solver_contract"))
    if canonical["requires_acknowledgement"] and require_acknowledgement:
        key = solver_contract_acknowledgement_key(manifest.id, manifest.version)
        acknowledgements = dict(project.get("maturity_acknowledgements") or {})
        if acknowledgements.get(key) != SOLVER_CONTRACT_ACK:
            raise ProjectSolverContractError(
                "GF_SOLVER_CONTRACT_ACK_REQUIRED",
                f"Acknowledge custom solver contract {manifest.id} {manifest.version} before saving.",
            )
    return canonical


def _issue(code: str, message: str, *, scope: str, detail: object = None) -> dict[str, object]:
    row: dict[str, object] = {"code": code, "message": message, "scope": scope}
    if detail is not None:
        row["detail"] = detail
    return row


def module_slot_catalog(
    registry: ModuleRegistryV2,
    module_catalog: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    """Derive all slots from manifests; required/optional is never hard-coded."""

    rows_by_id = {str(item["id"]): item for item in module_catalog}
    grouped: dict[str, list[dict[str, object]]] = {}
    for manifest in registry.manifests().values():
        row = rows_by_id.get(manifest.id, manifest.to_dict())
        if row.get("user_selectable") is False or manifest.slot == "network_expansion":
            continue
        grouped.setdefault(manifest.slot, []).append({
            "id": manifest.id,
            "name": manifest.name,
            "version": manifest.version,
            "status": manifest.status,
            "description": manifest.description,
            "provides_capabilities": list(manifest.provides_capabilities),
            "requires_capabilities": list(manifest.requires_capabilities),
            "origin": row.get("origin", "built_in"),
            "conformance": row.get("conformance", {"status": "not_evaluated"}),
        })
    result = []
    for slot, options in grouped.items():
        manifests = [item for item in registry.manifests().values() if item.slot == slot]
        order = min(
            int(rows_by_id.get(item.id, {}).get("order", 999)) for item in manifests
        )
        result.append({
            "slot": slot,
            "required": any(item.selection_required for item in manifests),
            "contract_version": manifests[0].contract_version,
            "order": order,
            "options": sorted(options, key=lambda item: (str(item["status"]), str(item["name"]))),
        })
    return sorted(result, key=lambda item: (int(item["order"]), str(item["slot"])))


def extension_catalogue(
    registry: ModuleRegistryV2,
    *,
    installation_records: Mapping[str, Mapping[str, object]] | None = None,
) -> list[dict[str, object]]:
    installations = dict(installation_records or {})
    rows = []
    for extension in sorted(
        registry.extension_manifests().values(), key=lambda item: (item.name, item.id)
    ):
        row = extension.to_dict()
        installation = installations.get(extension.id)
        row.update({
            "enabled": bool(installation.get("enabled", True)) if installation else True,
            "origin": "local_bundle" if installation else "built_in",
            "installation": dict(installation) if installation else None,
            "manifest_sha256": canonical_hash(extension.to_dict()),
        })
        rows.append(row)
    return rows


def active_dataset_slots(
    registry: ModuleRegistryV2,
    base_slots: Sequence[Mapping[str, object]],
    selected_extensions: Sequence[str],
) -> list[dict[str, object]]:
    rows = [dict(
        item,
        source="base",
        template_available=template_available(str(item["role"])),
        supported_formats=list(runtime_supported_formats(str(item["role"]), item.get("formats", ()))),
    ) for item in base_slots]
    rows.extend(
        dict(
            item,
            source="extension",
            template_available=template_available(str(item["role"])),
            supported_formats=list(runtime_supported_formats(str(item["role"]), item.get("formats", ()))),
        )
        for item in registry.extension_registry.conditional_dataset_slots(selected_extensions)
    )
    return rows


def _normalise_modules(
    project: Mapping[str, object], registry: ModuleRegistryV2
) -> dict[str, str]:
    modules = {
        str(slot): str(module_id)
        for slot, module_id in dict(project.get("modules") or {}).items()
    }
    psm_id = modules.get("psm")
    if psm_id:
        try:
            psm = registry.manifest(psm_id, expected_slot="psm")
            if "storage.bid-cost-function" in psm.requires_capabilities:
                modules.setdefault("storage_cost", "dynamic-annual-storage-cost")
            if "market.ahead-schedule/v1" in psm.provides_capabilities:
                balancing = _recommended_balancing_module(registry)
                if balancing is not None:
                    modules.setdefault("balancing", balancing)
            else:
                modules.pop("balancing", None)
        except ValueError:
            pass
    return modules


def _recommended_balancing_module(registry: ModuleRegistryV2) -> str | None:
    """Choose the built-in single-node provider for the basic staged preset.

    Advanced Studies may replace this explicit selection.  Capability and
    maturity determine the recommendation; a future zonal provider must not
    silently replace the copperplate default.
    """

    candidates = [
        manifest
        for manifest in registry.manifests().values()
        if manifest.slot == "balancing"
        and manifest.status == "ready"
        and "market.balancing/v1" in manifest.provides_capabilities
        and "domain.single_node" in manifest.provides_capabilities
    ]
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: (item.name, item.id))[0].id


def curtailment_attribution_resolution(
    graph: ResolvedModuleGraph | None,
) -> dict[str, object]:
    """Report capability only for the selected executable PSM/balancing pair."""

    selected_psm = None if graph is None else graph.manifests_by_slot.get("psm")
    selected_balancing = (
        None if graph is None else graph.manifests_by_slot.get("balancing")
    )
    psm_declares_snapshot = bool(
        selected_psm is not None
        and VRE_SNAPSHOT_CAPABILITY in selected_psm.provides_capabilities
    )
    balancing_produces_final_zonal_dispatch = bool(
        selected_balancing is not None
        and FINAL_ZONAL_DISPATCH_CONTRACT in selected_balancing.outputs
    )
    available = psm_declares_snapshot and balancing_produces_final_zonal_dispatch
    reason_code = None
    if not psm_declares_snapshot:
        reason_code = VRE_ATTRIBUTION_UNAVAILABLE_REASON
    elif not balancing_produces_final_zonal_dispatch:
        reason_code = VRE_ATTRIBUTION_BALANCING_UNAVAILABLE_REASON
    return {
        "capability": VRE_ATTRIBUTION_RESULT_CAPABILITY,
        "status": "available" if available else "unavailable",
        "reason_code": reason_code,
        "selected_psm_declares_snapshot": psm_declares_snapshot,
        "selected_balancing_produces_final_zonal_dispatch": (
            balancing_produces_final_zonal_dispatch
        ),
    }


def system_domain_presets(
    registry: ModuleRegistryV2,
    modules: Mapping[str, str],
) -> list[dict[str, object]]:
    """Return server-resolved minimal extension sets for every PSM choice."""

    extension_ids = tuple(sorted(registry.extension_manifests()))
    results: list[dict[str, object]] = []
    for psm in sorted(
        (item for item in registry.manifests().values() if item.slot == "psm"),
        key=lambda item: (item.status != "ready", item.name),
    ):
        candidate = dict(modules)
        candidate["psm"] = psm.id
        if "market.ahead-schedule/v1" in psm.provides_capabilities:
            balancing = _recommended_balancing_module(registry)
            if balancing is not None:
                candidate["balancing"] = balancing
        else:
            candidate.pop("balancing", None)
        if "storage.central-cooptimization" in psm.provides_capabilities:
            candidate.pop("storage_cost", None)
        elif "storage.bid-cost-function" in psm.requires_capabilities:
            candidate.setdefault("storage_cost", "dynamic-annual-storage-cost")
        resolved_extensions: tuple[str, ...] | None = None
        failure = "No registered extension combination satisfies this PSM."
        for count in range(len(extension_ids) + 1):
            if resolved_extensions is not None:
                break
            for selected in combinations(extension_ids, count):
                roles = tuple(
                    role.role
                    for extension_id in selected
                    for role in registry.extension_registry.manifest(extension_id).data_roles
                    if role.required
                )
                try:
                    registry.validate_selection(
                        candidate,
                        selected_extensions=selected,
                        available_data_roles=roles,
                    )
                    resolved_extensions = selected
                    break
                except (ValueError, KeyError) as exc:
                    failure = str(exc)
        capabilities = set(psm.provides_capabilities)
        if "domain.network.ac" in capabilities:
            domain_id = "domain.network.ac-feasibility"
            title = "AC feasibility"
            claim = "Checks a declared active-power schedule; this is not AC OPF."
        elif "domain.network.dc" in capabilities:
            domain_id = "domain.network.dc"
            title = "Reference DC network"
            claim = "Chronological linear DC network clearing in the declared reference scope."
        else:
            domain_id = "domain.single-node"
            title = "Single node"
            claim = "Internal transmission is not represented; interconnectors remain boundary offers."
        results.append({
            "id": domain_id,
            "title": title,
            "claim": claim,
            "psm_module_id": psm.id,
            "psm_name": psm.name,
            "description": psm.description,
            "maturity": psm.status,
            "recommended_modules": candidate,
            "required_extensions": list(resolved_extensions or ()),
            "available": resolved_extensions is not None,
            "unavailable_reason": None if resolved_extensions is not None else failure,
        })
    return results


def maturity_acknowledgement_requirements(
    registry: ModuleRegistryV2,
    modules: Mapping[str, str],
    selected_extensions: Sequence[str],
) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for slot, module_id in modules.items():
        try:
            manifest = registry.manifest(module_id, expected_slot=slot)
        except ValueError:
            continue
        if manifest.status in {"experimental", "not_evaluated"}:
            result.append({
                "key": maturity_acknowledgement_key("module", manifest.id, manifest.version),
                "kind": "module", "id": manifest.id, "version": manifest.version,
                "maturity": manifest.status, "acknowledgement": EXPERIMENTAL_ACK,
            })
    for extension_id in selected_extensions:
        try:
            manifest = registry.extension_registry.manifest(extension_id)
        except ValueError:
            continue
        if manifest.maturity in {"experimental", "not_evaluated"}:
            result.append({
                "key": maturity_acknowledgement_key("extension", manifest.id, manifest.version),
                "kind": "extension", "id": manifest.id, "version": manifest.version,
                "maturity": manifest.maturity, "acknowledgement": EXPERIMENTAL_ACK,
            })
    return result


def validate_maturity_acknowledgements(
    registry: ModuleRegistryV2,
    modules: Mapping[str, str],
    selected_extensions: Sequence[str],
    acknowledgements: Mapping[str, object],
) -> tuple[dict[str, str], ...]:
    requirements = maturity_acknowledgement_requirements(
        registry, modules, selected_extensions
    )
    missing = [
        item for item in requirements
        if acknowledgements.get(item["key"]) != EXPERIMENTAL_ACK
    ]
    if missing:
        raise ValueError(
            "Experimental acknowledgement required: "
            + ", ".join(item["key"] for item in missing)
        )
    return tuple(requirements)


def resolve_study_draft(
    project: Mapping[str, object],
    *,
    registry: ModuleRegistryV2,
    module_catalog: Sequence[Mapping[str, object]],
    base_dataset_slots: Sequence[Mapping[str, object]],
    available_data_roles: Sequence[str] = (),
    data_packs: Sequence[tuple[Mapping[str, object], bytes | None] | None] = (),
) -> dict[str, object]:
    """Resolve a browser draft through the one executable registry.

    Missing data is reported independently.  A graph preview may still be
    returned with declared roles so users can see the identity they are trying
    to satisfy; the draft remains invalid until the actual roles are bound.
    """

    errors: list[dict[str, object]] = []
    warnings: list[dict[str, object]] = []
    unknown_fields = sorted(set(project).difference(ALLOWED_DRAFT_FIELDS))
    if unknown_fields:
        errors.append(_issue(
            "GF_STUDY_FIELD_UNKNOWN",
            "Unknown Study fields: " + ", ".join(unknown_fields),
            scope="study", detail=unknown_fields,
        ))

    modules = _normalise_modules(project, registry)
    known_slots = {manifest.slot for manifest in registry.manifests().values()}
    unknown_slots = sorted(set(modules).difference(known_slots))
    if unknown_slots:
        errors.append(_issue(
            "GF_MODULE_SLOT_UNKNOWN",
            "Unknown module slots: " + ", ".join(unknown_slots),
            scope="modules", detail=unknown_slots,
        ))
    selected_extensions = tuple(
        str(item) for item in (project.get("selected_extensions") or ())
    )
    duplicate_extensions = sorted({item for item in selected_extensions if selected_extensions.count(item) > 1})
    if duplicate_extensions:
        errors.append(_issue(
            "GF_EXTENSION_DUPLICATE_SELECTION",
            "Extensions may be selected only once: " + ", ".join(duplicate_extensions),
            scope="extensions", detail=duplicate_extensions,
        ))
    # P0-2: a selected module/extension that is quarantined gets its own code
    # (not "unknown"); quarantine elsewhere is only a warning.
    blockers = selection_blockers(registry, modules.values(), selected_extensions)
    if blockers:
        errors.append(_issue(
            "GF_STUDY_MODULE_QUARANTINED",
            "This Study selects quarantined local code: " + ", ".join(
                f"{entry.kind} {entry.entry_id} ({entry.code})" for entry in blockers
            ) + ". Disable or repair it in Modules, or select another module.",
            scope="modules", detail=[entry.to_dict() for entry in blockers],
        ))
    elif all_quarantine_entries(registry):
        warnings.append(_issue(
            "GF_MODULE_QUARANTINE_PRESENT",
            "Some local modules or extensions are quarantined; this Study does not use them.",
            scope="modules", detail={"count": len(all_quarantine_entries(registry))},
        ))
    blocked_extensions = {str(entry.entry_id) for entry in blockers if entry.kind == "extension"}
    unknown_extensions = []
    for extension_id in selected_extensions:
        try:
            registry.extension_registry.manifest(extension_id)
        except ValueError:
            if extension_id not in blocked_extensions:
                unknown_extensions.append(extension_id)
    if unknown_extensions:
        errors.append(_issue(
            "GF_EXTENSION_UNKNOWN",
            "Unknown extensions: " + ", ".join(sorted(unknown_extensions)),
            scope="extensions", detail=sorted(unknown_extensions),
        ))

    active_slots = [
        dict(
            item,
            source="base",
            template_available=template_available(str(item["role"])),
            supported_formats=list(runtime_supported_formats(str(item["role"]), item.get("formats", ()))),
        )
        for item in base_dataset_slots
    ]
    if not unknown_extensions:
        active_slots = active_dataset_slots(
            registry, base_dataset_slots,
            tuple(item for item in selected_extensions if item in registry.extension_manifests()),
        )
    available = set(str(item) for item in available_data_roles)
    required_roles = {
        str(item["role"]) for item in active_slots if item.get("required")
    }
    missing_roles = sorted(required_roles.difference(available))
    for role in missing_roles:
        slot = next(item for item in active_slots if item["role"] == role)
        errors.append(_issue(
            "GF_EXTENSION_DATA_MISSING" if slot.get("source") == "extension" else "GF_DATA_MISSING",
            f"Missing required dataset: {slot['label']}",
            scope="data", detail={"role": role, "source": slot.get("source")},
        ))

    extension_parameters = dict(project.get("extension_parameters") or {})
    acknowledgements = dict(project.get("maturity_acknowledgements") or {})
    acknowledgement_requirements = maturity_acknowledgement_requirements(
        registry, modules, selected_extensions
    )
    for requirement in acknowledgement_requirements:
        if acknowledgements.get(requirement["key"]) != EXPERIMENTAL_ACK:
            errors.append(_issue(
                "GF_EXPERIMENTAL_ACK_REQUIRED",
                f"Acknowledge {requirement['kind']} {requirement['id']} {requirement['version']} before saving.",
                scope="maturity", detail=requirement,
            ))

    canonical_solver_contract: dict[str, object] | None = None
    try:
        canonical_solver_contract = validate_project_solver_contract(
            project,
            registry,
            modules=modules,
            require_acknowledgement=False,
        )
    except ProjectSolverContractError as exc:
        errors.append(_issue(
            exc.code,
            str(exc),
            scope="solver_contract",
        ))
    if canonical_solver_contract is not None:
        balancing = registry.manifest(
            str(modules["balancing"]), expected_slot="balancing"
        )
        acknowledgement_key = solver_contract_acknowledgement_key(
            balancing.id, balancing.version
        )
        if (
            canonical_solver_contract["requires_acknowledgement"]
            and acknowledgements.get(acknowledgement_key) != SOLVER_CONTRACT_ACK
        ):
            errors.append(_issue(
                "GF_SOLVER_CONTRACT_ACK_REQUIRED",
                f"Acknowledge custom solver contract {balancing.id} {balancing.version} before saving.",
                scope="solver_contract",
                detail={
                    "key": acknowledgement_key,
                    "acknowledgement": SOLVER_CONTRACT_ACK,
                },
            ))

    # Methodology profile (X0 S8, Q3): the combination whitelist is the same
    # check as preflight and the run entry (C16); a deviation from the frozen
    # profile's reference preset is allowed but reported.
    methodology_block: dict[str, object] | None = None
    profile_id: str | None = None
    try:
        methodology = resolve_project_methodology(project)
        profile_id = methodology.profile_id
        violations = selection_combination_violations(
            methodology,
            registry=registry,
            modules=modules,
            extensions=selected_extensions,
            data_packs=list(data_packs),
        )
        deviations = reference_deviations(
            methodology,
            modules=modules,
            scientific_parameters=dict(project.get("parameters") or project.get("parameter_overrides") or {}),  # type: ignore[arg-type]
        )
        if violations:
            errors.append(_issue(
                COMBINATION_ERROR_CODE,
                str(ProfileCombinationError(methodology.profile_id, violations)),
                scope="methodology", detail=violations,
            ))
        if deviations:
            warnings.append(_issue(
                "VALUE_PROFILE_REFERENCE_DEVIATION",
                f"{methodology.label}: the Study departs from the reference configuration; "
                "the run is allowed and records the deviation.",
                scope="methodology", detail=deviations,
            ))
        methodology_block = {
            **methodology.to_dict(),
            "violations": violations,
            "reference_deviations": deviations,
        }
    except UnknownProfileError as exc:
        errors.append(_issue(UnknownProfileError.code, str(exc), scope="methodology"))

    graph = None
    effective_extension_parameters: dict[str, object] = {}
    registry_error: str | None = None
    if not unknown_slots and not unknown_extensions and not blockers:
        ideal_roles = tuple(sorted(required_roles | available))
        try:
            graph = registry.resolve_selection(
                modules,
                selected_extensions=selected_extensions,
                extension_parameters=extension_parameters,
                available_data_roles=ideal_roles,
            )
            if graph.extension_graph is not None:
                effective_extension_parameters = dict(graph.extension_graph.parameters)
        except (ValueError, KeyError, TypeError) as exc:
            registry_error = str(exc)
            if getattr(exc, "code", None) == "GF_EXTENSION_HOOK_IMPORT":
                # A hook that cannot be imported is runtime-quarantined.
                code = "GF_STUDY_MODULE_QUARANTINED"
            else:
                code = "GF_EXTENSION_PARAMETER_INVALID" if "parameter" in registry_error.lower() else "GF_MODULE_INCOMPATIBLE"
            errors.append(_issue(code, registry_error, scope="resolution"))

    compatible: dict[str, list[dict[str, object]]] = {}
    for slot_row in module_slot_catalog(registry, module_catalog):
        slot = str(slot_row["slot"])
        compatible[slot] = []
        for raw_option in slot_row["options"]:
            option = dict(raw_option)
            if profile_id is not None:
                try:
                    scientific_version = registry.manifest(str(option["id"]), expected_slot=slot).scientific_version
                except (KeyError, ValueError):
                    scientific_version = None
                supported, reason = module_supported(profile_id, str(option["id"]), scientific_version)
                option["methodology_supported"] = supported
                option["methodology_reason"] = reason
            candidate = dict(modules)
            candidate[slot] = str(option["id"])
            if (
                slot == "psm"
                and "storage.central-cooptimization" in option.get("provides_capabilities", [])
            ):
                candidate.pop("storage_cost", None)
            try:
                registry.validate_selection(
                    candidate,
                    selected_extensions=selected_extensions,
                    extension_parameters=extension_parameters,
                    available_data_roles=tuple(sorted(required_roles | available)),
                )
                compatible[slot].append({**option, "compatible": True, "reason": None})
            except (ValueError, KeyError, TypeError) as exc:
                compatible[slot].append({**option, "compatible": False, "reason": str(exc)})

    normalised_project = dict(project)
    parameters = dict(project.get("parameters") or project.get("parameter_overrides") or {})
    runtime_controls = dict(project.get("runtime_options") or project.get("runtime_controls") or {})
    market_configuration = dict(project.get("market_configuration") or {})
    try:
        market_configuration = resolve_market_configuration(
            modules,
            parameters,
            runtime_controls,
            market_configuration,
        )
    except (TypeError, ValueError) as exc:
        errors.append(_issue(
            "GF_MARKET_CONFIGURATION_MISMATCH", str(exc), scope="market_configuration"
        ))
    if "network_expansion" in modules:
        errors.append(_issue(
            "GF_TRANSMISSION_EXPANSION_NOT_RELEASED",
            "Transmission-expansion CEM has a versioned interface but no selectable production implementation in this release.",
            scope="modules", detail={"slot": "network_expansion"},
        ))
        market_configuration = dict(project.get("market_configuration") or {})
    # R3-N1 (DECISIONS A23): numbers are saved in their registry type.
    from .parameters import normalise_numeric_values

    for key in ("parameters", "parameter_overrides", "runtime_options", "runtime_controls"):
        if isinstance(project.get(key), Mapping):
            normalised_project[key] = normalise_numeric_values(project[key])  # type: ignore[arg-type]
    normalised_project.update({
        "modules": modules,
        "selected_extensions": list(selected_extensions),
        "extension_parameters": effective_extension_parameters or extension_parameters,
        "maturity_acknowledgements": acknowledgements,
        "market_configuration": market_configuration,
    })
    if canonical_solver_contract is not None:
        normalised_project["solver_contract"] = canonical_solver_contract
    graph_preview = graph.to_dict() if graph is not None else None
    if graph_preview is not None:
        normalised_project["module_resolution_graph"] = graph_preview
    return {
        "schema_version": DRAFT_RESOLUTION_VERSION,
        "frontend_contract_version": FRONTEND_CONTRACT_VERSION,
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "module_slots": module_slot_catalog(registry, module_catalog),
        "system_domains": system_domain_presets(registry, modules),
        "compatible_modules": compatible,
        "active_dataset_slots": active_slots,
        "data_readiness": {
            "required": len(required_roles),
            "available": len(required_roles.intersection(available)),
            "missing_roles": missing_roles,
        },
        "effective_extension_parameters": effective_extension_parameters,
        "maturity": {
            "acknowledgement_contract": EXPERIMENTAL_ACK,
            "acknowledgements_required": acknowledgement_requirements,
        },
        "methodology": methodology_block,
        "curtailment_attribution": curtailment_attribution_resolution(graph),
        "graph_preview": graph_preview,
        "graph_sha256": graph.graph_sha256 if graph is not None else None,
        "normalised_project": normalised_project,
        "registry_error": registry_error,
    }
