# Prompt 55: Scenario-aware carbon release gate

Execute after the Prompt 52 legacy ten-year audit. Do not alter any carbon
factor, model activity or completed run artifact.

## Observed defect

The canonical legacy scenario deliberately selects
`scheme_c_reproduction_2026_07_18`. Prompt 21 requires this scenario to return
reason-coded `not_physically_interpretable` rather than relabel the historical
Scheme C storage scalars 40/50 as physical tCO2e. The completed legacy bundle
did exactly that, with null total emissions and reason code
`legacy_storage_scalars_have_no_declared_physical_unit`.

The Prompt 46 audit helper accepted only `reconciled`, which is correct for the
authoritative physical scenario but contradicts the explicit legacy contract.
It therefore failed a truthful legacy result while all execution, energy, cost,
investment, planning, lineage and bundle gates passed.

## Required change

1. Make the audit carbon gate scenario-aware.
2. Accept `reconciled` physical ledgers with a numeric total and no unresolved
   activity.
3. Accept `not_physically_interpretable` only for
   `scheme_c_reproduction_2026_07_18`, only when total tCO2e is null, no
   unresolved activity is hidden, and the exact reason code is present.
4. Reject the same status for the authoritative scenario and reject generic
   `not_evaluated` results.
5. Expose the carbon scenario, reason and gate interpretation in the audit.
6. Render the legacy annual carbon value as not physically interpretable, not
   zero and not a numeric dynamic-versus-legacy delta.

## Acceptance

- authoritative physical carbon still fails closed on missing factors;
- the declared legacy non-physical result passes its own truthful contract;
- JSON and SQLite carbon ledgers remain identical;
- the legacy Prompt 52 ten-year audit passes without changing its run files.

