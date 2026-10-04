# Prompt 35 — Solver-neutral pre-clearing declared-input artifact

Continue only from the verified pre-Prompt-35 snapshot. Read Prompts 08, 17B,
32–34 and their reports. Add no new market rule and do not edit retained Scheme C.

## Objective

Before each live FORCE clearing decision, persist the complete inputs needed by an
independent implementation: chronology, demand, resource price-volume offers,
availability and bounds, storage pre-period SOC, charge/discharge offers,
efficiencies and MW/MWh constraints, balancing offers, penalty terms, selected
module identity and input hash.

## Implementation

- Define a versioned typed `force.clearing-input/v1` contract.
- Write it before clearing to a batched SQLite/JSON artifact optimized for speed.
- Separate declared inputs from outcomes; never infer an input from dispatch.
- Hash each period block and link it to the corresponding outcome/provenance.
- Record unavailable concepts explicitly rather than silently using zero.
- Keep summary tracing bounded; enable complete declared inputs for validation
  runs without changing scientific decisions.

## Acceptance

For thermal, VRE, imports, batteries and pumped hydro, a two-period live run has
complete pre-clearing inputs, reproducible hashes and no post-outcome substitution.
Retained hashes and existing numerical results remain unchanged.

