"""Typed, deterministic annual lifecycle for every VALUE v2 project."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Mapping

from ..module_context import (
    ImmutableContextResolver,
    RunContextRef,
    RunStaticContext,
    YearContext,
    canonical_context_sha256,
)
from .contracts import OperatingState, PSMInput, ResolvedRun, YearResult, YearState
from .interfaces import ExpansionPolicy, InvestmentModule, PSMEngine, PlanningPipeline, StateTransition
from ..errors import ContractError, InvariantError
from ..extension_framework import ExtensionRuntime, canonical_hash
from ..cem_market_adapter import adapt_market_for_investment, inherit_frozen_zone_shares


@dataclass(frozen=True)
class StageEvent:
    sequence: int
    run_id: str
    year: int
    stage: str
    module_slot: str
    module_id: str
    module_version: str
    contract_version: str
    input_state_sha256: str
    output_sha256: str
    output_state_sha256: str
    artifact_ids: tuple[str, ...]
    duration_seconds: float
    schema_version: str = "value.stage-event/v3"

    def to_dict(self) -> dict[str, object]:
        return dict(self.__dict__)


def contract_hash(value: object) -> str:
    payload = value.to_dict() if hasattr(value, "to_dict") else value
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_year_context(
    *,
    run_context: RunStaticContext,
    model_input: PSMInput,
    transition_lineage: Mapping[str, object],
    annual_metadata: Mapping[str, object] | None = None,
    run_context_sha256: str | None = None,
) -> YearContext:
    """Freeze the exact opening fleet and annual PSM metadata for one year."""

    metadata = dict(annual_metadata or {})
    frozen_zone_shares = dict(metadata.get("frozen_zone_shares") or {})
    opening_soc = dict(metadata.get("opening_soc_mwh_by_asset") or {})
    operating_state = {
        **model_input.operating_state.to_dict(),
        **{
            key: value
            for key, value in metadata.items()
            if key not in {"frozen_zone_shares", "opening_soc_mwh_by_asset"}
        },
    }
    lineage_sha256 = (
        canonical_context_sha256(run_context)
        if run_context_sha256 is None
        else RunContextRef(run_context_sha256).sha256
    )
    return YearContext(
        run_id=model_input.run_id,
        year=model_input.year,
        run_context_sha256=lineage_sha256,
        operating_state=operating_state,
        frozen_zone_shares=frozen_zone_shares,
        opening_soc_mwh_by_asset=opening_soc,
        transition_lineage=dict(transition_lineage),
    )


def publish_year_context(
    resolver: ImmutableContextResolver,
    run_context: RunStaticContext,
    context: YearContext,
    directory: Path,
    *,
    run_context_sha256: str | None = None,
) -> YearContextRef:
    """Bind and atomically publish one immutable annual context."""

    run_digest = canonical_context_sha256(run_context)
    if resolver.resolve_run(RunContextRef(run_digest)) != run_context:
        raise ContractError("Run context is not exactly bound")
    lineage_sha256 = (
        run_digest
        if run_context_sha256 is None
        else RunContextRef(run_context_sha256).sha256
    )
    if context.run_context_sha256 != lineage_sha256:
        raise ContractError("Year context does not reference the bound run context")
    digest = canonical_context_sha256(context)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"year-{context.year}.json"
    encoded = json.dumps(
        context.to_dict(), indent=2, ensure_ascii=False, sort_keys=True
    )

    def require_matching_destination() -> None:
        try:
            existing_payload = json.loads(destination.read_text(encoding="utf-8"))
            if not isinstance(existing_payload, Mapping):
                raise TypeError("year context root must be an object")
            existing = YearContext.from_dict(existing_payload)
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ContractError(
                f"Existing year context is invalid: {destination}"
            ) from exc
        if canonical_context_sha256(existing) != digest or existing != context:
            raise ContractError(
                "Existing year context identity is bound to different content"
            )

    def publish() -> None:
        if destination.exists():
            require_matching_destination()
            return

        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="",
                dir=directory,
                prefix=f".year-{context.year}-",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary = Path(handle.name)
                handle.write(encoded)
            try:
                os.link(temporary, destination)
            except FileExistsError:
                require_matching_destination()
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    return resolver.bind_year_transaction(context, publish)


class JsonlStageEventWriter:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def __call__(self, event: StageEvent) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")


class CancellationRequested(RuntimeError):
    """Raised only at a declared model-safe cancellation boundary."""


def request_period_boundary_cancel(
    cancellation_check: Callable[[int, str], bool] | None,
    *,
    year: int,
    period: int,
) -> None:
    """Accept the existing cancellation request after a committed period."""

    if cancellation_check and cancellation_check(year, "after_period_commit"):
        raise CancellationRequested(
            f"Cancellation accepted after committed model year {year} period {period}"
        )


class AnnualModelOrchestratorV2:
    """Own the calendar and invoke exactly one implementation per selected slot."""

    def __init__(
        self,
        psm: PSMEngine,
        expansion_policies: Mapping[str, ExpansionPolicy],
        investment: InvestmentModule,
        planning: PlanningPipeline,
        transition: StateTransition,
        *,
        event_sink: Callable[[StageEvent], None] | None = None,
        checkpoint: Callable[[YearState], None] | None = None,
        year_result_sink: Callable[[YearResult], None] | None = None,
        psm_input_factory: Callable[[ResolvedRun, OperatingState], PSMInput] | None = None,
        cancellation_check: Callable[[int, str], bool] | None = None,
        extension_runtime: ExtensionRuntime | None = None,
        network_expansion: object | None = None,
        run_context: RunStaticContext | None = None,
        context_resolver: ImmutableContextResolver | None = None,
        context_directory: Path | None = None,
        year_start_recovery: Callable[[YearContext], None] | None = None,
        run_context_sha256: str | None = None,
    ) -> None:
        self.psm = psm
        self.expansion_policies = dict(expansion_policies)
        self.investment = investment
        self.planning = planning
        self.transition = transition
        self.event_sink = event_sink
        self.checkpoint = checkpoint
        self.year_result_sink = year_result_sink
        self.psm_input_factory = psm_input_factory
        self.cancellation_check = cancellation_check
        self.extension_runtime = extension_runtime
        self.network_expansion = network_expansion
        self.run_context = run_context
        self.context_resolver = context_resolver
        self.context_directory = Path(context_directory) if context_directory else None
        self.year_start_recovery = year_start_recovery
        self.run_context_sha256 = (
            None
            if run_context is None
            else (
                canonical_context_sha256(run_context)
                if run_context_sha256 is None
                else RunContextRef(run_context_sha256).sha256
            )
        )
        if (run_context is None) != (context_resolver is None):
            raise ValueError("Run context and resolver must be supplied together")
        if run_context is not None and context_directory is None:
            raise ValueError("Context-aware orchestration requires a context directory")
        configure_period_cancel = getattr(
            self.psm, "configure_period_boundary_cancellation", None
        )
        if callable(configure_period_cancel):
            configure_period_cancel(
                lambda year, period: request_period_boundary_cancel(
                    self.cancellation_check, year=year, period=period
                )
            )
        self._sequence = 0

    @staticmethod
    def _selection(run: ResolvedRun, slot: str) -> tuple[str, str]:
        try:
            selected = run.modules[slot]
        except KeyError as exc:
            raise ContractError(f"Resolved run is missing module slot {slot}") from exc
        return selected.module_id, selected.module_version

    def _verify(self, run: ResolvedRun, slot: str, module: object) -> None:
        selected_id, selected_version = self._selection(run, slot)
        actual_id = str(getattr(module, "id", ""))
        actual_version = str(getattr(module, "version", ""))
        if (actual_id, actual_version) != (selected_id, selected_version):
            raise ContractError(
                f"Selected {slot} is {selected_id}@{selected_version}, but implementation is "
                f"{actual_id or '<missing>'}@{actual_version or '<missing>'}"
            )

    def _record(
        self, run: ResolvedRun, year: int, stage: str, slot: str,
        module: object, input_value: object, output_value: object,
        duration_seconds: float,
    ) -> None:
        self._sequence += 1
        if self.event_sink:
            output_hash = contract_hash(output_value)
            artifacts = getattr(output_value, "artifacts", ())
            self.event_sink(StageEvent(
                self._sequence, run.run_id, year, stage, slot,
                str(getattr(module, "id")), str(getattr(module, "version")),
                run.modules[slot].contract_version,
                contract_hash(input_value), output_hash, output_hash,
                tuple(
                    str(getattr(artifact, "artifact_id"))
                    for artifact in artifacts
                    if getattr(artifact, "artifact_id", None)
                ),
                max(0.0, float(duration_seconds)),
            ))

    def validate_selection(self, run: ResolvedRun) -> None:
        self._verify(run, "pipeline", self.planning)
        self._verify(run, "psm", self.psm)
        for slot, policy in self.expansion_policies.items():
            self._verify(run, slot, policy)
        self._verify(run, "investment", self.investment)
        self._verify(run, "transition", self.transition)
        if self.network_expansion is not None:
            self._verify(run, "network_expansion", self.network_expansion)

    def run(self, run: ResolvedRun, initial_state: YearState) -> list[YearResult]:
        self.validate_selection(run)
        if initial_state.year < run.start_year or initial_state.year > run.end_year:
            raise InvariantError(
                f"Initial state year {initial_state.year} is outside runnable range "
                f"{run.start_year}-{run.end_year}"
            )
        state = initial_state
        # F-D1: the extension initialize step is the first link of the annual
        # state chain. It is recorded on the first executed year's result as
        # ``extension_initialize`` (source state -> initialized state) so the
        # run invariants verify source -> initialize -> annual input instead
        # of comparing the annual input with the pre-initialize source hash.
        extension_initialize: dict[str, object] | None = None
        if self.extension_runtime is not None:
            source_state_sha256 = contract_hash(state)
            self.extension_runtime.invoke(
                "preflight", {"run_id": run.run_id, "year": initial_state.year}
            )
            initialized = self.extension_runtime.invoke(
                "initialize", {"run_id": run.run_id, "year": initial_state.year}
            )
            extension_state = dict(state.extensions.get("extension_state") or {})
            manifests = {
                item.id: item for item in self.extension_runtime.graph.extensions
            }
            for output in initialized:
                owner = str(output.get("owner") or "")
                if owner not in manifests:
                    raise ContractError(f"Extension initialize returned unknown owner {owner}")
                extension_state[manifests[owner].namespace] = output
            state = replace(
                state,
                extensions={**dict(state.extensions), "extension_state": extension_state},
            )
            extension_initialize = {
                "schema_version": "value.extension-initialize-link/v1",
                "year": initial_state.year,
                "input_state_sha256": source_state_sha256,
                "output_state_sha256": contract_hash(state),
                "extension_ids": [item.id for item in self.extension_runtime.graph.extensions],
                "initialized_namespaces": sorted(
                    manifests[str(output.get("owner"))].namespace for output in initialized
                ),
            }
        results: list[YearResult] = []
        for year in range(initial_state.year, run.end_year + 1):
            if self.cancellation_check and self.cancellation_check(year, "before_year"):
                raise CancellationRequested(f"Cancellation accepted before model year {year}")
            if state.year != year:
                raise InvariantError(f"State year {state.year}; expected {year}")
            network_advance = None
            network_decision = None
            network_admission = None
            if self.network_expansion is not None:
                advance_input = state
                started = time.perf_counter()
                network_advance = self.network_expansion.advance_year(run, state)
                elapsed = time.perf_counter() - started
                if network_advance.year != year or network_advance.state.year != year:
                    raise ContractError("Network expansion advance returned the wrong year")
                state = network_advance.state
                self._record(
                    run, year, "network_expansion.advance_year", "network_expansion",
                    self.network_expansion, advance_input, network_advance, elapsed,
                )
            annual_input_state_sha256 = contract_hash(state)
            started = time.perf_counter()
            advanced = self.planning.advance_year(run, state)
            elapsed = time.perf_counter() - started
            if advanced.year != year or advanced.operating_state.year != year:
                raise InvariantError("Planning advance must return the current operating year")
            self._record(run, year, "planning.advance_year", "pipeline", self.planning, state, advanced, elapsed)

            if self.psm_input_factory is None:
                model_input = PSMInput(
                    run.run_id, year, run.data_pack_id, advanced.operating_state,
                    float(run.scientific_parameters["clock.period_hours"]), run.scientific_parameters,
                )
            else:
                model_input = self.psm_input_factory(run, advanced.operating_state)
                if model_input.run_id != run.run_id or model_input.year != year:
                    raise ContractError("PSM input factory returned the wrong run or year")
            annual_metadata: Mapping[str, object] = {}
            prepare_year_context = getattr(self.psm, "prepare_year_context", None)
            if callable(prepare_year_context):
                prepared = prepare_year_context(model_input)
                if (
                    not isinstance(prepared, tuple)
                    or len(prepared) != 2
                    or not isinstance(prepared[0], PSMInput)
                    or not isinstance(prepared[1], Mapping)
                ):
                    raise ContractError(
                        "PSM prepare_year_context must return (PSMInput, annual metadata)"
                    )
                model_input, annual_metadata = prepared
                if model_input.run_id != run.run_id or model_input.year != year:
                    raise ContractError("Prepared PSM input returned the wrong run or year")
            if self.run_context is not None:
                assert self.context_resolver is not None
                assert self.context_directory is not None
                year_context = build_year_context(
                    run_context=self.run_context,
                    model_input=model_input,
                    transition_lineage={
                        "annual_input_state_sha256": annual_input_state_sha256,
                        "planning_advance_sha256": contract_hash(advanced),
                        "commissioned_project_ids": [
                            project.project_id for project in advanced.commissioned_projects
                        ],
                        "active_project_ids": [
                            project.project_id for project in advanced.active_projects
                        ],
                    },
                    annual_metadata=annual_metadata,
                    run_context_sha256=self.run_context_sha256,
                )
                publish_year_context(
                    self.context_resolver,
                    self.run_context,
                    year_context,
                    self.context_directory,
                    run_context_sha256=self.run_context_sha256,
                )
                if self.year_start_recovery is not None:
                    self.year_start_recovery(year_context)
                start_year = getattr(self.psm, "start_year", None)
                if callable(start_year):
                    start_year(year_context)
            if self.extension_runtime is not None:
                self.extension_runtime.invoke(
                    "before_psm",
                    {"run_id": run.run_id, "year": year, "input_sha256": contract_hash(model_input)},
                )
            started = time.perf_counter()
            market = self.psm.run(model_input)
            elapsed = time.perf_counter() - started
            if market.year != year or market.module_id != self.psm.id:
                raise ContractError("PSM returned a result for the wrong year or module")
            doctoral_runtime = None
            if market.extensions.get("doctoral_alignment_profile") == "value.doctoral-national/v1":
                coverage = market.extensions.get("doctoral_cashflow_inputs", {}).get("period_coverage", {})
                if (coverage.get("annual_complete") is not True or coverage.get("period_count") != 17520
                        or coverage.get("start_period_index") != 0
                        or coverage.get("end_period_index_exclusive") != 17520
                        or coverage.get("year") != year):
                    raise ContractError("Doctoral annual lifecycle requires 17520 committed periods; diagnostic spans cannot invest")
                from ..builtin.scheme_c_1000twh.doctoral_market import _hash as doctoral_hash
                doctoral_runtime = market.extensions.get("doctoral_runtime")
                if (not isinstance(doctoral_runtime, Mapping)
                        or doctoral_hash(doctoral_runtime) != market.extensions.get("doctoral_runtime_sha256")):
                    raise ContractError("Doctoral annual runtime state identity is incomplete")
                if market.extensions.get("doctoral_annual_cem_ready") is not True:
                    raise ContractError("Doctoral annual CEM contract is unresolved; physical completion alone cannot authorize investment")
            if self.network_expansion is not None:
                network_costs = self.network_expansion.annual_resource_costs(
                    advanced.operating_state
                )
                network_resource_cost = float(
                    network_costs.get("annualized_capex_gbp", 0.0)
                    + network_costs.get("fixed_opex_gbp", 0.0)
                )
                market = replace(
                    market,
                    total_system_cost_gbp=market.total_system_cost_gbp + network_resource_cost,
                    total_levelized_capital_cost_gbp=(
                        market.total_levelized_capital_cost_gbp + network_resource_cost
                    ),
                    extensions={
                        **dict(market.extensions),
                        "network_resource_costs_gbp": dict(network_costs),
                        "informational_residual_value_gbp": float(
                            network_costs.get("retirement_residual_value_gbp", 0.0)
                        ),
                    },
                )
            if self.extension_runtime is not None:
                extension_artifacts = self.extension_runtime.invoke(
                    "after_psm",
                    {"run_id": run.run_id, "year": year, "input_sha256": contract_hash(model_input)},
                )
                if extension_artifacts:
                    market = replace(
                        market,
                        extensions={
                            **dict(market.extensions),
                            "extension_artifacts": list(extension_artifacts),
                        },
                    )
            self._record(run, year, "psm.run", "psm", self.psm, model_input, market, elapsed)

            if self.extension_runtime is not None:
                self.extension_runtime.invoke(
                    "before_cem",
                    {"run_id": run.run_id, "year": year, "market_sha256": contract_hash(market)},
                )
            headroom = []
            for slot in sorted(self.expansion_policies):
                policy = self.expansion_policies[slot]
                started = time.perf_counter()
                value = policy.evaluate(run, advanced.operating_state, market)
                elapsed = time.perf_counter() - started
                if value.year != year or value.module_id != policy.id:
                    raise ContractError(f"Expansion policy {policy.id} returned incompatible headroom")
                headroom.append(value)
                self._record(run, year, "expansion.evaluate", slot, policy, market, value, elapsed)

            started = time.perf_counter()
            investment_market = adapt_market_for_investment(
                market, advanced.operating_state
            )
            decision = self.investment.decide(
                run, advanced.operating_state, investment_market, tuple(headroom)
            )
            decision = inherit_frozen_zone_shares(decision, advanced.operating_state)
            elapsed = time.perf_counter() - started
            if decision.year != year or decision.module_id != self.investment.id:
                raise ContractError("Investment module returned an incompatible decision")
            self._record(
                run, year, "investment.decide", "investment", self.investment,
                {"market": investment_market.to_dict(), "headroom": [item.to_dict() for item in headroom]}, decision, elapsed,
            )

            started = time.perf_counter()
            admission = self.planning.admit_projects(run, advanced.operating_state, decision.proposals)
            elapsed = time.perf_counter() - started
            if admission.year != year:
                raise ContractError("Planning admission returned the wrong year")
            self._record(run, year, "planning.admit_projects", "pipeline", self.planning, decision, admission, elapsed)
            if self.network_expansion is not None:
                started = time.perf_counter()
                network_decision = self.network_expansion.propose(
                    run, advanced.operating_state, market
                )
                elapsed = time.perf_counter() - started
                if network_decision.year != year or network_decision.module_id != self.network_expansion.id:
                    raise ContractError("Network expansion decision returned the wrong year/module")
                self._record(
                    run, year, "network_expansion.propose", "network_expansion",
                    self.network_expansion, market, network_decision, elapsed,
                )
                started = time.perf_counter()
                network_admission = self.network_expansion.admit(
                    run, advanced.operating_state, network_decision
                )
                elapsed = time.perf_counter() - started
                if network_admission.year != year:
                    raise ContractError("Network expansion admission returned the wrong year")
                self._record(
                    run, year, "network_expansion.admit", "network_expansion",
                    self.network_expansion, network_decision, network_admission, elapsed,
                )
            if self.extension_runtime is not None:
                self.extension_runtime.invoke(
                    "after_cem",
                    {"run_id": run.run_id, "year": year, "decision_sha256": contract_hash(decision)},
                )

            started = time.perf_counter()
            transition_extensions = {
                **dict(state.extensions),
                **dict(advanced.operating_state.extensions),
                "storage_cost_observations": dict(
                    market.extensions.get("storage_cost_observations")
                    or advanced.operating_state.extensions.get("storage_cost_observations")
                    or state.extensions.get("storage_cost_observations")
                    or {}
                ),
            }
            if doctoral_runtime is not None:
                transition_extensions.update({"doctoral_runtime": doctoral_runtime,
                    "doctoral_runtime_sha256": market.extensions["doctoral_runtime_sha256"]})
            solver_validation_summary = market.extensions.get(
                "solver_validation_summary"
            )
            if isinstance(solver_validation_summary, Mapping):
                transition_extensions["solver_validation_state"] = dict(
                    solver_validation_summary
                )
            transition_state = YearState(
                year,
                advanced.operating_state.assets,
                advanced.active_projects,
                cumulative_metrics=state.cumulative_metrics,
                extensions=transition_extensions,
            )
            next_state = self.transition.apply(run, transition_state, admission, decision)
            elapsed = time.perf_counter() - started
            if next_state.year != year + 1:
                raise InvariantError("State transition must advance exactly one year")
            if any(asset.capacity_mw < 0 for asset in next_state.assets):
                raise InvariantError("State transition produced negative operating capacity")
            if self.network_expansion is not None:
                next_state = self.network_expansion.transition(
                    run, next_state, network_admission
                )
            if self.extension_runtime is not None:
                self.extension_runtime.invoke(
                    "transition",
                    {"run_id": run.run_id, "year": year, "state_sha256": contract_hash(next_state)},
                )
            self._record(run, year, "state_transition.apply", "transition", self.transition, state, next_state, elapsed)
            year_extensions: dict[str, object] = {
                "annual_input_state_sha256": annual_input_state_sha256,
            }
            if extension_initialize is not None and year == initial_state.year:
                year_extensions["extension_initialize"] = dict(extension_initialize)
            if self.network_expansion is not None:
                year_extensions["network_expansion"] = {
                    "advance": network_advance.to_dict(),
                    "decision": network_decision.to_dict(),
                    "admission": network_admission.to_dict(),
                }
            year_result = YearResult(
                f"{run.run_id}:{year}", year, advanced, market, tuple(headroom),
                decision, admission, next_state,
                extensions=year_extensions,
            )
            # The report is durable before the state checkpoint becomes the
            # resume boundary. A cancellation accepted after this pair can
            # therefore reproduce the uninterrupted annual result set.
            if self.year_result_sink:
                self.year_result_sink(year_result)
            if self.checkpoint:
                self.checkpoint(next_state)
            results.append(year_result)
            state = next_state
            if self.cancellation_check and self.cancellation_check(year, "after_annual_checkpoint"):
                raise CancellationRequested(f"Cancellation accepted after verified model year {year}")
        if self.extension_runtime is not None:
            self.extension_runtime.invoke(
                "finalize",
                {"run_id": run.run_id, "year": state.year, "results_sha256": canonical_hash([item.to_dict() for item in results])},
            )
        return results


def checkpoint_identity(run: ResolvedRun) -> dict[str, object]:
    result = {
        "run_id": run.run_id,
        "project_id": run.project_id,
        "project_revision_sha256": run.extensions.get("project_revision_sha256"),
        "data_pack_id": run.data_pack_id,
        "years": [run.start_year, run.end_year],
        "modules": {
            slot: {
                "module_id": selected.module_id,
                "module_version": selected.module_version,
                "contract_version": selected.contract_version,
            }
            for slot, selected in sorted(run.modules.items())
        },
        "scientific_parameters_sha256": contract_hash(dict(run.scientific_parameters)),
    }
    if run.extensions.get("execution_bundle"):
        result["execution_bundle"] = dict(run.extensions["execution_bundle"])
    extension_graph = run.extensions.get("extension_graph")
    if extension_graph:
        result["extension_graph"] = extension_graph
    if run.extensions.get("dispatch_weather_identity"):
        result["dispatch_weather_identity"] = dict(run.extensions["dispatch_weather_identity"])
    return result


def load_json_checkpoint(path: Path, run: ResolvedRun) -> YearState:
    """Load an atomic checkpoint only when state and research identity match."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "value.annual-checkpoint/v1":
        raise ContractError("Checkpoint schema is not supported")
    expected_identity = checkpoint_identity(run)
    if payload.get("identity") != expected_identity:
        raise ContractError("Checkpoint project, data, parameter or module identity does not match")
    state = YearState.from_dict(payload["state"])
    if payload.get("state_sha256") != contract_hash(state):
        raise ContractError("Checkpoint state SHA-256 does not match its content")
    return state


def json_checkpoint_writer(
    directory: Path,
    run: ResolvedRun | None = None,
    *,
    on_verified: Callable[[YearState, str], None] | None = None,
) -> Callable[[YearState], None]:
    directory.mkdir(parents=True, exist_ok=True)
    if on_verified is not None and run is None:
        raise ValueError("Verified annual checkpoint callbacks require a resolved run")

    def write(state: YearState) -> None:
        path = directory / f"state-{state.year}.json"
        temporary = path.with_suffix(".json.tmp")
        payload: object = state.to_dict()
        if run is not None:
            payload = {
                "schema_version": "value.annual-checkpoint/v1",
                "identity": checkpoint_identity(run),
                "state_sha256": contract_hash(state),
                "state": state.to_dict(),
                "contains": {
                    "operating_assets": len(state.assets),
                    "planning_projects": len(state.planning_projects),
                    "storage_cost_policy": run.modules.get("storage_cost").module_id if run.modules.get("storage_cost") else None,
                    "storage_cost_observations": state.extensions.get("storage_cost_observations", {}),
                },
            }
        temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)
        if run is not None:
            reloaded = load_json_checkpoint(path, run)
            if reloaded != state:
                raise ContractError(
                    "Reloaded annual checkpoint differs from the written state"
                )
            if on_verified is not None:
                on_verified(
                    state,
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                )

    return write
