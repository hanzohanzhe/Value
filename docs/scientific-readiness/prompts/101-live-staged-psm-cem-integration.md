# Prompt 101 — Live staged PSM–CEM integration and run recovery

Execute after Prompts 99–100. Act as the FORCE integration architect. Connect
the staged market to the real annual PSM→investment→caps→planning→next-year
chain. Do not replace the existing monolithic PSM path or alter retained Scheme C.

## Objective

Make the selected ahead market and selected balancing module the actual run path,
with real cashflow and physical-state consequences reaching CEM and the following
year.

## Requirements

1. Add explicit study fields for ahead-market module, balancing module,
   `network_pack_id`, weather spatialisation module, ledger detail and VOLL.
   Existing studies migrate to the monolithic or staged-copperplate equivalent
   without semantic change.
2. Execute national ahead clearing from the forecast state, create the declared
   balancing input, solve the selected module and commit only final realised
   dispatch/SOC/cashflow once.
3. Pass final dispatch, actual storage discharge, national settlement,
   redispatch settlement, policy payments and physical resource cost to the
   correct annual ledgers and investment owners.
4. Preserve agent×technology×zone shares for commissioned assets and new abstract
   capacity. No duplicated owner, capacity, CAPEX, FOM or economic-life state may
   be introduced by zonal tranches.
5. Keep the public versioned transmission-expansion interface, but do not bundle
   or register a selectable executable transmission-CEM implementation in this
   release line. Preserve historical source and audit evidence.
6. On zonal solver failure, leave the run failed with the declaration artefact.
   Expose an explicit `Rerun as copperplate` action that creates a new run ID and
   links the failed run as comparison parent; never mutate or resume the failed
   run under different physics.
7. Record module, pack, seed, environment, declaration and state-transition
   identities needed for replay.

## Acceptance

- A two-period integration fixture demonstrates a different zonal final dispatch,
  changed agent cashflow, correct storage SOC and next-year CEM input.
- A commissioned child keeps owner economics and the frozen zone-allocation rule
  and is present in next-year physical clearing.
- Staged copperplate matches the thesis-compatible path within the declared
  divergence contract.
- Failure/rerun creates two immutable linked runs and no silent fallback.
- The former experimental expansion module is absent from user-selectable
  production manifests without deleting its historical files.

## Deliverables

- study/config migration and live staged runner;
- CEM/cashflow/state adapters;
- explicit copperplate-rerun API and lineage artefact;
- bounded integration and regression tests.
