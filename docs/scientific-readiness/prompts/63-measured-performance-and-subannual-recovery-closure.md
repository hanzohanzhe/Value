# Prompt 63 — Measured performance and subannual recovery closure

Execute after Prompt 59 establishes the canonical Git base. Read Prompts 09,
10, 22, 46, 52 and their accepted evidence before changing code. Preserve the
retained Scheme C hashes, historical run bundles, scientific equations and
annual result definitions. Act as a scientific-performance engineer and
recovery-systems architect.

## Objective

Close the two operational limitations still recorded for long FORCE runs:

1. later model years use materially more time and memory than early years, but
   the dominant cause is not yet isolated; and
2. a native run can resume safely between years, but a failure late within a
   17,520-period year may still require that whole year to be repeated.

Optimize only measured hot paths. Add a subannual recovery boundary only when
all causal state needed to continue the selected PSM/CEM chain can be serialized
and proven equivalent. Do not change model behaviour merely to make it faster.

## Non-duplication boundary

- Reuse the existing stage timers, run lifecycle, annual atomic checkpoint,
  source-bound resume validation, quotas and artifact index from Prompts 10 and
  22. Do not create a second worker, run state machine or checkpoint catalogue.
- Reuse Prompt 52 traces and completed annual/ten-year bundles as immutable
  profiling evidence. Do not rerun both decade scenarios to establish a
  packaging or profiling claim.
- Do not aggregate, round, reorder or omit scientific calculations unless a
  numerical-equivalence gate proves the change is observationally identical.
- Keep market-ledger detail governed by its existing bounded/full export modes.
  A performance change must not silently reduce the declared audit level.

## Implement

1. Add a reproducible profiling command that reports wall time, CPU time, peak
   resident memory, artifact bytes and record counts by year and by stage:
   input materialization, PSM, market artifacts, investment, caps, planning,
   transition, ledgers, checkpoint and bundle validation.
2. Use existing Prompt 52 runs first. Attribute later-year growth to concrete
   quantities such as operating assets, planning projects, market rows, database
   indexes, Python objects or repeated adapter work. Report `UNKNOWN` where the
   evidence cannot distinguish causes; do not infer a bottleneck from elapsed
   time alone.
3. Establish bounded budgets for a supported local reference machine, expressed
   as measured baselines and warning thresholds rather than universal promises.
   Preflight should estimate likely disk and memory pressure from years, periods,
   asset/project counts and selected audit level.
4. Correct only demonstrated algorithmic or I/O hot paths. Prefer streaming,
   batched SQLite transactions, prepared indexes, immutable-data caching and
   removal of repeated canonicalization. Preserve deterministic ordering and
   exact identifiers.
5. Define `force.subannual-checkpoint/v1` as an optional extension of the
   existing checkpoint lineage. A checkpoint must include the last committed
   period, chronological storage/SOC state, agent observations needed by later
   bids, market and ledger writer offsets, random-generator states where used,
   frozen input/module hashes, and the owning annual checkpoint identity.
6. Commit a subannual checkpoint only at a declared safe chunk boundary after
   all writers for the preceding chunk are durable. Resume into a staging output,
   reject source/input/module/schema mismatch, and atomically replace only the
   incomplete suffix. Never append duplicate periods to SQLite or JSON indexes.
7. If the selected implementation has hidden state that cannot be represented,
   expose `subannual_resume_supported=false`, retain annual recovery, and report
   the exact state gap. Do not advertise or simulate a resumable checkpoint.
8. Expose concise UI/API estimates, latest safe recovery point and recovery
   capability. Keep profiling details in downloadable evidence, not the main
   results cards.

## Tests and acceptance

1. Profile the same deterministic 24-hour, 168-hour and representative complete
   annual workloads before and after each accepted optimization.
2. Compare pre/post scientific artifacts: energy, dispatch, SOC, bids, costs,
   carbon, investment, planning, transitions and annual results must match under
   their existing exact-hash or documented numerical tolerances.
3. Interrupt before, during and after a chunk commit. Resume must match an
   uninterrupted run, contain every period exactly once and retain valid
   provenance and bundle hashes.
4. Corrupt the chunk state, writer offset, module hash, input hash and parent
   checkpoint identity; each mutation must fail closed without altering the
   accepted prefix.
5. Cancellation, quotas, archive/export/import and annual resume tests from
   Prompt 22 must continue to pass.
6. Publish before/after time, memory and bytes by stage. A claimed improvement
   requires repeatable evidence; a regression above the declared tolerance must
   be explained or reverted.
7. Classify the change impact. Run a new full year only if production execution
   code changed. Run the causal two-year gate only if checkpoint/resume or annual
   transition state changed. Do not run a decade unless multi-year science changed.

## Stop conditions

Stop and retain annual-only recovery if a chunk checkpoint cannot encode all
causal state, if resume changes any scientific result, or if the only apparent
speed-up comes from dropping audit data or weakening validation. Record the
bounded beta limitation instead of forcing a green result.

## Deliverables

- reproducible stage/year profiler and machine-readable performance baseline;
- measured bottleneck analysis and only evidence-backed optimizations;
- optional safe `force.subannual-checkpoint/v1` implementation or an explicit
  unsupported-capability report;
- interruption, corruption, identity and numerical-equivalence tests;
- human- and machine-readable Prompt 63 report with release recommendation.
