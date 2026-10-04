"""VALUE v2 application service shared by the local API and CLI."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sqlite3
import sys
import time
from collections import Counter
from contextlib import closing, contextmanager, redirect_stdout
from dataclasses import replace
from pathlib import Path
from typing import Mapping, Sequence

from .value_runtime_adapter import (
    build_value_run_context,
    persist_or_verify_value_context,
)
from .canonical_psm_data import build_chronology, native_initial_state, build_doctoral_psm_input
from .doctoral_weather import uses_doctoral_weather, weather_execution_identity
from .cost_ledger import build_cem_cost_ledger, write_cost_ledgers
from .carbon_ledger import build_operational_carbon_ledger, write_carbon_ledgers
from .cem_identity import load_cem_identity
from .comparison_eligibility import (
    COPPERPLATE_SCENARIO_DEMAND,
    build_comparison_eligibility,
    write_comparison_eligibility,
)
from .parameters import resolve_scheme_c_parameters
from .parity import write_stage_parity_report
from .provenance import snapshot_module_manifests, write_run_provenance
from .builtin.scheme_c_1000twh.runtime_overlay import ensure_runtime_overlay_sealed
from .performance import write_performance_report
from .planning_index import materialize_planning_index
from .scientific_validation import (
    RETAINED_COMPARISON_INFORMATIONAL,
    RETAINED_COMPARISON_REQUIRED,
    write_scientific_validation_report,
)
from .run_policy import resolve_run_policy, validate_pack_run_mode
from .terminal_state import write_terminal_artifacts
from .run_lifecycle import cancellation_requested
from .runtime_capabilities import VALUE_NATIVE, capability_status
from .v2.contracts import ModuleSelection, OperatingState, PSMInput, ResolvedRun, YearResult
from .v2.module_manifest import ModuleRegistryV2, ResolvedModuleGraph, workspace_registry
from .extension_framework import ExtensionRuntime
from .network_contracts import load_network_input_from_pack
from .network_ac import load_ac_data_from_pack
from .network_expansion import (
    adjust_carbon_ledger_for_network,
    apply_commissioned_network_assets,
    load_network_expansion_state,
    write_network_expansion_artifacts,
)
from .zonal_contracts import load_zonal_network_pack
from .zonal_pack_selection import resolve_zonal_pack_selection
from .frontend_contract import validate_maturity_acknowledgements
from .errors import InvariantError
from .failure_evidence import (
    RECOVERY_AUTHORIZATION_SCHEMA_VERSION,
    recover_incomplete_v8_year,
    recover_v8_market_prefix,
    recovery_authorization_id,
)
from .market_ledger import (
    SCHEMA_VERSION as MARKET_LEDGER_SCHEMA_VERSION,
    MarketLedgerBoundary,
    market_ledger_capabilities,
)
from .market_ownership import MarketLedgerOwnershipLease
from .module_context import (
    ImmutableContextResolver,
    RunStaticContext,
    YearContext,
    canonical_context_sha256,
)
from .vre_curtailment_attribution import (
    ATTRIBUTION_METHOD_ID,
    ATTRIBUTION_SCHEMA,
    SNAPSHOT_SCHEMA,
)
from .zonal_results import query_zonal_annual_brief
from .zonal_redispatch import ZonalRedispatchBalancing
from .zonal_solver_contract import validate_solver_settings
from .staged_market_contracts import contract_sha256 as staged_contract_sha256
from .subannual_checkpoint import (
    PSMSubannualCheckpointEngine,
    SubannualCheckpoint,
    SubannualCheckpointIdentity,
    SubannualCheckpointStore,
    checkpoint_content_sha256,
    claim_subannual_recovery_authorization,
    issue_subannual_recovery_authorization,
)
from .v2.orchestrator import (
    AnnualModelOrchestratorV2,
    JsonlStageEventWriter,
    build_year_context,
    checkpoint_identity,
    contract_hash,
    json_checkpoint_writer,
    load_json_checkpoint,
    publish_year_context,
)


DEFAULT_TRANSITION = "value-annual-state-transition"
DEFAULT_STORAGE_COST = "dynamic-annual-storage-cost"
VRE_SNAPSHOT_CAPABILITY = "evidence.vre-counterfactual-snapshot/v1"
FINAL_ZONAL_DISPATCH_CONTRACT = "network.zonal-redispatch-result/v1"


def _atomic_json_artifact(path: Path, payload: Mapping[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(path)
    return path


def _configure_subannual_checkpoint_sink(
    *,
    psm: object,
    store: SubannualCheckpointStore,
    frozen_input_hashes: Mapping[str, object],
    frozen_module_hashes: Mapping[str, object],
    parent_annual_checkpoint_identity: Mapping[str, object],
) -> bool:
    """Configure the optional PSM protocol to publish full monthly checkpoints."""

    if not isinstance(psm, PSMSubannualCheckpointEngine):
        return False

    def publish(
        boundary,
        runtime_checkpoint: Mapping[str, object],
        ledger_boundary: MarketLedgerBoundary,
    ) -> None:
        if not isinstance(ledger_boundary, MarketLedgerBoundary):
            raise TypeError("Subannual checkpoint sink requires a market ledger boundary")
        if not isinstance(runtime_checkpoint, Mapping):
            raise TypeError("Subannual checkpoint sink requires a PSM runtime checkpoint")
        if (
            runtime_checkpoint.get("run_id") != boundary.run_id
            or runtime_checkpoint.get("year") != boundary.model_year
            or runtime_checkpoint.get("chronology_sha256")
            != boundary.chronology_sha256
            or ledger_boundary.year != boundary.model_year
            or ledger_boundary.last_committed_period != boundary.last_period_index
        ):
            raise ValueError("Subannual checkpoint components describe different boundaries")
        run_context_sha256 = runtime_checkpoint.get("run_context_sha256")
        year_context_sha256 = runtime_checkpoint.get("year_context_sha256")
        if (
            ledger_boundary.run_context_sha256 != run_context_sha256
            or ledger_boundary.year_context_sha256 != year_context_sha256
        ):
            raise ValueError("Subannual checkpoint contexts differ from the ledger boundary")
        runtime_state = runtime_checkpoint.get("runtime_state")
        if not isinstance(runtime_state, Mapping):
            raise ValueError("Subannual PSM runtime checkpoint has no runtime_state")
        if runtime_state.get("next_period_index") != boundary.next_period_index:
            raise ValueError("Subannual PSM writer offset differs from the boundary")
        soc = runtime_state.get("soc_mwh_by_asset")
        if not isinstance(soc, Mapping):
            raise ValueError("Subannual PSM runtime checkpoint has no storage state")
        storage_cost = runtime_state.get("storage_cost_state_by_asset")
        storage_cost = storage_cost if isinstance(storage_cost, Mapping) else {}
        checkpoint_inputs = {
            **dict(frozen_input_hashes),
            "run_context_sha256": run_context_sha256,
            "year_context_sha256": year_context_sha256,
        }
        payload = {
            "checkpoint_id": boundary.checkpoint_id,
            "run_id": boundary.run_id,
            "model_year": boundary.model_year,
            "calendar_month": boundary.calendar_month,
            "boundary_timestamp": boundary.boundary_timestamp,
            "last_committed_period": boundary.last_period_index,
            "last_committed_period_id": boundary.last_period_id,
            "next_period": boundary.next_period_index,
            "next_period_id": boundary.next_period_id,
            "period_hours": boundary.period_hours,
            "chronology_sha256": boundary.chronology_sha256,
            "chronological_storage_state": tuple(
                {
                    "asset_id": str(asset_id),
                    "soc_mwh": value,
                    "storage_cost_state": storage_cost.get(asset_id),
                }
                for asset_id, value in sorted(soc.items())
            ),
            "agent_observations": {
                "income_gbp_by_owner": runtime_state.get(
                    "income_gbp_by_owner", {}
                ),
                "national_settlement_gbp_by_owner": runtime_state.get(
                    "national_settlement_gbp_by_owner", {}
                ),
                "redispatch_settlement_gbp_by_owner": runtime_state.get(
                    "redispatch_settlement_gbp_by_owner", {}
                ),
            },
            "writer_offsets": {
                "next_period_index": boundary.next_period_index,
                "market_ledger_boundary": ledger_boundary.to_dict(),
            },
            "random_generator_states": {},
            "year_to_date": {
                "psm_runtime_checkpoint": dict(runtime_checkpoint),
            },
            "frozen_input_hashes": checkpoint_inputs,
            "frozen_module_hashes": dict(frozen_module_hashes),
            "parent_annual_checkpoint_identity": dict(
                parent_annual_checkpoint_identity
            ),
            "ledger_boundary": ledger_boundary.ledger_prefix_identity,
            "publication_state": "verified",
            "content_sha256": "0" * 64,
        }
        checkpoint = SubannualCheckpoint(**payload)
        checkpoint = replace(
            checkpoint,
            content_sha256=checkpoint_content_sha256(checkpoint),
        )
        store.publish(checkpoint)
        store.prune_verified(year=checkpoint.model_year)

    psm.configure_subannual_checkpoint_sink(publish)
    return True


def _plain_json_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            str(key): _plain_json_value(item) for key, item in value.items()
        }
    if isinstance(value, (tuple, list)):
        return [_plain_json_value(item) for item in value]
    return value


def _parent_annual_checkpoint_identity(
    *,
    resolved_identity: Mapping[str, object],
    state: object,
    annual_checkpoint_sha256: str | None,
) -> dict[str, object]:
    state_year = getattr(state, "year", None)
    if isinstance(state_year, bool) or not isinstance(state_year, int):
        raise ValueError("Parent annual checkpoint state has no valid year")
    if annual_checkpoint_sha256 is not None and (
        len(annual_checkpoint_sha256) != 64
        or any(
            character not in "0123456789abcdef"
            for character in annual_checkpoint_sha256
        )
    ):
        raise ValueError("Parent annual checkpoint SHA-256 is invalid")
    identity = _plain_json_value(resolved_identity)
    if not isinstance(identity, dict):
        raise TypeError("Resolved annual checkpoint identity is not an object")
    return {
        "schema_version": "value.parent-annual-checkpoint-identity/v1",
        "identity": identity,
        "state_year": state_year,
        "state_sha256": contract_hash(state),
        "annual_checkpoint_sha256": annual_checkpoint_sha256,
    }


def _advance_subannual_parent_after_annual_checkpoint(
    *,
    store: SubannualCheckpointStore,
    parent_annual_checkpoint_identity: dict[str, object],
    resolved_identity: Mapping[str, object],
    state: object,
    annual_checkpoint_sha256: str,
) -> None:
    """Supersede the completed year, then expose its verified next-year state."""

    state_year = getattr(state, "year", None)
    if isinstance(state_year, bool) or not isinstance(state_year, int):
        raise ValueError("Verified annual checkpoint has no valid state year")
    replacement = _parent_annual_checkpoint_identity(
        resolved_identity=resolved_identity,
        state=state,
        annual_checkpoint_sha256=annual_checkpoint_sha256,
    )
    store.supersede_with_annual(
        year=state_year - 1,
        annual_checkpoint_sha256=annual_checkpoint_sha256,
    )
    parent_annual_checkpoint_identity.clear()
    parent_annual_checkpoint_identity.update(replacement)


def _recover_explicit_subannual_checkpoint(
    *,
    output_dir: Path,
    resume_checkpoint_id: str | None,
    expected: SubannualCheckpointIdentity | None,
    expected_parent_annual_checkpoint_identity: Mapping[str, object] | None,
    psm: object,
) -> Mapping[str, object] | None:
    """Consume and apply only the exact monthly checkpoint named by the caller."""

    if resume_checkpoint_id is None:
        return None
    if not isinstance(resume_checkpoint_id, str) or not resume_checkpoint_id.strip():
        raise ValueError("resume_checkpoint_id must be a non-empty explicit ID")
    if not isinstance(expected, SubannualCheckpointIdentity):
        raise ValueError("Explicit subannual recovery has no frozen expected identity")
    if not isinstance(expected_parent_annual_checkpoint_identity, Mapping):
        raise ValueError(
            "Explicit subannual recovery has no parent annual checkpoint identity"
        )
    if not isinstance(psm, PSMSubannualCheckpointEngine):
        raise ValueError("Selected PSM does not support subannual recovery")

    output_dir = Path(output_dir).resolve()
    store = SubannualCheckpointStore(output_dir.parent)
    checkpoint = store.load(resume_checkpoint_id, expected)
    if checkpoint.checkpoint_id != resume_checkpoint_id:
        raise ValueError("Loaded subannual checkpoint does not match the explicit ID")
    if _plain_json_value(
        checkpoint.parent_annual_checkpoint_identity
    ) != _plain_json_value(expected_parent_annual_checkpoint_identity):
        raise ValueError(
            "Subannual checkpoint parent annual identity does not match"
        )
    runtime_checkpoint = checkpoint.year_to_date.get("psm_runtime_checkpoint")
    raw_boundary = checkpoint.writer_offsets.get("market_ledger_boundary")
    if not isinstance(runtime_checkpoint, Mapping) or not isinstance(
        raw_boundary, Mapping
    ):
        raise ValueError("Subannual checkpoint lacks recovery runtime evidence")
    boundary = MarketLedgerBoundary.from_dict(raw_boundary)
    checkpoint_ledger_identity = (
        checkpoint.ledger_boundary.to_dict()
        if hasattr(checkpoint.ledger_boundary, "to_dict")
        else dict(checkpoint.ledger_boundary)
    )
    if (
        boundary.year != checkpoint.model_year
        or boundary.last_committed_period != checkpoint.last_committed_period
        or boundary.ledger_prefix_identity.to_dict()
        != checkpoint_ledger_identity
        or runtime_checkpoint.get("run_id") != checkpoint.run_id
        or runtime_checkpoint.get("year") != checkpoint.model_year
        or runtime_checkpoint.get("chronology_sha256")
        != checkpoint.chronology_sha256
        or runtime_checkpoint.get("run_context_sha256")
        != checkpoint.frozen_input_hashes["run_context_sha256"]
        or runtime_checkpoint.get("year_context_sha256")
        != checkpoint.frozen_input_hashes["year_context_sha256"]
    ):
        raise ValueError("Subannual checkpoint recovery identities do not agree")

    issued = issue_subannual_recovery_authorization(
        run_id=checkpoint.run_id,
        checkpoint_id=checkpoint.checkpoint_id,
        checkpoint_content_sha256=checkpoint.content_sha256,
        model_year=checkpoint.model_year,
        last_committed_period=checkpoint.last_committed_period,
        next_period=checkpoint.next_period,
        run_context_sha256=str(runtime_checkpoint["run_context_sha256"]),
        year_context_sha256=str(runtime_checkpoint["year_context_sha256"]),
        source="explicit_resume_checkpoint_id",
        nonce=hashlib.sha256(
            f"{checkpoint.checkpoint_id}:{checkpoint.content_sha256}".encode(
                "utf-8"
            )
        ).hexdigest()[:32],
    )
    presented = {**dict(issued), "state": "presented"}
    consumed = claim_subannual_recovery_authorization(
        store=store, authorization=presented
    )
    status_path = output_dir.parent / "status.json"
    status: dict[str, object] = {}
    if status_path.is_file():
        loaded_status = json.loads(status_path.read_text(encoding="utf-8"))
        if not isinstance(loaded_status, Mapping):
            raise ValueError("Run status must contain an object")
        status = dict(loaded_status)
    status["subannual_recovery_authorization"] = dict(consumed)
    _atomic_json_artifact(status_path, status)

    database = output_dir / "market" / "market.sqlite"
    if not database.is_file():
        raise ValueError("Explicit subannual recovery has no live market ledger")
    with MarketLedgerOwnershipLease.acquire(database, role="recovery") as lease:
        recovery = recover_v8_market_prefix(
            database,
            boundary=boundary,
            diagnostic_directory=output_dir / "market" / "recovery",
            lease=lease,
        )
    psm.restore_runtime_checkpoint(runtime_checkpoint)
    evidence = {
        "resumed_from_checkpoint_id": checkpoint.checkpoint_id,
        "diagnostic_uri": recovery["diagnostic_database"],
        "diagnostic_sha256": recovery["diagnostic_sha256"],
        "cleaned_prefix": {
            "committed_period": recovery["committed_period"],
            "period_count": recovery["period_count"],
            "committed_prefix_sha256": recovery["committed_prefix_sha256"],
            "cleaned_database_sha256": recovery["cleaned_database_sha256"],
        },
    }
    status["subannual_recovery"] = evidence
    _atomic_json_artifact(status_path, status)
    return evidence


def _claim_recovery_authorization(
    *, output_dir: Path, authorization: Mapping[str, object]
) -> Path:
    """Atomically make one process the sole consumer of a recovery grant."""

    authorization_id = str(authorization["authorization_id"])
    claim_directory = Path(output_dir).resolve() / "market" / "recovery" / "claims"
    claim_directory.mkdir(parents=True, exist_ok=True)
    claim_path = claim_directory / f"{authorization_id}.json"
    payload = (json.dumps({
        "schema_version": "value.annual-recovery-claim/v1",
        "authorization_id": authorization_id,
        "run_id": authorization["run_id"],
        "incomplete_year": authorization["incomplete_year"],
        "source": authorization["source"],
        "issuance_nonce": authorization["issuance_nonce"],
    }, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    try:
        descriptor = os.open(
            claim_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except FileExistsError as exc:
        raise ValueError("Annual recovery authorization has already been claimed") from exc
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        # Keep even a partially written exclusive claim: fail closed rather than
        # allow the same destructive authorization to acquire a second owner.
        raise
    return claim_path


def _load_authorized_incomplete_year_context(
    *,
    output_dir: Path,
    run_context: RunStaticContext,
    run_id: str,
    year: int,
    checkpoint_state_sha256: str,
) -> YearContext | None:
    """Load one explicitly cancelled year and fail closed on every identity."""

    status_path = Path(output_dir).resolve().parent / "status.json"
    if not status_path.is_file():
        return None
    status = json.loads(status_path.read_text(encoding="utf-8"))
    if not isinstance(status, Mapping) or status.get("id") != run_id:
        return None
    authorization = status.get("recovery_authorization")
    if authorization is None:
        return None
    if not isinstance(authorization, Mapping):
        raise ValueError("Annual recovery authorization is invalid")
    authorised = (
        status.get("status") == "running"
        and status.get("execution_status") == "running"
        and run_context.run_id == run_id
        and authorization.get("schema_version") == RECOVERY_AUTHORIZATION_SCHEMA_VERSION
        and authorization.get("authorization_id") == recovery_authorization_id(authorization)
        and authorization.get("state") == "presented"
        and authorization.get("run_id") == run_id
        and authorization.get("incomplete_year") == year
        and isinstance(authorization.get("committed_period"), int)
        and int(authorization["committed_period"]) >= 0
        and authorization.get("checkpoint_state_sha256") == checkpoint_state_sha256
        and isinstance(authorization.get("run_context_sha256"), str)
        and len(str(authorization["run_context_sha256"])) == 64
        and all(
            character in "0123456789abcdef"
            for character in str(authorization["run_context_sha256"])
        )
        and authorization.get("source") == "period_boundary_cancellation"
        and isinstance(authorization.get("issuance_nonce"), str)
        and len(str(authorization["issuance_nonce"])) == 32
        and all(character in "0123456789abcdef" for character in str(authorization["issuance_nonce"]))
    )
    if not authorised:
        raise ValueError("Annual recovery authorization does not match the resumed boundary")
    path = (
        Path(output_dir).resolve()
        / "market"
        / "context"
        / f"year-{year}.json"
    )
    if not path.is_file():
        raise ValueError("Authorised annual recovery has no frozen opening YearContext")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("Frozen opening YearContext is not an object")
    context = YearContext.from_dict(payload)
    if (
        context.run_id != run_id
        or context.year != year
        or context.run_context_sha256 != authorization.get("run_context_sha256")
    ):
        raise ValueError("Frozen opening YearContext does not match the resumed run")
    if (
        context.transition_lineage.get("annual_input_state_sha256")
        != checkpoint_state_sha256
    ):
        raise ValueError("Frozen opening YearContext does not match the checkpoint")
    if authorization.get("year_context_sha256") != canonical_context_sha256(context):
        raise ValueError("Annual recovery authorization does not match YearContext")
    _claim_recovery_authorization(
        output_dir=output_dir,
        authorization=authorization,
    )
    consumed = dict(authorization)
    consumed["state"] = "consumed"
    updated_status = dict(status)
    updated_status["recovery_authorization"] = consumed
    _atomic_json_artifact(status_path, updated_status)
    return context


def build_run_static_context(
    *,
    resolved: ResolvedRun,
    project: Mapping[str, object],
    pack_manifest: Mapping[str, object],
    pack_manifest_sha256: str,
    resolution_graph: ResolvedModuleGraph,
    network_pack: object | None,
) -> RunStaticContext:
    """Materialise the immutable run boundary from already resolved inputs."""

    configured = dict(project.get("market_configuration") or {})
    if uses_doctoral_weather(pack_manifest):
        # Resource preflight also constructs this context, before the public
        # application entry attaches extensions to its ResolvedRun.
        configured["dispatch_weather_identity"] = weather_execution_identity()
    elif resolved.extensions.get("dispatch_weather_identity"):
        configured["dispatch_weather_identity"] = dict(resolved.extensions["dispatch_weather_identity"])
    trace_profile = str(
        resolved.runtime_controls.get("runtime.market_trace_level")
        or configured.get("ledger_detail")
        or "summary"
    )
    revision = str(
        resolved.extensions.get("project_revision_sha256")
        or project.get("revision_sha256")
        or contract_hash(project)
    )
    # Bind the context hash to the canonical settings actually executed.  The
    # module manifest retains the declaration wrapper (schema path, semantics,
    # ranges); it is not itself an executable settings payload.
    solver_contract = (
        validate_solver_settings(project.get("solver_contract")).to_dict()
        if project.get("solver_contract") is not None else {}
    )
    return RunStaticContext(
        run_id=resolved.run_id,
        study_revision_sha256=revision,
        start_year=resolved.start_year,
        end_year=resolved.end_year,
        period_hours=float(resolved.scientific_parameters["clock.period_hours"]),
        data_pack={
            "data_pack_id": resolved.data_pack_id,
            "manifest_sha256": pack_manifest_sha256,
            "scientific_sha256": pack_manifest.get("scientific_sha256"),
            "bindings": dict(pack_manifest.get("bindings") or {}),
        },
        module_graph=resolution_graph.to_dict(),
        scientific_parameters=dict(resolved.scientific_parameters),
        runtime_controls=dict(resolved.runtime_controls),
        trace_profile=trace_profile,
        solver_contract=solver_contract,
        market_configuration=configured,
        network_pack=(
            network_pack.to_dict()
            if network_pack is not None and hasattr(network_pack, "to_dict")
            else None
        ),
    )


def _finite_attribution_number(value: object, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise InvariantError(
            f"GF_VRE_ATTRIBUTION_IDENTITY_FAILED: {field} is not a finite number"
        ) from exc
    if not math.isfinite(number):
        raise InvariantError(
            f"GF_VRE_ATTRIBUTION_IDENTITY_FAILED: {field} is not a finite number"
        )
    return number


def write_vre_curtailment_attribution_artifact(
    *,
    output_dir: Path,
    database: Path,
    data_pack_id: str,
    network_pack_id: str,
    initial_state_sha256: str,
    resolution_graph: ResolvedModuleGraph,
) -> Path:
    """Write compact, capability-aware run evidence from a closed v6 ledger."""

    module_identities = {
        slot: identity.to_dict()
        for slot, identity in sorted(resolution_graph.identities_by_slot.items())
    }
    selected_psm = resolution_graph.manifests_by_slot.get("psm")
    selected_balancing = resolution_graph.manifests_by_slot.get("balancing")
    psm_declares_snapshot = bool(
        selected_psm is not None
        and VRE_SNAPSHOT_CAPABILITY in selected_psm.provides_capabilities
    )
    balancing_produces_final_zonal_dispatch = bool(
        selected_balancing is not None
        and FINAL_ZONAL_DISPATCH_CONTRACT in selected_balancing.outputs
    )
    capability_declared = (
        psm_declares_snapshot and balancing_produces_final_zonal_dispatch
    )
    common: dict[str, object] = {
        "schema_version": "value.vre-curtailment-run-evidence/v1",
        "contract_version": ATTRIBUTION_SCHEMA,
        "snapshot_contract_version": SNAPSHOT_SCHEMA,
        "reference_allocation_rule": ATTRIBUTION_METHOD_ID,
        "data_pack_id": str(data_pack_id),
        "network_pack_id": str(network_pack_id),
        "initial_state_sha256": str(initial_state_sha256),
        "module_resolution_graph_sha256": resolution_graph.graph_sha256,
        "module_identities": module_identities,
        "declared_snapshot_capability": capability_declared,
        "selected_psm_declares_snapshot": psm_declares_snapshot,
        "selected_balancing_produces_final_zonal_dispatch": (
            balancing_produces_final_zonal_dispatch
        ),
        "detail_location": "market/market.sqlite",
    }
    destination = output_dir / "network" / "vre-curtailment-attribution.json"
    if not capability_declared:
        return _atomic_json_artifact(destination, {
            **common,
            "attribution_method_id": None,
            "capability_status": "unavailable",
            "reason_code": "module_does_not_provide_counterfactual_snapshot",
            "matched_counterfactual_proof": None,
            "counterfactual_realised_input_set_sha256": None,
            "annual_totals": [],
            "maximum_absolute_period_residual_mwh": None,
            "maximum_residual_period_id": None,
            "maximum_period_tolerance_mwh": None,
        })

    if not database.is_file():
        raise InvariantError(
            "GF_VRE_ATTRIBUTION_CAPABILITY_MISSING: a capability-declaring "
            "resolution did not produce market/market.sqlite"
        )
    capabilities = market_ledger_capabilities(database)
    if capabilities["ledger_schema_version"] != MARKET_LEDGER_SCHEMA_VERSION:
        raise InvariantError(
            "GF_VRE_ATTRIBUTION_CAPABILITY_MISSING: a capability-declaring "
            "resolution did not produce a v6 attribution ledger"
        )
    connection_uri = f"{database.resolve().as_uri()}?mode=ro"
    with closing(sqlite3.connect(connection_uri, uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        trace_row = connection.execute(
            "SELECT value FROM metadata WHERE key='trace_level'"
        ).fetchone()
        trace_level = str(trace_row[0]) if trace_row is not None else "unknown"
        detail_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM vre_curtailment_detail"
            ).fetchone()[0]
        )
        accounting_rows = connection.execute("""
            SELECT year, period, period_id,
                counterfactual_realised_input_sha256 AS realised_input_sha256,
                accounting_status
            FROM zonal_period_accounting ORDER BY year, period, period_id
        """).fetchall()
        attribution_rows = connection.execute("""
            SELECT year, period, period_id,
                counterfactual_realised_input_sha256 AS realised_input_sha256,
                accounting_status, attribution_method_id,
                realised_available_vre_mwh,
                perfect_reference_dispatch_mwh,
                copperplate_reference_dispatch_mwh,
                zonal_final_dispatch_mwh,
                economic_curtailment_mwh,
                forecast_added_curtailment_mwh,
                forecast_avoided_curtailment_mwh,
                redispatch_added_curtailment_mwh,
                redispatch_avoided_curtailment_mwh,
                redispatch_net_impact_mwh,
                total_curtailment_mwh,
                curtailment_rate, identity_residual_mwh,
                validation_tolerance_mwh
            FROM vre_curtailment_period ORDER BY year, period, period_id
        """).fetchall()
    allow_summary_without_detail = (
        capabilities["ledger_schema_version"] == MARKET_LEDGER_SCHEMA_VERSION
        and trace_level == "summary"
        and detail_count == 0
    )
    common.update({
        "ledger_trace_level": trace_level,
        "detail_evidence_level": (
            "period_summary" if allow_summary_without_detail else "object_detail"
        ),
        "detail_location": (
            None if allow_summary_without_detail else "market/market.sqlite"
        ),
    })

    accounting_keys = {
        (int(row["year"]), int(row["period"]), str(row["period_id"]))
        for row in accounting_rows
    }
    attribution_keys = {
        (int(row["year"]), int(row["period"]), str(row["period_id"]))
        for row in attribution_rows
    }
    if not attribution_rows or accounting_keys != attribution_keys:
        raise InvariantError(
            "GF_VRE_ATTRIBUTION_CAPABILITY_MISSING: a capability-declaring "
            "resolution omitted one or more reconciled period rows"
        )
    if any(str(row["accounting_status"]) != "reconciled" for row in accounting_rows):
        raise InvariantError(
            "GF_VRE_ATTRIBUTION_CAPABILITY_MISSING: zonal accounting is not reconciled"
        )
    if any(str(row["accounting_status"]) != "reconciled" for row in attribution_rows):
        raise InvariantError(
            "GF_VRE_ATTRIBUTION_CAPABILITY_MISSING: VRE attribution is not reconciled"
        )
    accounting_by_key = {
        (int(row["year"]), int(row["period"]), str(row["period_id"])): row
        for row in accounting_rows
    }
    realised_input_hashes_match = all(
        str(row["realised_input_sha256"])
        == str(accounting_by_key[key]["realised_input_sha256"])
        for row in attribution_rows
        for key in ((
            int(row["year"]), int(row["period"]), str(row["period_id"])
        ),)
    )
    if not realised_input_hashes_match:
        raise InvariantError(
            "GF_VRE_COUNTERFACTUAL_SET_MISMATCH: cost and attribution evidence "
            "do not share period and realised-input identities"
        )
    methods = {str(row["attribution_method_id"]) for row in attribution_rows}
    if methods != {ATTRIBUTION_METHOD_ID}:
        raise InvariantError(
            "GF_VRE_ATTRIBUTION_CAPABILITY_MISSING: the capability-declaring "
            "resolution produced an unsupported or mixed attribution method"
        )

    detail_fields = (
        "realised_available_vre_mwh",
        "perfect_reference_dispatch_mwh",
        "copperplate_reference_dispatch_mwh",
        "zonal_final_dispatch_mwh",
        "economic_curtailment_mwh",
        "forecast_added_curtailment_mwh",
        "forecast_avoided_curtailment_mwh",
        "redispatch_added_curtailment_mwh",
        "redispatch_avoided_curtailment_mwh",
        "redispatch_net_impact_mwh",
        "total_curtailment_mwh",
    )
    for period_row in attribution_rows:
        period_numbers = {
            field: _finite_attribution_number(period_row[field], field)
            for field in detail_fields
        }
        tolerance = _finite_attribution_number(
            period_row["validation_tolerance_mwh"],
            "validation_tolerance_mwh",
        )
        _finite_attribution_number(
            period_row["curtailment_rate"], "curtailment_rate"
        )
        stored_residual = _finite_attribution_number(
            period_row["identity_residual_mwh"], "identity_residual_mwh"
        )
        redispatch_net = period_numbers["redispatch_net_impact_mwh"]
        expected_redispatch_net = _finite_attribution_number(
            period_numbers["redispatch_added_curtailment_mwh"]
            - period_numbers["redispatch_avoided_curtailment_mwh"],
            "recomputed_redispatch_net_impact_mwh",
        )
        recomputed_residual = _finite_attribution_number((
            period_numbers["economic_curtailment_mwh"]
            + period_numbers["forecast_added_curtailment_mwh"]
            - period_numbers["forecast_avoided_curtailment_mwh"]
            + period_numbers["redispatch_added_curtailment_mwh"]
            - period_numbers["redispatch_avoided_curtailment_mwh"]
            - period_numbers["total_curtailment_mwh"]
        ), "recomputed_identity_residual_mwh")
        if (
            tolerance < 0.0
            or abs(stored_residual) > tolerance
            or abs(redispatch_net - expected_redispatch_net) > tolerance
            or abs(recomputed_residual) > tolerance
            or abs(stored_residual - recomputed_residual) > tolerance
        ):
            raise InvariantError(
                "GF_VRE_ATTRIBUTION_IDENTITY_FAILED: period gross additions, "
                "avoidance, signed net or residual do not reconcile within tolerance"
            )

    with closing(sqlite3.connect(connection_uri, uri=True)) as connection:
        connection.row_factory = sqlite3.Row

        # Validate each raw value before SQLite performs aggregate arithmetic.
        for detail_row in connection.execute("""
            SELECT year, period, period_id,
                realised_available_vre_mwh,
                perfect_reference_dispatch_mwh,
                copperplate_reference_dispatch_mwh,
                zonal_final_dispatch_mwh,
                economic_curtailment_mwh,
                forecast_added_curtailment_mwh,
                forecast_avoided_curtailment_mwh,
                redispatch_added_curtailment_mwh,
                redispatch_avoided_curtailment_mwh,
                redispatch_net_impact_mwh,
                total_curtailment_mwh
            FROM vre_curtailment_detail
            ORDER BY year, period, period_id, asset_id, bid_tranche_id
        """):
            int(detail_row["year"])
            int(detail_row["period"])
            str(detail_row["period_id"])
            for field in detail_fields:
                _finite_attribution_number(detail_row[field], field)

        detail_iterator = iter(connection.execute("""
            SELECT year, period, period_id,
                SUM(realised_available_vre_mwh) AS realised_available_vre_mwh,
                SUM(perfect_reference_dispatch_mwh)
                    AS perfect_reference_dispatch_mwh,
                SUM(copperplate_reference_dispatch_mwh)
                    AS copperplate_reference_dispatch_mwh,
                SUM(zonal_final_dispatch_mwh) AS zonal_final_dispatch_mwh,
                SUM(economic_curtailment_mwh) AS economic_curtailment_mwh,
                SUM(forecast_added_curtailment_mwh)
                    AS forecast_added_curtailment_mwh,
                SUM(forecast_avoided_curtailment_mwh)
                    AS forecast_avoided_curtailment_mwh,
                SUM(redispatch_added_curtailment_mwh)
                    AS redispatch_added_curtailment_mwh,
                SUM(redispatch_avoided_curtailment_mwh)
                    AS redispatch_avoided_curtailment_mwh,
                SUM(redispatch_net_impact_mwh) AS redispatch_net_impact_mwh,
                SUM(total_curtailment_mwh) AS total_curtailment_mwh
            FROM vre_curtailment_detail
            GROUP BY year, period, period_id
            ORDER BY year, period, period_id
        """))
        detail_row = next(detail_iterator, None)
        for period_row in attribution_rows:
            period_key = (
                int(period_row["year"]),
                int(period_row["period"]),
                str(period_row["period_id"]),
            )
            detail_key = (
                (
                    int(detail_row["year"]),
                    int(detail_row["period"]),
                    str(detail_row["period_id"]),
                )
                if detail_row is not None
                else None
            )
            if detail_key is not None and detail_key < period_key:
                raise InvariantError(
                    "GF_VRE_ATTRIBUTION_CAPABILITY_MISSING: VRE detail evidence "
                    "contains a period absent from the attribution ledger"
                )

            tolerance = _finite_attribution_number(
                period_row["validation_tolerance_mwh"],
                "validation_tolerance_mwh",
            )
            period_numbers = {
                field: _finite_attribution_number(period_row[field], field)
                for field in detail_fields
            }
            period_has_vre_evidence = any(
                period_numbers[field] != 0.0 for field in detail_fields
            ) or _finite_attribution_number(
                period_row["curtailment_rate"], "curtailment_rate"
            ) != 0.0
            if detail_key is None or detail_key > period_key:
                if period_has_vre_evidence and not allow_summary_without_detail:
                    raise InvariantError(
                        "GF_VRE_ATTRIBUTION_CAPABILITY_MISSING: a nonzero VRE "
                        "period has no attribution detail evidence"
                    )
                continue

            detail_numbers = {
                field: _finite_attribution_number(
                    detail_row[field], f"detail_sum.{field}"
                )
                for field in detail_fields
            }
            mismatched_fields = [
                field for field in detail_fields
                if abs(detail_numbers[field] - period_numbers[field]) > tolerance
            ]
            if mismatched_fields:
                raise InvariantError(
                    "GF_VRE_ATTRIBUTION_CAPABILITY_MISSING: VRE detail "
                    "aggregates do not match period evidence for "
                    + ", ".join(mismatched_fields)
                )
            detail_row = next(detail_iterator, None)

        if detail_row is not None:
            raise InvariantError(
                "GF_VRE_ATTRIBUTION_CAPABILITY_MISSING: VRE detail evidence "
                "contains a period absent from the attribution ledger"
            )

    brief = query_zonal_annual_brief(database)
    annual_totals: list[dict[str, object]] = []
    for year_row in brief["years"]:
        curtailment = dict(year_row["vre_curtailment"])
        if curtailment.get("attribution_status") != "reconciled":
            raise InvariantError(
                "GF_VRE_ATTRIBUTION_CAPABILITY_MISSING: annual attribution is not reconciled"
            )
        annual_numbers = {
            field: _finite_attribution_number(curtailment[field], field)
            for field in (
                "available_mwh", "economic_mwh", "forecast_added_mwh",
                "forecast_avoided_mwh", "redispatch_added_mwh",
                "redispatch_avoided_mwh", "redispatch_net_mwh", "total_mwh",
                "rate", "aggregate_tolerance_mwh",
            )
        }
        residual = _finite_attribution_number((
            annual_numbers["economic_mwh"]
            + annual_numbers["forecast_added_mwh"]
            - annual_numbers["forecast_avoided_mwh"]
            + annual_numbers["redispatch_added_mwh"]
            - annual_numbers["redispatch_avoided_mwh"]
            - annual_numbers["total_mwh"]
        ), "annual_identity_residual_mwh")
        tolerance = annual_numbers["aggregate_tolerance_mwh"]
        if abs(residual) > tolerance:
            raise InvariantError(
                "GF_VRE_ATTRIBUTION_IDENTITY_FAILED: annual gross SQL sums do not reconcile"
            )
        annual_totals.append({
            "year": int(year_row["year"]),
            "period_count": int(curtailment["period_count"]),
            "available_mwh": curtailment["available_mwh"],
            "economic_mwh": curtailment["economic_mwh"],
            "forecast_added_mwh": curtailment["forecast_added_mwh"],
            "forecast_avoided_mwh": curtailment["forecast_avoided_mwh"],
            "redispatch_added_mwh": curtailment["redispatch_added_mwh"],
            "redispatch_avoided_mwh": curtailment["redispatch_avoided_mwh"],
            "redispatch_net_mwh": curtailment["redispatch_net_mwh"],
            "total_mwh": curtailment["total_mwh"],
            "rate": curtailment["rate"],
            "identity_residual_mwh": residual,
            "aggregate_tolerance_mwh": tolerance,
        })

    maximum_row = sorted(
        attribution_rows,
        key=lambda row: (
            -abs(float(row["identity_residual_mwh"])),
            int(row["year"]),
            int(row["period"]),
        ),
    )[0]
    period_identity_rows = [
        {
            "year": int(row["year"]),
            "period": int(row["period"]),
            "period_id": str(row["period_id"]),
        }
        for row in attribution_rows
    ]
    realised_input_identity_rows = [
        {
            "year": int(row["year"]),
            "period": int(row["period"]),
            "period_id": str(row["period_id"]),
            "realised_input_sha256": str(row["realised_input_sha256"]),
        }
        for row in attribution_rows
    ]
    payload = {
        **common,
        "attribution_method_id": ATTRIBUTION_METHOD_ID,
        "capability_status": "reconciled",
        "reason_code": None,
        "matched_counterfactual_proof": {
            "period_count": len(attribution_rows),
            "period_sets_match": True,
            "realised_input_hashes_match": True,
            "period_identity_set_sha256": contract_hash(period_identity_rows),
            # Compatibility field: it historically combined period and realised
            # input identity, so consumers must not use it as a pure period gate.
            "input_identity_set_sha256": contract_hash(realised_input_identity_rows),
        },
        "counterfactual_realised_input_set_sha256": contract_hash(
            realised_input_identity_rows
        ),
        "annual_totals": annual_totals,
        "maximum_absolute_period_residual_mwh": abs(
            float(maximum_row["identity_residual_mwh"])
        ),
        "maximum_residual_period_id": str(maximum_row["period_id"]),
        "maximum_period_tolerance_mwh": max(
            float(row["validation_tolerance_mwh"]) for row in attribution_rows
        ),
    }
    return _atomic_json_artifact(destination, payload)


def _capacity_row(year_result) -> dict[str, float | int]:
    values: dict[str, float] = {
        "solar": 0.0, "onshore": 0.0, "offshore": 0.0,
        "storage": 0.0, "CCGT": 0.0, "OCGT": 0.0,
    }
    for asset in year_result.planning_advance.operating_state.assets:
        technology = asset.technology
        if technology in values:
            values[technology] += float(asset.capacity_mw)
        elif technology in {"pumped_hydro", "1c_battery", "0.5c_battery", "0.25c_battery", "hydrogen_battery"}:
            values["storage"] += float(asset.capacity_mw)
    storage_energy = sum(
        float(asset.energy_capacity_mwh or 0.0)
        for asset in year_result.planning_advance.operating_state.assets
        if asset.technology in {"pumped_hydro", "1c_battery", "0.5c_battery", "0.25c_battery", "hydrogen_battery"}
    )
    return {
        "Year": year_result.year,
        "Solar_Capacity_MW": values["solar"],
        "Onshore_Capacity_MW": values["onshore"],
        "Offshore_Capacity_MW": values["offshore"],
        "Total_Storage_Capacity_MW": values["storage"],
        "Total_Storage_Energy_Capacity_MWh": storage_energy,
        "CCGT_Capacity_MW": values["CCGT"],
        "OCGT_Capacity_MW": values["OCGT"],
    }


def _native_result_payload(typed_results, ledgers, *, planning_mode: str) -> dict[str, object]:
    ledger_by_year = {item.year: item for item in ledgers}
    system_cost_history = []
    investment_decisions = []
    solver_validation_years: list[dict[str, object]] = []
    for result in typed_results:
        market = result.market
        solver_summary = market.extensions.get("solver_validation_summary")
        if isinstance(solver_summary, Mapping):
            solver_validation_years.append({
                "year": result.year,
                **dict(solver_summary),
            })
        ledger = ledger_by_year[result.year]
        system_cost_history.append({
            "Year": result.year,
            "Total_System_Cost_GBP": float(ledger.cem_system_cost_gbp or 0.0),
            "Cost_per_MWh_GBP": float(ledger.cem_system_cost_gbp_per_mwh_served or 0.0),
            "Total_Energy_Generated_MWh": market.total_generation_mwh,
            "Total_Levelized_Capital_Cost_GBP": market.total_levelized_capital_cost_gbp,
            "Total_Operational_Cost_GBP": market.total_operational_cost_gbp,
            "CM_Mechanism_Cost_Added_to_System_GBP": 0.0,
            "Decarbonization_Mechanism_Cost_Added_to_System_GBP": 0.0,
            "Total_Energy_Deficit_MWh": market.total_blackout_mwh,
            "Total_Excess_Energy_MWh": market.total_excess_mwh,
            "Total_Imports_MWh": sum(item.import_mwh for item in market.period_summaries),
            "Total_Storage_Charge_MWh": sum(item.storage_charge_mwh for item in market.period_summaries),
            "Total_Storage_Discharge_MWh": sum(item.storage_discharge_mwh for item in market.period_summaries),
            "Total_VRE_Curtailed_MWh": sum(item.curtailed_mwh for item in market.period_summaries),
        })
        for proposal in result.investment.proposals:
            investment_decisions.append({
                "year": result.year,
                "agent_id": proposal.agent_id,
                "technology": proposal.technology,
                "suggested_addition_mw": proposal.capacity_mw,
                "region": proposal.region,
                "expected_completion_year": proposal.expected_completion_year,
            })
        for asset_id, capacity in result.investment.retirements_mw.items():
            investment_decisions.append({
                "year": result.year,
                "agent_id": asset_id,
                "technology": "retirement",
                "suggested_addition_mw": -float(capacity),
                "region": "GB",
            })
    solver_validation_summary: dict[str, object] | None = None
    if solver_validation_years:
        terminal = solver_validation_years[-1]
        solver_validation_summary = {
            "schema_version": "value.study-solver-validation-summary/v1",
            "solver_validated": bool(terminal["solver_validated"]),
            "study_status": str(terminal["study_status"]),
            "first_causal_period": terminal.get("first_causal_period"),
            "maximum_validated_ceiling_use": max(
                float(row["maximum_validated_ceiling_use"])
                for row in solver_validation_years
            ),
            "warning_periods": sum(
                int(row["warning_periods"]) for row in solver_validation_years
            ),
            "unvalidated_periods": sum(
                int(row["unvalidated_periods"])
                for row in solver_validation_years
            ),
            "years": solver_validation_years,
            "detail_view": "solver-diagnostics",
        }
    return {
        "system_cost_history": system_cost_history,
        "capacity_history": [_capacity_row(result) for result in typed_results],
        "investment_decisions": investment_decisions,
        "planning_summary": [
            {
                "year": result.year,
                "active": len(result.planning_advance.active_projects),
                "commissioned": len(result.planning_advance.commissioned_projects),
                "failed": (
                    len(result.planning_advance.failed_projects)
                    if planning_mode in {"stochastic", "seeded_stochastic"}
                    else "not_applicable"
                ),
                "deferred": len(result.planning_advance.deferred_projects),
                "admitted": len(result.planning_admission.admitted_projects),
            }
            for result in typed_results
        ],
        "solver_validation_summary": solver_validation_summary,
    }


def _doctoral_native_input(run, pack_root, pack_manifest, state, periods):
    """Explicit national projection; existing staged/zonal entry stays unchanged."""
    return build_doctoral_psm_input(pack_root, pack_manifest, state,
        run_id=run.run_id, periods=periods,
        period_hours=float(run.scientific_parameters["clock.period_hours"]),
        parameters={**dict(run.scientific_parameters), **dict(run.runtime_controls)},
        voll_gbp_per_mwh=float(run.scientific_parameters.get("market.voll_gbp_per_mwh", 10_000.0)))


def _configure_doctoral_native_psm(psm, pack_root, pack_manifest, output_dir):
    from .canonical_psm_data import _binding_path
    from .nuclear_policy import POLICY_PATH
    fleet_path = _binding_path(pack_root, pack_manifest, "fleet.generators")
    raw = fleet_path.read_bytes()
    expected = pack_manifest["bindings"]["fleet.generators"].get("sha256")
    if not expected or hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("Doctoral native constructor fleet binding SHA-256 mismatch")
    fleet = json.loads(raw)
    weather_identity = {
        "bindings": {role: pack_manifest["bindings"].get(role) for role in ("weather.solar", "weather.wind")},
        "execution": weather_execution_identity(),
    }
    psm.configure_run(output_dir=output_dir, fleet_parameters=fleet,
        battery_parameters=fleet.get("batteries", {}),
        frozen_data_identity={
            "data_pack_sha256": hashlib.sha256((pack_root / "manifest.json").read_bytes()).hexdigest(),
            "weather_sha256": contract_hash(weather_identity),
            "nuclear_policy_sha256": hashlib.sha256(POLICY_PATH.read_bytes()).hexdigest(),
        })


def _run_native_project(
    *,
    project: Mapping[str, object],
    resolved: ResolvedRun,
    registry: ModuleRegistryV2,
    resolution_graph: ResolvedModuleGraph,
    selected: Mapping[str, str],
    pack_root: Path,
    network_pack_root: Path | None,
    output_dir: Path,
    periods: int,
    mode: str,
    manifest_snapshots: Mapping[str, Path],
    preparation_seconds: float,
    resume_checkpoint_id: str | None = None,
) -> dict[str, object]:
    """Execute selected public contracts directly, with no compatibility replay."""

    implementations = dict(resolution_graph.implementations_by_slot)
    (output_dir / "cem-model-identity.json").write_text(
        json.dumps(load_cem_identity(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    pack_manifest = json.loads((pack_root / "manifest.json").read_text(encoding="utf-8"))
    validate_pack_run_mode(pack_manifest, mode)
    source_initial_state = native_initial_state(
        pack_root,
        resolved.start_year,
        capital_discount_rate=float(
            resolved.scientific_parameters.get("cost.capital_discount_rate", 0.05) or 0.05
        ),
        scientific_parameters=resolved.scientific_parameters,
        doctoral_alignment=selected.get("psm") == "value-doctoral-national-psm",
    )
    if selected.get("psm") == "value-doctoral-national-psm":
        from .builtin.scheme_c_1000twh.doctoral_commissioning import apply_thesis96_pumped_schedule
        source_initial_state = apply_thesis96_pumped_schedule(source_initial_state)
    network_expansion = implementations.get("network_expansion")
    if network_expansion is not None:
        source_initial_state = load_network_expansion_state(
            pack_root, pack_manifest, source_initial_state
        )
    initial_state = source_initial_state
    network_pack = None
    run_context: RunStaticContext | None = None
    context_resolver: ImmutableContextResolver | None = None
    if selected.get("psm") == "value-bid-at-cost-psm":
        native_work = output_dir / "value-kernel-session"
        native_work.mkdir(parents=True, exist_ok=True)
        context = build_value_run_context(
            run_id=resolved.run_id,
            project_id=resolved.project_id,
            start_year=resolved.start_year,
            end_year=resolved.end_year,
            periods=periods,
            scenario_id=resolved.scenario_id,
            pack_root=pack_root,
            output_dir=output_dir,
            reference_work_dir=native_work,
            module_ids=selected,
            scientific_parameters=resolved.scientific_parameters,
            runtime_options=resolved.runtime_controls,
            environment={
                "PYTHONHASHSEED": "0",
                "START_YEAR": str(resolved.start_year),
                "END_YEAR": str(resolved.end_year),
                "OUTPUT_DIR": str(output_dir),
                "MARKET_TRACE_BASE_DIR": str(output_dir),
                "MARKET_TRACE_RUN_ID": resolved.run_id,
                "PHYSICAL_PERIOD_HOURS": str(resolved.scientific_parameters["clock.period_hours"]),
            },
        )
        persist_or_verify_value_context(context)
        configure = getattr(implementations["psm"], "configure_run", None)
        if not callable(configure):
            raise TypeError("value-bid-at-cost-psm does not expose the live v2 run configuration boundary")
        configure(context, implementations["storage_cost"])
    elif selected.get("psm") == "value-staged-bid-at-cost-psm":
        configure = getattr(implementations["psm"], "configure_run", None)
        if not callable(configure):
            raise TypeError(
                "value-staged-bid-at-cost-psm does not expose its live run configuration boundary"
            )
        balancing_identity = resolution_graph.identity("balancing")
        configured = dict(project.get("market_configuration") or {})
        if balancing_identity.module_id == "value-zonal-redispatch-balancing":
            if network_pack_root is None:
                raise ValueError("Zonal balancing has no resolved signed network overlay")
            network_manifest = json.loads(
                (network_pack_root / "manifest.json").read_text(encoding="utf-8")
            )
            network_pack = load_zonal_network_pack(
                network_pack_root, network_manifest
            )
            declared_pack_id = str(configured.get("network_pack_id") or "")
            if declared_pack_id and declared_pack_id != network_pack.network_pack_id:
                raise ValueError(
                    "Study network_pack_id does not match the immutable selected data pack"
                )
            if "weather_spatializer" not in selected:
                raise ValueError(
                    "Zonal staged balancing requires an explicit weather spatialisation module"
                )
        configure(
            output_dir=output_dir,
            storage_cost=implementations["storage_cost"],
            balancing=implementations["balancing"],
            expected_balancing_identity=(
                balancing_identity.module_id,
                balancing_identity.module_version,
            ),
            network_pack=network_pack,
            zonal_demand_mode=str(configured.get("zonal_demand_mode") or ""),
            weather_spatializer_identity=(
                (
                    resolution_graph.identity("weather_spatializer").module_id,
                    resolution_graph.identity("weather_spatializer").module_version,
                )
                if "weather_spatializer" in selected else None
            ),
            ledger_detail=str(
                dict(project.get("market_configuration") or {}).get(
                    "ledger_detail", "summary"
                )
            ),
        )
        run_context = build_run_static_context(
            resolved=resolved,
            project=project,
            pack_manifest=pack_manifest,
            pack_manifest_sha256=hashlib.sha256(
                (pack_root / "manifest.json").read_bytes()
            ).hexdigest(),
            resolution_graph=resolution_graph,
            network_pack=network_pack,
        )
    if selected.get("psm") == "value-doctoral-national-psm":
        _configure_doctoral_native_psm(implementations["psm"], pack_root, pack_manifest, output_dir)
    checkpoint_dir = output_dir / "checkpoints-v2"
    partial_dir = output_dir / "partial-year-results"
    prior_results: list[YearResult] = []
    checkpoints = sorted(
        checkpoint_dir.glob("state-*.json"),
        key=lambda path: int(path.stem.split("-")[-1]),
    )
    resume_year_context: YearContext | None = None
    if checkpoints:
        initial_state = load_json_checkpoint(checkpoints[-1], resolved)
        if (
            resume_checkpoint_id is None
            and run_context is not None
            and initial_state.year <= resolved.end_year
        ):
            resume_year_context = _load_authorized_incomplete_year_context(
                output_dir=output_dir,
                run_context=run_context,
                run_id=resolved.run_id,
                year=initial_state.year,
                checkpoint_state_sha256=contract_hash(initial_state),
            )
        for path in sorted(partial_dir.glob("year-*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("identity") != checkpoint_identity(resolved):
                raise ValueError("Partial annual result identity does not match the resumed run")
            result = YearResult.from_dict(payload["result"])
            if payload.get("result_sha256") != contract_hash(result):
                raise ValueError("Partial annual result SHA-256 does not match its content")
            if result.year < initial_state.year:
                prior_results.append(result)

    ledger_run_context_sha256 = (
        canonical_context_sha256(run_context)
        if run_context is not None else None
    )
    if resume_year_context is not None:
        ledger_run_context_sha256 = resume_year_context.run_context_sha256
    elif resume_checkpoint_id is not None and run_context is not None:
        existing_year_context_path = (
            output_dir / "market" / "context" / f"year-{initial_state.year}.json"
        )
        if not existing_year_context_path.is_file():
            raise ValueError(
                "Explicit subannual recovery has no frozen opening YearContext"
            )
        existing_year_payload = json.loads(
            existing_year_context_path.read_text(encoding="utf-8")
        )
        if not isinstance(existing_year_payload, Mapping):
            raise ValueError("Frozen opening YearContext is not an object")
        existing_year_context = YearContext.from_dict(existing_year_payload)
        if (
            existing_year_context.run_id != resolved.run_id
            or existing_year_context.year != initial_state.year
        ):
            raise ValueError(
                "Frozen opening YearContext does not match explicit subannual recovery"
            )
        ledger_run_context_sha256 = existing_year_context.run_context_sha256

    if run_context is not None:
        assert ledger_run_context_sha256 is not None
        runtime_run_context_sha256 = canonical_context_sha256(run_context)
        context_directory = output_dir / "market" / "context"
        if ledger_run_context_sha256 == runtime_run_context_sha256:
            _atomic_json_artifact(
                context_directory / "run-context.json",
                run_context.to_dict(),
            )
            authorized_lineage: tuple[str, ...] = ()
        else:
            runtime_context_path = _atomic_json_artifact(
                context_directory / "run-context-resume-runtime.json",
                run_context.to_dict(),
            )
            historical_context_path = context_directory / "run-context.json"
            historical_artifact_sha256 = None
            if historical_context_path.is_file():
                historical_payload = json.loads(
                    historical_context_path.read_text(encoding="utf-8")
                )
                if isinstance(historical_payload, Mapping):
                    historical_artifact_sha256 = canonical_context_sha256(
                        historical_payload
                    )
            _atomic_json_artifact(
                context_directory / "run-context-resume-lineage.json",
                {
                    "schema_version": "value.run-context-resume-lineage/v1",
                    "run_id": resolved.run_id,
                    "historical_run_context_sha256": ledger_run_context_sha256,
                    "historical_artifact_sha256": historical_artifact_sha256,
                    "historical_artifact_verified": (
                        historical_artifact_sha256 == ledger_run_context_sha256
                    ),
                    "runtime_run_context_sha256": runtime_run_context_sha256,
                    "runtime_context_artifact": runtime_context_path.relative_to(
                        output_dir
                    ).as_posix(),
                    "reason": "authorized_runtime_only_checkpoint_upgrade",
                },
            )
            authorized_lineage = (ledger_run_context_sha256,)
        context_resolver = ImmutableContextResolver(
            run_contexts=(run_context,),
            year_contexts=(),
            modules_by_slot=implementations,
            authorized_year_run_context_sha256=authorized_lineage,
        )
        configure_context = getattr(implementations["psm"], "configure", None)
        if not callable(configure_context):
            raise TypeError(
                "value-staged-bid-at-cost-psm does not expose its context lifecycle"
            )
        configure_context(run_context, context_resolver)
        if authorized_lineage:
            bind_resume_run_context = getattr(
                implementations["psm"], "bind_resume_run_context", None
            )
            if not callable(bind_resume_run_context):
                raise TypeError(
                    "Maintained staged PSM does not expose resume run lineage"
                )
            bind_resume_run_context(ledger_run_context_sha256)

    def write_partial(result: YearResult) -> None:
        partial_dir.mkdir(parents=True, exist_ok=True)
        destination = partial_dir / f"year-{result.year}.json"
        temporary = destination.with_suffix(".json.tmp")
        temporary.write_text(json.dumps({
            "schema_version": "value.partial-year-result/v1",
            "identity": checkpoint_identity(resolved),
            "result_sha256": contract_hash(result),
            "result": result.to_dict(),
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        temporary.replace(destination)

    recovery_consumed = False

    def recover_cancelled_year(context: YearContext) -> None:
        nonlocal recovery_consumed
        if resume_year_context is None or recovery_consumed:
            return
        expected = canonical_context_sha256(resume_year_context)
        if context != resume_year_context or canonical_context_sha256(context) != expected:
            raise ValueError("Frozen opening YearContext SHA-256 does not match")
        database = (output_dir / "market" / "market.sqlite").resolve()
        if not database.is_file():
            if run_context is not None and run_context.trace_profile != "off":
                raise ValueError("Authorised annual recovery has no staged v8 ledger")
            recovery_consumed = True
            return
        recovery_status = json.loads(
            (output_dir.resolve().parent / "status.json").read_text(encoding="utf-8")
        )
        recovery_authorization = recovery_status.get("recovery_authorization")
        if (
            not isinstance(recovery_authorization, Mapping)
            or recovery_authorization.get("state") != "consumed"
            or recovery_authorization.get("incomplete_year") != context.year
            or not isinstance(recovery_authorization.get("committed_period"), int)
        ):
            raise ValueError("Consumed annual recovery authorization is unavailable")
        recovery = recover_incomplete_v8_year(
            database,
            year=context.year,
            expected_committed_period=int(recovery_authorization["committed_period"]),
            expected_run_context_sha256=str(ledger_run_context_sha256),
            expected_year_context_sha256=expected,
            diagnostic_directory=output_dir / "market" / "recovery",
        )
        _atomic_json_artifact(
            output_dir / "market" / "recovery" / f"year-{context.year}-recovery.json",
            {
                **dict(recovery),
                "run_id": resolved.run_id,
                "checkpoint_state_sha256": str(
                    context.transition_lineage["annual_input_state_sha256"]
                ),
            },
        )
        recovery_consumed = True

    def input_factory(run: ResolvedRun, state):
        if selected.get("psm") == "value-doctoral-national-psm":
            return _doctoral_native_input(run, pack_root, pack_manifest, state, periods)
        chronology = build_chronology(
            pack_root,
            pack_manifest,
            state,
            periods=periods,
            period_hours=float(run.scientific_parameters["clock.period_hours"]),
            terminal_soc_rule=str(
                run.scientific_parameters.get(
                    "market.perfect_foresight_terminal_soc_rule", "cyclic"
                )
            ),
            voll_gbp_per_mwh=float(
                run.scientific_parameters.get("market.voll_gbp_per_mwh", 10_000.0)
            ),
        )
        if network_pack is not None:
            chronology = replace(
                chronology,
                period_ids=_network_period_ids_for_year(
                    network_pack.zonal_demand.period_ids,
                    year=state.year,
                    periods=periods,
                ),
            )
        input_extensions: dict[str, object] = {
            "artifact_directory": str(output_dir / "solver")
        }
        if selected.get("psm") in {
            "value-reference-dc-network", "value-reference-ac-feasibility"
        }:
            is_ac = selected.get("psm") == "value-reference-ac-feasibility"
            network_input = load_network_input_from_pack(
                pack_root, pack_manifest, chronology,
                run_id=run.run_id, year=state.year,
                period_hours=float(run.scientific_parameters["clock.period_hours"]),
                capability="domain.network.ac" if is_ac else "domain.network.dc",
                information_structure=(
                    "declared_schedule_ac_feasibility"
                    if is_ac else "chronological_perfect_foresight"
                ),
            )
            if is_ac:
                network_input = load_ac_data_from_pack(
                    pack_root, pack_manifest, network_input
                )
            if network_expansion is not None:
                network_input = apply_commissioned_network_assets(
                    network_input, state
                )
            input_extensions["network_input"] = network_input.to_dict()
        return PSMInput(
            run.run_id,
            state.year,
            run.data_pack_id,
            state,
            float(run.scientific_parameters["clock.period_hours"]),
            {**dict(run.scientific_parameters), **dict(run.runtime_controls)},
            chronology=chronology,
            extensions=input_extensions,
        )

    subannual_store = SubannualCheckpointStore(output_dir.parent)
    current_parent_annual_checkpoint_identity = _parent_annual_checkpoint_identity(
        resolved_identity=checkpoint_identity(resolved),
        state=initial_state,
        annual_checkpoint_sha256=(
            hashlib.sha256(checkpoints[-1].read_bytes()).hexdigest()
            if checkpoints
            else None
        ),
    )
    subannual_sink_configured = False
    subannual_recovery_evidence: Mapping[str, object] | None = None
    frozen_subannual_inputs: dict[str, object] | None = None
    frozen_subannual_modules: dict[str, object] | None = None
    if run_context is not None:
        psm_identity = resolution_graph.identity("psm")
        balancing_identity = resolution_graph.identity("balancing")
        solver_contract = dict(run_context.solver_contract)
        frozen_subannual_inputs = {
            "study_revision_sha256": run_context.study_revision_sha256,
            "resolved_run_sha256": contract_hash(resolved),
            "run_context_sha256": str(ledger_run_context_sha256),
            "year_context_sha256": "pending-year-context",
            "data_pack_id": resolved.data_pack_id,
            "data_pack_manifest_sha256": hashlib.sha256(
                (pack_root / "manifest.json").read_bytes()
            ).hexdigest(),
            "network_pack_id": (
                network_pack.network_pack_id
                if network_pack is not None else "not-applicable"
            ),
            "network_pack_manifest_sha256": (
                hashlib.sha256(
                    (network_pack_root / "manifest.json").read_bytes()
                ).hexdigest()
                if network_pack_root is not None else "0" * 64
            ),
            "scientific_parameters_sha256": contract_hash(
                dict(resolved.scientific_parameters)
            ),
            "runtime_controls_sha256": contract_hash(
                dict(resolved.runtime_controls)
            ),
        }
        frozen_subannual_modules = {
            "module_graph_sha256": resolution_graph.graph_sha256,
            "psm_module_id": psm_identity.module_id,
            "psm_module_version": psm_identity.module_version,
            "balancing_module_id": balancing_identity.module_id,
            "balancing_module_version": balancing_identity.module_version,
            "solver_contract_id": str(
                solver_contract.get("schema_version")
                or "value.network-solver-contract/v2"
            ),
            "solver_contract_version": str(
                solver_contract.get("contract_version") or "not-applicable"
            ),
        }
        subannual_sink_configured = _configure_subannual_checkpoint_sink(
            psm=implementations["psm"],
            store=subannual_store,
            frozen_input_hashes=frozen_subannual_inputs,
            frozen_module_hashes=frozen_subannual_modules,
            parent_annual_checkpoint_identity=(
                current_parent_annual_checkpoint_identity
            ),
        )

    if resume_checkpoint_id is not None:
        if (
            not subannual_sink_configured
            or run_context is None
            or frozen_subannual_inputs is None
            or frozen_subannual_modules is None
            or network_pack is None
        ):
            raise ValueError(
                "Explicit subannual recovery requires the maintained zonal PSM chain"
            )
        year_context_path = (
            output_dir / "market" / "context" / f"year-{initial_state.year}.json"
        )
        if not year_context_path.is_file():
            raise ValueError(
                "Explicit subannual recovery has no frozen opening YearContext"
            )
        year_context_payload = json.loads(
            year_context_path.read_text(encoding="utf-8")
        )
        if not isinstance(year_context_payload, Mapping):
            raise ValueError("Frozen opening YearContext is not an object")
        subannual_year_context = YearContext.from_dict(year_context_payload)
        if (
            subannual_year_context.run_id != resolved.run_id
            or subannual_year_context.year != initial_state.year
            or subannual_year_context.run_context_sha256
            != ledger_run_context_sha256
        ):
            raise ValueError(
                "Frozen opening YearContext does not match explicit subannual recovery"
            )
        period_ids = _network_period_ids_for_year(
            network_pack.zonal_demand.period_ids,
            year=initial_state.year,
            periods=periods,
        )
        chronology_sha256 = staged_contract_sha256({
            "period_ids": tuple(period_ids),
            "period_hours": float(
                resolved.scientific_parameters["clock.period_hours"]
            ),
            "model_year": initial_state.year,
        })
        expected_subannual_identity = SubannualCheckpointIdentity(
            run_id=resolved.run_id,
            model_year=initial_state.year,
            period_hours=float(
                resolved.scientific_parameters["clock.period_hours"]
            ),
            chronology_sha256=chronology_sha256,
            frozen_input_hashes={
                **frozen_subannual_inputs,
                "year_context_sha256": canonical_context_sha256(
                    subannual_year_context
                ),
            },
            frozen_module_hashes=frozen_subannual_modules,
        )
        subannual_recovery_evidence = _recover_explicit_subannual_checkpoint(
            output_dir=output_dir,
            resume_checkpoint_id=resume_checkpoint_id,
            expected=expected_subannual_identity,
            expected_parent_annual_checkpoint_identity=(
                current_parent_annual_checkpoint_identity
            ),
            psm=implementations["psm"],
        )

    if mode == "value_101_day":
        if resolved.start_year != resolved.end_year:
            raise ValueError("The VALUE 101 one-day lesson must resolve to one model year")
        operating_state = OperatingState(
            year=resolved.start_year,
            assets=source_initial_state.assets,
            active_planning_projects=source_initial_state.planning_projects,
            extensions={"source": "value_101_day_opening_state"},
        )
        model_input = input_factory(resolved, operating_state)
        if run_context is not None:
            assert context_resolver is not None
            prepare_year_context = getattr(
                implementations["psm"], "prepare_year_context", None
            )
            annual_metadata: Mapping[str, object] = {}
            if callable(prepare_year_context):
                model_input, annual_metadata = prepare_year_context(model_input)
            year_context = build_year_context(
                run_context=run_context,
                model_input=model_input,
                transition_lineage={
                    "annual_input_state_sha256": contract_hash(initial_state),
                    "execution_scope": "psm_only",
                },
                annual_metadata=annual_metadata,
            )
            publish_year_context(
                context_resolver,
                run_context,
                year_context,
                output_dir / "market" / "context",
            )
            start_year = getattr(implementations["psm"], "start_year", None)
            if callable(start_year):
                start_year(year_context)
        started = time.perf_counter()
        market = implementations["psm"].run(model_input)
        execution_seconds = time.perf_counter() - started
        if market.year != resolved.start_year or market.module_id != implementations["psm"].id:
            raise ValueError("The selected PSM returned an incompatible one-day result")
        day_path = _atomic_json_artifact(
            output_dir / "teaching" / "one-day-market-result.json",
            {
                "schema_version": "value.one-day-market-result/v1",
                "run_id": resolved.run_id,
                "year": resolved.start_year,
                "periods": periods,
                "period_hours": float(resolved.scientific_parameters["clock.period_hours"]),
                "execution_scope": "psm_only",
                "psm_module_id": implementations["psm"].id,
                "psm_input_sha256": contract_hash(model_input),
                "market_result": market.to_dict(),
            },
        )
        event_path = output_dir / "orchestrator-events.jsonl"
        event_path.write_text(
            json.dumps(
                {
                    "schema_version": "value.stage-event/v1",
                    "run_id": resolved.run_id,
                    "year": resolved.start_year,
                    "stage": "psm.run",
                    "module_id": implementations["psm"].id,
                    "duration_seconds": execution_seconds,
                },
                sort_keys=True,
            ) + "\n",
            encoding="utf-8",
        )
        validation_path = _atomic_json_artifact(
            output_dir / "validation" / "scientific-validation.json",
            {
                "schema_version": "value.scientific-validation/v1",
                "mode": mode,
                "periods_per_year": periods,
                "execution_status": "passed",
                "contract_validation_status": "passed",
                "scientific_validation_status": "not_evaluated",
                "annual_economics_eligible": False,
                "short_run_diagnostics_only": True,
                "execution_scope": "psm_only",
                "cem_stages_executed": False,
            },
        )
        provenance_path = _atomic_json_artifact(
            output_dir / "provenance.json",
            {
                "schema_version": "value.run-provenance/v1",
                "run_id": resolved.run_id,
                "project_id": resolved.project_id,
                "data_pack_id": resolved.data_pack_id,
                "execution_scope": "psm_only",
                "selected_psm": implementations["psm"].id,
                "periods": periods,
                "year": resolved.start_year,
                "result_artifact": day_path.relative_to(output_dir).as_posix(),
                "runtime_overlay": ensure_runtime_overlay_sealed(),
            },
        )
        # Publish the executed effective configuration for frozen Run comparison,
        # using the same resolved payload as the annual execution path.
        _atomic_json_artifact(output_dir / "resolved-run.json", resolved.to_dict())
        return {
            "engine": "value-psm-only/v1",
            "execution_engine": "value-psm-only/v1",
            "execution_path": "native_public_contracts",
            "selected_psm": implementations["psm"].id,
            "one_day_market_result": day_path.relative_to(output_dir).as_posix(),
            "scientific_validation_artifact": validation_path.relative_to(output_dir).as_posix(),
            "provenance_artifact": provenance_path.relative_to(output_dir).as_posix(),
        }

    annual_checkpoint = json_checkpoint_writer(
        checkpoint_dir,
        resolved,
        on_verified=(
            lambda state, digest: _advance_subannual_parent_after_annual_checkpoint(
                store=subannual_store,
                parent_annual_checkpoint_identity=(
                    current_parent_annual_checkpoint_identity
                ),
                resolved_identity=checkpoint_identity(resolved),
                state=state,
                annual_checkpoint_sha256=digest,
            )
        ) if subannual_sink_configured else None,
    )
    orchestrator = AnnualModelOrchestratorV2(
        implementations["psm"],
        {
            "vre_cap": implementations["vre_cap"],
            "storage_cap": implementations["storage_cap"],
        },
        implementations["investment"],
        implementations["pipeline"],
        implementations["transition"],
        event_sink=JsonlStageEventWriter(output_dir / "orchestrator-events.jsonl"),
        checkpoint=annual_checkpoint,
        year_result_sink=write_partial,
        psm_input_factory=input_factory,
        cancellation_check=lambda _year, _boundary: cancellation_requested(output_dir.parent),
        extension_runtime=(
            ExtensionRuntime(resolution_graph.extension_graph)
            if resolution_graph.extension_graph is not None
            else None
        ),
        network_expansion=network_expansion,
        run_context=run_context,
        context_resolver=context_resolver,
        context_directory=(
            output_dir / "market" / "context" if run_context is not None else None
        ),
        year_start_recovery=(
            recover_cancelled_year if resume_year_context is not None else None
        ),
        run_context_sha256=ledger_run_context_sha256,
    )
    started = time.perf_counter()
    new_results = (
        orchestrator.run(resolved, initial_state)
        if initial_state.year <= resolved.end_year
        else []
    )
    typed_results = sorted(
        {result.year: result for result in [*prior_results, *new_results]}.values(),
        key=lambda result: result.year,
    )
    expected_years = list(range(resolved.start_year, resolved.end_year + 1))
    if [result.year for result in typed_results] != expected_years:
        raise ValueError(
            "Resumed annual results are incomplete: expected "
            f"{expected_years}, found {[result.year for result in typed_results]}"
        )
    execution_seconds = time.perf_counter() - started
    ledgers = [build_cem_cost_ledger(result.market) for result in typed_results]
    cost_ledger_path = write_cost_ledgers(
        output_dir / "ledgers" / "annual-cost-ledger.json", ledgers
    )
    carbon_scenario = str(
        resolved.scientific_parameters.get(
            "carbon.factor_scenario", "value_current_authoritative_v1"
        )
    )
    carbon_ledgers = []
    for result in typed_results:
        technology_by_asset = {
            asset.asset_id: asset.technology
            for asset in result.planning_advance.operating_state.assets
        }
        # Imports are PSM boundary resources and therefore are not operating assets.
        import_countries = {}
        for asset_id in result.market.generation_mwh_by_asset:
            if asset_id.startswith("import:"):
                technology_by_asset[asset_id] = "import_electricity"
                import_countries[asset_id] = asset_id.split(":", 1)[1]
        carbon_ledger = build_operational_carbon_ledger(
            year=result.year,
            scenario_id=carbon_scenario,
            generation_mwh_by_asset=result.market.generation_mwh_by_asset,
            technology_by_asset=technology_by_asset,
            delivered_demand_mwh=max(
                result.market.total_demand_mwh - result.market.total_blackout_mwh, 0.0
            ),
            import_country_by_asset=import_countries,
            asset_states=result.planning_advance.operating_state.assets,
        )
        if network_expansion is not None:
            carbon_ledger = adjust_carbon_ledger_for_network(
                carbon_ledger,
                year=result.year,
                state=result.planning_advance.operating_state,
            )
        carbon_ledgers.append(carbon_ledger)
    carbon_ledger_path = write_carbon_ledgers(
        output_dir / "ledgers" / "annual-carbon-ledger.json", carbon_ledgers
    )
    carbon_ledger_sqlite_path = carbon_ledger_path.with_suffix(".sqlite")
    network_artifacts = None
    if network_expansion is not None:
        network_artifacts = write_network_expansion_artifacts(
            output_dir / "network", typed_results
        )
    terminal_paths = write_terminal_artifacts(
        output_dir / "terminal",
        typed_results[-1].next_state,
        horizon_year=resolved.end_year,
        discount_rate=float(
            resolved.scientific_parameters.get("fleet.valuation_discount_rate", 0.05)
        ),
        policy=str(resolved.scientific_parameters.get("terminal.policy", "report_only")),
    )
    planning_summary = materialize_planning_index(
        output_dir / "planning" / "project-index.sqlite",
        typed_results,
        run_id=resolved.run_id,
        project_revision=str(resolved.extensions.get("project_revision_sha256") or "not_declared"),
    )
    (output_dir / "planning" / "typed-summary.json").write_text(
        json.dumps(planning_summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (output_dir / "planning" / "summary.json").write_text(
        json.dumps(planning_summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (output_dir / "year-results-v2.json").write_text(
        json.dumps([item.to_dict() for item in typed_results], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (output_dir / "resolved-run.json").write_text(
        json.dumps(resolved.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    validation_dir = output_dir / "validation"
    validation_dir.mkdir(parents=True, exist_ok=True)
    parity_path = output_dir / "parity" / "stage-parity.json"
    parity_path.parent.mkdir(parents=True, exist_ok=True)
    market_metadata_path = output_dir / "market" / "metadata.json"
    if market_metadata_path.is_file():
        market_metadata = json.loads(market_metadata_path.read_text(encoding="utf-8"))
        market_periods = int(market_metadata["rows"]["period_summary"])
        market_database_artifact: str | None = "market/market.sqlite"
    else:
        # A conformant external PSM may return typed period summaries without
        # using VALUE's optional SQLite writer. Typed results are the contract;
        # the built-in ledger is an implementation artifact, not a hidden API.
        market_periods = sum(len(result.market.period_summaries) for result in typed_results)
        market_database_artifact = None
    configured_network_pack_id = str(
        dict(project.get("market_configuration") or {}).get("network_pack_id")
        or "not_selected"
    )
    vre_attribution_path = write_vre_curtailment_attribution_artifact(
        output_dir=output_dir,
        database=output_dir / "market" / "market.sqlite",
        data_pack_id=resolved.data_pack_id,
        network_pack_id=(
            network_pack.network_pack_id
            if network_pack is not None
            else configured_network_pack_id
        ),
        initial_state_sha256=contract_hash(source_initial_state),
        resolution_graph=resolution_graph,
    )
    parity_path.write_text(json.dumps({
        "schema_version": "value.stage-parity-report/v2",
        "passed": True,
        "contract_parity_passed": True,
        "retained_numerical_parity_passed": None,
        "release_gate_passed": None,
        "first_divergence": None,
        "execution_path": "native_public_contracts",
        "selected_psm": selected["psm"],
        "market_evidence": {
            "available": True,
            "periods": market_periods,
            "database_artifact": market_database_artifact,
            "source": "sqlite_ledger" if market_database_artifact else "typed_contract",
        },
        "planning_evidence": {
            "available": True,
            "years": len(typed_results),
            "database_artifact": "planning/project-index.sqlite",
        },
        "agent_economics_evidence": {
            "available": False,
            "reason": "Native typed investment decisions are recorded directly; the legacy investment-analysis replay table is reference-only.",
        },
    }, indent=2), encoding="utf-8")
    scientific_path = write_scientific_validation_report(
        output_dir,
        mode=mode,
        periods_per_year=periods,
        parity_path=parity_path,
        retained_comparison_role=RETAINED_COMPARISON_INFORMATIONAL,
    )
    comparison_path: Path | None = None
    annual_comparison_evidence = []
    for result in typed_results:
        evidence = result.market.extensions.get("comparison_input_evidence")
        if not isinstance(evidence, Mapping):
            annual_comparison_evidence = []
            break
        annual_comparison_evidence.append(dict(evidence))
    if annual_comparison_evidence:
        treatment_slots = {"balancing", "weather_spatializer"}
        fixed_modules = {
            slot: f"{selection.module_id}@{selection.module_version}"
            for slot, selection in sorted(resolved.modules.items())
            if slot not in treatment_slots
        }
        binding_identity = {
            str(role): {
                "sha256": binding.get("sha256"),
                "bytes": binding.get("bytes"),
            }
            for role, binding in sorted(
                dict(pack_manifest.get("bindings") or {}).items()
            )
            if isinstance(binding, Mapping)
        }
        configured_market = dict(project.get("market_configuration") or {})
        demand_authority_mode = (
            str(configured_market.get("zonal_demand_mode") or "")
            if network_pack is not None
            else COPPERPLATE_SCENARIO_DEMAND
        )
        balancing = resolved.modules.get("balancing")
        weather = resolved.modules.get("weather_spatializer")
        comparison_artifact = build_comparison_eligibility(
            run_id=resolved.run_id,
            demand_authority_mode=demand_authority_mode,
            fixed_inputs={
                "data_pack_id": resolved.data_pack_id,
                "data_pack_scientific_sha256": pack_manifest.get("scientific_sha256"),
                "data_bindings_sha256": contract_hash(binding_identity),
                "start_year": resolved.start_year,
                "end_year": resolved.end_year,
                "initial_state_sha256": contract_hash(source_initial_state),
                "scientific_parameters_sha256": contract_hash(
                    dict(resolved.scientific_parameters)
                ),
                "modules": fixed_modules,
            },
            annual_input_evidence=annual_comparison_evidence,
            network_treatment={
                "balancing_module_id": balancing.module_id if balancing else None,
                "balancing_module_version": (
                    balancing.module_version if balancing else None
                ),
                "network_pack_id": (
                    network_pack.network_pack_id if network_pack is not None else None
                ),
                "network_pack_scientific_sha256": (
                    network_pack.scientific_sha256 if network_pack is not None else None
                ),
                "weather_spatializer_module_id": weather.module_id if weather else None,
                "weather_spatializer_module_version": (
                    weather.module_version if weather else None
                ),
            },
        )
        comparison_path = write_comparison_eligibility(
            output_dir / "comparison-eligibility.json", comparison_artifact
        )
    write_performance_report(
        output_dir,
        preparation_seconds=preparation_seconds,
        copied_kernel_seconds=0.0,
        contract_materialisation_seconds=execution_seconds,
        serialization_and_validation_seconds=0.0,
    )
    provenance_path = write_run_provenance(
        project_root=Path(__file__).resolve().parents[1],
        pack_root=pack_root,
        output_dir=output_dir,
        resolved_run=resolved,
        registry=registry,
        selected=selected,
        project_schema=str(project.get("schema_version") or "value.project/v1"),
        manifest_snapshots=manifest_snapshots,
        initial_state=source_initial_state,
        year_results=typed_results,
        runtime_overlay=ensure_runtime_overlay_sealed(),
    )
    payload = _native_result_payload(
        typed_results,
        ledgers,
        planning_mode=str(resolved.scientific_parameters.get("planning.success_mode", "expected_capacity")),
    )
    payload.update({
        "engine": "value-annual-orchestrator/v2",
        "execution_engine": "value-annual-orchestrator/v2",
        "execution_path": "native_public_contracts",
        "orchestrator_results": [item.to_dict() for item in typed_results],
        "cem_cost_ledgers": [item.to_dict() for item in ledgers],
        "carbon_ledgers": carbon_ledgers,
        "cost_ledger_artifact": cost_ledger_path.relative_to(output_dir).as_posix(),
        "carbon_ledger_artifact": carbon_ledger_path.relative_to(output_dir).as_posix(),
        "carbon_ledger_sqlite_artifact": carbon_ledger_sqlite_path.relative_to(output_dir).as_posix(),
        "terminal_state_artifact": terminal_paths[0].relative_to(output_dir).as_posix(),
        "fleet_vintage_artifact": terminal_paths[1].relative_to(output_dir).as_posix(),
        "planning_index_artifact": "planning/project-index.sqlite",
        "compatibility_boundary": None,
        "provenance_artifact": provenance_path.name,
        "stage_parity_artifact": parity_path.relative_to(output_dir).as_posix(),
        "scientific_validation_artifact": scientific_path.relative_to(output_dir).as_posix(),
    })
    if comparison_path is not None:
        payload["comparison_eligibility_artifact"] = comparison_path.relative_to(
            output_dir
        ).as_posix()
    if vre_attribution_path is not None:
        payload["vre_curtailment_attribution_artifact"] = (
            vre_attribution_path.relative_to(output_dir).as_posix()
        )
    if network_artifacts is not None:
        payload["network_expansion_artifacts"] = [
            path.relative_to(output_dir).as_posix() for path in network_artifacts
        ]
    if subannual_recovery_evidence is not None:
        payload["subannual_recovery"] = dict(subannual_recovery_evidence)
    return payload


def _years_for_mode(project: Mapping[str, object], mode: str) -> tuple[int, int, int]:
    policy = resolve_run_policy(mode)
    start, end = policy.years(project)
    return start, end, policy.periods_per_year


def _network_period_ids_for_year(
    period_ids: Sequence[str], *, year: int, periods: int
) -> tuple[str, ...]:
    """Select a model-year clock or a bounded slice of one annual reference clock."""

    declared = tuple(str(item) for item in period_ids)
    if len(declared) < periods:
        raise ValueError(
            "Selected zonal network pack is shorter than the requested run clock"
        )
    if len(declared) == periods:
        return declared
    if len(declared) == 17_520 and periods < 17_520:
        return declared[:periods]
    matching = tuple(
        period_id for period_id in declared
        if period_id.startswith(f"{int(year)}:")
    )
    if len(matching) < periods:
        raise ValueError(
            f"Selected zonal network pack has no {int(year)} clock with "
            f"{periods} periods"
        )
    return matching[:periods]


def _headroom_from_evidence(path: Path) -> dict[tuple[int, str], dict[str, float]]:
    values: dict[tuple[int, str], dict[str, float]] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        limits = event.get("limits_mw")
        if isinstance(limits, dict):
            values[(int(event["year"]), str(event["module_id"]))] = {
                str(key): float(value) for key, value in limits.items()
            }
    return values


def _agent_economics_from_trace(path: Path) -> dict[int, dict[str, object]]:
    """Materialise compact decision evidence without putting asset rows in the UI."""

    if not path.is_file():
        return {}
    with sqlite3.connect(path) as connection:
        rows = connection.execute(
            "SELECT year, total_income, operational_cost, recommendation "
            "FROM investment_analysis ORDER BY year, asset_name"
        ).fetchall()
    grouped: dict[int, list[tuple[float, float, str]]] = {}
    for year, income, cost, recommendation in rows:
        grouped.setdefault(int(year), []).append(
            (float(income or 0.0), float(cost or 0.0), str(recommendation))
        )
    return {
        year: {
            "agent_rows": len(values),
            "total_income_gbp": sum(value[0] for value in values),
            "total_operational_cost_gbp": sum(value[1] for value in values),
            "recommendations": dict(sorted(Counter(value[2] for value in values).items())),
        }
        for year, values in grouped.items()
    }


def _resolved_run(
    project: Mapping[str, object],
    run_id: str,
    resolution_graph: ResolvedModuleGraph,
    scientific: Mapping[str, object],
    runtime: Mapping[str, object],
    sources: Mapping[str, Mapping[str, object]],
    start: int,
    end: int,
) -> ResolvedRun:
    modules = {
        slot: ModuleSelection(
            slot, manifest.id, manifest.version, manifest.contract_version
        )
        for slot, manifest in resolution_graph.manifests_by_slot.items()
    }
    extension_metadata: dict[str, object] = {}
    execution_bundle = dict(project.get("extensions") or {}).get("execution_bundle")
    if isinstance(execution_bundle, Mapping):
        extension_metadata["execution_bundle"] = dict(execution_bundle)
    if resolution_graph.extension_graph is not None:
        extension_metadata["extension_graph"] = resolution_graph.extension_graph.to_dict()
    return ResolvedRun(
        run_id,
        str(project.get("id") or "project"),
        str(scientific["scenario.id"]),
        str(project["data_pack_id"]),
        start,
        end,
        modules,
        dict(scientific),
        dict(runtime),
        extensions={
            "execution_kind": "live_module",
            "runtime_capability": VALUE_NATIVE,
            "runtime_capability_status": capability_status(
                VALUE_NATIVE,
                selected_module_ids=(
                    identity.module_id
                    for identity in resolution_graph.identities_by_slot.values()
                ),
            ),
            "parameter_sources": {key: dict(value) for key, value in sources.items()},
            "project_revision_sha256": project.get("revision_sha256"),
            "project_revision_number": project.get("revision_number"),
            "module_resolution_graph_sha256": resolution_graph.graph_sha256,
            **extension_metadata,
        },
    )


def run_project_application(
    project: Mapping[str, object],
    *,
    run_id: str,
    pack_root: Path,
    output_dir: Path,
    mode: str,
    registry: ModuleRegistryV2 | None = None,
    network_pack_root: Path | None = None,
    resume_checkpoint_id: str | None = None,
) -> dict[str, object]:
    """Run the selected project without fallback to any other module set."""

    preparation_started = time.perf_counter()
    # The sealed runtime kernel is verified once per process before any run
    # (RUNTIME_OVERLAY v2, X0 S5); a changed or unregistered kernel file fails
    # closed here instead of silently producing numbers.
    ensure_runtime_overlay_sealed()
    pack_root = pack_root.resolve()
    output_dir = output_dir.resolve()
    registry = registry or workspace_registry()
    start, end, periods = _years_for_mode(project, mode)
    selected = dict(project.get("modules") or {})  # type: ignore[arg-type]
    selected.setdefault("transition", DEFAULT_TRANSITION)
    selected_psm = str(selected.get("psm") or "")
    if selected_psm:
        psm_manifest = registry.manifest(selected_psm, expected_slot="psm")
        if "storage.bid-cost-function" in psm_manifest.requires_capabilities:
            selected.setdefault("storage_cost", DEFAULT_STORAGE_COST)
    project_parameter_overrides = (
        project.get("parameters") or project.get("parameter_overrides") or {}
    )
    project_runtime_options = dict(
        project.get("runtime_options") or project.get("runtime_controls") or {}
    )
    run_policy = resolve_run_policy(mode)
    if mode == "value_101_day":
        project_runtime_options["runtime.market_trace_level"] = "full"
    # Independent validation must capture the exact information seen before
    # each live VALUE clearing.  This evidence is a property of the validation
    # run, not an expensive trace setting that users must remember to enable in
    # their saved research project.
    if run_policy.requires_declared_clearing_inputs:
        project_runtime_options["runtime.market_trace_level"] = "full"
    resolved_parameters = resolve_scheme_c_parameters(
        pack_root,
        project_parameter_overrides,  # type: ignore[arg-type]
        project_runtime_options,  # type: ignore[arg-type]
        periods_per_year=periods,
    )
    resolved_sources = {
        key: dict(value) for key, value in resolved_parameters.sources.items()
    }
    if run_policy.requires_declared_clearing_inputs:
        resolved_sources["runtime.market_trace_level"] = {
            "source": "run_policy_required",
            "run_mode": mode,
            "reason": "independent VALUE validation requires pre-clearing declarations",
            "project_override": False,
            "data_pack_role": None,
        }
    elif mode == "value_101_day":
        resolved_sources["runtime.market_trace_level"] = {
            "source": "run_policy_required",
            "run_mode": mode,
            "reason": "the one-day lesson includes auction-level market replay",
            "project_override": False,
            "data_pack_role": None,
        }
    pack_selection = resolve_zonal_pack_selection(
        project,
        base_pack_root=pack_root,
        explicit_network_pack_root=network_pack_root,
    )
    pack_manifest = dict(pack_selection.base_manifest)
    selected_extensions = tuple(
        str(item) for item in project.get("selected_extensions", ())
    )
    validate_maturity_acknowledgements(
        registry,
        selected,
        selected_extensions,
        dict(project.get("maturity_acknowledgements") or {}),
    )
    resolution_graph = registry.resolve_selection(
        selected,
        selected_extensions=selected_extensions,
        extension_parameters=dict(project.get("extension_parameters") or {}),
        available_data_roles=pack_selection.available_data_roles,
    )
    balancing_manifest = resolution_graph.manifests_by_slot.get("balancing")
    if (
        balancing_manifest is not None
        and balancing_manifest.id == "value-zonal-redispatch-balancing"
    ):
        solver_settings = validate_solver_settings(project.get("solver_contract"))
        implementations = dict(resolution_graph.implementations_by_slot)
        implementations["balancing"] = ZonalRedispatchBalancing(solver_settings)
        resolution_graph = replace(
            resolution_graph,
            implementations_by_slot=implementations,
        )
    resolved = _resolved_run(
        project, run_id, resolution_graph,
        resolved_parameters.scientific.values,
        resolved_parameters.runtime.values,
        resolved_sources,
        start, end,
    )
    if uses_doctoral_weather(pack_manifest):
        # Do not rely on a stored project revision: CLI callers can reuse it.
        # Annual and subannual recovery must see the currently loaded method.
        resolved = replace(resolved, extensions={
            **resolved.extensions, "dispatch_weather_identity": weather_execution_identity(),
        })
    manifest_snapshots = snapshot_module_manifests(
        output_dir, registry, selected, resolution_graph=resolution_graph
    )
    (output_dir / "module-resolution.json").write_text(
        json.dumps(resolution_graph.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    preparation_seconds = time.perf_counter() - preparation_started

    return _run_native_project(
        project=project,
        resolved=resolved,
        registry=registry,
        resolution_graph=resolution_graph,
        selected=selected,
        pack_root=pack_root,
        network_pack_root=pack_selection.network_pack_root,
        output_dir=output_dir,
        periods=periods,
        mode=mode,
        manifest_snapshots=manifest_snapshots,
        preparation_seconds=preparation_seconds,
        resume_checkpoint_id=resume_checkpoint_id,
    )


@contextmanager
def _stdout_to_stderr():
    """Send everything written to stdout (Python prints, the sealed kernel's
    progress output, child processes inheriting fd 1) to stderr, so the CLI's
    stdout carries only its JSON summary (P7-24)."""

    sys.stdout.flush()
    try:
        saved = os.dup(1)
        os.dup2(2, 1)
    except OSError:  # no usable fd 1/2 (embedded or detached interpreter)
        saved = None
    try:
        with redirect_stdout(sys.stderr):
            yield
    finally:
        sys.stderr.flush()
        if saved is not None:
            os.dup2(saved, 1)
            os.close(saved)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Run a VALUE v2 research project")
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--pack", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--run-id", default="cli-run")
    parser.add_argument(
        "--resume-checkpoint-id",
        help=(
            "Exact published subannual checkpoint ID to consume once; omit to "
            "retain annual v1 resume behavior"
        ),
    )
    parser.add_argument(
        "--network-pack",
        type=Path,
        help="Optional explicit signed network-overlay root; otherwise resolve network_pack_id from VALUE_DATA_HOME.",
    )
    parser.add_argument(
        "--mode",
        choices=("smoke", "two_year_smoke", "validation_24h", "validation_168h", "value_101_day", "two_year", "full"),
        default="smoke",
    )
    args = parser.parse_args()
    project = json.loads(args.project.read_text(encoding="utf-8"))
    from .catalog import DATASET_SLOTS
    from .preflight import run_preflight

    args.output.mkdir(parents=True, exist_ok=True)
    pack_manifest = json.loads((args.pack / "manifest.json").read_text(encoding="utf-8"))
    with _stdout_to_stderr():
        preflight = run_preflight(
            project,
            mode=args.mode,
            pack_root=args.pack.resolve(),
            pack_manifest=pack_manifest,
            dataset_slots=DATASET_SLOTS,
            output_root=args.output.resolve(),
            network_pack_root=(args.network_pack.resolve() if args.network_pack else None),
        )
    (args.output / "preflight.json").write_text(
        json.dumps(preflight, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    if not preflight["accepted"]:
        print(json.dumps(preflight, ensure_ascii=False))
        raise SystemExit(2)
    with _stdout_to_stderr():
        result = run_project_application(
            project, run_id=args.run_id, pack_root=args.pack.resolve(),
            output_dir=args.output.resolve(), mode=args.mode,
            network_pack_root=(args.network_pack.resolve() if args.network_pack else None),
            resume_checkpoint_id=args.resume_checkpoint_id,
        )
    print(json.dumps({
        "engine": result["engine"],
        # PSM-only and native paths return orchestrator_results instead of the
        # legacy system_cost_history (P7-24); count whichever the engine wrote.
        "years": len(result.get("system_cost_history") or result.get("orchestrator_results") or []),
        "output": str(args.output.resolve()),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
