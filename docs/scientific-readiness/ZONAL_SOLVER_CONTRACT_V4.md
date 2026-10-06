# VALUE zonal solver contract v4: shed lock, then a numerical bid-cost lock

Status: current executable contract (`value.zonal-lexicographic-shed-lock/v4`,
module `value-zonal-redispatch-balancing` `4.0.0`, formulation
`value.lossless-zonal-redispatch/v2`). It supersedes v3 (GBP 1 lock) and v2;
both remain readable for historical Runs only. The embedded HiGHS binary is
source-registered as `candidate`, not independently validated. This document
does not promote it to a validated solver stack.

## Why v4 (decision Q5, findings P2-01, F3-01, P3-09, R2-02, P2-07)

v3 used GBP 1 as the primary lock allowance. Later lexicographic phases spent
that allowance on spurious load shedding (about 1/(VOLL - price) MWh per
redispatch period) and on asset-id dependent dispatch shifts. If the numerical
tolerance is computed on the whole primary objective, VOLL x shedding inflates
it beyond GBP 1 at GB scale. v4 therefore:

1. solves the primary objective (accepted bids plus VOLL x shedding);
2. locks total load shedding: every shedding variable is fixed at zero when
   the primary sheds exactly nothing, otherwise one row `sum(shed) <= shed*`
   is added (the primary point satisfies it);
3. locks only the bid-cost terms with the coefficient-aware numerical cap
   below; GBP 1 is only the validated/absolute acceptance ceiling;
4. accepts equal-price bids pro rata whatever their resource class; a down
   bid's forced part (schedule above an upper bound on final dispatch, i.e.
   realised availability or an interconnector envelope) stays outside the
   group.

## Numerical lexicographic method

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

For the bid-cost lock the solver scale is the declared feasibility tolerance
(`1e-9` by default) with a GBP floor of `1e-8 GBP`; the MWh locks keep the
`1e-8` solver floor and the `1e-9 MWh` unit floor. Numerical tolerance does not
relax physical feasibility: balance, SOC, capacity, network and settlement
constraints remain fail-closed. A violated lock may be repaired by at most
three deterministic tighter-cap retries that also recompute the later locks.

| Objective | Unit | Validated ceiling / half-hour | Recorded reference threshold / half-hour |
| --- | --- | ---: | ---: |
| Redispatch bid cost | GBP | `1.0` | `1.0` |
| Absolute schedule deviation | MWh | `0.001` | `0.01` |
| Physical throughput | MWh | `0.001` | `0.01` |

Classification uses `max(computed_tolerance, observed_degradation) / validated_ceiling`:
up to 10% is `GO`; above 10% and up to 100% is
`GO_WITH_NUMERICAL_WARNING`; above 100% is
`COMPLETED_WITH_NUMERICAL_WARNING`. At GB scale (23-zone chain fixture,
6 scarce and 8 normal seeds) every primary row is `GO`.

## Network economics carried by the same solve (P0-8b)

* Dec bids are priced economically by the staged PSM (`network_method_rules`):
  the solver itself is unchanged, but dispatch no longer depends on asset ids.
* The network-free counterfactual (`value.network-free-lp/v1`) is this LP
  collapsed to one node with the same settings; network cost is zonal minus
  network-free, and `J_1(zonal) >= J_1(network-free) - tol` is checked per
  period.
* Boundary marginal values are the primary-phase row duals (before any lock
  row is added), signed in the forward direction, with status `computed`,
  `degenerate_dual` or `shared_member`.

## Evidence and compatibility

Each period and locked phase writes one solver diagnostic row (contract
version, tolerances, optimum, achieved value, computed tolerance, degradation,
classification). Saving or running a Study with a v2 or v3 contract returns
`GF_SOLVER_CONTRACT_UPGRADE_REQUIRED`; the upgrade is previewed and saved as a
new Study revision. Historical v2/v3 ledgers stay readable; v3 ledgers carry
the derived known defect `p08.zonal-v3-gbp1-lock`. There is no automatic
fallback to another solver or to copperplate.
