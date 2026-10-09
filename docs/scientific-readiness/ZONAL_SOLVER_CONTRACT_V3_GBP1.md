# VALUE zonal solver contract v3: GBP 1 study policy

Status: **superseded** by [contract v4](ZONAL_SOLVER_CONTRACT_V4.md) (P0-8, decision Q5).
v3 is readable for historical Runs only; executing it returns
`GF_SOLVER_CONTRACT_UPGRADE_REQUIRED`. Former status: candidate. This policy does not inherit scientific approval from v2.

For every solved period, the primary objective is the total redispatch bid cost
across all assets. Its one-sided LP lock and final hard acceptance boundary are
both exactly `1.0 GBP` above the independently solved primary optimum. The
amount is not per asset and not per MWh. The stored `computed_tolerance`,
`validated_ceiling`, and `absolute_ceiling` are therefore all `1.0 GBP` for
this objective.

The secondary schedule-deviation and physical-throughput locks retain the v2
coefficient-aware formula and all existing MWh thresholds. Energy balance,
transmission, storage power and SOC constraints are unchanged.

The final solution recomputes every objective from final variable values.
Primary degradation of `0.999 GBP` and `1.0 GBP` is within the contract;
`1.001 GBP` is a hard `GF_ZONAL_OBJECTIVE_LOCK_VIOLATION`. A lock residual may
trigger at most three deterministic tighter-cap retries. Exhaustion remains a
hard failure and retains the repair history in failure evidence.

Classification conservatively uses the larger of observed degradation and the
declared allowance. Consequently every v3 primary row is at least
`GO_WITH_NUMERICAL_WARNING`, even when observed degradation is zero. This is a
qualification status caused by the user-authorized GBP 1 policy allowance; it
does not claim that GBP 1 of cost degradation actually occurred. MWh
classification retains v2 semantics.

The source-controlled v2 validation-registry entry remains unchanged. v3 has
a distinct candidate entry and may be promoted only from v3-specific evidence.
