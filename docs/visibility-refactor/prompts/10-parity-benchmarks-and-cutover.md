# Prompt 10 — Final parity, model benchmarks and production cutover

Continue only after Prompts 01-09 are accepted. Act as the release owner. Do not
add new model features in this task.

## Objective

Prove that the typed production path preserves the accepted Scheme C result, make
the old annual entry point reference-only, update documentation and produce a clear
release decision.

## Mandatory constraints

- Never change retained fixtures to make a test pass.
- Never weaken tolerances without a numerical justification and owner approval.
- Architecture parity and scientific parity are separate gates.
- Do not delete historical runs or the reference comparison path.

## Work

1. Build a stage-level comparison harness between old modular reference execution
   and v2 execution for:
   - beginning fleet/pipeline;
   - PSM annual summary;
   - VRE/storage expansion headroom;
   - agent incomes/costs/recommendations;
   - admitted/failed/commissioned projects;
   - next-year fleet and pipeline.
2. Run and record:
   - contract/unit suite;
   - frontend build/render suite;
   - two-period wiring run;
   - one full year;
   - full 2025-2026 transition;
   - retained numerical comparison.
3. Add a small convex bid-at-cost benchmark that can later be compared with PyPSA
   economic dispatch. This task may define/export the fixture and expected balance;
   do not add PyPSA as a mandatory dependency unless explicitly approved.
4. Verify pipeline reconciliation and market energy-balance invariants across the
   two-year run.
5. Record trace performance for off/summary/full and API payload bounds.
6. Remove normal API/website references to the legacy orchestration entry point.
   Keep a clearly named reference-comparison command.
7. Update README and architecture documentation to describe only the real executed
   lifecycle, fixed assumptions, advanced parameters, artifacts and extension API.
8. Add a migration note for existing v1 projects/runs and state that old runs remain
   immutable.
9. Produce a release report listing exact matches, tolerated floating differences,
   known limitations and any intentionally deferred item.

## Tests

- Run the complete unit, integration and frontend suites from a clean process.
- Execute the two-period, one-year and 2025-2026 transition fixtures.
- Assert stage-by-stage numerical parity, pipeline reconciliation and period energy
  balance before evaluating the release gate.
- Benchmark trace `off`, `summary` and `full`, and record both runtime overhead and
  artifact size.

## Release decision

Return one of:

- `GO`: all mandatory gates pass and website uses v2 only;
- `NO-GO`: list the first divergent stage, evidence and safest next action.

Do not report partial execution as a successful release.

## Deliverable

Provide test commands/results, two-year comparison, performance measurements,
documentation links, legacy containment proof and the final GO/NO-GO decision.
