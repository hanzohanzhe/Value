# Interconnector imports in the day-ahead clearing (FX6 draft for methodology 0.4)

Status: draft written with construction unit FX6 (2026-10-06), following decision
A16-2 of `docs/dev/P0_DECISIONS.md` (four-role finding S-D3). It extends
`p06_default_psm_clearing.md` (whose corrected rule-set table now has an
interconnector row) and lists the 0.3 sentences that the 0.4 edition must
change. The 0.3 sources (`en/`, `zh/`) stay frozen until the 0.4 edition is
generated and reviewed (plan C26).

## 1 Where imports happen in the thesis kernel (doctoral reproduction)

The default PSM (`value-bid-at-cost-psm`) runs the retained Scheme C kernel
`runtime_compat/modular_simulation_model.py`. Each period it receives one
`Connection` object per country with two inputs, set by
`kernel_boundary.assign_period` from `market.<country>.profile` and
`market.<country>.price`:

* `transfer_constraint` (MW, signed): positive = import capability,
  negative = export capability, zero = no exchange;
* `external_price` (GBP/MWh): the counterparty price of the period.

The thesis rule (`interconnector_import_stage = balancing_residual_only`):

| Stage | Function | What a connection does |
|---|---|---|
| Day-ahead clearing | `ahead_market_bidding(generators, batterys, ...)` | Nothing. The function receives no connection; the forecast is met by generator offers and storage tranches only. |
| Real time, realised demand below forecast | `curtailment_market_bidding` (`store_service_three`) | A connection with a negative constraint exports surplus at a positive price (descending price). A positive constraint does nothing. |
| Real time, realised demand at or above forecast | `balancing_market_bidding` | Every connection with a constraint >= 0 becomes an import offer `(connection, external_price x bid multiplier, transfer_constraint)` in the balancing merit order, together with the marginal and later generators and storage tranches aged at least 2 periods. It can serve only the residual upward requirement (realised minus forecast demand, after the ahead surplus). An accepted import is added to the final dispatch (`import_mwh`), paid through the balancing fee and booked as the import payment. A negative constraint exports surplus at a positive price. |

So under the doctoral reproduction an import can appear only in a period whose
realised demand exceeds the day-ahead schedule, and only for the part of that
gap that cheaper domestic up-regulation and aged storage did not cover. A
positive "import availability" has no effect in a period with realised demand
at or below forecast; in the VALUE 101 one-day lesson no period has realised
demand above forecast, so no import appears whatever the France inputs are
(the observation behind S-D3).

**GBP1 doctoral numbers.** The GBP1 first model year (golden case D5,
`docs/dev/GBP1_DOCTORAL_BEFORE_AFTER.md`) imports 0.336 TWh after the
universal reading corrections A3/A5 (1.548 TWh at 35aadb3, mostly the zero-priced
Netherlands line). All of it comes from the balancing stage: on the FX6 code the D5 run
(digest identical to its golden revision, identity zone only) imports
335,895 MWh in 1,130 periods, and every one of those periods has realised
demand above forecast demand (9,125 such periods in the year); no period with
realised demand at or below forecast imports anything. Per country the D5
imports are Norway 164.2, Belgium 53.0, Netherlands 48.4, Ireland 44.5 and
France 25.8 GWh. The same holds for the corrected profile before FX6 (section
4): 1,301 import periods, all with realised above forecast demand.

## 2 The corrected rule (A16-2)

Corrected profile only (`value-corrected`; correction id
`fx6.day-ahead-interconnector-imports`; rule-set field
`interconnector_import_stage = day_ahead_offer_then_balancing_residual`):

1. **Day-ahead offer.** Every connection with a positive transfer constraint
   offers its available import capacity `transfer_constraint` (MW) to the
   day-ahead clearing at `external_price x bid multiplier` (the same price
   the balancing stage has always used). The offer enters the same merit
   order as domestic generation and storage under the corrected merit key
   `(round(price, 2), is_storage, price, input order)`: at an equal 0.01
   GBP/MWh band domestic generation clears first, then the import, then
   storage. An import has no ramp limit and no start-up adder. Under the
   corrected uniform-price settlement an accepted import is paid the stage's
   marginal price, and an import can be the marginal offer.
2. **No double counting.** The balancing stage offers only
   `max(transfer_constraint - day-ahead import, 0)` of each connection, so the
   import of a period never exceeds its available capacity.
3. **Down regulation.** When realised demand is below forecast, an accepted
   day-ahead import is part of the avoided-cost down-regulation stack at its
   avoided import price (`external_price`, no bid multiplier); at an equal
   rounded price it is reduced after thermal and before hydro/biomass, VRE and
   nuclear (the order of `network_method_rules.DEC_CLASSES`, where an import
   follows fuel). Reducing an import pays no curtailment fee: the energy is
   simply not bought.
4. **Exports unchanged.** A negative constraint is export capability, used as
   before in the curtailment and balancing branches.
5. **Ledger.** The ahead clearing declaration lists each import offer
   (`ahead:i:<index>:<connection>`, `resource_kind` import, with the
   counterparty price); the `orders` table books it as an `ahead_offer` row
   (offered = capacity x 0.5 h, accepted = the period's final import, status
   accepted / partially accepted / rejected); the import payment diagnostic
   covers day-ahead and balancing imports; the market replay draws the import
   in the ahead supply curve. The energy balance is unchanged in form: an
   import is supply.

The doctoral rule set is unchanged (trajectory bit-identical, golden D1-D5).
The method change raises `value-bid-at-cost-psm` to 6.3.0 with
`requires_user_opt_in`: a saved corrected Study needs explicit confirmation
(Q13).

## 3 Sentences of the 0.3 edition to change

| Source (0.3) | Current text | 0.4 text |
|---|---|---|
| `en/national_alternatives.md` line 68 (Native loop) | "Construct generator and storage-batch offers; stably sort by price" | "Construct generator and storage-batch offers (corrected methodology: also one import offer per interconnector with positive capacity, at the period's counterparty price); stably sort by price" |
| `en/national_alternatives.md` lines 76-77 | "Merge the marginal and subsequent generators, batches aged at least 2 periods, and import offers" | "Merge the marginal and subsequent generators, batches aged at least 2 periods, and import offers (corrected methodology: the import capacity the ahead schedule left)" |
| `zh/national_alternatives.md` line 67 | “生成机组与储能批次报价，稳定地按价格升序排列” | “生成机组与储能批次报价（修正口径另加每条正容量互联线的进口报价，按当期对侧价格），稳定地按价格升序排列” |
| `zh/national_alternatives.md` line 75 | “合并边际及后续机组、年龄至少2期的储能和进口报价” | “合并边际及后续机组、年龄至少2期的储能和进口报价（修正口径只报日前未用完的进口容量）” |
| `en/national_alternatives.md` / `zh/national_alternatives.md` (new paragraph after the Native loop) | not in 0.3 | EN: "Interconnector imports. In the doctoral reproduction an import is offered only in the balancing branch, for the requirement left when realised demand exceeds the ahead schedule. Under the corrected methodology each interconnector with a positive transfer limit also offers that capacity to the ahead clearing at the period's counterparty price; the balancing branch offers only the capacity left, and an accepted ahead import is reduced at its avoided import price in the downward branch." ZH: “互联线进口。论文复现口径中，进口只在平衡分支报价，用于实际需求超出日前计划后的剩余缺口。修正口径中，每条正向容量的互联线还按当期对侧价格把该容量报入日前出清；平衡分支只报剩余容量，下调分支按进口避免成本减少已接受的日前进口。” |
| `en/datasets.md` line 158 / `zh/datasets.md` line 158 | "positive values assign import capacity and negative values assign export capacity" | add: "Under the corrected methodology the import capacity is offered to the day-ahead clearing; under the doctoral reproduction only to the balancing stage (Chapter on national dispatch)." / “修正口径中进口容量进入日前出清；论文复现口径中只进入平衡环节（见全国调度章）。” |
| `VALUE_METHODOLOGY.md` section 4 ("Interconnectors are external boundary offers ...") | describes the staged PSM | unchanged; the staged PSM already clears imports in its ahead market at the period price. |

## 4 Numbers

VALUE 101 (golden C1-C6, corrected): the France boundary offers 12 MW at 82
GBP/MWh, dearer than the CCGT (66.5 GBP/MWh including its start-up adder), so
the day-ahead import offer is rejected in every period and the two-year runs
also import nothing; dispatch, prices and costs are unchanged. C1-C4 gained a
revision for the import offer rows (orders, clearing declarations); C5/C6 are
summary-trace runs and changed only in identity.

GBP1 first model year, corrected profile, on a locally rebuilt GBP1 public2
(not published; same frozen project as D5 with `methodology.profile =
value-corrected`), before and after FX6:

| Quantity (2025) | before FX6 (6.2.0) | after FX6 (6.3.0) | change |
|---|---:|---:|---:|
| Imports, total (TWh) | 0.331 | 1.560 | +1.229 |
| Norway / Belgium / Netherlands / Ireland / France (GWh) | 130.3 / 66.2 / 44.6 / 67.9 / 22.4 | 612.4 / 285.6 / 255.5 / 240.8 / 166.2 | |
| Periods with an import | 1,301 (all with realised > forecast demand) | 2,837 (1,389 with realised > forecast) | +1,536 |
| CCGT / OCGT generation (TWh) | 102.722 / 0.846 | 101.449 / 0.941 | -1.273 / +0.095 |
| Exports (TWh) | 0.393 | 0.411 | +0.018 |
| Mean period price (GBP/MWh, average period cost, Q6) | 24.45 | 24.30 | -0.15 |
| Highest period price (GBP/MWh) | 100.31 | 74.06 | -26.24 |
| Operating cost, headline (GBP m) | 5,738.82 | 5,713.24 | -25.58 |
| System cost, headline (GBP m) | 28,709.98 | 28,684.40 | -25.58 |
| Recorded blackout / stress events | 0 / 0 | 0 / 0 | 0 |
| Raw energy-balance residual (sum of absolute values, MWh) | 4.2e-8 | 4.3e-8 | numerical noise |

Imports in 2025 rise roughly fivefold, mostly from Norway (the counterparty
with the lowest mean price, 126.5 GBP/MWh on the corrected reading), in the
periods when a counterparty price was below the marginal domestic offer; 0.774 TWh
of the 1.560 TWh falls in periods whose realised demand did not exceed the
forecast, where the thesis rule could not import at all. They displace about 1.3 TWh of CCGT.
OCGT rises slightly (0.1 TWh): a path effect of the CCGT ramp state, not of
the import offer itself. The numbers are a local check on an unpublished
pack (decision A16-7 runs the corrected GBP1 year acceptance separately);
they are not a calibration.
