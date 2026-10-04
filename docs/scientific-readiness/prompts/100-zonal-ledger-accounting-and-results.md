# Prompt 100 — Zonal ledger, accounting and results

Execute after Prompt 99. Act as a market-settlement engineer and scientific data
architect. Extend the existing batched SQLite market ledger; do not create a
second competing result store and do not place verbose audit fields directly on
the run-centre summary.

## Objective

Make staged national clearing and zonal redispatch fully auditable while keeping
the default annual output compact and fast.

## Settlement and cost identities

1. The base ahead schedule is paid at the national clearing price.
2. Redispatch is signed pay-as-bid:
   `cashflow_to_agent = accepted_delta_mwh * bid_price_gbp_per_mwh`, where a
   positive delta is increased injection or reduced consumption and a negative
   delta is reduced injection or increased consumption.
3. Keep separate, reconcilable accounts for system resource cost, incremental
   transmission-constraint resource cost, national settlement, redispatch
   settlement, policy transfers and boundary shadow value.
4. Describe boundary shadow value as a diagnostic marginal value in the accepted
   bid objective. Never label it as a zonal price or an observed cash cost.
5. CEM agents read their own realised national plus redispatch plus policy
   cashflows minus eligible costs. Dynamic storage recovery uses actual final
   discharge MWh after redispatch.

## Counterfactual and curtailment identities

Store three matched counterfactuals per period:

1. perfect-forecast copperplate realised dispatch;
2. forecast schedule plus realised copperplate balancing;
3. forecast schedule plus realised zonal balancing.

Report forecast-error cost as 2−1, network-constraint cost as 3−2 and total
deviation cost as 3−1. Split VRE into economic/ahead unused energy, realised
availability change, network-added curtailment and total curtailment.

## Ledger contract

Upgrade the existing schema with migrations and indexes for:

- period, zone and ETYS-boundary summaries;
- resource final dispatch, signed adjustment and storage state;
- every full-mode bid, acceptance, payment and reason code;
- solver/failure declaration links;
- reliability events: observed loss-of-load half-hours, duration, unserved MWh,
  affected zones and maximum deficit;
- network-pack, data-pack, module and run-parent identities.

Annual runs default to summary mode. A research preset enables the full bid
ledger only after showing a disk estimate. Use batched inserts and prove that the
ledger does not alter model decisions.

## Acceptance

- All six cost/settlement accounts reconcile without double counting.
- Three counterfactuals use identical realised inputs and expose the declared
  algebra.
- Reliability output uses observed chronology metrics and does not call a single
  chronology LOLE.
- Summary and full modes return identical model totals.
- Database migration, query latency, interruption recovery and malformed-row
  tests pass.

## Deliverables

- versioned SQLite migration and batched writer;
- public query/export API for period, zone, boundary and agent audit;
- accounting, counterfactual, curtailment and reliability tests;
- machine-readable field dictionary.
