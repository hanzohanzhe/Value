# Prompt 03 — Replace positional Scheme C results with a named boundary

Continue from accepted Prompts 01-02. Act as the maintainer of a legacy scientific
kernel integration. Read the numeric-index inventory before editing.

## Objective

Contain the retained `run_simulation` tuple behind one validated anti-corruption
adapter. All modular/production consumers must use named fields.

## Mandatory constraints

- Do not edit the retained `compat/case3.py`, `exact_run.py` or authoritative
  metadata.
- Do not change the tuple returned by the retained simulation.
- No numerical or unit conversion change is allowed in this task.
- Do not guess tuple positions. Establish them from the retained implementation,
  current modular consumer and regression fixture.

## Work

1. Define a private `LegacySchemeCSimulationTuple` description and a public
   conversion target compatible with `MarketYearResult`.
2. Implement one `SchemeCLegacyResultAdapter` that:
   - validates tuple length;
   - validates required field shapes/types;
   - names every consumed field;
   - performs existing period-hour conversions in one documented place;
   - raises a specific compatibility error on mismatch.
3. Replace all numeric tuple indexing outside this adapter in the modular execution
   path. Tests may construct legacy tuples but must not teach production code new
   indexes.
4. Replace anonymous multi-value function returns introduced by GridForm code with
   named dataclasses where practical. Do not rewrite the complete market kernel.
5. Add invariant checks for year, number of periods, demand length, price length,
   dispatch length and energy units.
6. Add a static test or focused source scan asserting that forbidden patterns such
   as `results[20]` and `results[-8]` do not occur outside the adapter/reference
   allowlist.
7. Document every legacy-to-public field mapping and its unit.

## Tests

- Unit tests for correct conversion and each validation failure.
- Two-period modular execution.
- Existing dynamic storage-cost tests.
- Numerical comparison of old and adapted named summaries on the same fixture.
- Retained-source hash test.

## Deliverable

Report the mapping table, removed positional consumers, invariant failures now made
visible, and parity results. Do not alter the production annual orchestration yet.
