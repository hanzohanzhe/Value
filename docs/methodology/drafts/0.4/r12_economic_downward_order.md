# Economic down-regulation order of the default PSM (R1-2 draft for methodology 0.4)

Status: draft written with construction unit R1-2 (2026-10-07), following
decisions A19 and A22 of `docs/dev/P0_DECISIONS.md`. It replaces the
"down regulation" row of the corrected rule-set table in
`p06_default_psm_clearing.md` for gas and biomass units. The 0.3 sources
(`en/`, `zh/`) stay frozen until the 0.4 edition is generated and reviewed
(plan C26). Restart values: `docs/dev/REFERENCE_STATISTICS_FOR_AUTHOR_REVIEW.md`
section 4 (author-reviewed in A22), stored in
`gridform_core/data/thermal/value_thermal_restart_v1.json`.

## 1 What changes and why

When realised demand is below the day-ahead forecast, the default PSM
(`value-bid-at-cost-psm`) runs its curtailment branch: storage, exports and
flexible demand absorb the surplus first (decision Q5 of P0-6), and what is
left is removed from the accepted day-ahead schedule ("down regulation").

* **Thesis (doctoral reproduction, unchanged, Q1).** Accepted rows are reduced
  in ascending `curtail_cost`; VRE (`curtail_cost` 0) is curtailed first and
  gas keeps running (review finding P3-03).
* **P0-6 corrected rule (S7), now withdrawn by A19.** Rows were reduced in
  descending avoided cost (`gen_cost`), so every gas or biomass unit was turned
  down to its ramp floor before any VRE was curtailed. This silently assumed
  that reducing thermal output is always cheaper than curtailing wind.
* **A19/A22 corrected rule.** The cost of reducing thermal output is decided
  by two things together: the short-run cost the reduction avoids (fuel,
  carbon and variable cost) and the restart cost incurred when units have to
  shut down. That cost is compared with VRE curtailment (cost 0); neither side
  is assumed to be dearer.

## 2 The rule

Corrected profile only (`value-corrected`; correction id
`r12.economic-downward-order`; rule-set field
`downward_restart_economics = restart_cost_vs_avoided_cost_v1`; doctoral value
`not_modelled`; `value-bid-at-cost-psm` 6.5.0, method change requiring
confirmation of saved Studies, Q13).

For a gas (CCGT, OCGT) or biomass row `k` of the accepted day-ahead schedule
in period `t`, with accepted output `P_k` and ramp floor
`F_k = max(g_{k,t-1} - alter_limit_k, 0)`:

* `c_k` = `gen_cost` = base + fuel + carbon + `unit_time_cost` (VOM), GBP/MWh,
  the short-run cost avoided per MWh not generated;
* `m_k` = minimum stable generation (fraction of online capacity);
* online capacity = `P_k`: the aggregate fleet has no commitment state, so the
  units scheduled day-ahead are taken as online and fully loaded;
* `S_k(H)` = restart cost per MW of capacity shut down, GBP/MW (not per MW
  of output);
* `MDT_k` = minimum down time, h;
* `H` = expected downtime of a shutdown decided in period `t`:

      H = (1 + n_t) x 0.5 h,

  where `n_t` is the number of consecutive later periods `t+1, t+2, ...` whose
  day-ahead forecast is in surplus, i.e. forecast demand <= forecast VRE
  availability + nuclear availability (no thermal output needed). The current
  period counts once because down regulation is being decided precisely
  because it is in surplus. The forecast is the kernel's own day-ahead
  information (forecast demand series; VRE and nuclear availability from the
  corrected site-CF and firm-availability arrays, p05). Without those arrays
  (unit sessions) `H` is the current period only.

The row is split into two segments:

1. **Running range** `max(P_k - max(F_k, m_k P_k), 0)` MW: the units stay above
   minimum stable generation and nothing has to restart. Reducing it saves
   `c_k > 0` per MWh, so it is ranked by `c_k` like the P0-6 stack and always
   comes before VRE.
2. **Shutdown segment** `max(min(P_k, m_k P_k) - F_k, 0)` MW: reducing below
   minimum stable generation needs units to stop and restart later. The
   running range is always taken first, so when this segment is reached every
   online unit runs at minimum stable generation, `m_k` MW of output per MW of
   capacity. Removing `x` MW of output therefore shuts `x / m_k` MW of
   capacity: over `H` hours it saves `c_k x H` and costs `S_k(H) x / m_k` at
   restart. The net saving per MWh not generated is

      a_k(H) = c_k - S_k(H) / (m_k H).

   (Unit check: `S / m` is GBP per MW of output removed; divided by `H` it is
   GBP/MWh. Decision A22 wrote `c_k - S_k/H`, which charges the restart per MW
   of output instead of per MW of capacity and understates it by `1/m_k`;
   corrected after the R1-2 review, author confirmation pending, see
   `docs/dev/P0_DECISIONS.md` A22a.)

   * `H >= MDT_k` and `a_k(H) > 0`: ranked by `a_k(H)`, before VRE;
   * `H >= MDT_k` and `a_k(H) <= 0`: after VRE (and before nuclear at an equal
     rounded value);
   * `H < MDT_k`: a unit may not shut down for less than its minimum down
     time; the segment is used only as a last resort, after every other
     resource, so a surplus the P0-6 stack could remove is never left in the
     node.

All other rows keep the P0-6 key: VRE at its own avoided cost (`gen_cost`,
0.0001 GBP/MWh in the packs, i.e. 0.00 after rounding), imports at the
counterparty price (FX6), hydro and nuclear (with its 100 GBP/MWh dec premium)
as before. Segments are sorted by `(-round(cost, 2), class rank, name, segment)`
with a stable sort (input order last); shutdown segments carry class rank 2.5
(after VRE, before nuclear), so a net saving that rounds to the VRE value goes
to VRE ("a > 0" is strict). Hydro and biomass get the reduced energy back into
their annual budget; requirement left after the whole stack is in-dispatch
spill (unchanged).

Restart values (A22, restated in the model's 2025 price base by A24-4; GBP
per MW of capacity per start; section 2a):

| Technology | S hot / warm / cold (2025 GBP, in use) | A22 value (2024 GBP) | Start class by H | m | MDT | Break-even H* = S/(m c) (GBP1 c) |
|---|---|---|---|---|---|---|
| CCGT | 113.7 / 134.4 / 155.0 | 110 / 130 / 150 | hot H < 12 h, warm 12-48 h, cold > 48 h | 50 % | 6 h | 4.13 h (c = 55.07) |
| OCGT | 175.7 | 170 | - | 50 % | 0.5 h | 4.69 h (c = 74.92) |
| Biomass | 129.2 | 125 | - | 35 % | 6 h | 4.34 h (c = 85.0) |

Because `MDT >= H*` for CCGT and biomass, a CCGT or biomass shutdown that is
allowed at all (`H >= 6 h`) always has `a > 0` and goes before VRE (at the GBP1
costs; a cheaper unit with `c < S/(m MDT)`, e.g. CCGT below 37.9 GBP/MWh, would
still curtail wind first); for OCGT the comparison decides (`H >= 5 h`, i.e.
at least ten surplus periods).

### 2a Price base of the restart costs (decision A24-4)

The restart costs are compared with the avoided cost `c` (fuel, carbon and
variable cost), so both must be in the same money. VALUE states every amount
in start-year money (decision A6), and every shipped study starts in 2025
(R029 2025-2034, VALUE 101 2025-2026, GBP1 2025); the dated cost inputs are
declared in 2025 GBP (storage technology catalogue `currency_base_year`
2025, pumped-hydro CAPEX, policy budgets). The fuel and carbon prices carry no
price year of their own and are therefore 2025 money. The A22 values were
compiled in 2024 GBP (reference statistics 4.2), so they are restated with the
UK CPI (ONS D7BT, 2015 = 100, annual averages):

    S_2025 = round(S_2024 x CPI_2025 / CPI_2024, 1),  CPI_2025 / CPI_2024 = 138.4 / 133.9 = 1.0336

(correction `r33.restart-cost-price-base-2025`; default PSM 6.6.0 and staged
PSM 1.6.0, both opt-in under Q13). The table
`gridform_core/data/thermal/value_thermal_restart_v1.json` keeps the 2024
values, the two index values, the factor and the source, and the loader checks
that the values in use are the restated 2024 values. The 2025 index is the
mean of the twelve 2025 monthly values as known when the table was revised and
still has to be checked once against the ONS series (reference statistics
4.2a); 0.1 index point changes every value by 0.07 %. The conversion moves
each break-even downtime `H* = S/(m c)` up by 3.4 % (CCGT 3.99 -> 4.13 h,
OCGT 4.54 -> 4.69 h, biomass 4.20 -> 4.34 h at the GBP1 costs); with
half-hour periods an OCGT still shuts down first from `H = 5 h`.

The restart cost ranks the stack only. The cost accounts are unchanged: the
physical operating cost keeps its start-up term (thesis `startup_cost` adder
of a unit that was not running in the previous period, P5-06).

## 3 Worked example

GBP1 CCGT parameters (`c = 55.07` GBP/MWh, `m = 50 %`, `S = 113.7` GBP/MW hot,
`MDT = 6 h`). Period `t`: CCGT accepted 400 MW (ramp floor 0), wind accepted
500 MW; after storage, exports and flexible demand 300 MW still has to be
removed.

* Running range = 400 - 0.5 x 400 = 200 MW at 55.07 GBP/MWh: reduced first in
  every case (saves 200 x 0.5 h x 55.07 = GBP 5,507).
* The remaining 100 MW must come from the CCGT shutdown segment (200 MW of
  output, i.e. all 400 MW of online capacity at 50 %) or from wind. Taking
  100 MW of output from the CCGT means shutting 100 / 0.5 = 200 MW of
  capacity: a restart bill of 200 x S against a saving of 100 x 55.07 x H.

| Forecast after `t` | H | Shutdown allowed? | a(H) | Result |
|---|---|---|---|---|
| next period not in surplus | 0.5 h | no (H < 6 h) | - | wind curtailed 100 MW; CCGT stays at 200 MW |
| 5 more surplus periods | 3 h | no (H < 6 h) | (55.07 - 113.7/1.5 = -20.7) | wind curtailed 100 MW |
| 11 more surplus periods | 6 h | yes | 55.07 - 113.7/3 = 17.2 > 0 (restart GBP 22,740 < saving GBP 33,042) | CCGT reduced to 100 MW; no wind curtailed |
| 27 more surplus periods | 14 h | yes (warm start, S = 134.4) | 55.07 - 134.4/7 = 35.9 > 0 | CCGT reduced to 100 MW |

Under the thesis rule the 300 MW would have come from wind (curtail cost 0);
under the withdrawn P0-6 rule from the CCGT (400 -> 100 MW) whatever H.

An OCGT example (`c = 74.92`, `S = 175.7`, `m = 50 %`, `MDT = 0.5 h`, so the
restart costs `S/m = 351.4` GBP per MW of output removed): with `H = 0.5 h`,
`a = 74.92 - 702.8 = -627.9` (wind first); with `H = 2 h`, `a = -100.8` (wind
first); with `H = 3 h`, `a = -42.2` (wind first: shutting 20 MW of capacity to
remove 10 MW of output costs GBP 3,514 at restart and saves GBP 2,248); with
`H = 5 h`, `a = +4.6` (OCGT shuts down first).

## 4 Outputs

Every corrected market year records
`market.extensions.downward_restart_economics`
(`value.downward-restart-economics/v1`): the rule, the restart table id and
sha256, the outlook basis and VRE coverage, the number of periods with down
regulation and their mean `H`, and the MWh and period counts by segment
(`thermal_running_range`, `thermal_shutdown_net_saving`,
`thermal_shutdown_after_vre`, `thermal_shutdown_below_min_down_time`, `vre`,
`import`, `hydro`, `nuclear`, `other`).

## 5 0.3 text to change in the 0.4 edition

* `p06_default_psm_clearing.md`, corrected rule-set table, row "down
  regulation": add the gas/biomass split of this draft (done in the draft).
* The 0.3 `en/core.md` / `zh/core.md` realisation paragraph ("Their downward
  capacity is `q_a^0`, priced at the negative of the curtailment cost, which
  defaults to 0" / "下调容量为 `q_a^0`，价格取弃电成本的相反数，缺省为 0")
  describes the staged copperplate PSM and is not changed by this rule. The
  default-PSM chapter (methodology editor hand-off, chapter 5 "Native") must
  describe the two rule sets: thesis curtail-cost order; corrected
  economic order of this draft.

## 6 Numbers (unit R1-2 re-runs, corrected profile)

Before = the code at `c9c1cc1` (P0-6 avoided-cost stack, thermal before VRE);
after = this rule. Golden numeric reports: `docs/dev/p0-reports/r12-golden/`.

| Run | Down-regulation periods | Mean H | Reduced by segment (MWh) | Change |
|---|---:|---:|---|---|
| VALUE 101 two_year (C5), 2025 | 1 | 0.5 h | thermal running range 0.16, VRE 0.84 | CCGT +0.16 MWh, curtailment +0.16 MWh, emissions +0.06 tCO2, system cost +GBP 10.4 (one period) |
| VALUE 101 two_year (C5), 2026 | 2 | 0.5 h | VRE 8.37 | none |
| GBP1 public2 2025 (C9, local only) | 357 | 3.77 h | thermal running range 190.7 (2 periods), hydro 91,515, VRE 21,996, import 3,750 | none: curtailment 1.735 TWh, CCGT 67.53 TWh, OCGT 1.47 TWh, emissions 27.56 MtCO2, headline operating cost GBP 3,880.9 m all bit-identical |

R3-3 (A24-4) restated the restart costs in 2025 GBP. The reference runs do not
change: C1-C6 (VALUE 101), C9 (GBP1 public2 2025) and C10 (R029 public2 2025)
are bit-identical apart from the restart table sha256, because no shutdown
segment is priced against VRE in them (golden revisions C1-C4 r16/r16/r17/r16,
C5 r15, C6 r13, C9 r5, C10 r1).

Why so small: down regulation (realised demand below the forecast after
storage, exports and flexible demand) occurs almost only in periods whose
day-ahead schedule already has no gas, so the gas rows that the two rules
order differently are rarely present. Where gas is present, the reduction
needed stays within its running range, which both rules reduce first. The
difference between the rules appears only when a reduction would have to go
below minimum stable generation (VALUE 101 2025, one period: the withdrawn
rule took the CCGT below 50 %, the new rule curtails 0.16 MWh of solar
instead because H = 0.5 h is below the 6 h minimum down time).
