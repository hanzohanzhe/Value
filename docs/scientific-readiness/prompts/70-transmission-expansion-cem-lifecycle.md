# Prompt 70 — Transmission-expansion CEM lifecycle

Execute after Prompts 65 and 67; use Prompt 68 for the first production
integration unless an accepted AC expansion formulation is explicitly selected.
Read the current investment-owner, shared-headroom, planning, commissioning,
asset-economics, transition, cost and carbon contracts. Act as a transmission
planning modeller and CEM architecture lead.

## Objective

Let a Study select a transmission-expansion module that can propose, plan,
commission, retire and cost network assets through the same annual PSM → CEM →
planning → next-year state chain. A commissioned line must enter the actual next
year network clearing exactly once with complete scientific identity.

Do not reuse generator rows, VRE/storage expansion caps or hydro site logic as a
shortcut for transmission. Network investment is a separate declared capability
and lifecycle.

## Contracts and state

1. Add typed `NetworkAsset`, `NetworkCandidate`, `NetworkInvestmentProposal`,
   `NetworkPlanningProject` and `NetworkCommissioningEvent` schemas through the
   Prompt 65 namespaced extension state. Include stable corridor/end buses,
   technology, circuits/capacity, impedance/loss parameters, owner/planner,
   CAPEX, FOM, construction life, economic life, embodied-carbon factor,
   development stage, lead time and source/provenance.
2. Add an explicit `network_expansion` module slot/capability to the one registry
   and annual graph. Do not disguise it as `vre_cap`, `storage_cap` or a generic
   generation agent.
3. Separate existing transmission stock, externally supplied candidates and
   model-generated proposals. Candidate corridors and maximum build are data,
   not silently assumed complete graph connectivity.
4. Define investment objective/information structure: central planner, regulated
   owner or agent-based rule; costs/benefits; foresight horizon; discounting;
   congestion, reliability and policy treatment. The selected method must be
   visible and replaceable through the public module contract.
5. Apply planning success/timeline/seed rules once, with location and lineage
   retained. Expansion headroom is shared by declared corridor/technology budget,
   never multiplied by incumbent lines or parallel asset rows.
6. Commission only after accepted planning completion. Transition must inject the
   new network asset into next-year canonical topology, preserve electrical and
   economic properties, and reject duplicate IDs/circuits.
7. Retire or uprate assets through explicit events. A replacement or uprate must
   state whether it changes impedance, rating, circuits, remaining life and
   residual value.

## Ledgers and outputs

- Add annualized network CAPEX/FOM, retirement/residual value and declared policy
  support to the same FORCE CEM resource-cost ledger without double-counting
  settlement transfers or congestion rent.
- Add construction/asset embodied emissions to the selected carbon-factor
  scenario with provenance and allocation method. Do not fabricate factors.
- Extend planning inspection with corridors/end buses, MW, stage, success/failure,
  commissioning year and lineage. Extend network results with capacity additions,
  congestion changes and reliability outcomes; avoid causal claims without a
  controlled comparison.
- Store detailed events and assets in SQLite/typed artifacts; keep main result
  cards concise.

## Minimum reference implementation and tests

Provide a transparent small candidate-selection method sufficient to exercise
the contract; it need not be declared the recommended national planning model.

1. In a congested two-bus fixture, produce or import one candidate, pass it
   through planning, commission it, and prove next-year branch capacity changes
   in the actual selected DC PSM.
2. In one causal two-year test, reconcile proposal → planning event → commissioned
   network asset → next-year pre-clearing input → branch flow/result.
3. Test failed, delayed, duplicate, over-budget, invalid-endpoint and retired-line
   cases. No failed project may enter topology or cost as operating stock.
4. Prove complete CAPEX/FOM/life/carbon identity inheritance and cost/carbon
   ledger reconciliation.
5. Prove shared corridor/system budget is not multiplied by owners, incumbent
   circuits or project rows.
6. Compare unchanged no-expansion/single-node Studies with their accepted
   baselines. A ten-year run is required only before publishing a long-horizon
   endogenous transmission pathway, not to accept the lifecycle mechanism.

## Stop conditions

Stop if candidate data are absent, if new lines enter clearing before commission,
if commissioning changes impedance/economics silently, if a line is represented
as generation, or if a cost/benefit is counted both in objective and system ledger
without an explicit accounting identity.

## Deliverables

- public transmission-expansion contracts and registered reference module;
- versioned network asset/planning/transition state and data adapters;
- next-year live PSM coupling, cost and carbon ledger integration;
- planning/network UI and typed SQLite/artifact outputs;
- causal two-year, failure, budget, lineage and reconciliation evidence;
- Prompt 70 report and bounded model-card claims.
