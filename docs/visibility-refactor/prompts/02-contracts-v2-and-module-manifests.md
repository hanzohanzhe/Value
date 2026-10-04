# Prompt 02 — Contracts v2 and executable module manifests

Continue from an accepted Prompt 01 result. Read the architecture plan and the
baseline audit. Act as the contract owner for an open scientific modelling SDK.

## Objective

Define the versioned public contracts and make the executable registry and UI
catalog derive from the same module manifests. Do not switch the production runner
yet and do not change numerical behavior.

## Mandatory constraints

- Retained Scheme C files and imported data packs remain byte-identical.
- Keep v1 readable for existing saved projects/runs; add explicit migration or
  compatibility parsing rather than silently reinterpreting v1.
- Do not use `Callable[..., Any]`, `*args` or `**kwargs` at a public module boundary.
- Core contract fields must be typed and named. Extension metadata must live in an
  explicit namespace.

## Work

1. Define v2 Python contracts for:
   `ResolvedRun`, `YearState`, `OperatingState`, `PlanningProject`,
   `PlanningEvent`, `PlanningAdvanceResult`, `PSMInput`, `MarketYearResult`,
   `PeriodSummary`, `ExpansionHeadroom`, `InvestmentProposal`,
   `InvestmentDecision`, `PlanningAdmissionResult`, `YearResult` and
   `ArtifactReference`.
2. Define protocols for:
   - `PSMEngine.run`;
   - `ExpansionPolicy.evaluate`;
   - `InvestmentModule.decide`;
   - `PlanningPipeline.advance_year` and `admit_projects`;
   - `StateTransition.apply`.
3. Include schema version, year, units and stable IDs in the appropriate contracts.
4. Mirror the public serializable contracts in TypeScript without maintaining a
   contradictory hand-written role list.
5. Introduce `gridform.module/v2` manifests with ID, semantic version, slot,
   implementation entry point, contract version, I/O roles, parameters, state
   reads/writes, determinism and artifact declarations.
6. Build the registry from manifests. Make API catalog output come from resolved
   registrations, not a second hard-coded module-to-slot dictionary.
7. Validate duplicate IDs, wrong slots, unsupported contract versions, missing
   implementation entry points and incompatible module capabilities.
8. Add JSON serialization/deserialization tests and v1 project migration tests.

## Tests

- Contract round-trip tests.
- Module manifest schema tests.
- Registry resolution tests for valid, missing, duplicate and wrong-slot modules.
- Existing v1 project validation tests.
- Frontend TypeScript/build test if generated types are changed.
- Retained-source hash test.

## Deliverable

Explain the exact v2 lifecycle encoded by the types, how old projects are handled,
and prove there is one source of truth for registry and catalog metadata. Do not
route production execution through v2 yet.
