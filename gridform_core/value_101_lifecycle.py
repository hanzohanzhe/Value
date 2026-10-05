"""Auditable Study and Run lifecycle helpers for the VALUE 101 course."""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence

from .zonal_solver_contract import DEFAULT_ZONAL_SOLVER_SETTINGS


ORIGIN_KEY = "value_101"
COURSE_ORIGIN = "guided-course"
COURSE_REVISION = "value-101/v1"
VARIANT_KINDS = {"baseline", "network"}
REVISION_BOOKKEEPING_KEYS = {
    "revision_sha256",
    "revision_number",
    "parent_revision_sha256",
    "change_summary",
    "updated_at",
    "fingerprint_basis",
    "revision_reason",
}
SCIENTIFIC_ROOT_KEYS = (
    "data_pack_id",
    "start_year",
    "end_year",
    "modules",
    "parameters",
    "parameter_overrides",
    "runtime_options",
    "runtime_controls",
    "selected_extensions",
    "extension_parameters",
    "maturity_acknowledgements",
    "market_configuration",
    "solver_contract",
)


def value_101_origin(
    *,
    variant_kind: str,
    parent_project_id: str | None,
    changed_dimensions: Sequence[str],
) -> dict[str, object]:
    if variant_kind not in VARIANT_KINDS:
        raise ValueError(f"Unknown VALUE 101 variant kind: {variant_kind}")
    return {
        "origin": COURSE_ORIGIN,
        "course_revision": COURSE_REVISION,
        "variant_kind": variant_kind,
        "parent_project_id": parent_project_id,
        "changed_dimensions": [str(item) for item in changed_dimensions],
    }


def _record_origin(record: Mapping[str, object]) -> Mapping[str, object]:
    extensions = record.get("extensions")
    if not isinstance(extensions, Mapping):
        return {}
    origin = extensions.get(ORIGIN_KEY)
    return origin if isinstance(origin, Mapping) else {}


def is_value_101_record(record: Mapping[str, object]) -> bool:
    origin = _record_origin(record)
    return (
        origin.get("origin") == COURSE_ORIGIN
        and origin.get("course_revision") == COURSE_REVISION
        and origin.get("variant_kind") in VARIANT_KINDS
    )


def _flatten(value: object, prefix: str = "") -> dict[str, object]:
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for key, child in sorted(value.items(), key=lambda item: str(item[0])):
            path = f"{prefix}.{key}" if prefix else str(key)
            result.update(_flatten(child, path))
        return result
    if isinstance(value, (list, tuple)):
        return {prefix: list(value)}
    return {prefix: value}


def _scientific_paths(project: Mapping[str, object]) -> dict[str, object]:
    selected = {
        key: project[key]
        for key in SCIENTIFIC_ROOT_KEYS
        if key in project
    }
    return _flatten(selected)


def _changed_paths(
    before: Mapping[str, object],
    after: Mapping[str, object],
) -> list[str]:
    left = _flatten(before)
    right = _flatten(after)
    return sorted(
        path for path in set(left) | set(right)
        if left.get(path) != right.get(path)
    )


def _prepare_clone(
    base: Mapping[str, object],
    *,
    new_id: str,
    new_name: str,
) -> dict[str, object]:
    if not is_value_101_record(base):
        raise ValueError("Only an explicitly marked VALUE 101 Study can be cloned here")
    clone = copy.deepcopy(dict(base))
    clone["id"] = new_id
    clone["name"] = new_name
    for key in REVISION_BOOKKEEPING_KEYS:
        clone.pop(key, None)
    return clone


def _clone_audit(
    base: Mapping[str, object],
    clone: Mapping[str, object],
    *,
    intended_scientific_paths: Sequence[str],
) -> dict[str, object]:
    before_science = _scientific_paths(base)
    after_science = _scientific_paths(clone)
    changed_science = sorted(
        path for path in set(before_science) | set(after_science)
        if before_science.get(path) != after_science.get(path)
    )
    expected = sorted(str(item) for item in intended_scientific_paths)
    return {
        "schema_version": "value.101-clone-identity-diff/v1",
        "changed_paths": _changed_paths(base, clone),
        "changed_scientific_paths": changed_science,
        "intended_scientific_paths": expected,
        "only_intended_dimension_changed": changed_science == expected,
    }


def build_value_101_network_pair(
    base: Mapping[str, object],
    *,
    network_pack_id: str,
) -> tuple[dict[str, dict[str, object]], dict[str, object]]:
    """Build matched staged-market Studies that differ only in delivery method."""

    if not is_value_101_record(base):
        raise ValueError("Only an explicitly marked VALUE 101 Study can seed the network lesson")
    if (base.get("start_year"), base.get("end_year")) != (2025, 2026):
        raise ValueError("The VALUE 101 network lesson requires the fixed 2025 to 2026 teaching clock")
    common = copy.deepcopy(dict(base))
    for key in REVISION_BOOKKEEPING_KEYS:
        common.pop(key, None)
    common["data_pack_id"] = network_pack_id
    modules = copy.deepcopy(dict(common.get("modules") or {}))
    modules["psm"] = "value-staged-bid-at-cost-psm"
    modules["weather_spatializer"] = "value-representative-point-weather"
    common["modules"] = modules
    runtime_options = copy.deepcopy(dict(common.get("runtime_options") or {}))
    runtime_options["runtime.market_trace_level"] = "full"
    common["runtime_options"] = runtime_options

    # Acknowledgement keys follow the registered module versions (X0 S7), so a
    # later version bump cannot leave the lesson with a stale key.
    from .frontend_contract import EXPERIMENTAL_ACK, builtin_maturity_acknowledgement_key

    weather_acknowledgement = {
        builtin_maturity_acknowledgement_key("module", "value-representative-point-weather"):
            EXPERIMENTAL_ACK
    }

    copperplate = copy.deepcopy(common)
    copperplate.update({
        "id": "value-101-network-copperplate",
        "name": "VALUE 101 · network control (copperplate)",
        "selected_extensions": [],
        "market_configuration": {},
        "maturity_acknowledgements": weather_acknowledgement,
    })
    copperplate.pop("solver_contract", None)
    copperplate_modules = copy.deepcopy(modules)
    copperplate_modules["balancing"] = "value-copperplate-balancing"
    copperplate["modules"] = copperplate_modules
    copperplate_extensions = copy.deepcopy(dict(copperplate.get("extensions") or {}))
    copperplate_extensions[ORIGIN_KEY] = {
        **value_101_origin(
            variant_kind="network",
            parent_project_id=str(base.get("id") or ""),
            changed_dimensions=("network.delivery_method",),
        ),
        "network_role": "copperplate_control",
    }
    copperplate["extensions"] = copperplate_extensions

    constrained = copy.deepcopy(common)
    constrained.update({
        "id": "value-101-network-constrained",
        "name": "VALUE 101 · fixed three-zone redispatch",
        "selected_extensions": ["value-zonal-redispatch-extension"],
        "market_configuration": {
            "network_pack_id": network_pack_id,
            "zonal_demand_mode": "scenario_scaled_zonal_shares",
            "ledger_detail": "full",
        },
        "solver_contract": DEFAULT_ZONAL_SOLVER_SETTINGS.to_dict(),
        "maturity_acknowledgements": {
            **weather_acknowledgement,
            builtin_maturity_acknowledgement_key("module", "value-zonal-redispatch-balancing"): EXPERIMENTAL_ACK,
            builtin_maturity_acknowledgement_key("extension", "value-zonal-redispatch-extension"): EXPERIMENTAL_ACK,
        },
    })
    constrained_modules = copy.deepcopy(modules)
    constrained_modules["balancing"] = "value-zonal-redispatch-balancing"
    constrained["modules"] = constrained_modules
    constrained_extensions = copy.deepcopy(dict(constrained.get("extensions") or {}))
    constrained_extensions[ORIGIN_KEY] = {
        **value_101_origin(
            variant_kind="network",
            parent_project_id=str(base.get("id") or ""),
            changed_dimensions=("network.delivery_method",),
        ),
        "network_role": "fixed_three_zone_constrained",
    }
    constrained["extensions"] = constrained_extensions

    controlled_dimensions = [
        "modules.balancing",
        "selected_extensions",
        "market_configuration",
        "solver_contract",
        "maturity_acknowledgements",
    ]
    ahead_keys = (
        "data_pack_id", "start_year", "end_year", "parameters",
        "runtime_options", "extension_parameters",
    )
    ahead_inputs_identical = all(
        copperplate.get(key) == constrained.get(key) for key in ahead_keys
    ) and (
        dict(copperplate["modules"]).get("psm")
        == dict(constrained["modules"]).get("psm")
    )
    changed = _changed_paths(
        _scientific_paths(copperplate), _scientific_paths(constrained)
    )
    accepted_prefixes = tuple(f"{item}." for item in controlled_dimensions)
    only_network = all(
        path in controlled_dimensions or path.startswith(accepted_prefixes)
        for path in changed
    )
    identity = {
        "schema_version": "value.101-network-pair-identity/v1",
        "ahead_inputs_identical": ahead_inputs_identical,
        "ahead_schedule_comparison": "verified_after_both_runs",
        "only_network_delivery_changed": bool(ahead_inputs_identical and only_network),
        "controlled_dimensions": controlled_dimensions,
        "changed_scientific_paths": changed,
        "same_national_demand_authority": True,
        "network_method": "fixed_lossless_zonal_transport_and_pay_as_bid_redispatch",
    }
    if not identity["only_network_delivery_changed"]:
        raise ValueError("VALUE 101 network pair changed an unintended scientific dimension")
    return {"copperplate": copperplate, "constrained": constrained}, identity


def value_101_completion_report(
    projects: Sequence[Mapping[str, object]],
    runs: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    teaching_projects = [project for project in projects if is_value_101_record(project)]
    teaching_runs = [run for run in runs if is_value_101_record(run)]
    study_rows = [
        {
            "id": project.get("id"),
            "name": project.get("name"),
            "revision_sha256": project.get("revision_sha256"),
            "data_pack_id": project.get("data_pack_id"),
            "modules": dict(project.get("modules") or {}),
            "origin": dict(_record_origin(project)),
        }
        for project in sorted(teaching_projects, key=lambda item: str(item.get("id") or ""))
    ]
    run_rows = [
        {
            "id": run.get("id"),
            "project_id": run.get("project_id"),
            "status": run.get("status"),
            "updated_at": run.get("updated_at"),
            "error_code": run.get("error_code"),
            "diagnostic_bundle": run.get("diagnostic_bundle"),
            "origin": dict(_record_origin(run)),
            "network_status": (
                "optional_network_variant"
                if _record_origin(run).get("variant_kind") == "network"
                else "core_course_run"
            ),
            "diagnostic_paths": [
                value for value in (
                    run.get("diagnostic_bundle"),
                    run.get("failure_bundle"),
                    run.get("checkpoint_path"),
                ) if value
            ],
        }
        for run in sorted(teaching_runs, key=lambda item: str(item.get("id") or ""))
    ]
    return {
        "schema_version": "value.101-completion-report/v1",
        "local_only": True,
        "telemetry_uploaded": False,
        "studies": study_rows,
        "runs": run_rows,
        "summary": {
            "study_count": len(study_rows),
            "run_count": len(run_rows),
            "completed_run_count": sum(row["status"] == "completed" for row in run_rows),
            "failed_run_count": sum(row["status"] == "failed" for row in run_rows),
        },
    }
