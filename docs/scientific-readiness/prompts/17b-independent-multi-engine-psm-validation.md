# Prompt 17B - Independent validation of FORCE and solver-backed PSM engines

Continue only after Prompt 17A is accepted. Read Prompt 01, visibility Prompt 10,
the native runtime proof from Prompt 12, both selected PSM implementations, the
market artifact schema and the exact public PSM contract. Act as an independent
power-system optimization validator, not as the author of either engine.

Apply the preservation boundary in `docs/scientific-readiness/README.md`. Never
edit retained Scheme C source, fixtures, installed data packs, historical runs or
accepted baselines to make a comparison pass.

## Objective

Build an independently formulated optimization oracle and use it to answer two
different questions:

1. Given the offers and physical availability visible to the market, does the
   actual project-selected FORCE PSM clear each period at minimum offered cost
   while satisfying its declared single-node constraints?
2. Does the optional perfect-foresight PSM solve its declared chronological LP to
   the independent optimum?

Do not require the endogenous multi-period FORCE agent path to reproduce the
perfect-foresight dispatch. That difference is a scientific counterfactual, not
automatically a defect. FORCE equivalence claims are limited to the convex
bid-at-cost, no-start-up/shut-down, no-minimum-up/down, no-ramping and no-network
scope actually tested.

## Independence requirements

- Place the oracle in a validation-only package that imports public contracts and
  serialized fixtures, but imports no production clearing, merit-order, storage
  dispatch, constraint-builder or replay function.
- Write the mathematical model from the published equations and contract fields,
  not by translating production control flow line by line.
- Use a separately declared test dependency and, for validation of the
  solver-backed perfect-foresight module, a distinct formulation implementation.
  Prefer a distinct solver backend as well. If solver independence cannot be
  demonstrated, label that gate `NOT_INDEPENDENT` rather than passing it.
- Record oracle package, solver binary/library, versions, license, tolerances,
  random seeds, source hash and exact command in every report.

## Implement

1. **Define a solver-neutral fixture schema.** Include period duration, demand,
   VRE availability, import limits and bids, thermal limits and bids, storage
   charge/discharge power, energy capacity, efficiencies, initial/terminal SOC,
   storage energy tranches/offers where applicable, VOLL, curtailment treatment
   and expected invariants. Use MW for power and MWh for per-period energy/SOC
   with explicit conversions.

2. **Create the independent LP oracle.** At minimum implement generation, VRE
   acceptance/curtailment, imports, storage charge/discharge/SOC, blackout and
   balance constraints. The oracle must expose objective, variables, residuals,
   bound violations and termination status. Multiple optima must be compared by
   objective and invariant aggregates, not fragile asset ordering.

3. **Validate FORCE clearing at the correct boundary.** Run the actual
   project-selected FORCE engine through the production application service.
   Capture the offers, available quantities and pre-period storage state that the
   market actually saw in a stable validation artifact. Solve each clearing
   problem independently with those offers. Compare accepted quantities,
   curtailment, blackout, marginal price convention, offered-cost objective and
   balance. Separately replay the chronological physical state to validate SOC,
   efficiencies, power/energy limits and conservation.

4. **Treat endogenous storage behaviour honestly.** The published dynamic annual
   storage-cost module determines agent offers from previous-year sold energy and
   dwell time. Validate that the emitted offers match that policy, but do not give
   the oracle future knowledge when testing FORCE period clearing. Report the
   difference between FORCE and perfect foresight as `counterfactual_optimality_gap`,
   not as a FORCE clearing failure, unless a declared theorem/fixture says they
   should coincide.

5. **Validate perfect foresight end to end.** Feed the identical canonical 24-hour
   and 168-hour fixtures to the real selected perfect-foresight PSM and the
   independent chronological oracle. Compare feasibility, resource-cost
   objective, aggregate dispatch, storage trajectory, curtailment and blackout.
   Where prices are compared, state the dual sign and scarcity-price convention.

6. **Add randomized convex cases.** Generate bounded, deterministic cases with
   recorded seeds covering thermal, VRE, imports and at least two storage
   technologies. Include single-period cases, 24-hour cases and a small sample of
   168-hour cases. Avoid exact ties unless the case is explicitly testing tie
   handling.

7. **Prove the gate can fail.** Mutation tests must independently alter or remove
   at least: demand balance, one storage efficiency, storage energy capacity,
   terminal SOC and an import/thermal bound. Each mutation must fail the relevant
   feasibility/objective gate. Also prove that running a private toy helper while
   claiming the public module ID fails invocation provenance.

8. **Publish bounded evidence.** Write a versioned
   `independent-psm-validation.json` containing scope, equations/version,
   invocation proof, cases, maximum residuals, objective deltas, mutations and
   gate decisions. The frontend may show a compact validation badge and link to
   the artifact; do not put per-variable solver logs on the main results page.

## Required case matrix

| Case | FORCE offer-clearing gate | Perfect-foresight optimum gate |
| --- | --- | --- |
| Thermal vs import merit order | required | required |
| VRE acceptance and curtailment | required | required |
| Scarcity and blackout/VOLL | required | required |
| Battery SOC and round-trip loss | required | required |
| Pumped hydro without battery wear | required | required |
| 24-hour chronology | required | required |
| 168-hour chronology | physical-feasibility required | required |
| Random convex fixtures | required | required |
| Deliberately broken constraints | must fail | must fail |

## Acceptance gates

- The report proves the website-selected module ID, version and source hash was
  invoked by the production worker; replay/private substitutes cannot pass.
- Every FORCE result is feasible under its declared physical constraints, and
  each period's offered-cost objective matches the independent clearing optimum
  within a documented absolute/relative tolerance.
- Every perfect-foresight result is feasible and matches the independent
  chronological optimum within tolerance. Tie cases pass only with equal
  objectives and invariant aggregates.
- Energy-balance and SOC residual maxima are reported in MWh, not rounded away.
- All required mutations fail for the expected reason.
- Solver errors, unavailable scientific dependencies or unsupported capabilities
  yield `NOT_EVALUATED`/failure, never a skipped green check.
- Retained Scheme C comparison remains a separate regression gate and is never
  described as independent solver evidence.

## Stop conditions

- If the production runner still replays a compatibility result, return to Prompt
  12 and leave this gate `NOT_EVALUATED`.
- If FORCE does not expose the offers/available quantities seen by clearing, add
  the bounded audit artifact first; do not reconstruct hidden bids from outputs.
- If independent perfect-foresight validation uses the production constraint
  builder or the same serialized model, mark it `NOT_INDEPENDENT`.
- Never change bids, constraints, tolerances or accepted model code merely to make
  the oracle comparison green. Report the first divergent period and equation.

## Deliverable

Provide the independent mathematical LP, fixture schema, dependency and license
record, actual public-runner invocation proof, deterministic/random case report,
mutation report, `counterfactual_optimality_gap`, retained-hash result and two
separate decisions: `FORCE_CLEARING_VALIDATED` and
`PERFECT_FORESIGHT_PSM_VALIDATED` (or their explicit failure/not-evaluated forms).
