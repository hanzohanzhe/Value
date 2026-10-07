"""One deterministic preflight report for CLI, API and the local website."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .data_pack_validation import validate_data_pack
from .domain_readiness import build_domain_readiness
from .module_conformance import conformance_report
from .module_quarantine import external_code_evidence, quarantine_check
from .parameters import ParameterValidationError, resolve_scheme_c_parameters
from .methodology import (
    COMBINATION_ERROR_CODE,
    ProfileCombinationError,
    UnknownProfileError,
    pack_entry,
    resolve_project_methodology,
    selection_combination_violations,
)
from .module_context import canonical_context_sha256
from .preflight_resources import (
    ResourceEstimate,
    build_frozen_resource_contexts,
    estimate_run_resources,
    evaluate_resource_gate,
)
from .project_revision import project_fingerprint
from .revision_migration import classify_revision_mismatch
from .run_quota import (
    QUOTA_CORRECTIVE_ACTIONS,
    QuotaUsage,
    RunQuotaPolicy,
    global_quota_reasons,
    output_reservation_bytes,
    quota_usage,
)
from .run_policy import (
    resolve_run_policy,
    scope_extension_block_message,
    scope_runs_extensions,
    validate_pack_run_mode,
)
from .frontend_contract import validate_maturity_acknowledgements
from .v2.module_manifest import ModuleRegistryV2, workspace_registry
from .runtime_paths import user_data_root
from .runtime_capabilities import VALUE_NATIVE, capability_status
from .study_market_config import resolve_market_configuration
from .zonal_pack_selection import resolve_zonal_pack_selection
from .zonal_contracts import load_zonal_network_pack
from .zonal_solver_contract import validate_solver_settings


SCHEMA_VERSION = "value.run-preflight/v1"
# Storage-cost modules whose bid has a dwell (holding) term (P0-6 S10, P5-15).
DWELL_STORAGE_COST_MODULES = frozenset({"dynamic-annual-storage-cost", "user-formula-storage-cost"})


def _issue(code: str, severity: str, scope: str, message: str, action: str) -> dict[str, str]:
    return {
        "code": code,
        "severity": severity,
        "scope": scope,
        "message": message,
        "corrective_action": action,
    }


def resource_gate_report(
    *,
    project: Mapping[str, object],
    estimate: ResourceEstimate,
    free_bytes: int,
    quota_policy: RunQuotaPolicy,
    existing_run_bytes: int = 0,
    already_reserved_bytes: int = 0,
) -> dict[str, object]:
    """Expose Prompt122's hard decision without changing Study controls."""

    runtime = dict(project.get("runtime_options") or project.get("runtime_controls") or {})
    requested_trace = str(
        runtime.get("runtime.market_trace_level")
        or dict(project.get("market_configuration") or {}).get("ledger_detail")
        or "summary"
    )
    if requested_trace != estimate.trace_profile:
        raise ValueError("Resource estimate trace does not match the requested Study trace")
    return evaluate_resource_gate(
        estimate,
        free_bytes=free_bytes,
        quota_policy=quota_policy,
        existing_run_bytes=existing_run_bytes,
        already_reserved_bytes=already_reserved_bytes,
    )


def _quota_usage(runs_root: Path | None, run_id: str | None) -> QuotaUsage:
    if runs_root is None:
        return QuotaUsage(0, 0, ())
    return quota_usage(Path(runs_root), exclude_run=run_id)


# F2-N2 (four-role report): the former 0.35 s per period estimated a
# 35,040-period VALUE 101 run at 3.4 hours; it took about 3 minutes.  Measured
# on the reference machine: VALUE 101 two-year about 0.005 s per period, GBP1
# public1 one year about 0.02 s (F3 report, 351 s); 0.03 stays conservative.
DEFAULT_SECONDS_PER_PERIOD = 0.03
ANNUAL_RUNTIME_PERIODS = 17_520


def _runtime_observations(runs_root: Path | None, *, mode: str | None, minimum_periods: int = 1) -> list[float]:
    values: list[float] = []
    if runs_root is None or not runs_root.is_dir():
        return values
    for status_path in runs_root.glob("*/status.json"):
        try:
            status = json.loads(status_path.read_text(encoding="utf-8"))
            if status.get("status") != "completed" or (mode is not None and status.get("mode") != mode):
                continue
            policy = status.get("run_policy") or {}
            periods = int(policy.get("total_periods") or 0)
            if periods <= 0 or periods < minimum_periods:
                continue
            started = datetime.fromisoformat(str(status["started_at"]))
            finished = datetime.fromisoformat(str(status["finished_at"]))
            elapsed = (finished - started).total_seconds()
            if elapsed > 0:
                values.append(elapsed / periods)
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            continue
    return values[-10:]


def _binding_path(pack_root: Path, pack_manifest: Mapping[str, object], role: str) -> Path | None:
    bindings = pack_manifest.get("bindings")
    if not isinstance(bindings, Mapping) or not isinstance(bindings.get(role), Mapping):
        return None
    uri = str(bindings[role].get("uri") or "")  # type: ignore[index]
    path = (pack_root / uri).resolve()
    try:
        path.relative_to(pack_root.resolve())
    except ValueError:
        return None
    return path if path.is_file() else None


def _data_scale(pack_root: Path, pack_manifest: Mapping[str, object]) -> dict[str, object]:
    operating_assets = 0
    fleet = _binding_path(pack_root, pack_manifest, "fleet.generators")
    if fleet and fleet.suffix.lower() == ".json":
        try:
            payload = json.loads(fleet.read_text(encoding="utf-8"))
            if isinstance(payload, Mapping):
                operating_assets = sum(
                    len(value) for value in payload.values() if isinstance(value, list)
                )
        except (OSError, json.JSONDecodeError):
            pass
    planning_projects = 0
    projects = _binding_path(pack_root, pack_manifest, "projects.repd")
    if projects and projects.suffix.lower() == ".csv":
        try:
            lines = 0
            with projects.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    lines += chunk.count(b"\n")
            planning_projects = max(0, lines - 1)
        except OSError:
            pass
    return {
        "operating_assets": operating_assets,
        "planning_projects": planning_projects,
        "basis": "counts from fleet.generators and projects.repd bindings",
    }


def _estimates(
    project: Mapping[str, object],
    policy: Mapping[str, object],
    resolved_runtime: Mapping[str, object],
    runs_root: Path | None,
    scale: Mapping[str, object],
) -> dict[str, object]:
    periods = int(policy["total_periods"])
    years = int(policy["years"])
    trace = str(resolved_runtime.get("runtime.market_trace_level", "summary"))
    estimated_orders_per_period = 50 if trace == "full" else 0
    estimated_storage_rows_per_period = 10 if trace != "off" else 0
    rows = {
        "period_summary": periods if trace != "off" else 0,
        "orders": periods * estimated_orders_per_period,
        "storage_state": periods * estimated_storage_rows_per_period,
        "physical_dispatch": periods * 15 if trace != "off" else 0,
    }
    modules = dict(project.get("modules") or {})
    zonal = str(modules.get("balancing") or "") == "value-zonal-redispatch-balancing"
    if zonal and trace != "off":
        estimated_zones = 14
        estimated_boundaries = 20
        estimated_assets = max(int(scale.get("operating_assets") or 0), 15)
        rows.update({
            "zonal_period_summary": periods,
            "zone_period_summary": periods * estimated_zones,
            "boundary_period_summary": periods * estimated_boundaries,
            "zonal_resource_dispatch": periods * estimated_assets,
            "redispatch_settlement": periods * estimated_orders_per_period,
        })
    estimated_bytes = (
        512 * 1024 * 1024
        + rows["period_summary"] * 240
        + rows["orders"] * 190
        + rows["storage_state"] * 120
        + rows["physical_dispatch"] * 150
        + years * 64 * 1024 * 1024
    )
    if zonal and trace != "off":
        estimated_bytes += (
            rows["zonal_period_summary"] * 320
            + rows["zone_period_summary"] * 180
            + rows["boundary_period_summary"] * 180
            + rows["zonal_resource_dispatch"] * 220
            + rows["redispatch_settlement"] * 220
        )
    if str(resolved_runtime.get("runtime.market_export_format", "sqlite")) == "parquet":
        estimated_bytes = int(estimated_bytes * 1.6)
    operating_assets = int(scale.get("operating_assets") or 0)
    planning_projects = int(scale.get("planning_projects") or 0)
    periods_per_year = int(policy["periods_per_year"])
    estimated_peak_memory = (
        768 * 1024 * 1024
        + operating_assets * 4 * 1024 * 1024
        + planning_projects * 64 * 1024
        + periods_per_year * max(1, operating_assets) * (80 if trace == "full" else 48)
    )
    observations = _runtime_observations(runs_root, mode=str(policy["mode"]))
    if not observations and periods >= ANNUAL_RUNTIME_PERIODS:
        # F2-N2: a full-year scope without a same-mode run uses the per-period
        # time of any completed run of at least a year (the per-period cost of
        # a two-year and a full run is the same; short runs are dominated by
        # their fixed start-up time and are not used).
        observations = _runtime_observations(runs_root, mode=None, minimum_periods=ANNUAL_RUNTIME_PERIODS)
    if observations:
        seconds_per_period = sum(observations) / len(observations)
        basis = f"mean of {len(observations)} comparable completed local run(s)"
    else:
        seconds_per_period = DEFAULT_SECONDS_PER_PERIOD
        basis = (
            "initial heuristic of 0.03 s per period (measured: VALUE 101 two-year run about 0.005 s, "
            "GBP1 one-year run about 0.02 s); no comparable completed local run"
        )
    return {
        "label": "estimate_not_guarantee",
        "periods": periods,
        "ledger_rows": rows,
        "disk_bytes": estimated_bytes,
        "runtime_seconds": max(60.0, periods * seconds_per_period),
        "runtime_basis": basis,
        "peak_memory_bytes": estimated_peak_memory,
        "peak_memory_warning_bytes": max(4 * 1024 * 1024 * 1024, estimated_peak_memory * 2),
        "memory_basis": "bounded structural heuristic from pack asset/project counts and selected audit level; not a universal promise",
        "data_scale": dict(scale),
        "assumed_full_trace_orders_per_period": estimated_orders_per_period,
        "assumed_storage_assets_per_period": estimated_storage_rows_per_period,
        "zonal_redispatch": zonal,
        "full_trace_requires_presented_disk_estimate": trace == "full",
    }


def data_eligibility_issues(project: Mapping[str, Any], pack_manifest: Mapping[str, Any],
                            data_report: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Preflight issues of the data layers under the Study's profile (P0-5a S9)."""

    from .data_method import project_policy
    from .data_validation_layers import finding_severity

    layers = dict(data_report.get("layers") or {})
    findings = [*dict(layers.get("chronology") or {}).get("findings", []),
                *dict(layers.get("plausibility") or {}).get("findings", [])]
    if not findings:
        return []
    try:
        policy = project_policy(project, pack_manifest)
    except ValueError:
        return []
    issues = []
    for finding in findings:
        severity = finding_severity(policy, finding)
        if severity == "not_applicable":
            continue
        issue = _issue(
            str(finding["code"]), severity, "data",
            f"{finding.get('role') or 'data pack'}: {finding['message']}",
            "Use a pack revision that declares this series correctly (or the doctoral reproduction profile, "
            "which reads the known GBP1 public1 defects repaired and records them)."
            if severity == "error" else "Review the data-pack finding before publication.",
        )
        # Spec 11.1 (S-D1): the readiness card groups findings by their layer.
        issue["layer"] = str(finding.get("layer") or "")
        issues.append(issue)
    return issues


def run_preflight(
    project: Mapping[str, object],
    *,
    mode: str,
    pack_root: Path,
    pack_manifest: Mapping[str, object],
    dataset_slots: Sequence[Mapping[str, object]],
    registry: ModuleRegistryV2 | None = None,
    output_root: Path | None = None,
    runs_root: Path | None = None,
    network_pack_root: Path | None = None,
    resource_calibration_root: Path | None = None,
    resource_quota_policy: RunQuotaPolicy = RunQuotaPolicy(),
    preflight_run_id: str | None = None,
    resource_calibration_runner: Callable[
        [dict[str, object]], Mapping[str, object]
    ] | None = None,
) -> dict[str, object]:
    """Return a complete report; the caller must refuse when ``accepted`` is false."""

    registry = registry or workspace_registry()
    pack_root = pack_root.resolve()
    output_root = (output_root or pack_root.parent).resolve()
    issues: list[dict[str, str]] = []
    checks: dict[str, object] = {}

    selected = dict(project.get("modules") or {})  # type: ignore[arg-type]
    selected_extensions = tuple(
        str(item) for item in project.get("selected_extensions", ())
    )
    try:
        resolve_market_configuration(
            selected,
            dict(project.get("parameters") or project.get("parameter_overrides") or {}),
            dict(project.get("runtime_options") or project.get("runtime_controls") or {}),
            dict(project.get("market_configuration") or {}),
        )
    except (TypeError, ValueError) as exc:
        message = str(exc)
        issues.append(_issue(
            (
                "GF_PREFLIGHT_ZONAL_DEMAND_MODE"
                if "zonal_demand_mode" in message
                else "GF_PREFLIGHT_MARKET_CONFIGURATION"
            ),
            "error",
            "market_configuration",
            message,
            "Open the Study model-chain settings and save an explicit supported market configuration.",
        ))
    extension_parameters = dict(project.get("extension_parameters") or {})
    # P0-2: a selected module/extension that is quarantined blocks the run
    # with its own code; quarantine elsewhere only warns and is recorded.
    quarantine = quarantine_check(registry, selected.values(), selected_extensions)
    checks["module_quarantine"] = quarantine
    checks["external_code"] = external_code_evidence(registry, selected.values(), selected_extensions)
    if quarantine["blockers"]:
        issues.append(_issue(
            "GF_PREFLIGHT_MODULE_QUARANTINED", "error", "modules",
            "The Study selects quarantined local code: " + ", ".join(
                f"{row['kind']} {row['id']} ({row['error_code']})" for row in quarantine["blockers"]
            ),
            "Open Modules: disable or repair the quarantined entry, then select a working module.",
        ))
    elif quarantine["entries"]:
        issues.append(_issue(
            "GF_PREFLIGHT_MODULE_QUARANTINE_PRESENT", "warning", "modules",
            f"{len(quarantine['entries'])} local module or extension entr"
            + ("y is" if len(quarantine["entries"]) == 1 else "ies are")
            + " quarantined; this Study does not use them.",
            "Open Modules to disable or repair them; the run is unaffected.",
        ))
    # M2-N2: a selected local module or extension that is installed but
    # disabled is named as such (the selection check below would only say
    # "not registered").
    from .module_installation import disabled_selections

    disabled = disabled_selections(registry, selected.values(), selected_extensions)
    checks["module_disabled"] = disabled
    if disabled:
        issues.append(_issue(
            "GF_PREFLIGHT_MODULE_DISABLED", "error", "modules",
            "The Study selects disabled local code: " + ", ".join(
                f"{row['kind']} {row['id']}" + (f" {', '.join(row['versions'])}" if row["versions"] else "")
                for row in disabled
            ) + ".",
            "Open Modules > Disabled and quarantined and Enable it, or select another module in the Study.",
        ))
    # A16-4 (M-D2, spec 11.7): an installed module whose source was edited in
    # place is accepted and recorded; preflight says so before the run.
    from .module_installation import installed_source_changes

    source_changes = installed_source_changes(selected.values())
    checks["module_source_changes"] = source_changes
    # R3M-5: a quarantined module cannot run, so no result records anything yet.
    quarantined_modules = {
        str(row.get("id")) for row in quarantine["blockers"] if str(row.get("kind")) == "module"
    }
    for change in source_changes:
        recorded = (
            "It is quarantined, so no Run can start; once it is repaired, results record the new source hash."
            if str(change["module_id"]) in quarantined_modules
            else "Results will record the new source hash."
        )
        issues.append(_issue(
            "GF_PREFLIGHT_MODULE_SOURCE_CHANGED", "warning", "modules",
            f"Module {change['module_id']} source changed since install "
            f"({str(change['installed_sha256'])[:8]}… → {str(change['current_sha256'])[:8]}…). "
            + recorded,
            "No action needed if the edit is intended: Compare shows the module method as changed. "
            "Reinstall under a new version to keep the installed identity.",
        ))
    registered_extensions = registry.extension_manifests()
    active_dataset_slots = tuple(dataset_slots) + registry.extension_registry.conditional_dataset_slots(
        tuple(item for item in selected_extensions if item in registered_extensions)
    )
    pack_selection = None
    try:
        pack_selection = resolve_zonal_pack_selection(
            project,
            base_pack_root=pack_root,
            base_manifest=pack_manifest,
            explicit_network_pack_root=network_pack_root,
        )
        available_data_roles = pack_selection.available_data_roles
    except ValueError as exc:
        available_data_roles = tuple(dict(pack_manifest.get("bindings") or {}))
        issues.append(_issue(
            "GF_PREFLIGHT_ZONAL_PACK_SELECTION", "error", "data", str(exc),
            "Install and select the signed network pack named by market_configuration.network_pack_id.",
        ))
    selected.setdefault("transition", "value-annual-state-transition")
    if selected.get("psm") == "value-staged-bid-at-cost-psm" and selected.get("storage_cost") in DWELL_STORAGE_COST_MODULES:
        # P0-6 S10 (P5-15): the staged PSM bids storage with d = 0 (one SoC pool).
        issues.append(_issue(
            "GF_STAGED_DWELL_NOT_TRACKED", "warning", "modules",
            "The staged PSM keeps one storage pool and does not track dwell: storage bids use d = 0, so the "
            "selected storage-cost module's holding (dwell) term is reported but never bid.",
            "Read storage revenue and dwell-based recovery of this Study as indicative, or use the default PSM.",
        ))
    runtime_capability = capability_status(
        VALUE_NATIVE, selected_module_ids=selected.values()
    )
    python_ok = bool(runtime_capability["python_supported"])
    checks["python"] = {"version": sys.version.split()[0], "executable": sys.executable, "passed": python_ok}
    checks["runtime_capability"] = runtime_capability
    if not python_ok:
        issues.append(_issue(
            "GF_PREFLIGHT_PYTHON_VERSION", "error", "environment",
            f"The selected VALUE native runtime is not validated on Python {sys.version.split()[0]}.",
            str(runtime_capability["corrective_action"]),
        ))
    # M-D6: the run entry verifies the sealed runtime kernel and refuses an
    # unregistered edit (GF_COMPATIBILITY_001) only after the inputs are
    # frozen; preflight runs the same uncached check so readiness says so.
    from .builtin.scheme_c_1000twh.runtime_overlay import inspect_runtime_overlay

    try:
        overlay_errors = [str(item) for item in inspect_runtime_overlay()["errors"]]
    except Exception as exc:  # a missing or unreadable manifest refuses the run as well
        overlay_errors = [f"{type(exc).__name__}: {exc}"]
    checks["runtime_overlay"] = {"passed": not overlay_errors, "errors": overlay_errors[:10]}
    if overlay_errors:
        issues.append(_issue(
            "GF_PREFLIGHT_RUNTIME_OVERLAY_UNSEALED", "error", "environment",
            "The runtime kernel differs from its sealed manifest (RUNTIME_OVERLAY.json); a run would stop with "
            "GF_COMPATIBILITY_001 after freezing its inputs: " + "; ".join(overlay_errors[:3]),
            "Restore the changed kernel files, or record the edit as a method change: raise the module version, "
            "append docs/release/VERSION_LEDGER.json and run scripts/seal_runtime_overlay.py --correction <id> "
            "(MODULE_DEVELOPER_101, built-in method upgrades).",
        ))
    missing_imports = list(runtime_capability["missing_imports"])
    checks["scientific_dependencies"] = {"passed": not missing_imports, "missing": missing_imports}
    if missing_imports:
        issues.append(_issue(
            "GF_PREFLIGHT_SCIENTIFIC_DEPENDENCY", "error", "environment",
            "Required scientific Python packages are missing: " + ", ".join(missing_imports),
            str(runtime_capability["corrective_action"]),
        ))

    try:
        psm_manifest = registry.manifest(str(selected.get("psm")), expected_slot="psm")
        if "storage.bid-cost-function" in psm_manifest.requires_capabilities:
            selected.setdefault("storage_cost", "dynamic-annual-storage-cost")
    except ValueError:
        # The normal selection error below provides the stable public message.
        pass
    selected_reports: list[dict[str, object]] = []
    resolution_graph = None
    try:
        registry.validate_selection(
            selected,
            selected_extensions=selected_extensions,
            extension_parameters=extension_parameters,
            available_data_roles=available_data_roles,
        )
        resolution_graph = registry.resolve_selection(
            selected,
            selected_extensions=selected_extensions,
            extension_parameters=extension_parameters,
            available_data_roles=available_data_roles,
        )
        validate_maturity_acknowledgements(
            registry,
            selected,
            selected_extensions,
            dict(project.get("maturity_acknowledgements") or {}),
        )
        all_conformance = {
            str(row["module_id"]): row for row in conformance_report(registry)["modules"]
        }
        selected_reports = [all_conformance[module_id] for module_id in selected.values()]
        failed = [row for row in selected_reports if row["status"] != "passed"]
        if failed:
            issues.append(_issue(
                "GF_PREFLIGHT_MODULE_CONFORMANCE", "error", "modules",
                "Selected module conformance failed: " + ", ".join(str(row["module_id"]) for row in failed),
                "Open Model modules, correct the listed manifest or callable contract, and run preflight again.",
            ))
    except (ValueError, KeyError) as exc:
        if getattr(exc, "code", None) == "GF_EXTENSION_HOOK_IMPORT":
            # A selected extension's hook failed to import during this
            # resolution: it is runtime-quarantined now, so the code is the
            # same as on every later preflight (P0-2 review).
            checks["module_quarantine"] = quarantine_check(registry, selected.values(), selected_extensions)
            issues.append(_issue(
                "GF_PREFLIGHT_MODULE_QUARANTINED", "error", "modules", str(exc),
                "Open Modules: disable or repair the quarantined entry, then select a working module.",
            ))
        else:
            issues.append(_issue(
                "GF_PREFLIGHT_MODULE_SELECTION", "error", "modules", str(exc),
                "Select one compatible registered module for every required model slot.",
            ))
    checks["modules"] = {"passed": bool(selected_reports) and all(row["status"] == "passed" for row in selected_reports), "selected": selected_reports}

    # Methodology profile and its combination whitelist (X0 S8, Q3, C16): the
    # same check as Study resolution and the run entry.
    whitelist_packs = [
        pack_entry(pack_root, pack_manifest),
        pack_entry(pack_selection.network_pack_root)
        if pack_selection is not None and pack_selection.network_pack_root is not None else None,
    ]
    try:
        methodology = resolve_project_methodology(project)
        violations = selection_combination_violations(
            methodology,
            registry=registry,
            modules=selected,
            extensions=selected_extensions,
            data_packs=whitelist_packs,
        )
        checks["methodology"] = {
            "passed": not violations,
            **methodology.to_dict(),
            "violations": violations,
        }
        if violations:
            issues.append(_issue(
                COMBINATION_ERROR_CODE, "error", "methodology",
                str(ProfileCombinationError(methodology.profile_id, violations)),
                "Select the corrected methodology, or keep to the thesis-lineage modules and data packs "
                "and disable external code for the doctoral reproduction.",
            ))
    except UnknownProfileError as exc:
        checks["methodology"] = {"passed": False, "error": str(exc)}
        issues.append(_issue(
            UnknownProfileError.code, "error", "methodology", str(exc),
            "Choose one of the installed methodology profiles.",
        ))

    try:
        revision_manifest = (
            pack_selection.revision_manifest
            if pack_selection is not None else dict(pack_manifest)
        )
        declared_revision = project.get("revision_sha256")
        # A mismatch is classified, never silently re-identified (X0 S11, Q13).
        classification = (
            classify_revision_mismatch(project, registry, revision_manifest, whitelist_packs=whitelist_packs)
            if declared_revision is not None else None
        )
        calculated_revision = (
            classification["calculated_sha256"] if classification is not None
            else project_fingerprint(project, registry, revision_manifest)
        )
        kind = classification["classification"] if classification is not None else "unsaved"
        revision_ok = kind in {"unsaved", "none"} or bool(classification and classification["automatic"])
        checks["project_revision"] = {
            "passed": revision_ok,
            "declared_sha256": declared_revision,
            "calculated_sha256": calculated_revision,
            "classification": classification,
        }
        if declared_revision is None:
            issues.append(_issue(
                "GF_PREFLIGHT_UNSAVED_REVISION", "warning", "project",
                "This legacy project has no saved immutable revision identity.",
                "Save the project once before using its output as a published scientific result.",
            ))
        elif classification is not None and classification["automatic"]:
            issues.append(_issue(
                str(classification["error_code"]), "warning", "project",
                "Only the code identity of this Study changed (no change to methods or results expected); "
                "a new revision is appended when the run starts.",
                "No action needed.",
            ))
        elif kind == "content_changed":
            issues.append(_issue(
                "GF_PREFLIGHT_PROJECT_REVISION", "error", "project",
                "The project content no longer matches its saved revision hash.",
                "Reload or save a new project revision; do not run an edited stale snapshot.",
            ))
        elif classification is not None and kind != "none":
            issues.append(_issue(
                str(classification["error_code"]), "error", "project",
                "The installed VALUE computes this Study differently from its saved revision ("
                + kind.replace("_", " ") + "); review the changes and confirm them as a new revision.",
                "Open the Study and confirm the listed changes (POST /api/projects/<id>/revision-migration).",
            ))
    except (ValueError, KeyError) as exc:
        checks["project_revision"] = {"passed": False, "error": str(exc)}
        issues.append(_issue("GF_PREFLIGHT_PROJECT_REVISION", "error", "project", str(exc), "Correct the project modules and save a new revision."))

    zonal_roles = {
        str(row.get("role")) for row in active_dataset_slots
        if str(row.get("role") or "").startswith("value.zonal.")
    }
    base_slots = tuple(
        row for row in active_dataset_slots if str(row.get("role")) not in zonal_roles
    )
    data_report = validate_data_pack(pack_root, pack_manifest, base_slots)
    network_data_report = None
    if zonal_roles and pack_selection is not None and pack_selection.network_pack_root is not None:
        network_slots = tuple(
            row for row in active_dataset_slots if str(row.get("role")) in zonal_roles
        )
        network_data_report = validate_data_pack(
            pack_selection.network_pack_root,
            pack_selection.network_manifest or {},
            network_slots,
        )
    checks["extension_readiness"] = {
        "selected": list(selected_extensions),
        "base_roles": len(dataset_slots),
        "conditional_roles": len(active_dataset_slots) - len(dataset_slots),
        "executes_in_scope": bool(selected_extensions) and scope_runs_extensions(mode),
    }
    # F-D2 (DECISIONS A16-3): a market-step-only scope never runs extension
    # hooks, so selecting extensions there would record methods that do not run.
    if selected_extensions and not scope_runs_extensions(mode):
        issues.append(_issue(
            "GF_PREFLIGHT_SCOPE_SKIPS_EXTENSIONS", "error", "project",
            scope_extension_block_message(selected_extensions),
            "Choose two-period or a longer scope, or deselect the extension(s) in the Study.",
        ))
    checks["data_pack"] = data_report
    checks["network_data_pack"] = network_data_report
    if not data_report["valid"]:
        issues.append(_issue(
            "GF_PREFLIGHT_DATA_PACK", "error", "data",
            str(data_report["errors"][0]),
            "Open Data interfaces and correct or re-import the named semantic role.",
        ))
    if network_data_report is not None and not network_data_report["valid"]:
        issues.append(_issue(
            "GF_PREFLIGHT_NETWORK_DATA_PACK", "error", "data",
            str(network_data_report["errors"][0]),
            "Correct or reinstall the signed network overlay; do not modify the base research data pack.",
        ))
    for warning in data_report["warnings"]:
        issues.append(_issue("GF_PREFLIGHT_DATA_WARNING", "warning", "data", str(warning), "Review the declared adapter behaviour before publication."))
    # P0-5a S9: the chronology and plausibility layers never decide `valid`;
    # the run's methodology profile decides which of their findings block.
    issues.extend(data_eligibility_issues(project, pack_manifest, data_report))
    if network_data_report is not None:
        for warning in network_data_report["warnings"]:
            issues.append(_issue(
                "GF_PREFLIGHT_NETWORK_DATA_WARNING", "warning", "data", str(warning),
                "Review the signed network-overlay evidence before publication.",
            ))

    resolved = None
    policy_dict: dict[str, object] | None = None
    try:
        policy = resolve_run_policy(mode)
        validate_pack_run_mode(pack_manifest, mode)
        policy_dict = policy.to_dict(project)
        resolved = resolve_scheme_c_parameters(
            pack_root,
            project.get("parameters") or project.get("parameter_overrides") or {},  # type: ignore[arg-type]
            project.get("runtime_options") or project.get("runtime_controls") or {},  # type: ignore[arg-type]
            periods_per_year=policy.periods_per_year,
        )
        checks["parameters"] = {"passed": True, **resolved.to_dict()}
        for warning in resolved.warnings:
            issues.append(_issue("GF_PREFLIGHT_PARAMETER_WARNING", "warning", "parameters", str(warning), "Review this experimental assumption in Advanced settings."))
    except (ParameterValidationError, ValueError, KeyError) as exc:
        checks["parameters"] = {"passed": False, "error": str(exc)}
        teaching_mode_error = str(exc).startswith("Teaching data pack ")
        issues.append(_issue(
            "GF_PREFLIGHT_TEACHING_RUN_MODE" if teaching_mode_error else "GF_PREFLIGHT_PARAMETERS",
            "error",
            "data" if teaching_mode_error else "parameters",
            str(exc),
            (
                "Use the tutorial run button for this shortened teaching pack."
                if teaching_mode_error
                else "Correct the highlighted project years or Advanced settings."
            ),
        ))

    if policy_dict is not None:
        domain_readiness = build_domain_readiness(
            project,
            pack_root=pack_root,
            pack_manifest=pack_manifest,
            registry=registry,
            requested_periods=int(policy_dict["periods_per_year"]),
            network_pack_root=(
                pack_selection.network_pack_root if pack_selection is not None else None
            ),
            network_pack_manifest=(
                pack_selection.network_manifest if pack_selection is not None else None
            ),
        )
        checks["domain_readiness"] = domain_readiness
        issues.extend(dict(item) for item in domain_readiness["issues"])

    writable = output_root.is_dir() and os.access(output_root, os.W_OK)
    checks["output"] = {"path": str(output_root), "passed": writable}
    if not writable:
        issues.append(_issue("GF_PREFLIGHT_OUTPUT_PERMISSION", "error", "output", f"The run output directory is not writable: {output_root}", "Choose or repair a writable local workspace."))

    estimates: dict[str, object] = {}
    resource_readiness: dict[str, object] | None = None
    if resolved is not None and policy_dict is not None:
        try:
            volume = shutil.disk_usage(output_root)
            free = volume.free
        except OSError:
            volume = None
            free = 0
        staged_zonal = (
            selected.get("psm") == "value-staged-bid-at-cost-psm"
            and selected.get("balancing") == "value-zonal-redispatch-balancing"
        )
        if staged_zonal:
            try:
                if pack_selection is None or pack_selection.network_pack_root is None:
                    raise ValueError("Selected staged/zonal graph has no resolved network pack")
                if resolution_graph is None:
                    raise ValueError("Selected module resolution graph is unavailable")
                estimate_run_context, estimate_year_context, headroom_bounds = build_frozen_resource_contexts(
                    project=project,
                    policy=policy_dict,
                    run_id=preflight_run_id or f"resource-estimate-{project.get('id') or 'study'}",
                    pack_root=pack_root,
                    network_pack_root=pack_selection.network_pack_root,
                    registry=registry,
                )
                estimate = estimate_run_resources(
                    project=project,
                    policy=policy_dict,
                    run_context=estimate_run_context,
                    year_context=estimate_year_context,
                    calibration_root=(
                        resource_calibration_root
                        or user_data_root() / "resource-calibration"
                    ),
                    free_bytes=free,
                    quota_policy=resource_quota_policy,
                    target_volume_bytes=(volume.total if volume is not None else None),
                    calibration_runner=resource_calibration_runner,
                    headroom_bounds=headroom_bounds,
                )
                usage = _quota_usage(runs_root, preflight_run_id)
                decision = resource_gate_report(
                    project=project,
                    estimate=estimate,
                    free_bytes=free,
                    quota_policy=resource_quota_policy,
                    existing_run_bytes=usage.existing_run_bytes,
                    already_reserved_bytes=usage.outstanding_reserved_bytes,
                )
                estimates = {
                    "label": "estimate_not_guarantee",
                    **estimate.to_dict(),
                    "periods": estimate.row_cardinality["periods"],
                    "ledger_rows": dict(estimate.row_cardinality),
                    "disk_bytes": estimate.persisted_bytes,
                    "context_copies": estimate.calibration_basis["context_copies"],
                    "persisted_safety_multiplier": estimate.calibration_basis[
                        "persisted_safety_multiplier"
                    ],
                }
                checks["disk"] = {
                    "passed": bool(decision["accepted"]),
                    **decision,
                    "estimated_persisted_bytes": estimate.persisted_bytes,
                    "estimated_temporary_bytes": estimate.temporary_bytes,
                    "reserve_bytes": estimate.reserve_bytes,
                }
                for error in decision["errors"]:
                    issues.append({
                        **dict(error),
                        "corrective_action": "Choose Summary, move the output root, or free space.",
                    })
                resource_readiness = {
                    "trace_profile": estimate.trace_profile,
                    "run_context_sha256": canonical_context_sha256(estimate_run_context),
                    "year_context_sha256": canonical_context_sha256(estimate_year_context),
                    "calibration_key": dict(estimate.calibration_basis["calibration_key"]),
                    "calibration_basis": dict(estimate.calibration_basis),
                    "free_space_observation": {
                        "free_bytes": free,
                        "target_volume_capacity_bytes": (
                            volume.total if volume is not None else None
                        ),
                    },
                    "quota_decision": decision,
                    "selected_output_root": str(output_root),
                    "estimate": estimate.to_dict(),
                }
            except (OSError, TypeError, ValueError) as exc:
                checks["disk"] = {"passed": False, "error": str(exc)}
                issues.append(_issue(
                    "VALUE_PREFLIGHT_RESOURCE_ESTIMATE", "error", "output", str(exc),
                    "Correct the selected staged/zonal graph or its local calibration evidence.",
                ))
        else:
            estimates = _estimates(
                project,
                policy_dict,
                resolved.runtime.values,
                runs_root,
                _data_scale(pack_root, pack_manifest),
            )
            required = int(estimates["disk_bytes"])
            checks["disk"] = {"passed": free >= required * 2, "free_bytes": free, "estimated_output_bytes": required, "safety_factor": 2}
            if free < required * 2:
                issues.append(_issue("GF_PREFLIGHT_DISK_SPACE", "error", "output", "Free disk space is below twice the estimated run output size.", "Free disk space or reduce market tracing before launch."))
            # The same quota rule the reservation applies (F5-04): no preflight
            # pass followed by a 507 at launch.
            usage = _quota_usage(runs_root, preflight_run_id)
            reserved = output_reservation_bytes(estimates)
            quota_reasons = global_quota_reasons(usage, reserved, resource_quota_policy)
            checks["quota"] = {
                "passed": not quota_reasons, "required_bytes": reserved,
                "reason_codes": quota_reasons, **usage.to_dict(),
                "global_quota_bytes": resource_quota_policy.global_quota_bytes,
                "per_run_quota_bytes": resource_quota_policy.per_run_quota_bytes,
            }
            if quota_reasons:
                issues.append(_issue(
                    "GF_PREFLIGHT_RUN_QUOTA", "error", "output",
                    "The run would exceed the local run-output quota (" + ", ".join(quota_reasons) + ").",
                    " ".join(QUOTA_CORRECTIVE_ACTIONS),
                ))
        export_format = str(resolved.runtime.values.get("runtime.market_export_format", "sqlite"))
        parquet_ok = export_format != "parquet" or importlib.util.find_spec("pyarrow") is not None
        checks["optional_parquet"] = {"requested": export_format == "parquet", "passed": parquet_ok}
        if not parquet_ok:
            issues.append(_issue("GF_PREFLIGHT_OPTIONAL_PARQUET", "error", "output", "Parquet export was selected but pyarrow is not installed.", "Use the default SQLite output or install the approved optional pyarrow dependency."))
        if not bool(resolved.runtime.values.get("runtime.checkpoint_enabled", True)) and int(policy_dict["years"]) > 1:
            issues.append(_issue("GF_PREFLIGHT_CHECKPOINT_DISABLED", "warning", "recovery", "Annual checkpoints are disabled for a multi-year run.", "Enable checkpoints unless the loss of completed years after interruption is acceptable."))
        checks["run_policy"] = policy_dict

    errors = [row for row in issues if row["severity"] == "error"]
    warnings = [row for row in issues if row["severity"] == "warning"]
    return {
        "schema_version": SCHEMA_VERSION,
        "accepted": not errors,
        "mode": mode,
        "project_id": project.get("id"),
        "project_revision_sha256": checks.get("project_revision", {}).get("calculated_sha256") if isinstance(checks.get("project_revision"), Mapping) else None,
        "data_pack_id": pack_manifest.get("id"),
        "runtime_capability": VALUE_NATIVE,
        "checks": checks,
        "issues": issues,
        "errors": errors,
        "warnings": warnings,
        "estimates": estimates,
        "resource_readiness": resource_readiness,
    }


def main() -> None:
    from .dataset_slots import DATASET_SLOTS

    parser = argparse.ArgumentParser(description="Preflight a VALUE research project")
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--pack", required=True, type=Path)
    parser.add_argument("--mode", choices=("smoke", "two_year_smoke", "validation_24h", "validation_168h", "two_year", "full"), default="smoke")
    parser.add_argument("--output-root", type=Path, default=user_data_root() / "runs")
    parser.add_argument("--runs-root", type=Path)
    parser.add_argument("--network-pack", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    project = json.loads(args.project.read_text(encoding="utf-8"))
    manifest = json.loads((args.pack / "manifest.json").read_text(encoding="utf-8"))
    report = run_preflight(
        project, mode=args.mode, pack_root=args.pack, pack_manifest=manifest,
        dataset_slots=DATASET_SLOTS, output_root=args.output_root,
        runs_root=args.runs_root,
        network_pack_root=(args.network_pack.resolve() if args.network_pack else None),
    )
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    raise SystemExit(0 if report["accepted"] else 1)


if __name__ == "__main__":
    main()
