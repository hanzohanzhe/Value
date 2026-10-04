# Prompt 121 — atomic VALUE failure evidence and annual recovery

## Scope

Prompt 121 changes failure, cancellation and recovery plumbing only for the
staged bid-at-cost plus balancing/zonal path. It does not alter offers, the
four-phase zonal optimisation, solver settings, dispatch, settlement, storage
SOC, curtailment, CEM or annual transition science. A zonal failure never
produces a copperplate or alternative-solver result.

## First-failure bundle

Every `off`, `summary` and `full` run publishes the same mandatory evidence at
`market/failures/first-failure/`. The directory contains:

- `run-context.json` and `year-context.json`;
- the complete current `period-input.json`, including bids;
- `solver.json`, including method, settings, stack/binary identity and
  completed phases;
- `residuals.json`;
- `error.json`, including stage, exception identity, raw diagnostics and
  `fallback_used=false`;
- `manifest.json`, written last with every member SHA-256 and byte count.

Members are written and synced in a unique sibling temporary directory. The
complete directory is published with a non-overwriting atomic rename. If a
canonical bundle already exists, it is verified and returned unchanged, so
the first failure wins concurrent and secondary-failure races. Publication
errors remove the temporary directory, leave no partial canonical bundle and
raise `FailureBundlePublicationError` with both publication and original
solver diagnostics available to the caller.

## Period-boundary cancellation

The annual orchestrator passes its existing cancellation callback to the
staged PSM. The PSM calls it only after `record_period_batch` has returned,
which means every common row, trace row and integrity row for the current
period has committed. A cancellation then closes the unsealed ledger without
calling annual `seal_year`; committed periods remain present and the current
`year_integrity.complete` remains zero. No second cancellation subsystem is
introduced.

The run status records `after_committed_period`, marks the current model year
incomplete and declares `prior_annual_checkpoint` plus
`recompute_full_incomplete_year` as the only resume mode.

## Annual-only recovery

Application recovery is fail closed and requires all of the following:

1. the status belongs to the exact run and carries the Prompt 121 cancellation
   boundary, incomplete-year flag and annual recompute mode;
2. the latest verified annual checkpoint points to the target model year;
3. the frozen `year-YYYY.json` belongs to that run/year and its parent run
   context hash matches;
4. its `annual_input_state_sha256` equals the checkpoint state hash;
5. the v8 `year_integrity` and `context_registry` rows carry the same opening
   YearContext hash and `complete=0`.

The orchestrator rebuilds the opening YearContext and passes the existing
atomic context-publication equality check before recovery runs. Recovery uses
SQLite backup to retain the interrupted ledger under `market/recovery/`,
cleans a sibling copy in one `BEGIN IMMEDIATE` transaction with predicates for
the single incomplete year, and atomically replaces the canonical database.
Clearing outcomes are removed only through that year's declared clearing
inputs. Completed years, their context files, roots and annual checkpoints are
not selected or rewritten. The resumed staged PSM then appends from period
zero and recomputes the complete year; no subannual state is accepted.

## Focused evidence

The Prompt121 test first failed because the period-boundary commit wrapper and
central failure module did not exist. The final focused test covers all three
trace profiles, first-wins concurrency and secondary failure, publication
failure cleanup, cancellation after the second committed period, application
status/context/checkpoint authorization, wrong opening-hash refusal, scoped
incomplete-year cleanup with retained diagnostic database, and full-year
recomputation while the completed prior-year integrity row remains identical.

No full suite, annual run or ten-year run belongs to this Prompt.
