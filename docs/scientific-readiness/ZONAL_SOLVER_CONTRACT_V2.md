# VALUE zonal solver contract v2

Superseded by [contract v4](ZONAL_SOLVER_CONTRACT_V4.md) (P0-8); kept as the record of v2.

Status: built-in default settings documented; independently validated execution
is not yet claimed.

`value-zonal-redispatch-balancing` `2.0.0` is an Experimental, lossless zonal
transport representation. It is not DC or AC power flow, security analysis,
N-1 analysis or transmission expansion. Copperplate remains the default VALUE
study mode. The embedded HiGHS binary is source-registered as `candidate`, not
independently validated. This document does not promote it to a validated solver
stack.

## Built-in settings and failure boundary

The built-in defaults are SciPy `1.8.1`, `scipy.optimize.linprog` method
`highs-ds`, presolve enabled, primal feasibility tolerance `1e-9`, and dual
feasibility tolerance `1e-9`. Exact SciPy and embedded HiGHS identities are run
evidence. There is no automatic fallback to `highs-ipm`, another solver or
copperplate.

Advanced settings may select `highs-ds`, `highs-ipm` or `highs`; primal and
dual feasibility tolerances from `1e-10` through `1e-7`; IPM optimality
tolerance from `1e-12` through `1e-7`; and lower validated ceilings or warning
fractions within the recorded reference thresholds. Non-default settings need
an explicit acknowledgement and create a new Study revision.

## Numerical lexicographic method

The four objectives are redispatch bid cost, absolute deviation from the
national ahead schedule, physical storage and boundary-flow throughput, and a
stable key for reproducible asset selection. Only the first three are locked.
For locked objective `k` at optimum `x*`:

```text
U_k     = sum(abs(c_i * x_i*))
C_k     = sum(abs(c_i))
gamma_n = n * epsilon / (1 - n * epsilon)
epsilon_effective = max(solver_tolerance_k, bound_canonicalisation_tolerance)
tau_k   = max(unit_floor_k, epsilon_effective * max(1, U_k), gamma_n * U_k, C_k * epsilon_effective)
objective_k(x) <= objective_k(x*) + tau_k
d_k = max(0, objective_k(x_final) - objective_k(x*))
```

The GBP floor is `1e-8 GBP`; the MWh floor is `1e-9 MWh`. `n` is the non-zero
objective-term count. Non-finite values, an invalid term count, an uncomputable
scale or `d_k > tau_k` are hard failures. Numerical tolerance does not relax
physical feasibility: balance, SOC, capacity, network and settlement
constraints remain fail-closed.

| Objective | Unit | Validated ceiling / half-hour | Recorded reference threshold / half-hour |
| --- | --- | ---: | ---: |
| Redispatch bid cost | GBP | `0.01` | `0.10` |
| Absolute schedule deviation | MWh | `0.001` | `0.01` |
| Physical throughput | MWh | `0.001` | `0.01` |

Classification uses `max(computed_tolerance, observed_degradation) / validated_ceiling`:
up to 10% is `GO`; above 10% and up to 100% is
`GO_WITH_NUMERICAL_WARNING`; above 100% is
`COMPLETED_WITH_NUMERICAL_WARNING`. Crossing a recorded reference threshold
does not itself discard a physically feasible result, but that result is not
numerically validated. Numerical warning and unvalidated status propagate to
later PSM/CEM years and the complete Study.

## Evidence and compatibility

SQLite and JSON retain one diagnostic per period and locked phase: run, year,
period, module, solver-contract and binary identities; active tolerances;
objective values; computed tolerance; observed degradation; validation and
reference thresholds; term count; classification; and the declared-input hash.
Historical v1 ledgers remain read-only evidence and are not rewritten.

Failures preserve declared input, module, Study, data and network identities,
solver settings, completed-phase optima and raw solver status. VALUE does not
change solver or network model after failure. A different solver or copperplate
comparison must be a separate Study revision.
