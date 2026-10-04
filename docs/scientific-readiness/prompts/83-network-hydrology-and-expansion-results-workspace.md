# Prompt 83 — Network, hydrology and expansion results workspace

Execute after Prompt 82 and only against immutable completed run artifacts. Read
Prompts 56–57, Audit/Inspect APIs, Prompt 66–70 result contracts, SQLite indexes,
cost/carbon ledgers and comparison workspace. Act as a scientific visualization
engineer and power-system results auditor. Do not implement a second solver or
reconstruct unavailable quantities in React.

## Objective

Add capability-driven result tabs to a completed run. Tabs appear only when the
run's frozen module/extension graph and artifact index prove support.

## Network results

For DC runs provide bounded annual and selected-period views of nodal balance,
branch flow/rating/utilisation, congestion periods, voltage angles, load shed,
nodal prices and storage SOC. Show a topology view linked to a paginated branch
table; geographic placement is used only when coordinates are declared.

For AC-feasibility runs add convergence class, active/reactive residuals, voltage
magnitudes/angles, reactive output, real losses, branch MVA loading and equipment
violations. Keep AC feasibility separate from economic dispatch and label
non-convergence/infeasibility as failed scientific evidence, never zero.

## Hydrology results

Show, by site and chronology, inflow/usable availability, generation, release,
reservoir volume, spill and binding constraints. Distinguish water units from
MWh and run-of-river curtailment from reservoir spill. Pumped-hydro charge,
discharge and SOC remain in the storage/market view and may only be linked, not
duplicated as natural inflow.

## Transmission-expansion results

Show candidate → proposal → planning → commissioned/failed/retired lineage,
end buses, capacity/circuits, timing, budget use and next-year topology entry.
Link annual network CAPEX/FOM/residual value and embodied carbon to their existing
ledger rows. Compare congestion/reliability before and after only as a temporal
description unless a controlled counterfactual Study is selected.

## Query and performance rules

- Add versioned bounded query responses over existing typed artifacts; do not
  create one annual JSON payload.
- Use server-side range aggregation, pagination and indexed filtering. Exact
  half-hour values remain available after zoom.
- Every metric exposes definition ID, unit, run/project/module/extension identity
  and source artifact hash.
- Unsupported, missing and not-evaluated values display those states, not zero.
- Reuse Market replay, VRE, Inspect, export and cross-Study selection instead of
  duplicating their data.

## Tests and acceptance

Cover DC uncongested/congested/island/storage cases, AC converged/infeasible
cases, run-of-river and drought/flood reservoir cases, and the causal two-year
commissioned-line fixture. Displayed aggregates must reconcile to authoritative
period, annual, cost, carbon and lineage ledgers. Deliberately swapped signs,
wrong units, duplicated pumped hydro, missing losses, fabricated nodal price or
pre-commissioning line entry must fail.

Measure API latency, payload size and rendering for 24-hour and 168-hour
artifacts. Initial rendering must remain bounded with 17,520-period-shaped
fixtures. Meet keyboard, contrast, reduced-motion, screen-reader summary and
responsive-layout requirements.

