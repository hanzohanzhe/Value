# Prompt 01 — Scientific acceptance baselines

Act as a power-system model validation engineer. Establish scientific
acceptance independently of process completion.

## Constraints

- Preserve every retained Scheme C source, fixture, data pack and historical run.
- Do not bless a changed result by overwriting a fixture.
- Separate analytical mechanism tests, modular regression baselines and retained
  Scheme C comparisons.

## Implement

1. Add a versioned scientific-validation report schema with distinct statuses
   for execution, contract/invariant validation, analytical mechanism tests,
   modular numerical baseline and retained numerical comparison.
2. Add small deterministic fixtures for continuous convex bid-at-cost dispatch,
   storage energy conservation, fixed technology duration/efficiency, battery
   cycle depreciation, non-battery absence of cycle depreciation, dwell-time
   holding cost and first-year full-utilisation cost recovery.
3. A missing or inapplicable retained comparison must be `not_evaluated`, never
   `passed`.
4. Write the report into a run bundle and expose a compact summary without
   publishing short-run annual economics.

## Tests and acceptance

- Analytical expected values must use explicit units and tight tolerances.
- Include a deliberately failing fixture proving that a scientific gate fails.
- Retained-source hash tests pass.
- Existing two-period and two-year-smoke tests continue to pass.
