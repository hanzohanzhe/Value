# Prompt 49 — FORCE cost identity and hydro CAPEX boundary

Continue after Prompt 48. Reuse Prompt 11's one reconciled cost ledger and Prompt
42 commissioned-asset economics.

## Objective

Align model-card metadata with the already implemented FORCE CEM resource-cost
definition and prevent an existing-stock hydro accounting value from becoming a
new-build cost assumption.

## Non-duplication boundary

- Do not create another cost ledger or change historical Scheme C numbers.
- Do not change dynamic or legacy storage pricing formulas.
- Keep settlements, transfers and pipeline commitments outside the headline
  resource cost as Prompt 11 requires.

## Implement

1. Make `cost.system_boundary` resolve to the same versioned definition ID used by
   `AnnualCostLedger`: annualised active-fleet CAPEX/FOM plus physical operation,
   storage degradation and reliability cost per demand served.
2. Preserve Scheme C's historical metric under its separate legacy definition ID.
3. Label the current natural-flow-hydro CAPEX as an existing-stock compatibility
   basis. It may remain in compatibility annual accounting but cannot be inherited
   by a new project.
4. Require a sourced new-build cost record plus site/hydrology evidence before
   commissioning new natural-flow or pumped hydro.
5. Ensure API/frontend/model-card readers display the ledger definition ID and do
   not recompute the headline.

## Acceptance

- Parameter registry, model card, annual ledger, API summary and frontend agree on
  one FORCE definition ID.
- A hydro proposal cannot inherit £100m/MW from existing stock.
- Existing-stock compatibility results remain numerically unchanged in a fixture.
- Legacy metrics remain readable and differently named.

## Stop condition

Do not publish a cost comparison if the model card and ledger name different
accounting boundaries or a new hydro asset lacks a new-build cost source.
