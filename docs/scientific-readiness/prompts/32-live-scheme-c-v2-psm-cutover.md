# Prompt 32 — Live Scheme C v2 PSM cutover; replay becomes reference-only

Continue only after Prompts 29-31 are accepted. Read visibility Prompts 06 and 10
and scientific Prompts 12 and 17B in full. Treat Prompt 12 as an incomplete
cutover whose stop condition left the compatibility path enabled. Act jointly as
a power-system modeller and production runtime architect.

## Objective

Make `AnnualModelOrchestratorV2` call the actual project-selected Scheme C market
clearing implementation for each model year and receive a typed
`MarketYearResult` directly. Remove whole-kernel-then-replay execution from the
website, CLI and backend worker while retaining it as an explicitly labelled
reference-comparison tool.

## Non-duplication boundary

- Reuse contracts v2, canonical data adapters, market ledger, storage-cost
  policies, planning ledger, cost/carbon ledgers and state transition. Do not
  recreate them inside a new PSM wrapper.
- Reuse the actual Scheme C bid-at-cost, day-ahead/balancing, VRE, import, thermal
  and storage functions through narrow adapters. Do not substitute the simplified
  demo PSM or the perfect-foresight LP.
- The perfect-foresight PSM remains a separate selectable counterfactual.
- Preserve the retained reference runner and its hashes. Reference parity and
  native architecture correctness remain separate decisions.

## Implement

1. Produce a field-level map from the compatibility clearing state and outputs to
   `PSMInput`, `PeriodSummary`, `MarketYearResult`, market ledger rows and the
   operating state consumed by downstream CEM modules. Resolve MW versus
   MWh/period, SOC, storage efficiencies, import signs, curtailment and blackout
   explicitly.
2. Implement one canonical live `SchemeCNativePSM` registered as the executable
   `scheme-c-psm`. Its `run(PSMInput)` must perform clearing for that year and
   return the typed result; it must not read annual CSV results or
   `SchemeCReplayData`.
3. Move annual ownership to `AnnualModelOrchestratorV2`:
   `planning.advance_year -> live PSM -> expansion policies -> investment ->
   planning.admit_projects -> transition`. Ensure the next year's PSM receives
   the commissioned/retired fleet and storage state produced by the prior year.
4. Invoke storage-cost policy through its declared capability in the live market.
   Keep battery cycle depreciation, pumped-hydro exclusion, dwell recovery and
   user-formula semantics unchanged.
5. Move the current whole `run_modular_scheme_c -> SchemeCReplayData` path behind
   an explicit `scheme-c-reference-comparison` command/service that cannot be
   selected as a production PSM and labels every artifact
   `reference_compatibility`.
6. Remove production imports, construction and binding of `SchemeCReplayData`.
   Enforce this with a source scan whose only allowlist is the reference package
   and comparison tests.
7. Ensure stage progress, cancellation, checkpoints and output artifacts are
   emitted during live orchestration, not reconstructed after an entire
   compatibility run has finished.

## Tests and acceptance

- A spy around the actual clearing function proves one live PSM invocation per
  model year from the backend application's v2 orchestrator.
- Two-period tests cover thermal, VRE, boundary imports, storage charge/discharge,
  SOC, curtailment, balancing and blackout with ledger reconciliation.
- One full year and full 2025-2026 transition compare stage by stage with the
  preserved reference path. Report the first divergent period, asset and equation;
  never weaken a tolerance without scientific justification.
- Replace every downstream CEM slot one at a time with the accepted external
  fixtures from Prompt 31 and prove the live PSM output reaches them.
- Cancellation before a year and at declared within-year safe boundaries produces
  no fabricated replay result. Resume uses the frozen context and verified state.
- Prompt 17B's FORCE gate invokes this live public PSM, captures the offers and
  pre-period SOC it actually saw, and cannot pass using a replay/private helper.
- Retained-source hashes pass.

## Stop condition

If stage parity is not understood, keep the reference compatibility route for
research comparison and return `NATIVE_SCHEME_C_CUTOVER_NO_GO`. Do not reintroduce
replay into the production application to obtain a green test.

## Deliverable

Provide old/reference and new/live call graphs, the field/unit map, invocation
proof, parity report, cancellation/checkpoint evidence, replay source scan,
independent-validation status and explicit cutover decision.
