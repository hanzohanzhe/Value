# Prompt 10 — Performance, recovery and final release gates

Act as a senior scientific-software release engineer. Make long studies
observable, resumable and comparable without changing equations.

## Implement

1. Record timings for data preparation, annual PSM, each CEM stage, ledger flush
   and serialization. Identify but do not silently rewrite scientific hot paths.
2. Use annual atomic checkpoints containing state, pipeline and storage-cost
   observations. Validate hashes before resume and refuse mismatched project,
   data or module revisions.
3. Add a run artifact index and bundle validation covering checkpoints,
   scientific-validation report, planning ledger and market index.
4. Add a comparison command for dynamic policy, legacy-tariff policy and the
   retained 2026-07-18 Scheme C result, with explicit units and tolerances.
5. Produce a release report separating functional GO/NO-GO from numerical claims.

## Tests and acceptance

- Simulate interruption after year one and prove deterministic resume into year two.
- Run the full Python suite, frontend build/render tests, retained hashes,
  conformance suite, bundle validator and browser smoke.
- Then launch complete 2025-2034 dynamic and legacy-tariff projects through the
  public application path and compare both with retained Scheme C.
- Never call the legacy-tariff modular scenario an exact reproduction unless its
  declared numerical comparison passes.
