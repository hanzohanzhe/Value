# VALUE Zonal Solver Contract v2 Design

## Purpose

Prevent a physically feasible zonal redispatch result from being rejected only
because VALUE canonicalises solver-scale bound noise before reconstructing a
locked lexicographic objective. The change is numerical bookkeeping: it does
not alter bids, demand, network capacities, redispatch merit order, storage
state transitions, settlement rules, or any PSM/CEM economic logic.

## Confirmed root cause

The 2025 zonal run failed at period 2431 (`2022-02-20:32`) during final
objective validation. HiGHS returned a load-shedding variable of
`-1.1597277799918362e-11 MWh`. This is feasible solver noise at a lower bound.
VALUE correctly canonicalised it to zero, but the v1 objective lock tolerance
was calculated from the objective value at the optimum. Because the primary
optimum was effectively zero, v1 fell back to `1e-8 GBP`. Canonicalisation then
changed the reconstructed VOLL-valued objective by about `1.97e-7 GBP`, so the
physical solution was falsely rejected as an objective-lock violation.

## Numerical contract

For every locked objective, VALUE v2 computes:

```text
epsilon_effective = max(epsilon_solver, epsilon_canonicalisation)
tau_coefficient   = ||c||_1 * epsilon_effective
tau_v2            = max(tau_v1, tau_coefficient)
```

`c` is the objective coefficient vector over non-zero terms. The current bound
canonicalisation tolerance is `1e-8`; the active solver tolerance is the
largest declared tolerance used by the selected HiGHS method. Larger declared
solver or canonicalisation tolerances therefore propagate into the objective
lock instead of being silently clipped.

The final canonicalised solution must still satisfy every physical equality,
inequality and variable bound. An observed objective degradation greater than
its computed `tau_v2` remains a hard failure. This contract does not introduce
fallback, retry with looser settings, or copperplate substitution.

## Scientific-status classification

The existing validated ceilings remain the boundary for a validated numerical
result. The existing absolute-ceiling values remain recorded reference
thresholds, but v2 no longer treats them as an execution kill switch.

- At or below the warning fraction: `GO`.
- Above the warning fraction and at or below the validated ceiling:
  `GO_WITH_NUMERICAL_WARNING`.
- Above the validated ceiling, including above the former absolute threshold:
  `COMPLETED_WITH_NUMERICAL_WARNING` and not numerically validated.
- Observed degradation above the computed tolerance: hard failure.
- Any physical infeasibility: hard failure.

This preserves evidence rather than discarding a feasible run solely because a
large but explicitly calculated numerical allowance crosses an old fixed cap.

## Public identities

- Solver schema: `value.network-solver-contract/v2`.
- Solver contract: `value.zonal-lexicographic/v2`.
- Built-in zonal redispatch module: `value-zonal-redispatch-balancing@2.0.0`.
- Market-ledger diagnostic rows retain the current public columns. The
  `absolute_ceiling` column is a recorded reference threshold in v2, not a hard
  execution boundary.

Saved Studies, acknowledgements, frontend types, schemas, manifests and the
solver-validation registry must use the same v2 identities. No FORCE names or
identities are introduced.

## Verification sequence

1. Add minimal unit regressions for coefficient-norm tolerance and completion
   above the former absolute threshold; observe them fail under v1.
2. Implement the v2 calculation and classification; run the focused solver and
   ledger tests.
3. Replay the exact preserved period-2431 declared input and require a feasible
   completion without copperplate fallback.
4. Run a 48-period zonal gate and a 336-period zonal gate.
5. Only after those gates pass, delete the explicitly enumerated obsolete v1
   zonal/copperplate run directories and their run-specific diagnostic reports.
   Source, data packs, Studies, Scheme C references and unrelated evidence stay.
6. Launch fresh matched copperplate and zonal 2025-2034 runs at one numerical
   thread and BelowNormal priority. Long runs are monitored; they are not
   evidence that the bounded gates passed until their own bundles validate.

## Non-goals

- No change to transmission topology or limits.
- No change to CEM, bids, storage pricing, settlement, demand, weather or data.
- No broad refactor of the output architecture.
- No automatic solver or copperplate fallback.
- No claim that the experimental zonal domain is security analysis, DC load
  flow, AC power flow, or transmission expansion.
