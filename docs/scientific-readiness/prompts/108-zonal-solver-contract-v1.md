# Prompt 108 — Zonal solver contract v1

Execute only against the approved design
[`2026-08-23-zonal-solver-contract-v1-design.md`](../../superpowers/specs/2026-08-23-zonal-solver-contract-v1-design.md).
This prompt is traceability for the implementation; it is not evidence that any
short, annual, 24-hour, 168-hour or multi-year execution gate has passed.

## Approved scope

Publish the four-phase numerical lexicographic contract for the Experimental
lossless zonal redispatch module. The built-in baseline is SciPy `1.8.1` with
`highs-ds`, presolve and `1e-9` primal/dual tolerances. Lock only cost (GBP),
schedule deviation (MWh) and physical throughput (MWh) through the declared
one-sided tolerance; retain the stable-key tie objective as the final unlocked
phase. Record v7 diagnostics and preserve failures without fallback.

## Task list

1. Define solver-contract schema/defaults, one-sided tolerance and validation
   classifications.
2. Bind all solver-contract fields into project identity, migration and exports.
3. Add v7 ledger/JSON evidence, failure preservation and annual propagation.
4. Expose advanced settings, acknowledgement and bounded run-summary evidence.
5. Implement analytical, mutation, contract, compatibility and UI coverage.
6. Publish the handbook, module-author contract, generated module reference and
   source-release membership.

## Non-goals and boundaries

- Do not modify retained Scheme C or old Prompt 104 bytes.
- Do not silently replace an old study/database or insert defaults into its
  identity.
- Do not call the zonal transport model DC/AC power flow, security analysis or
  transmission expansion.
- Do not promote the source-registered embedded HiGHS `candidate` as
  independently validated execution.
- Do not add real UK data, run outputs, caches or local state to the source
  product.

## Acceptance gates

The contract is complete only when public settings are fingerprinted and
auditable; physical and ledger validators remain strict; final solutions satisfy
every one-sided cap; warning/unvalidated states propagate through PSM, CEM and
exports; v7 diagnostics reconcile with annual/JSON records; defaults and custom
contracts are distinct; and production execution either reaches its declared
gate or reports an input-preserving blocker.

Run the contract tests, then documentation/source-release checks. Stop the
production sequence on the first failure: matched two-period smoke, preserved
failed periods, matched 24-hour, matched 168-hour, matched full 2025, then
causal 2025–2026 only after annual `GO`. Prompt 105 ten-year studies remain
outside this work.
