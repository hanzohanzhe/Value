# Default PSM clearing and storage dispatch (P0-6 draft for methodology 0.4)

Status: draft written with the P0-6 S4-S12 construction (2026-10-06); to be merged
into `core.md` / `national_alternatives.md` (en, zh) when the 0.4 edition is
generated.

The default PSM (`value-bid-at-cost-psm` 6.0.0) runs the retained Scheme C kernel
(`runtime_compat/modular_simulation_model.py`) under one immutable market rule
set (`gridform_core/builtin/scheme_c_1000twh/native_market_rules.py`).  The rule
set is derived only from the methodology catalogue
(`corrections/p06.json`): the doctoral reproduction profile
`doctoral-lineage-0.6.0a2` runs `native-doctoral-thesis-v1` (the 0.6.0-alpha.2
behaviour, frozen), the default profile `value-corrected` runs
`native-corrected-v1`.  The kernel refuses any other combination.

## What does not change (both rule sets)

* **Realisation branch (decision A2).** The real-time stage still chooses the
  curtailment branch when realised demand is below the *forecast* and the
  balancing branch otherwise.  A period whose ahead stage could not meet the
  forecast therefore keeps its hidden shortfall; it is booked as a stress
  event (shortfall, stress flag, contiguous events, annual summary) and as
  unserved energy in the energy-balance account (P0-4 S6), never hidden by a
  compatibility adjustment.
* **Investment rule (decision A6).** Money is in constant base-year terms and
  investment tests stay undiscounted (ROI / payback); P4-02 is not a defect.
* **Absorption order of the curtailment branch (appendix P0-6 Q5).** Storage,
  export, flexible demand, then down regulation, as in the thesis.

## Physical operating cost (P5-06, universal)

`total_operational_cost_gbp` of a default-PSM year is the physical cost

    operating = sum(gen_cost x output) + sum(import price x import)
              + start-up adder + unserved x VoLL + storage cycle wear

* `gen_cost` is the unit's running cost (fuel, carbon and unit-time cost); the
  bid multiplier is not applied, so `market.bid_multiplier` does not change the
  physical cost.
* The start-up adder is the thesis offer adder (`startup_cost` per MWh of a
  gas, biomass or nuclear unit that did not run in the previous period),
  reported apart as `startup_adder_resource`.
* VoLL (decision A16-5, see `fx5_voll_17000.md`): 17000 GBP/MWh in both
  profiles. The doctoral rule set uses the constant 17000 GBP/MWh (the thesis
  constant 8000 was replaced by the universal accounting correction
  `fx5.voll-17000`); the corrected rule set reads `market.voll_gbp_per_mwh`
  (default 17000 GBP/MWh; 10000 before A16-5).
  Unserved energy is the recorded blackout (the headline keeps it; hidden
  shortfalls are reported by the stress-event account, appendix P0-6 Q4).
* Storage bid payments are settlement transfers and already contain the cycle
  wear; before P0-6 the wear was counted twice.

`physical_operating_cost_detail_gbp` lists the terms;
`market_settlement_components_gbp` lists the transfers of the period at their
actual value (generation offers, storage offers of the same period, curtailment,
balancing, export revenue, import payment) and reconciles them with the retained
period-cost column, whose thesis storage-fee carry is reported as
`storage_fee_carry_residual`.

## Corrected market rule set (`native-corrected-v1`)

| Field | Corrected | Correction id | Finding |
|---|---|---|---|
| surplus accounting | D1-surplus: ahead surplus rebuilt per source as availability minus acceptance; must-run surplus (in S) is used before VRE surplus (outside S); consumed VRE surplus is gross VRE output; must-run surplus serving the balancing requirement is not generated or paid twice | `p06.d1-surplus-accounting` | review blocker, DEV-BAL-04 |
| ahead / balancing merit key | `(round(price, 2), is_storage, price, input order)`: storage clears after generation in the same 0.01 GBP/MWh band | `p06.storage-after-generation-merit-key` | P5-04 (Q8) |
| down regulation | avoided-cost stack: descending rounded avoided cost (nuclear carries a 100 GBP/MWh dec premium), ties thermal, hydro/biomass, VRE, nuclear, then name; ramp floor `max(previous - alter_limit, 0)` by object identity; hydro/biomass budgets returned; requirement left after the stack is in-dispatch spill. Since A19/A22 a gas or biomass row is split at minimum stable generation: the running range keeps this key (before VRE), the shutdown segment is ranked by the net saving `c - S(H)/H` against VRE (only when the expected downtime H reaches the minimum down time; otherwise last resort). See `r12_economic_downward_order.md` | `p06.avoided-cost-downward-order`, `r12.economic-downward-order` | P3-03 (A19, A22) |
| storage position | one net position per period: stages share the rated power; a store that discharged buys back (need first, then surplus) before it can charge; a store that charged offers no discharge; sales recorded at the net position; `close_period` asserts discharge <= P, no charge with discharge, 0 <= SoC <= E | `p06.storage-net-per-period` | P5-03 |
| storage fee | settled in its own period (no carry) | `p06.storage-fee-per-period` | P5-06 |
| VRE direct electrolysis | none before clearing (electrolysis only consumes surplus) | `p06.no-vre-pre-clearing-skim` | P3-08 |
| storage bid | `cycle_only`: batteries bid `CAPEX / (E * eta_dis * N_max)`, pumped hydro and hydrogen bid 0, oldest tranche first; holding recovery only in investment adequacy | `p06.storage-bid-cycle-only` | P5-04 (Q8) |
| settlement | every accepted supplier of a stage, storage included, is paid the stage's uniform marginal price | `p06.storage-uniform-price-settlement` | P5-05 (A8) |
| VoLL | `market.voll_gbp_per_mwh` | `p06.voll-chronology-parameter` | P5-06 (Q7) |
| interconnector imports | every connection with a positive transfer constraint offers its available import capacity to the day-ahead clearing at the period's counterparty price x bid multiplier; balancing offers only the capacity left; an accepted day-ahead import is reduced at its avoided import price (doctoral: imports only in the balancing stage). See `fx6_day_ahead_imports.md` | `fx6.day-ahead-interconnector-imports` | S-D3 (A16-2) |
| nuclear initial state | every nuclear unit is running before the first period of each model year (no start-up adder in its first offer; baseload at its availability); a unit that was not accepted in a period pays the start-up adder once, when it restarts (doctoral: every unit is off before the first period, so nuclear offers its start-up cost until first accepted, A15 path dependency). See `fx8_nuclear_in_service.md` | `fx8.nuclear-in-service-at-start` | A18 (A15) |

The `cycle_only` basis applies only to the built-in
`dynamic-annual-storage-cost` object (2.0.0); the legacy tariff, the user formula
and external storage modules keep their own bids (`module_defined`).

### Ledger column semantics (C20)

`semantic_metadata` declares them per rule set.  Corrected:
`vre_accepted` is gross VRE output (including surplus consumed by storage,
export and flexible demand), `curtailed` is VRE availability minus that gross
output, `excess` is the non-VRE (must-run) spill, and the two unused quantities
are disjoint (`leftover = excess + curtailed`).  Doctoral: the 0.6.0-alpha.2
declarations (`inflexible_mixed` excess, balancing-stage down regulation).

### Energy balance (C19, decision Q7)

Corrected runs declare `native_corrected_full_node_v1`:

    S + B - D - C - E - X - XS = 0

with S the gross output of every non-storage, non-interconnector source plus
imports and storage discharge, and XS the non-VRE spill; per VRE source,
available = accepted + consumed surplus + curtailed.  The spill a period can
book is capped at the supply the node did not use; a requirement the kernel
would route without supply behind it (the A2 case) is reported as
`phantom_surplus_mwh` and its shortfall as a stress event.  Doctoral runs
declare `default_psm_surplus_node_v1` (P0-4).

## Doctoral rule set: declared deviations

The doctoral rule set reproduces 0.6.0-alpha.2 dispatch bit for bit (96-period
synthetic golden) and reports its known deviations in
`market_rule_diagnostics`: `unrecorded_vre_mwh` (VRE crowded out and not
recorded), `non_vre_double_counted_mwh` (DEV-BAL-04),
`storage_fee_carry_gbp`, `vre_skim_leak_mwh` and
`vre_skim_to_electrolysis_mwh`.

Nuclear path dependency (A15, not a diagnostic column): the doctoral rule set
starts every model year with no unit running, so nuclear offers its start-up
cost until first accepted and then stays on until the year end; its annual
output depends on when the first scarcity period falls
(`fx8_nuclear_in_service.md` section 1, GBP1 example).

## Known approximations (corrected)

* Zero-priced pumped hydro and hydrogen storage dispatch myopically (no water
  value); seasonal value is left to a later round (P2).
* A buy-back does not refund the ahead storage payment (P1, P3-05).
* Storage charging cost and the storage investment test are P0-7's
  (`agent_cashflow`, decision A8 (3)).
* The staged PSM keeps one SoC pool and bids `d = 0`; its storage reports now
  carry `dwell_source = not_tracked_staged_single_pool` and preflight warns
  (`GF_STAGED_DWELL_NOT_TRACKED`) when it is combined with a dwell-based cost
  module (P5-15, numbers unchanged).
