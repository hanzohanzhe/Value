# Prompt 103 — Independent zonal solver validation

Execute after Prompts 99–102. Act as an adversarial optimisation validator. The
oracle must be independently formulated with PuLP/CBC and must not import the
production HiGHS matrix builder, objective assembly or constraint rows.

## Objective

Demonstrate that the FORCE single-period zonal redispatch implementation solves
the declared optimisation problem, and that the validation gate fails when the
production formulation is intentionally damaged.

## Validation suite

1. Repeat all hand-solvable fixtures from Prompt 99 in the independent oracle.
2. Generate seeded random convex cases covering thermal, VRE, signed imports,
   storage, DSR, load shedding, asymmetric corridor capacity and overlapping
   cut-set boundaries.
3. Compare feasibility, primary objective, secondary deviation objective,
   zonal balances, boundary transfers, dispatch, SOC and accepted adjustments
   with tolerances that are declared before execution.
4. Run deterministic 24-hour and 168-hour sequential-SOC cases. These remain
   independent half-hour optimisations; the test must not add future knowledge.
5. Mutate or disable, one at a time, zonal balance, forward limit, reverse limit,
   cut-set incidence, storage efficiency, storage power, storage energy,
   interconnector sign, realised availability, VOLL and secondary tie-breaking.
   Each mutation must make its designated validation gate fail.
6. Test malformed schemas, impossible starting SOC, isolated zones, all-zero
   flexibility and infeasible cases. Preserve both production and oracle
   declarations on disagreement.

## Difference classification

Classify every mismatch as production defect, oracle defect, degenerate optimum
with equivalent objective/physics, or declared information-structure difference.
Do not waive a difference merely because aggregate cost is close.

## Acceptance

- All analytical, random, 24-hour and 168-hour valid cases pass.
- Every deliberate mutation is detected by the intended gate.
- Oracle independence is enforced by a source/import scan.
- A machine-readable report records seeds, versions, tolerances, declarations,
  comparisons and classifications.

## Deliverables

- independent PuLP/CBC oracle and generators;
- mutation, random and chronology validation suite;
- human and machine-readable validation report;
- a blocking release gate consumed by later prompts.
