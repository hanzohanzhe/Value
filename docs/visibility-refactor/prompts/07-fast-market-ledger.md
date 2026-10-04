# Prompt 07 — Fast, queryable period-level market ledger

Continue from an accepted Prompt 06 cutover. Act as a performance-conscious data
engineer embedded in a market-simulation team.

## Objective

Persist period summaries by default and optional full bid/dispatch evidence with
measured low overhead. SQLite is the primary artifact; JSON is paginated API or
explicit export only.

## Mandatory constraints

- Do not perform per-order JSON serialization, pandas construction, file open/close
  or console logging inside the clearing hot loop.
- Disabled tracing must be near-zero overhead through a null writer.
- Do not mix physical resource cost, market payment and policy transfer fields.
- The ledger must not alter order sorting, clearing or numerical results.

## Work

1. Define `MarketLedger` protocol with null, summary and full implementations.
2. Implement one SQLite writer per run with prepared batched inserts and explicit
   schema version.
3. Add `period_summary`, `orders` and `storage_state` tables described in the
   architecture plan, plus indexes optimized for year/period/stage/asset queries.
4. Instrument the named Scheme C market boundary so each period summary is emitted.
   Full mode records offered, accepted and rejected orders with reason codes.
5. Calculate and assert the period energy-balance residual from named quantities.
6. Store artifact metadata, row counts, byte size, write time and selected trace
   level in the annual result/provenance.
7. Add paginated read services with filters. Keep them independent from HTTP so
   they can be tested directly.
8. Add an explicit streaming/export function for JSONL or CSV when requested; never
   create it automatically during a normal run.
9. Benchmark `off`, `summary` and `full` on the same deterministic fixture. Record
   wall time, writer time, rows and bytes. Optimize measured bottlenecks only.

## Tests

- Ledger schema and migration/version tests.
- Order and period round-trip tests.
- Pagination/filter tests.
- Failure-safe close/transaction tests.
- Energy-balance invariant tests.
- Result parity with tracing off/summary/full.
- Performance benchmark with documented hardware/runtime; avoid asserting an
  unrealistically brittle absolute time.
- Retained-source hash test.

## Deliverable

Report schemas, trace levels, measured overhead, artifact sizes, query examples and
proof that tracing does not change model results.
