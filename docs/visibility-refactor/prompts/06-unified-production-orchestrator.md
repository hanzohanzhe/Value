# Prompt 06 — Make the typed orchestrator the only production path

Continue from accepted Prompts 01-05. This is the architectural cutover task. Act
as a senior application and modelling architect.

## Objective

Make website, CLI and tests execute `AnnualModelOrchestratorV2` with registered
typed modules. Preserve Scheme C numerical behavior through adapters. Remove
production orchestration responsibility from `modular_case3.main()`.

## Mandatory constraints

- Never edit retained reference files.
- Do not replace Scheme C science with the simplified v1 demo implementations.
- Do not silently fall back to the old runner if a v2 module fails.
- Caps must be computed before the investment recommendation they constrain.
- Pipeline commissioning must occur before the current year's PSM; new proposals
  enter the pipeline after investment.
- A module selected in the project must be the exact implementation called.

## Work

1. Implement the lifecycle specified in the architecture plan:
   `planning.advance_year -> PSM -> expansion policies -> investment ->
   planning.admit_projects -> state transition`.
2. Extract or wrap the actual copied Scheme C stage behavior into typed v2 module
   classes. Reuse existing functions through narrow adapters; do not call a whole
   annual script as one module.
3. Make `PlanningPipeline` a two-phase module and record both phase invocations.
4. Make expansion headroom a named input to investment decisions.
5. Introduce an application service used by backend runner and a CLI entry point.
6. Change `backend/model_runner.py` to build a `ResolvedRun`, resolve manifests and
   call that application service.
7. Keep the old modular runner callable only from explicit reference-comparison
   tests/commands. Label its results legacy/reference; remove it from normal API run
   selection.
8. Ensure progress events and checkpoints come from the orchestrator, not from
   parsing console strings.
9. Verify module IDs, versions and state hashes in every stage event.
10. Update the UI lifecycle wording only enough to avoid a known false sequence;
    full frontend work belongs to Prompt 08.

## Tests

- A spy/fake module in every slot proves website/application execution reaches the
  selected implementation and data flows to the next stage.
- Wrong-slot and incompatible-contract modules fail before running.
- Call-order test including both planning phases.
- State-year and capacity transition invariants.
- Two-period wiring test.
- One-year numerical comparison against the previous modular path.
- Full 2025-2026 comparison including investment, planning and 2026 starting state.
- Retained-source hash test.

## Stop condition

If exact parity cannot be achieved, do not weaken tolerances or alter fixtures.
Produce a field-level comparison identifying the first divergent stage and leave
the old website runner in place. The prompt is incomplete until the divergence is
understood.

## Deliverable

Show the new real call graph, proof that selected modules execute, old-path
containment, stage-by-stage parity and remaining legacy adapter boundaries.
