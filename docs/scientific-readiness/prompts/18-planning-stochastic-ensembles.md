# Prompt 18 — Planning-success semantics and reproducible stochastic ensembles

Continue from accepted Prompt 17. Read planning Prompt 07, the parameter registry
and all expected/stochastic success code. Act as a CEM uncertainty modeller.

Apply the preservation boundary in `docs/scientific-readiness/README.md`: never
edit retained Scheme C sources, fixtures, the installed data pack or historical
run bundles.

## Objective

Make expected-capacity and seeded stochastic planning scientifically distinct, and
provide a reproducible ensemble workflow for stochastic policy conclusions.

## Non-duplication boundary

- Reuse the project/event causal ledger and existing success calculations.
- Do not reinterpret expected fractional capacity as observed project success.
- Do not change the accepted planning probability formula in this task.

## Implement

1. Define explicit modes:
   - `expected_capacity`, which probability-weights capacity and has no realised
     pass/fail event count;
   - `seeded_stochastic`, which realises project outcomes and records RNG evidence.
2. Correct summaries and UI so `failed projects` is `not_applicable` in expected
   mode unless it refers to a different deterministic exclusion. Never display
   zero realised failures as evidence that all projects succeeded.
3. Add an immutable ensemble specification with base project revision, mode,
   master seed, deterministic child-seed derivation, number of replications and
   selected outputs. Each child is a normal run bundle linked to the ensemble.
4. Add bounded parallel/sequential orchestration that respects disk/runtime
   preflight and never shares mutable RNG or pipeline state across children.
5. Aggregate annual distributions for capacity, commissioning/failure, pipeline,
   cost, emissions, curtailment, unmet demand and storage outcomes. Report sample
   count, quantiles/confidence intervals and missing/failed child runs.
6. Keep raw child evidence queryable on demand; normal ensemble payloads contain
   only bounded summaries.
7. Materialize a versioned, queryable planning-project database from the accepted
   causal ledger. Store immutable run/project/year keys, source project ID,
   technology, region/location, MW/MWh, stage, admission year, expected completion,
   selected success mode/probability, realised draw/outcome where applicable,
   failure/deferment reason and latest status. This is an index over evidence, not
   a second planning state machine.
8. Report planning success correctly by technology, stage and region:
   `expected_capacity` reports probability-weighted MW and mean declared
   probability; `seeded_stochastic` may report realised project-count and MW
   success rates with numerator, denominator and replication count. Never mix
   deterministic exclusions with stochastic planning failures.

## Tests and acceptance

- Same ensemble specification yields the same child seeds and results.
- Changing master seed changes realised outcomes but not model/data revisions.
- Expected mode conserves probability-weighted MW and exposes no fabricated
  realised failure KPI.
- Seeded fixtures converge toward the expected-capacity result within a statistical
  tolerance as replications increase.
- Failed/interrupted children are explicit and excluded according to a declared
  aggregation rule, never silently dropped.
- Project-database totals reconcile exactly to ledger events and terminal pipeline
  stock. Database rebuild is deterministic and cannot alter run evidence.

## Stop condition

Do not make a planning-risk claim from one stochastic seed. If the ensemble is too
small for a requested interval, label it exploratory and report the sample limit.

## Deliverable

Provide mode definitions, seed derivation, ensemble schema, aggregation rules,
fixture convergence evidence and corrected UI wording.
