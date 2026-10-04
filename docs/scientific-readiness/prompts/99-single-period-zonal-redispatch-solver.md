# Prompt 99 — Single-period zonal redispatch solver

Execute only after Prompt 98 has produced an owner-signed immutable network
pack. Act as a power-market optimisation engineer. Use test-driven development
and the staged contracts frozen by Prompts 93–98. Do not edit retained Scheme C
and do not reuse the full-chronology DC-OPF builder as though it were this
transport model.

## Objective

Implement the replaceable half-hour zonal balancing module that jointly resolves
realised forecast error and network congestion after the national ahead-market
schedule.

## Mathematical contract

1. Solve each half-hour independently with SciPy/HiGHS linear programming. No
   foresight, rolling horizon, security analysis or transmission expansion is
   implied.
2. Represent the signed zonal injection adjustment of thermal, VRE, storage,
   imports, DSR and involuntary load shedding. Use the declared bid-price
   objective, not an undisclosed physical-cost objective.
3. Enforce zonal balance, directed corridor limits, ETYS cut-set limits, unit
   availability, signed interconnector envelopes, storage power/SOC/efficiency
   constraints and VOLL-priced load shedding. Default VOLL is £17,000/MWh.
4. Storage must use a convex charge/idle/discharge representation that cannot
   self-cycle. Reject non-conforming non-convex storage-bid contracts; do not
   silently approximate them.
5. First minimise total accepted signed bid value. Within the optimum tolerance,
   minimise total absolute deviation from the ahead schedule. Resolve any
   remaining equal-price/equal-network-effect tie pro rata, then by a stable
   deterministic key.
6. Return accepted adjustments, final physical dispatch, SOC, curtailment,
   corridor routing, boundary transfer, slack use, primary/secondary objective,
   residuals and solver diagnostics.

## Required analytical fixtures

- one unconstrained and one infinite-limit case reproducing copperplate;
- one directional cut-set congestion case with hand-calculated redispatch;
- signed import and export envelopes;
- thermal up/down, VRE curtailment, storage charge/discharge, zero-capacity DSR
  and VOLL load shedding;
- no-simultaneous-storage-cycle and inter-period SOC handoff;
- proportional equal-bid allocation and deterministic rerun;
- deliberate infeasibility and malformed-contract failures.

## Failure policy

On build or solve failure, preserve the exact declared input, pack identity,
solver status/message, residuals, log and environment metadata and fail the run.
Never switch to copperplate automatically.

## Acceptance

- Analytical objective, dispatch, flows, SOC and payments reconcile within
  declared tolerances.
- Infinite limits reproduce staged copperplate results.
- Repeated runs are byte-stable for scientific output after excluding declared
  runtime timestamps.
- Mutation of each physical constraint makes at least one targeted test fail.

## Deliverables

- registered `force-zonal-redispatch-balancing` module and manifest;
- solver declaration schema and diagnostics artefact;
- focused unit/contract/mutation fixtures and methodology note.
