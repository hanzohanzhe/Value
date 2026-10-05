"""Background entry point for project-composed VALUE modules."""

from __future__ import annotations

import argparse
import json
import re
import secrets
import sys
import traceback
from datetime import datetime
from pathlib import Path

from backend.frozen_run_recovery import verify_recovered_configuration, verify_recovered_inputs
from backend.lifecycle.atomic_io import atomic_write_json
from backend.lifecycle.run_status import (
    WRITER_WORKER,
    LateWriteRejected,
    guard_worker_write,
    update_status,
)
from backend.lifecycle.worker_lease import WorkerTerminated
from backend.run_execution import verify_run_execution
from gridform_core.application import run_project_application
from gridform_core.errors import public_failure, warning_event
from gridform_core.provenance import write_failed_run_provenance
from gridform_core.methodology import methodology_record
from gridform_core.run_policy import resolve_run_policy
from gridform_core.project_revision import attach_revision_identity
from gridform_core.preflight import run_preflight
from gridform_core.preflight_resources import (
    ResourceCalibrationKey,
    build_frozen_resource_contexts,
    selected_staged_zonal_calibration_runner,
)
from gridform_core.dataset_slots import DATASET_SLOTS
from gridform_core.module_quarantine import ModuleQuarantinedError, blocker_error, selection_blockers
from gridform_core.v2.module_manifest import workspace_registry
from gridform_core.run_snapshot import SnapshotError, verify_run_input_snapshot
from gridform_core.run_input_snapshot import (
    ResourceSnapshotMismatch,
    verify_frozen_resource_readiness,
)
from gridform_core.v2.orchestrator import CancellationRequested
from gridform_core.run_lifecycle import cancellation_requested
from gridform_core.runtime_paths import user_data_root
from gridform_core.results_summary import validate_vre_curtailment_attribution
from gridform_core.zonal_pack_selection import resolve_zonal_pack_selection
from gridform_core.failure_evidence import (
    RECOVERY_AUTHORIZATION_SCHEMA_VERSION,
    recovery_authorization_id,
)
from gridform_core.module_context import RunStaticContext, YearContext, canonical_context_sha256


ROOT = Path(__file__).resolve().parents[1]
STATE_ROOT = user_data_root()


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def write_json(path: Path, payload: dict) -> None:
    """Write a worker-owned artifact (never ``status.json``; see run_status)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, payload)


def _load_declared_run_status(
    status_path: Path, run_id: str, project_id: str
) -> dict[str, object]:
    try:
        value = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"The declared run status is missing or corrupt: {status_path}"
        ) from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"The declared run status is not a JSON object: {status_path}")
    if value.get("id") != run_id or value.get("project_id") != project_id:
        raise RuntimeError(
            "The declared run status identity does not match the worker request"
        )
    return value


_PERIOD_CANCEL = re.compile(
    r"after committed model year (?P<year>\d+) period (?P<period>\d+)"
)


def _issuance_nonce() -> str:
    """Generate one runtime-only identity for each recovery grant issuance."""
    return secrets.token_hex(16)


def _issue_recovery_authorization(
    status_path: Path, *, run_id: str, year: int, committed_period: int
) -> dict[str, object] | None:
    output = status_path.parent / "model-output"
    try:
        run_context = RunStaticContext.from_dict(json.loads(
            (output / "market" / "context" / "run-context.json").read_text(encoding="utf-8")
        ))
        year_context = YearContext.from_dict(json.loads(
            (output / "market" / "context" / f"year-{year}.json").read_text(encoding="utf-8")
        ))
        checkpoints = sorted(
            (output / "checkpoints-v2").glob("state-*.json"),
            key=lambda path: int(path.stem.split("-")[-1]),
        )
        checkpoint = json.loads(checkpoints[-1].read_text(encoding="utf-8"))
        state_sha256 = str(checkpoint["state_sha256"])
        if (
            run_context.run_id != run_id
            or year_context.run_id != run_id
            or year_context.year != year
            or year_context.run_context_sha256 != canonical_context_sha256(run_context)
            or year_context.transition_lineage.get("annual_input_state_sha256") != state_sha256
        ):
            return None
        authorization: dict[str, object] = {
            "schema_version": RECOVERY_AUTHORIZATION_SCHEMA_VERSION,
            "run_id": run_id,
            "incomplete_year": year,
            "committed_period": committed_period,
            "checkpoint_state_sha256": state_sha256,
            "run_context_sha256": canonical_context_sha256(run_context),
            "year_context_sha256": canonical_context_sha256(year_context),
            "source": "period_boundary_cancellation",
            "issuance_nonce": _issuance_nonce(),
            "state": "issued",
        }
        authorization["authorization_id"] = recovery_authorization_id(authorization)
        return authorization
    except (OSError, ValueError, TypeError, KeyError, IndexError, json.JSONDecodeError):
        return None


def _present_recovery_authorization(
    declared_status: dict[str, object],
) -> dict[str, object] | None:
    authorization = declared_status.get("recovery_authorization")
    if (
        declared_status.get("status") == "cancelled"
        and declared_status.get("execution_status") == "cancelled"
        and isinstance(authorization, dict)
        and authorization.get("state") == "issued"
        and authorization.get("authorization_id")
        == recovery_authorization_id(authorization)
    ):
        return {**authorization, "state": "presented"}
    return None


def record_run_failure(
    status_path: Path,
    *,
    run_id: str,
    project_id: str,
    mode: str,
    error: BaseException,
    error_code: str | None = None,
) -> dict:
    """Record a worker failure in two phases (P0-3 S2).

    Phase one refuses a late write (the run already left the active states)
    before any diagnostic or provenance artifact is touched; phase two writes
    the diagnostic and seals the failed provenance outside the status lock; the
    final status change merges into the current file under its lock.
    """
    public = public_failure(error)
    code = error_code or public.code
    run_dir = status_path.parent
    observed = guard_worker_write(run_dir, attempted_transition="failed", reason_code=code)
    warnings: list[dict[str, str]] = []
    if observed == "invalid":
        warnings.append(warning_event(
            "GF_STATUS_READ_WARNING", "artifact",
            "The previous public status could not be read; a new failure status was created.",
        ))
    elif observed == "not_object":
        warnings.append(warning_event(
            "GF_STATUS_READ_WARNING", "artifact",
            "The previous public status was structurally invalid; a new failure status was created.",
        ))
    diagnostic = run_dir / "diagnostics" / "error.json"
    write_json(diagnostic, {
        "schema_version": "value.run-diagnostic/v1",
        "run_id": run_id,
        "error_code": code,
        "category": public.category,
        "exception_type": type(error).__name__,
        "exception_message": str(error),
        "traceback": traceback.format_exc(),
        "recorded_at": now(),
    })
    provenance = None
    try:
        provenance = write_failed_run_provenance(
            run_dir,
            run_id=run_id,
            project_id=project_id,
            error_code=code,
        )
    except Exception:
        warnings.append(warning_event(
            "GF_FAILED_PROVENANCE_WARNING", "artifact",
            "The failed run could not be sealed while transient artifacts remained; "
            "the failure status and local diagnostic were retained.",
        ))

    def apply(existing: dict) -> None:
        previous_warnings = existing.get("warnings")
        if not isinstance(previous_warnings, list):
            previous_warnings = []
        existing.update({
            "id": run_id,
            "project_id": project_id,
            "mode": mode,
            "execution_status": "failed",
            "current_stage": "Run failed",
            "error": public.message,
            "error_code": code,
            "error_category": public.category,
            "diagnostic_artifact": "diagnostics/error.json",
            "warnings": [*previous_warnings, *warnings],
            "finished_at": now(),
        })
        if provenance is not None:
            existing["provenance_artifact"] = provenance.name
        else:
            existing.pop("provenance_artifact", None)
        existing.pop("traceback", None)
        for key in (
            "recovery_authorization", "cancellation_boundary",
            "current_model_year_complete", "resume_boundary", "resume_mode",
        ):
            existing.pop(key, None)

    return update_status(
        run_dir, mutate=apply, transition="failed", reason_code=code,
        writer=WRITER_WORKER, legacy_replace=True,
    )


def record_run_cancelled(status_path: Path, *, run_id: str, project_id: str, mode: str, message: str) -> dict:
    run_dir = status_path.parent
    guard_worker_write(
        run_dir, attempted_transition="cancelled", reason_code="GF_RUN_CANCELLED_SAFE_BOUNDARY",
    )
    cancellation = {
        "cancellation_boundary": "before_worker_execution",
        "current_model_year_complete": None,
        "resume_boundary": "prior_annual_checkpoint",
        "resume_mode": "start_from_verified_checkpoint",
    }
    match = _PERIOD_CANCEL.search(message)
    authorization = None
    if match:
        cancellation = {
            "cancellation_boundary": "after_committed_period",
            "current_model_year_complete": False,
            "resume_boundary": "prior_annual_checkpoint",
            "resume_mode": "recompute_full_incomplete_year",
        }
        authorization = _issue_recovery_authorization(
            status_path, run_id=run_id, year=int(match.group("year")),
            committed_period=int(match.group("period")),
        )
    elif "after verified model year" in message:
        cancellation = {
            "cancellation_boundary": "after_annual_checkpoint",
            "current_model_year_complete": True,
            "resume_boundary": "latest_annual_checkpoint",
            "resume_mode": "continue_next_model_year",
        }

    def apply(existing: dict) -> None:
        existing.update({
            "id": run_id, "project_id": project_id, "mode": mode,
            "execution_status": "cancelled",
            "current_stage": "Cancelled at a model-safe boundary",
            **cancellation,
            "cancellation_message": message, "finished_at": now(),
        })
        existing.pop("recovery_authorization", None)
        if authorization is not None:
            existing["recovery_authorization"] = authorization

    return update_status(
        run_dir, mutate=apply, transition="cancelled",
        reason_code="GF_RUN_CANCELLED_SAFE_BOUNDARY", writer=WRITER_WORKER, legacy_replace=True,
    )


# Reviewed basis of every CEM cost-ledger line that can enter the headline
# (P0-9 S9 review response): True = the line contains blackout x VoLL, False =
# it does not, ZONAL_VOLL = it does exactly when the Run cleared zonal
# redispatch.  A line id outside this map makes the basis unknown ("VoLL basis
# not recorded") instead of being guessed from its name.
#   operation.blackout_prevention_failure   perfect_foresight_psm: blackout x VoLL
#   operation.blackout_reliability           P0-6 S4 native VoLL line (C30)
#   operation.generation_import_and_reliability  scheme_c native/staged PSM:
#       copperplate balancing prices dispatch only (no VoLL, plan 4.6 / C30);
#       zonal redispatch adds load_shedding x VoLL to the same class total, and
#       staged_psm._build_redispatch_summary_rows enforces that reconciliation
#       whenever a network pack is bound (the ledger then carries zonal.* lines)
#   operation.psm_resource_cost              opaque total: basis unknown (absent here)
ZONAL_VOLL = "included_when_zonal_redispatch"
VOLL_BASIS_BY_LEDGER_LINE: dict[str, bool | str] = {
    "commissioned_fleet.annualised_capital": False,
    "network.commissioned_assets.annualised_capex": False,
    "network.commissioned_assets.fixed_opex": False,
    "operation.blackout_prevention_failure": True,
    "operation.blackout_reliability": True,
    "operation.generation_and_import_variable": False,
    "operation.generation_import_and_reliability": ZONAL_VOLL,
    "operation.storage_cycle_depreciation": False,
    "operation.storage_variable_degradation": False,
}


def _system_cost_includes_voll(ledger: dict | None) -> bool | None:
    """Whether the headline system cost contains the value of lost load.

    The legacy (doctoral) total adds Lost_Value_of_Electricity.  For a CEM
    resource-cost ledger the answer comes from the declared components of the
    headline (``VOLL_BASIS_BY_LEDGER_LINE``): True when a VoLL line is part of
    it, False when every included line is known not to be VoLL, and None
    ("VoLL basis not recorded") when an included line is not in the map
    (P0-9 S9, F3-04)."""

    if ledger is None:
        return True
    lines = [line for line in ledger.get("lines") or [] if isinstance(line, dict)]
    zonal = any(str(line.get("id", "")).startswith("zonal.") for line in lines)
    bases = []
    for line in lines:
        if not line.get("included_in_cem_system_cost"):
            continue
        basis = VOLL_BASIS_BY_LEDGER_LINE.get(str(line.get("id", "")))
        bases.append(zonal if basis == ZONAL_VOLL else basis)
    if any(basis is True for basis in bases):
        return True
    if not bases or any(basis is None for basis in bases):
        return None
    return False


def _frontend_results(
    exact: dict,
    modules: dict[str, str],
    vre_curtailment_attribution: dict | None = None,
    *,
    mode: str,
    periods_per_year: int,
    expected_years: tuple[int, ...],
) -> list[dict]:
    capacities_by_year = {int(row["Year"]): row for row in exact["capacity_history"]}
    cost_ledgers_by_year = {
        int(row["year"]): row for row in exact.get("cem_cost_ledgers", [])
    }
    investments_by_year: dict[int, list[dict]] = {}
    carbon_by_year = {
        int(row["year"]): row for row in exact.get("carbon_ledgers", [])
    }
    planning_by_year = {
        int(row["year"]): row for row in exact.get("planning_summary", [])
    }
    curtailment_validation = validate_vre_curtailment_attribution(
        vre_curtailment_attribution,
        mode=mode,
        periods_per_year=periods_per_year,
        expected_years=expected_years,
    )
    curtailment_by_year = curtailment_validation["annual_by_year"]
    for row in exact["investment_decisions"]:
        investments_by_year.setdefault(int(row["year"]), []).append(row)

    results = []
    for cost in exact["system_cost_history"]:
        year = int(cost["Year"])
        capacity = capacities_by_year.get(year, {})
        investments = investments_by_year.get(year, [])
        ledger = cost_ledgers_by_year.get(year)
        carbon = carbon_by_year.get(year, {})
        curtailment = curtailment_by_year.get(year)
        cem_total = (
            ledger.get("cem_system_cost_gbp")
            if ledger is not None
            else cost["Total_System_Cost_GBP"]
        )
        cem_per_mwh = (
            ledger.get("cem_system_cost_gbp_per_mwh_served")
            if ledger is not None
            else cost["Cost_per_MWh_GBP"]
        )
        results.append({
            "year": year,
            "metrics": {
                "total_system_cost_gbp": cem_total,
                "cost_per_mwh_gbp": cem_per_mwh,
                "system_cost_definition_id": (
                    ledger.get("definition_id") if ledger else "legacy_storage_tariff"
                ),
                "system_cost_reconciliation_status": (
                    ledger.get("status") if ledger else "legacy_unreconciled"
                ),
                "legacy_system_cost_gbp": cost["Total_System_Cost_GBP"],
                "legacy_cost_per_mwh_generated": cost["Cost_per_MWh_GBP"],
                "demand_served_mwh": ledger.get("demand_served_mwh") if ledger else None,
                "total_energy_generated_mwh": cost["Total_Energy_Generated_MWh"],
                "total_levelized_capital_cost_gbp": cost["Total_Levelized_Capital_Cost_GBP"],
                # P0-7 S8 (P4-03): memo of the capital kept out of the headline (corrected).
                "ror_hydro_compatibility_capital_gbp": cost.get("RoR_Hydro_Compatibility_Capital_GBP"),
                "total_operational_cost_gbp": cost["Total_Operational_Cost_GBP"],
                # F3-04 (P0-9 S9): a mechanism the path does not model is null
                # with a status, never 0.0; the legacy path records all five
                # components of its headline (VoLL included).
                "cm_mechanism_cost_gbp": cost.get("CM_Mechanism_Cost_Added_to_System_GBP"),
                "cm_mechanism_cost_status": cost.get("CM_Mechanism_Cost_Status") or (
                    "recorded" if cost.get("CM_Mechanism_Cost_Added_to_System_GBP") is not None else "not_recorded"
                ),
                "decarbonization_mechanism_cost_gbp": cost.get("Decarbonization_Mechanism_Cost_Added_to_System_GBP"),
                "decarbonization_mechanism_cost_status": cost.get("Decarbonization_Mechanism_Cost_Status") or (
                    "recorded" if cost.get("Decarbonization_Mechanism_Cost_Added_to_System_GBP") is not None else "not_recorded"
                ),
                "lost_value_of_electricity_gbp": cost.get("Lost_Value_of_Electricity_GBP"),
                "system_cost_includes_voll": _system_cost_includes_voll(ledger),
                "blackout_mwh": cost["Total_Energy_Deficit_MWh"],
                "curtailment_mwh": cost.get("Total_VRE_Curtailed_MWh", cost.get("Total_Excess_Energy_MWh")),
                "vre_curtailment_mwh": curtailment.get("total_mwh") if curtailment is not None else None,
                "vre_curtailment_rate": curtailment.get("rate") if curtailment is not None else None,
                "redispatch_net_impact_mwh": curtailment.get("redispatch_net_mwh") if curtailment is not None else None,
                "vre_curtailment_attribution_status": curtailment_validation["status"],
                "vre_curtailment_attribution_reason_code": curtailment_validation["reason_code"],
                "imports_mwh": cost.get("Total_Imports_MWh"),
                "storage_charge_mwh": cost.get("Total_Storage_Charge_MWh"),
                "storage_discharge_mwh": cost.get("Total_Storage_Discharge_MWh"),
                "total_carbon_emissions_tco2e": carbon.get("total_carbon_emissions_tco2e"),
                "carbon_status": carbon.get("status", "not_evaluated"),
                "carbon_intensity_kgco2e_per_mwh_delivered": (carbon.get("intensities") or {}).get("delivered_demand_kgco2e_per_mwh") if isinstance(carbon.get("intensities"), dict) else None,
            },
            "capacity_mw": {
                "solar": capacity.get("Solar_Capacity_MW", 0),
                "onshore": capacity.get("Onshore_Capacity_MW", 0),
                "offshore": capacity.get("Offshore_Capacity_MW", 0),
                "storage": capacity.get("Total_Storage_Capacity_MW", 0),
                "CCGT": capacity.get("CCGT_Capacity_MW", 0),
                "OCGT": capacity.get("OCGT_Capacity_MW", 0),
            },
            "capacity_mwh": {"storage": capacity.get("Total_Storage_Energy_Capacity_MWh")},
            "planning": planning_by_year.get(year, {}),
            "decisions": [
                {
                    "module_id": modules["investment"],
                    "additions_mw": {
                        row["technology"]: row["suggested_addition_mw"]
                        for row in investments
                    },
                    "retirements_mw": {},
                    "evidence": {
                        "source": "project-selected executable VALUE module"
                    },
                },
                {
                    "module_id": modules["pipeline"],
                    "additions_mw": {},
                    "retirements_mw": {},
                    "evidence": {"source": "module-events.jsonl"},
                },
                {
                    "module_id": modules["vre_cap"],
                    "additions_mw": {},
                    "retirements_mw": {},
                    "evidence": {"source": "module-events.jsonl"},
                },
                {
                    "module_id": modules["storage_cap"],
                    "additions_mw": {},
                    "retirements_mw": {},
                    "evidence": {"source": "module-events.jsonl"},
                },
            ],
        })
    return results


def _refuse_quarantined_selection(input_snapshot_root: Path, registry: object) -> None:
    """Fail with GF_MODULE_QUARANTINED when the frozen Study selects local code
    the registry has quarantined (P0-2): never a generic verification error,
    never a run left queued."""

    try:
        project = json.loads((input_snapshot_root / "project.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return  # snapshot verification reports the damaged snapshot itself
    if not isinstance(project, dict):
        return
    blockers = selection_blockers(
        registry,
        dict(project.get("modules") or {}).values(),
        tuple(project.get("selected_extensions") or ()),
    )
    if blockers:
        raise blocker_error("GF_MODULE_QUARANTINED", blockers)


def run(project_id: str, run_id: str, mode: str) -> None:
    run_dir = STATE_ROOT / "runs" / run_id
    status_path = run_dir / "status.json"
    input_snapshot_root = run_dir / "input-snapshot"
    registry = workspace_registry()
    _refuse_quarantined_selection(input_snapshot_root, registry)
    try:
        input_snapshot = verify_run_input_snapshot(input_snapshot_root, registry)
    except ModuleQuarantinedError:
        raise
    except (OSError, ValueError, SnapshotError) as exc:
        raise RuntimeError(f"Frozen run inputs failed verification: {exc}") from exc
    if cancellation_requested(run_dir):
        raise CancellationRequested("Cancellation accepted before worker execution")
    project = json.loads((input_snapshot_root / "project.json").read_text(encoding="utf-8"))
    declared = _load_declared_run_status(status_path, run_id, project_id)
    if declared.get("mode") != mode or declared.get("input_snapshot_id") != input_snapshot.get("snapshot_id"):
        raise RuntimeError("Worker scope or snapshot differs from its declared Run")
    verify_run_execution(run_dir, project, source_root=Path(__file__).resolve().parent.parent, data_home=STATE_ROOT, require_record=True)
    verify_recovered_configuration(project, mode=mode)
    policy = resolve_run_policy(mode)
    start_year, end_year = policy.years(project)
    periods = policy.periods_per_year
    modules = dict(project["modules"])
    psm_manifest = registry.manifest(str(modules["psm"]), expected_slot="psm")
    if "storage.bid-cost-function" in psm_manifest.requires_capabilities:
        modules.setdefault("storage_cost", "dynamic-annual-storage-cost")
    pack_root = input_snapshot_root / "pack"
    network_pack_root = (
        input_snapshot_root / "network-pack"
        if (input_snapshot_root / "network-pack" / "manifest.json").is_file()
        else None
    )
    verify_recovered_inputs(project, pack_root, network_pack_root, frozen=True)
    pack_manifest_path = pack_root / "manifest.json"
    pack_manifest = json.loads(pack_manifest_path.read_text(encoding="utf-8"))
    pack_selection = resolve_zonal_pack_selection(
        project,
        base_pack_root=pack_root,
        explicit_network_pack_root=network_pack_root,
    )
    if not project.get("revision_sha256"):
        project = attach_revision_identity(
            project, registry, pack_selection.revision_manifest
        )
    preflight_path = run_dir / "preflight.json"
    if preflight_path.is_file():
        preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    else:
        preflight = run_preflight(
            project,
            mode=mode,
            pack_root=pack_root,
            pack_manifest=pack_manifest,
            dataset_slots=DATASET_SLOTS,
            output_root=run_dir.parent,
            runs_root=run_dir.parent,
            network_pack_root=network_pack_root,
            resource_calibration_root=STATE_ROOT / "resource-calibration",
            preflight_run_id=run_id,
            resource_calibration_runner=(
                selected_staged_zonal_calibration_runner(
                    project=project,
                    pack_root=pack_root,
                    network_pack_root=network_pack_root,
                    registry=registry,
                )
                if network_pack_root is not None
                and modules.get("psm") == "value-staged-bid-at-cost-psm"
                and modules.get("balancing") == "value-zonal-redispatch-balancing"
                else None
            ),
        )
        write_json(preflight_path, preflight)
    if not preflight.get("accepted"):
        errors = preflight.get("errors") or []
        message = errors[0].get("message") if errors else "Run preflight failed"
        raise RuntimeError(str(message))
    staged_zonal = (
        modules.get("psm") == "value-staged-bid-at-cost-psm"
        and modules.get("balancing") == "value-zonal-redispatch-balancing"
    )
    resource_readiness = preflight.get("resource_readiness")
    if staged_zonal and not isinstance(resource_readiness, dict):
        raise RuntimeError("Frozen staged/zonal resource readiness is missing")
    if staged_zonal:
        assert network_pack_root is not None
        actual_run_context, actual_year_context, actual_headroom = (
            build_frozen_resource_contexts(
                project=project,
                policy=policy.to_dict(project),
                run_id=run_id,
                pack_root=pack_root,
                network_pack_root=network_pack_root,
                registry=registry,
            )
        )
        actual_key = ResourceCalibrationKey.from_inputs(
            project=project,
            policy=policy.to_dict(project),
            run_context=actual_run_context,
            trace_profile=actual_run_context.trace_profile,
            headroom_bounds=actual_headroom,
        )
        try:
            verify_frozen_resource_readiness(
                input_snapshot_root,
                project=project,
                selected_output_root=run_dir.parent,
                actual_run_context=actual_run_context,
                actual_year_context=actual_year_context,
                actual_calibration_key=actual_key.to_dict(),
            )
        except ResourceSnapshotMismatch as exc:
            raise RuntimeError(
                f"Frozen staged/zonal resource identities failed verification: {exc}"
            ) from exc
    write_json(run_dir / "project-snapshot.json", project)
    write_json(run_dir / "data-pack-snapshot.json", pack_manifest)
    declared_status = _load_declared_run_status(status_path, run_id, project_id)
    presented_authorization = _present_recovery_authorization(declared_status)
    running_fields = {
        "id": run_id,
        "execution_engine": "value-annual-orchestrator/v2",
        "project_id": project_id,
        "project_name": project["name"],
        "mode": mode,
        "started_at": now(),
        "current_stage": (
            "Running the two-period modular PSM and CEM-chain verification"
            if mode == "smoke"
            else "Running a two-period-per-year PSM, CEM and state-transition verification"
            if mode == "two_year_smoke"
            else "Running one teaching day through the selected VALUE PSM"
            if mode == "value_101_day"
            else f"Running the project-selected VALUE modules for {start_year}-{end_year}"
        ),
        "completed_years": 0,
        "total_years": end_year - start_year + 1,
        "results": [],
        "modules": modules,
        "python": sys.version.split()[0],
        "runtime_capability": "value-native",
        "run_policy": policy.to_dict(project),
        "execution_status": "running",
        "contract_validation_status": "not_evaluated",
        "scientific_validation_status": "not_evaluated",
        "preflight_artifact": "preflight.json",
        "preflight_warnings": preflight.get("warnings", []),
        "input_snapshot_id": input_snapshot.get("snapshot_id"),
        "input_tree_sha256": input_snapshot.get("input_tree_sha256"),
        # The methodology profile is part of the run's method identity and is
        # recorded before execution, so a failed run carries it too (X0 S9).
        "methodology": methodology_record(project),
    }

    def mark_running(current: dict) -> None:
        for key in (
            "recovery_authorization", "cancellation_boundary",
            "current_model_year_complete", "resume_boundary", "resume_mode",
        ):
            current.pop(key, None)
        current.update(running_fields)
        if presented_authorization is not None:
            current["recovery_authorization"] = presented_authorization

    update_status(
        run_dir, mutate=mark_running,
        transition=None if declared_status.get("status") == "running" else "running",
        reason_code="GF_WORKER_STARTED", writer=WRITER_WORKER,
    )
    exact = run_project_application(
        project,
        run_id=run_id,
        pack_root=pack_root,
        output_dir=run_dir / "model-output",
        mode=mode,
        network_pack_root=network_pack_root,
    )
    validation_path = run_dir / "model-output" / str(
        exact.get("scientific_validation_artifact")
        or "validation/scientific-validation.json"
    )
    scientific_validation = json.loads(validation_path.read_text(encoding="utf-8"))
    final: dict = {}
    final["execution_status"] = scientific_validation["execution_status"]
    final["contract_validation_status"] = scientific_validation["contract_validation_status"]
    final["scientific_validation_status"] = scientific_validation["scientific_validation_status"]
    # P0-4 S3: the recomputed validation evidence is public on the run status
    # (run invariants, energy balance, A2 stress events, Q14 raw invariants).
    for field in VALIDATION_STATUS_FIELDS:
        if field in scientific_validation:
            final[field] = scientific_validation[field]
    final["scientific_validation_artifact"] = str(
        exact.get("scientific_validation_artifact")
        or "validation/scientific-validation.json"
    )
    if not policy.annual_economics_candidate:
        # Two half-hour periods exercise wiring only. Annual capital and policy
        # terms inside VALUE make any system-cost or GBP/MWh value from this
        # run economically meaningless, so they are deliberately not published.
        final["results"] = []
        final["diagnostic"] = {
            "periods_per_year": periods,
            "total_periods": periods * (end_year - start_year + 1),
            "years": list(range(start_year, end_year + 1)),
            "purpose": policy.purpose,
            "annual_economics_published": False,
            "scientific_results_published": False,
            "warning": (
                "Teaching diagnostic: the 48-period VALUE 101 market lesson runs the PSM "
                "only and is not an annual or national result."
                if mode == "value_101_day"
                else "Two-period annual costs, investment quantities and pipeline quantities "
                "are diagnostic only and must not be used as scientific results."
            ),
        }
        final["completed_years"] = end_year - start_year + 1
    elif scientific_validation["annual_economics_eligible"]:
        attribution_path = run_dir / "model-output" / "network" / "vre-curtailment-attribution.json"
        try:
            attribution_payload = json.loads(attribution_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            attribution_payload = None
        final["results"] = _frontend_results(
            exact,
            modules,
            attribution_payload if isinstance(attribution_payload, dict) else None,
            mode=mode,
            periods_per_year=periods,
            expected_years=tuple(range(start_year, end_year + 1)),
        )
        final["completed_years"] = len(final["results"])
    else:
        final["results"] = []
        final["completed_years"] = end_year - start_year + 1
        gate = scientific_validation.get("validation_gate")
        gate_failed = isinstance(gate, dict) and gate.get("policy") == "production" and gate.get("status") == "failed"
        final["publication_blocked"] = {
            # P0-4 S7: a failed validation gate (run invariants, energy
            # balance, storage invariants) blocks annual economics too.
            "reason": (
                "A validation gate failed (run invariants, energy balance or storage invariants)."
                if gate_failed
                else "Required contract or analytical invariant validation failed."
            ),
            "reason_code": "GF_VALIDATION_GATE_FAILED" if gate_failed else "GF_VALIDATION_CONTRACT_OR_MECHANISM",
            "scientific_validation_artifact": final["scientific_validation_artifact"],
        }
    final["current_stage"] = "Run completed"
    final["finished_at"] = now()
    final["provenance_artifact"] = str(exact.get("provenance_artifact") or "provenance.json")

    def complete(current: dict) -> None:
        # Merge only the worker's own completion fields into the latest file:
        # application evidence (subannual_recovery*) and server fields survive.
        current.update(final)
        current.pop("recovery_authorization", None)

    update_status(
        run_dir, mutate=complete, transition="completed",
        reason_code="GF_RUN_COMPLETED", writer=WRITER_WORKER,
    )


# Fields of the v2 scientific-validation report copied onto the run status.
VALIDATION_STATUS_FIELDS = (
    "analytical_mechanism_status",
    "run_invariant_status",
    "run_invariants",
    "energy_balance_status",
    "energy_balance",
    "stress",
    "raw_invariants",
    "validation_warnings",
    "storage_invariant_status",
    "storage_invariants",
    "validation_gate",
    "declared_deviations",
)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--run", required=True)
    parser.add_argument(
        "--mode",
        choices=["smoke", "two_year_smoke", "validation_24h", "validation_168h", "value_101_day", "two_year", "full"],
        default="smoke",
    )
    args = parser.parse_args()
    status_path = STATE_ROOT / "runs" / args.run / "status.json"
    raise SystemExit(execute(args.project, args.run, args.mode, status_path=status_path))


def execute(project_id: str, run_id: str, mode: str, *, status_path: Path) -> int:
    """Run one worker and record every outcome; return the process exit code.

    0 completed, cancelled or late (nothing recorded); 1 failed;
    128+signal after a termination signal; 130 after KeyboardInterrupt.
    """
    try:
        run(project_id, run_id, mode)
        return 0
    except LateWriteRejected:
        return 0
    except CancellationRequested as exc:
        try:
            record_run_cancelled(
                status_path, run_id=run_id, project_id=project_id, mode=mode,
                message=str(exc),
            )
        except LateWriteRejected:
            pass
        return 0
    except WorkerTerminated as exc:
        _record_termination(status_path, project_id, run_id, mode, exc)
        return 128 + exc.signum
    except KeyboardInterrupt as exc:
        _record_termination(status_path, project_id, run_id, mode, exc)
        return 130
    except Exception as exc:
        traceback.print_exc()
        try:
            record_run_failure(
                status_path,
                run_id=run_id,
                project_id=project_id,
                mode=mode,
                error=exc,
            )
        except LateWriteRejected:
            return 0
        return 1


def _record_termination(
    status_path: Path, project_id: str, run_id: str, mode: str, error: BaseException
) -> None:
    try:
        record_run_failure(
            status_path, run_id=run_id, project_id=project_id, mode=mode,
            error=RuntimeError(str(error) or "The model worker was interrupted"),
            error_code="GF_WORKER_TERMINATED",
        )
    except LateWriteRejected:
        pass


if __name__ == "__main__":
    main()
