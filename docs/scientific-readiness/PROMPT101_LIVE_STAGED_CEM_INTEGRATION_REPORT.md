# Prompt 101 — live staged PSM–CEM integration report

## Decision

**Accepted for interface and bounded causal integration.** A Study's selected
ahead market, balancing module, immutable network pack, weather spatialiser,
ledger detail and VOLL now resolve into the live annual path. The staged result
reaches investment, planning and the following year's physical fleet without
duplicating economic owners or commissioned-asset CAPEX/FOM.

This decision does not approve an annual zonal scientific result. The production
HiGHS formulation remains behind the independent Prompt 103 validation gate.

## State and accounting boundary

- National clearing is run from the declared forecast state; balancing receives
  realised demand, availability and the pre-period SOC.
- Only the final realised dispatch and SOC are committed to the annual result.
  Counterfactual copperplate clears are read-only accounting calculations.
- National settlement and signed pay-as-bid redispatch settlement are credited
  once to the economic owner. A private CEM adapter allocates that owner total
  across the owner's physical assets only because the retained investment
  contract is asset-keyed; the allocation preserves the total exactly.
- Physical zonal tranches retain `base_asset_id`, `investment_owner_id`, zone
  share and pack revision. They do not become extra investment agents and do not
  carry additional CAPEX, FOM or economic life.
- New abstract capacity inherits the owner's capacity-weighted frozen zone
  shares. A commissioned child is rebuilt as a genuine next-year chronological
  PSM resource with its owner and spatial identity intact.

## Persistent evidence

The live staged runner now writes the authoritative `gridform.market-ledger/v5`
SQLite database. Summary evidence contains final period dispatch, storage state,
zone and boundary balances, the six accounting views, three matched cost
counterfactuals, reliability chronology and solver/declaration links. Full trace
adds every accepted or rejected redispatch bid. The annual CEM cost ledger reads
the same physical resource-cost total while keeping settlement and policy
transfers outside system cost.

The market contract stream, annual staged identity and SQLite ledger are returned
as run artefacts. Module, version, data pack, network pack, weather spatialiser,
parent run and final-dispatch commitment semantics are stored in ledger metadata.

## Failure and rerun semantics

A zonal solver failure remains a failed immutable run with its declaration and
solver evidence. `POST /api/runs/{run_id}/rerun-copperplate` verifies the failed
run's frozen input snapshot, creates a new Study snapshot and run ID, changes only
the declared balancing physics, and writes an explicit comparison-parent lineage.
There is no automatic fallback, mutation or resume under different physics.

The public transmission-expansion interface and historical implementation remain
in source for compatibility evidence. No transmission-CEM executable is exposed
as a user-selectable production module in this release line.

## Verification

- Prompt 101 focused integration: 8 passed.
- Related staged, spatial, solver, ledger, project-migration and orchestration
  regressions: passed.
- Generated runtime tables: current.
- Retained Scheme C source hashes: passed.
- Python 3.10 complete suite: 530 passed, 21 declared skips, 89 passed subtests,
  0 failures.

Prompt 102 may now build the Network & redispatch workspace on this persisted
result contract. Annual and ten-year execution remain blocked by Prompts 103 and
104 respectively.
