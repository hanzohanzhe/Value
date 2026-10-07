# Kernel corrections in both profiles (R4-1 draft for methodology 0.4)

Status: draft written with the R4-1 construction (DECISIONS A26, 2026-10-08);
to be merged into `core.md` / `national_alternatives.md` (en, zh) when the 0.4
edition is generated.  It describes how the default PSM (`value-bid-at-cost-psm`
6.7.0) clears in both methodology profiles.

The default PSM runs the retained Scheme C kernel under one market rule set per
profile (`p06_default_psm_clearing.md`).  The three rules below hold in both rule
sets (universal corrections).  They are model behaviour, not reporting
conventions: each changes dispatch, storage state, curtailment and unserved
energy.

## 1 Down regulation in the curtailment branch is taken once

When realised demand \(R_t\) is below the forecast \(F_t\), the scheduled output
exceeds demand by \(n_t = F_t - R_t\).  Storage, export and flexible demand absorb
what they can; the remaining requirement \(n_t'\) is taken out of the day-ahead
schedule by down regulation.  In the doctoral rule set the units are reduced in
ascending curtail cost (wind at zero first, as in the thesis); in the corrected
rule set by the avoided-cost stack (`r12_economic_downward_order.md`).

Every unit \(i\) gives \(\min(\Delta_i, n')\), where \(\Delta_i\) is the reduction its
ramp floor allows, and the requirement falls by that amount; once it is zero no
further unit is reduced.  So the total reduction equals the booked requirement:

$$
\sum_i \delta_i = \min\Big(n_t', \sum_i \Delta_i\Big).
$$

Correction id `r41.down-regulation-taken-once`.  The retained kernel cleared the
requirement after a wind unit but not after a hydro, biomass or thermal unit
that met it, so the same amount was reduced again from the next offers (usually
wind) and the demand that energy should have served went unmet.  Example: 15 MW
to remove, hydro first with 20 MW reducible, wind 30 MW next: hydro 20 → 5 MW and
wind stays at 30 MW (the retained kernel also cut wind to 15 MW).  On GBP1 public1
2025 (doctoral profile) the double reduction affected 563 half-hours and 217 GWh.

## 2 One storage position per store and period

Each store \(k\) has one grid-side position per period, shared by the clearing
stages (day-ahead, curtailment or balancing):

$$
0 \le d_{k,t} \le P_k, \qquad 0 \le c_{k,t} \le P_k, \qquad d_{k,t}\,c_{k,t} = 0,
\qquad 0 \le \mathrm{SoC}_{k,t} \le E_k ,
$$

with discharge \(d\), charge \(c\), rated power \(P\) and energy capacity \(E\) (MW
held over the period).

* A later stage offers only the power the earlier stages left
  (\(P_k - d_{k,t}\)); a store that charged in the period offers no discharge.
* A store that discharged and is then asked to absorb surplus first reduces its
  own discharge of the period (buy-back: the withdrawn energy returns to the
  tranche it came from); it charges only when no discharge is left.
* The store's sales of the period are recorded at its net position when the
  period closes, and the close asserts the four conditions above.

Bids, merit order and settlement are those of each rule set; the ahead payment
of a store whose discharge is bought back is not refunded.  How the absorbed
surplus is booked in the doctoral surplus-node boundary
(`default_psm_surplus_node_v1`): netting the forecast surplus takes scheduled
output out of S (`surplus_routing.curtailed`); netting must-run or VRE surplus
lets that surplus serve demand (`to_dispatch`), and VRE surplus then enters S as
VRE output.  Charging is booked as before (`to_storage`).

Correction id `p06.storage-net-per-period`, which the corrected profile has
applied since P0-6 and which R4-1 made universal.  The retained kernel reset a
store's power limit in every stage, so a store could discharge up to twice its
rating in one period and charge and discharge in the same period (on GBP1
public1 2025, 15,653 store-periods charged and discharged, 448 discharged above
rated power).  Example: a 200 MW store gives 200 MW day-ahead; a further 100 MW
balancing requirement is met by the next generator, not by the same store again.

## 3 Must-run surplus serving the balancing requirement is counted once

When must-run nuclear cannot ramp down to the forecast, its surplus
\(s_t = g_t - F_t\) is part of the accepted supply S and is settled day-ahead.
If realised demand is higher (\(R_t > F_t\)), the surplus serves the balancing
requirement first; it is used up without being generated or paid a second time.
VRE surplus outside S that serves the requirement is still dispatched and paid
as balancing energy.

Correction id `r41.must-run-surplus-counted-once`.  Example (VALUE 101
`nuclear_balancing` fixture): 29 MW nuclear, forecast 6 MW below real demand:
nuclear is recorded at 14.5 MWh per half-hour, not 17.5 MWh, and the period
balances.  The ledger column `non_vre_double_counted_mwh` is zero.

## 4 Effect on the shipped doctoral cases

| Case | Before R4-1 | After R4-1 |
|---|---|---|
| VALUE 101 day (D3) | storage gate failed in 10 store-periods (charge and discharge) | all gates pass; annual results published (Q14) |
| VALUE 101 two years (D4) | storage gate failed in 9,343 store-periods | all gates pass; results published |
| GBP1 public1 2025 (D5) | surplus conservation failed in 563 rows; storage gate failed; unserved energy 300.9 GWh in 890 stress periods | all gates pass; unserved energy 78.8 GWh in 487 stress periods (the remaining hidden shortfall of decision A2); results published |

GBP1 2025 also changes by: storage charge 5.05 → 2.42 TWh and discharge 3.66 →
1.75 TWh (no same-period cycling), operating cost £4,317.5 m → £4,287.0 m,
direct emissions 30.91 → 30.68 MtCO2, investment proposals 3,036 → 3,029 MW.
Corrected-profile Runs are unchanged: their rule set already behaved this way.

## 5 What the 0.3 text needs

* The doctoral reproduction profile is no longer "bit for bit" the
  0.6.0-alpha.2 dispatch: it keeps the thesis settings (bid rules, merit order,
  wind curtailed first at zero cost, no loss factors, full availability, the
  original data readings) and applies the universal corrections, these three
  included.
* The declared deviations DEV-BAL-04 and DEV-STO-01 no longer exist; the
  remaining ones (DEV-BAL-01/02/03) are a definition and evidence and explain no
  gate failure (`p04_energy_balance_validation.md`).
