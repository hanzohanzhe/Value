# Zonal solver contract v1

Status: built-in default settings documented; independently validated execution
is not yet claimed.

`value-zonal-redispatch-balancing` `1.2.0` is an Experimental, lossless zonal
transport representation. It is not DC or AC power flow, security analysis,
N-1 analysis or transmission expansion. Copperplate is still the default VALUE
study mode. The embedded HiGHS binary is source-registered as `candidate`, not
independently validated. This document does not promote it to a validated solver
stack.

## Built-in baseline and execution boundary

The built-in defaults are SciPy `1.8.1`, `scipy.optimize.linprog` method
`highs-ds`, presolve enabled, primal feasibility tolerance `1e-9`, and dual
feasibility tolerance `1e-9`. The exact SciPy and embedded HiGHS identities are
run evidence. There is no automatic fallback to `highs-ipm`, another solver or
copperplate.

Advanced settings may select `highs-ds`, `highs-ipm` or `highs`; primal and
dual feasibility tolerances from `1e-10` through `1e-7`; IPM optimality
tolerance from `1e-12` through `1e-7`; and lower validated ceilings/warning
fraction within immutable execution ceilings. Non-default settings require an
explicit acknowledgement, create a new project revision and remove the
built-in solver-validated label. A different solver may execute but has no
validated badge until its declared independent random, mutation, 24-hour and
168-hour gates pass.

## Numerical lexicographic method

The solver uses these objectives, in order:

1. redispatch bid cost (GBP);
2. absolute deviation from the national ahead schedule (MWh);
3. physical storage and boundary-flow throughput (MWh); and
4. a stable-key objective for reproducible asset-level selection.

Only objectives 1–3 are locked; the stable-key objective is last. For locked
objective (k), at optimum (x^*):

```text
U_k     = sum(abs(c_i * x_i*))
gamma_n = n * epsilon / (1 - n * epsilon)
tau_k   = max(unit_floor_k, solver_tolerance_k * max(1, U_k), gamma_n * U_k)
objective_k(x) <= objective_k(x*) + tau_k
d_k = max(0, objective_k(x_final) - objective_k(x*))
```

The GBP floor is `1e-8 GBP`; the MWh floor is `1e-9 MWh`. `n` is the number of
non-zero objective terms. Non-finite values, an invalid term count, an
uncomputable scale or `d_k > tau_k` are hard failures. Numerical tolerance does
not relax physical feasibility: balance, SOC, capacity and settlement
constraints remain strict.

| Objective | Unit | Validated ceiling / half-hour | Immutable execution ceiling / half-hour |
| --- | --- | ---: | ---: |
| Redispatch bid cost | GBP | `0.01` | `0.10` |
| Absolute schedule deviation | MWh | `0.001` | `0.01` |
| Physical throughput | MWh | `0.001` | `0.01` |

Classification uses `max(computed_tolerance, observed_degradation) / validated_ceiling`:
up to 10% is `GO`; above 10% and up to 100% is `GO_WITH_NUMERICAL_WARNING`;
above 100% and up to the absolute ceiling is `COMPLETED_WITH_NUMERICAL_WARNING`;
above the absolute ceiling is a hard failure. Numerical warning and unvalidated status propagate to later PSM/CEM
years and the entire study.

## Evidence, compatibility and failure preservation

New executions use ledger schema v7. SQLite and JSON retain period-by-locked-
phase diagnostics: run/year/period/phase IDs; module and contract versions;
SciPy and HiGHS identities; method/presolve/tolerances; objective unit and
values; tolerance/degradation/ceilings; term count and scale; validation/error
state; and declared-input SHA-256. v5 and v6 readers remain read-only
compatible; completed databases are never rewritten.

Failures preserve declared input, module/project/data/network identities, solver
settings/environment, every completed-phase optimum/tolerance and raw solver
status/message. They do not change solver or network model. Users may create a
separate copperplate or alternative-solver Study explicitly.

Third-party modules must emit conforming v7 diagnostics for every locked phase.
The platform continues to enforce energy, SOC, capacity, settlement and ledger
validators. Contract compatibility or installation conformance is not a
scientific validation badge.
