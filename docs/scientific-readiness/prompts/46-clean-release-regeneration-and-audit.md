# Prompt 46 — Clean release regeneration and audit

Execute only after Prompts 42–45 pass. Treat all Prompt 39 bundles as immutable
negative evidence; create new run IDs and never overwrite them.

## Objective

Regenerate the complete scientific and software release evidence from a clean
installation, then issue a new independent GO/NO-GO decision.

## Ordered gates

1. Run unit, contract, retained-hash, package/path, lint, build, render and browser
   E2E tests from a clean wheel install.
2. Run two-period and short chronology smoke tests with full pre-clearing traces.
3. Repeat 24-hour, 168-hour, random convex and constraint-mutation validation
   against the independent CBC oracle.
4. Run a full 17,520-period year and a causal two-year PSM -> CEM -> next-year
   chain. Verify that commissioned capacity and economics affect year two.
5. Run new dynamic-storage and legacy-tariff 2025–2034 scenarios with identical
   data, seeds and non-storage assumptions.
6. Compare both with the retained Scheme C result using declared cost/carbon
   definition compatibility; do not score incomparable definitions as parity.
7. Validate checkpoints, cancellation/recovery, artifact hashes, SQLite/API/export
   equality, carbon coverage, planning causality and data-rights packaging.

## Acceptance

- Zero unexplained conservation, SOC, capacity, cost, carbon or state-transition
  mismatches.
- Annual fleet cost changes consistently with commissioning and retirement.
- Each commissioned asset has a demonstrated live-clearing and ledger lineage.
- Dynamic-policy warnings and sensitivity results are published without promoting
  one pricing policy as universally preferred.
- Machine-readable and human-readable reports make separate decisions for source,
  synthetic data, local UK data, public UK distribution, FORCE clearing, CEM and
  the complete platform.

## Final decision rule

The platform is GO only if every blocker is closed. An experimental source release
may be decided separately, but it must not be described as a scientifically
validated open-source power-system modelling platform.
