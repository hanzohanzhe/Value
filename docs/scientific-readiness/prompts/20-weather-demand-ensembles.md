# Prompt 20 — Weather-year and demand-path ensembles

Continue from accepted Prompt 19. Read the canonical weather/demand adapter roles,
clock assumptions and ensemble infrastructure from Prompt 18. Act as a power-
system adequacy and scenario-design modeller.

Apply the preservation boundary in `docs/scientific-readiness/README.md`: never
edit retained Scheme C sources, fixtures, the installed data pack or historical
run bundles.

## Objective

Replace single-path weather and demand evidence with reproducible, declared
multi-year/scenario experiments while preserving each selected profile exactly.

## Non-duplication boundary

- Do not change the PSM clearing equation or planning-success RNG.
- Reuse immutable project revisions, data snapshots and ensemble aggregation.
- Do not synthetically label averaged weather as a historical year.

## Implement

1. Define canonical scenario dimensions for weather realization, demand path and
   optional climate transformation. Each member must carry source revision,
   historical/model year, timezone, interval, transformation and uncertainty type.
2. Add deterministic clock mapping for 17,520 half-hours, leap years and DST. A
   resampling or calendar substitution must be explicit and energy-conserving.
3. Allow one project specification to generate a bounded experiment design across
   selected weather years and demand paths. Support full factorial and an explicit
   reduced design; never silently omit combinations.
4. Prevent future information leakage: a CEM year may use only the weather/demand
   information allowed by the declared experiment design.
5. Aggregate dispatch, adequacy, cost, emissions, curtailment, storage utilization,
   investment and pipeline distributions. Keep weather/demand variation separate
   from planning RNG before presenting a combined uncertainty summary.
6. Add coverage diagnostics for extremes, annual energy, peak demand, VRE capacity
   factor and correlation structure. Flag an ensemble that is too narrow for a
   robustness claim.
7. Publish three separate rates with explicit numerators and denominators:
   `execution_completion_rate` for successfully completed design members;
   `adequacy_success_rate` for members meeting a project-selected adequacy
   criterion such as zero blackout or a declared LOLE/EENS threshold; and planning
   success statistics supplied by Prompt 18. Never call weather or demand itself
   a success/failure event and never merge failed computations with inadequate
   power-system outcomes.
8. Join bounded ensemble summaries to the planning-project database by immutable
   child run ID so users can inspect how weather/demand members affect investment,
   commissioning and remaining pipeline without duplicating project rows.

## Tests and acceptance

- Energy-conserving clock tests cover leap day, DST and missing/duplicate periods.
- Two weather years with distinct profiles produce fingerprint-distinct child runs
  through the actual PSM contract.
- Re-running the same design yields identical membership and outputs.
- Aggregation preserves scenario weights and reports failed/missing members.
- Averages and quantiles can be recomputed from child artifacts within tolerance.
- Completion, adequacy and planning-success rates remain distinct when a member
  fails to execute or violates the adequacy criterion.

## Stop condition

Do not report a probabilistic confidence interval unless scenario weights have a
defensible probability interpretation. Otherwise report empirical ranges and
quantiles with that limitation.

## Deliverable

Provide scenario schemas, calendar rules, experiment-design manifest, coverage
diagnostics, aggregation evidence and scientific limitations.
