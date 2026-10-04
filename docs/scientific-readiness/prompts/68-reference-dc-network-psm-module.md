# Prompt 68 — Reference DC network PSM module

Execute after Prompt 67. Read the FORCE bid-at-cost clearing equations,
pre-clearing declared inputs, market ledger/replay, storage contracts and Prompt
36-37 independent-oracle evidence. Act as a power-system optimization modeller
and independent validation lead. Do not alter the single-node PSM or implement
transmission expansion.

## Objective

Add a selectable open reference DC network PSM that clears thermal generation,
VRE, boundary imports, load shedding and storage competition subject to nodal
balance and finite branch capacity. It must use the public network contract and
the normal Study-selected execution path, not a private benchmark runner.

The scientific claim is bounded to the declared linear DC approximation. It does
not model reactive power, voltage magnitude or resistive losses and must never be
labelled AC power flow.

## Mathematical scope

For each period, include as applicable:

- accepted thermal, VRE and boundary-import offers at their mapped buses;
- storage charge/discharge, chronological SOC, power/energy limits and fixed
  charging/discharging efficiencies;
- bus voltage angles with one declared reference per connected island;
- branch flow from susceptance/reactance and angle difference;
- nodal Kirchhoff current balance, branch thermal limits and load shedding/VOLL;
- explicit VRE curtailment and the existing physical dispatch identities.

Minimize the declared offered/resource-cost objective. State whether storage
offers/state are endogenous FORCE period information or part of a chronological
optimization; do not give a FORCE auction future information silently. Parallel
lines, out-of-service elements, islands and boundary imports follow Prompt 67.

## Implementation boundary

1. Package the engine as a normal registry module providing
   `domain.network.dc`, with exact solver dependency/version/licence and source
   hash. The frontend only selects parameters; it contains no clearing logic.
2. Use canonical Prompt 67 inputs and typed outputs. No module may reach into the
   raw UK files or mutate global configuration.
3. Extend the declared pre-clearing artifact with nodal offers, topology, limits,
   reference buses and initial state, then publish branch/nodal results through
   the existing bounded market artifact system.
4. Reconcile system-wide and bus-level energy, storage chronology, blackout,
   curtailment, operating cost and settlement-transfer reporting. Congestion rent
   is a transfer unless the declared system-cost identity says otherwise.
5. Preserve deterministic IDs and stable tie handling. Compare multiple optima by
   objective and invariant aggregates rather than row order.

## Independent validation

Build or extend a validation-only formulation from the published equations. It
must consume serialized public fixtures and must not import the production DC
constraint builder, branch-flow function or solver model.

Required cases:

| Case | Required result |
| --- | --- |
| One bus | Equivalent to current single-node clearing |
| Two buses, no congestion | Same aggregate dispatch/price within convention |
| Two buses, binding line | Correct flow, redispatch and nodal-price separation |
| Three-bus mesh | KCL/KVL and branch bounds close |
| Thermal, VRE and import competition | Merit order plus network feasibility |
| Battery and pumped hydro | SOC, efficiency, power and energy constraints |
| Scarcity/island | Explicit load shedding and VOLL convention |
| 24-hour and 168-hour chronology | Feasible state and independent objective |
| Deterministic random convex cases | Recorded seeds and bounded tolerances |
| Broken constraints | Every required mutation makes the gate fail |

Mutate nodal balance, angle-flow relation, one line limit, reference angle,
storage efficiency/energy limit and asset-to-bus mapping. Invocation provenance
must prove the actual Study-selected module ran.

## Frontend and outputs

- Let users select the DC PSM only when all network roles and capabilities are
  ready. Explain the DC approximation and unavailable AC quantities.
- Add an optional network results workspace with bus balance/prices, branch flow
  and utilization, congestion intervals, curtailment/blackout location and a
  topology-data download. Keep large period tables in SQLite/Parquet-backed
  artifacts, not in page payloads.
- The existing auction and VRE pages should filter by bus/branch when the selected
  result supports it and remain unchanged for single-node runs.

## Acceptance

- All required fixtures and independent-solver comparisons pass within declared
  primal, objective and dual/price tolerances; every mutation fails.
- One-bus results satisfy the declared equivalence boundary to current FORCE.
- A deterministic 24-hour and 168-hour production invocation passes bundle,
  cost/carbon, storage, market and network residual checks.
- Old single-node projects and outputs are unchanged and require no network data.
- No claim of AC feasibility, loss modelling, N-1 security or endogenous network
  investment appears in UI, docs or model card.

## Stop conditions

Stop if independent validation reuses production constraint code, if infeasible
network cases are silently converted to copper plate, if a disconnected island
lacks an explicit reference/load-shedding rule, or if solver unavailability is
reported as a passing skip.

## Deliverables

- registered reference DC PSM and exact mathematical reference;
- declared network-clearing inputs and typed period/annual artifacts;
- independent formulation, analytical/random/mutation fixtures and report;
- bounded network results UI and bilingual method/limitation guide;
- machine-readable Prompt 68 validation and decision.
