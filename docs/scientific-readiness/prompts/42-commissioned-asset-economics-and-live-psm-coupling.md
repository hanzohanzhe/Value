# Prompt 42 — Commissioned-asset economics and live PSM coupling

Continue only after Prompt 41. Preserve the retained Scheme C source hashes,
historical runs and Prompt 39 bundles. Modify only the public contracts and the
copied modular runtime.

## Objective

Make every CEM commissioning and retirement event causally affect both the next
year's actual FORCE clearing and the reconciled annual system-cost ledger.

## Required implementation

- Define one versioned commissioned-asset record carrying technology, location,
  commissioning/retirement year, MW, MWh where relevant, efficiencies, CAPEX,
  fixed O&M, economic life and factor/catalogue identifiers.
- Populate that record from the project and technology catalogues. Fail closed
  before commissioning if required physical or economic fields are absent; do
  not silently invent zero cost.
- Build or update the live FORCE generator/storage objects from annual state,
  including additions, retirements and capacity changes. Do not depend on an
  exact match with a fixed initial-fleet asset ID.
- Recompute annualised capital and fixed O&M for every active asset and reconcile
  fleet CAPEX/FOM plus PSM operation, flexibility, adequacy and policy ledgers to
  the single published CEM system-cost definition.
- Record compact causal links from project -> commissioned asset -> annual state
  -> live clearing input -> annual cost row.

## Acceptance tests

- A one-project fixture proves that a project commissioned after year one changes
  year-two declared capacity and clearing; deleting that state transition makes
  the test fail.
- Commissioned-asset CAPEX/FOM appears exactly once in the correct years; missing
  economics is rejected rather than reported as zero.
- Retirement removes physical capacity and the appropriate future cost rows.
- Asset-level sums reproduce the annual fleet ledger within a declared numeric
  tolerance.
- The retained Scheme C hashes and Prompt 39 artifact hashes remain unchanged.

## Stop condition

Do not continue to Prompt 43 if a planning asset can appear in the dashboard
without entering both next-year clearing and the cost ledger.
