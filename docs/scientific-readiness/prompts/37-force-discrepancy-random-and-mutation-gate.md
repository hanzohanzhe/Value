# Prompt 37 — FORCE discrepancy classification, random cases and mutation gate

Continue after Prompt 36 produces results. Do not tune expected outputs merely to
make the gate pass.

## Objective

Classify every FORCE/oracle difference as implementation defect, numerical
tolerance/equal-price degeneracy, or a genuine information-structure/formulation
difference. Run seeded random convex cases and mutation tests for balance, SOC,
efficiency, MW/MWh, availability and import limits.

## Acceptance

- Random seeds and generated inputs are durable and reproducible.
- Every required mutation makes the validation gate fail for the intended reason.
- Implementation defects are fixed and regression-tested without changing retained
  Scheme C; genuine formulation differences narrow the public claim instead.
- Prompt 17B is regenerated with explicit FORCE and perfect-foresight decisions.

