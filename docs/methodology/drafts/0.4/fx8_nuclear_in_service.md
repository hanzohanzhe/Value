# Nuclear start-up state of the default PSM (FX8 draft for methodology 0.4)

Status: draft written with construction unit FX8 (2026-10-06), following
decision A18 of `docs/dev/P0_DECISIONS.md` (and A15 for the doctoral
disclosure). It extends `p06_default_psm_clearing.md` (whose corrected
rule-set table now has a nuclear row) and lists the 0.3 sentences that the
0.4 edition must change. The 0.3 sources (`en/`, `zh/`) stay frozen until the
0.4 edition is generated and reviewed (plan C26).

## 1 The thesis rule and its path dependency (doctoral reproduction, A15)

The default PSM (`value-bid-at-cost-psm`) runs the retained Scheme C kernel
`runtime_compat/modular_simulation_model.py` once per model year
(`run_simulation`, 17,520 periods). The ordinary generator offer is

    b_{i,t} = m c_i + s_i 1[i not in A_{t-1}]

with `A_{t-1}` the units accepted in the day-ahead clearing of the previous
period and `s_i` the start-up adder (`startup_cost`, GBP/MWh). Water and VRE
units have no adder. The thesis kernel starts every model year with
`A_{-1}` empty, so in the first period every gas, biomass and nuclear unit
carries its adder, and a unit keeps carrying it in every period until it is
accepted. Three further rules of the frozen kernel make nuclear output path
dependent:

1. On GBP1 nuclear offers `0 + 500` GBP/MWh while it is off (CCGT
   `0.1 + fuel + carbon + 50`), so an off nuclear unit is the last resource of
   the merit order and is accepted only when every other resource,
   including the CCGT ramp limit, is short.
2. Once accepted, nuclear offers its running cost (0) and is treated as a
   unit that cannot be turned down by more than `alter_limit` per period (500
   MW on GBP1): its acceptance is `max(g_{t-1} - r, remaining forecast)`, so it
   stays on until the end of the year.
3. In a period without any accepted nuclear, the remembered output `g` of
   each nuclear unit is multiplied by 0.99, so a unit accepted late in the
   year starts from a low output and ramps up by `alter_limit` per period.

Nuclear output in the doctoral reproduction therefore depends on when the
first scarcity period of the year falls, not on nuclear availability. GBP1
first model year (golden D5, `docs/dev/GBP1_DOCTORAL_BEFORE_AFTER.md`): at
35aadb3 nuclear was first accepted in period 16,588 (12 December, about 14:00
UTC) and then ran 932 periods, 2.73 TWh; all 30 periods above 1,000 GBP/MWh
fall in that window. After the universal reading corrections A3/A5 (revision
1, accepted by the author in A15) no period is short enough, nuclear is never
accepted in 2025, and the price spikes disappear. This is not a nuclear
correction; it shows that the frozen kernel is sensitive to its boundary
inputs, and that the nuclear output and price spikes of a reproduction run can
appear or vanish as a block after a small input change. The doctoral profile
keeps this behaviour (Q1); a doctoral Run carries the read-time advisory of
`fx8.nuclear-in-service-at-start` (severity high).

## 2 The corrected rule (A18)

Corrected profile only (`value-corrected`; correction id
`fx8.nuclear-in-service-at-start`; rule-set field
`nuclear_initial_state = in_service_at_start`; doctoral value
`off_until_accepted`):

1. **In service at the start.** Every nuclear unit counts as accepted before
   the first period of each model year (`A_{-1}` = the nuclear units;
   `native_corrected.initial_running_rows`). Its first day-ahead offer is its
   running cost without the start-up adder, so it clears first and runs as
   baseload at its availability: on GBP1 public2 the station load factors of
   `p05.firm-availability` (A10/A14), with month-exact generation ends
   (`p05.nuclear-generation-end-month`).
2. **Start-up only after a period off.** The rest of the thesis rule is kept:
   a nuclear unit that was not accepted in a period (refuelling or outage,
   zero availability, or not cleared) adds `startup_cost` to its offer from
   the next period until it is accepted again, and the physical operating
   cost books the start-up term `startup_cost x energy` in the period it
   restarts, once. With the fixed station availabilities of A10 there is no
   refuelling calendar, so on GBP1 nuclear does not stop during the year.
3. **Gas and biomass unchanged.** They keep the thesis rule (off before the
   first period), as before.
4. **Accounting.** The start-up term of the physical operating cost
   (`startup_adder_resource`, P5-06) follows the same running state, so
   nuclear books no start-up cost in the first period of a year.

The method change raises `value-bid-at-cost-psm` to 6.4.0 with
`requires_user_opt_in`: a saved corrected Study needs explicit confirmation
(Q13). The doctoral rule set is unchanged (trajectory bit-identical, golden
D1-D5).

## 3 Sentences of the 0.3 edition to change

| Source (0.3) | Current text | 0.4 text |
|---|---|---|
| `en/national_alternatives.md` line 15 | "where \(c_i\) is composite unit operating cost, \(s_i\) the start-up bid adder, \(\mathcal A_{t-1}\) the previously accepted generator set, and \(m\) defaults to 1. Hydro and renewables have a zero start-up adder." | add after it: "Each model year starts with \(\mathcal A_{-1}=\varnothing\) in the doctoral reproduction, so every thermal and nuclear unit carries its start-up adder until first accepted. Under the corrected methodology nuclear units are in \(\mathcal A_{-1}\): they start the year running and pay the start-up adder only when they restart after a period in which they were not accepted." |
| `zh/national_alternatives.md` line 15 | “其中 \(c_i\) 为综合单位运行成本，\(s_i\) 为启动报价加项，\(\mathcal A_{t-1}\) 为上一期接受机组集合，\(m\) 默认为 1；水电和风光的启动加项取 0。” | 其后加：“论文复现口径中每个模型年从 \(\mathcal A_{-1}=\varnothing\) 开始，火电和核电在第一次被接受之前都带启动加项。修正口径中核电属于 \(\mathcal A_{-1}\)：年初即在运，只有在某期未被接受（换料、停运或未出清）之后重新启动时才加启动加项。” |
| `en/national_alternatives.md` / `zh/national_alternatives.md` (new paragraph after the Native loop, with the A15 disclosure) | not in 0.3 | EN: "Nuclear path dependency (doctoral reproduction). Because an off nuclear unit offers its start-up adder (500 GBP/MWh on GBP1) and an accepted one cannot be turned down by more than its ramp allowance, nuclear output depends on when the first scarcity period of the year occurs: on the GBP1 first model year nuclear runs only from 12 December (2.7 TWh at 35aadb3) or not at all after the input reading corrections. The corrected methodology starts nuclear in service." ZH: “核电路径依赖（论文复现口径）。未运行的核电报价带启动加项（GBP1 为 500 £/MWh），被接受后每期下调又受爬坡量限制，所以核电发电量取决于当年第一次缺电出现的时间：GBP1 第一年中，核电在 35aadb3 只从 12 月 12 日起运行（2.7 TWh），数据读取修正后全年不运行。修正口径中核电开局在运。” |
| `en/r029_cem.md` line 17 / `zh/r029_cem.md` line 17 | "Existing nuclear retains positive initial output from its source parameters." | unchanged (R029 event accounting); add a cross-reference to the national chapter for the default PSM rule. |

## 4 Numbers

VALUE 101 (golden C1-C8): the VALUE 101 fleet has no nuclear unit, so
dispatch, prices and costs are unchanged (identity zone only).

GBP1 first model year, corrected profile, local GBP1 public2 (new golden case
C9; numeric report `docs/dev/p0-reports/fx8-golden/C9-r1.json`; acceptance
table in `docs/dev/GBP1_CORRECTED_LOCAL_ACCEPTANCE.md` section 10):

| Quantity (2025) | before A18 (6.3.0) | after A18 (6.4.0) | change |
|---|---:|---:|---:|
| Nuclear (TWh) | 2.02 (first accepted in period 16,593, 927 periods) | 38.26 (every period from period 0) | +36.24 |
| Nuclear vs Energy Trends 5.1, 2023-2024 supplied about 37.3 TWh | -95 % | +2.5 % (within +-10 %) | |
| CCGT / OCGT (TWh) | 101.41 / 0.95 | 67.53 / 1.47 | -33.89 / +0.52 |
| Curtailment (TWh) | 0.43 | 1.74 | +1.31 |
| Imports / exports (TWh) | 1.56 / 0.41 | 1.38 / 1.51 | -0.18 / +1.10 |
| Period price mean / max (GBP/MWh, Q6 average period cost) | 24.30 / 74.06 | 16.23 / 46.30 | -8.07 / -27.76 |
| Headline operating / system cost (GBP m) | 5,711.6 / 28,682.8 | 3,880.9 / 26,852.1 | -1,830.7 |
| Direct emissions (MtCO2, authoritative factors) | 40.58 | 27.56 | -13.02 |
| Investment proposals (MW) | 3,054.8 | 2,810.5 | -244.3 |

Nuclear output equals its availability ceiling (five stations, weighted load
factor 0.733), so it never stopped; with no stop the start-up adder never
applies, and the year is identical to the FX7 diagnostic run with nuclear
`startup_cost` = 0. The difference between the two rules appears only after
an outage, where A18 still charges the start-up cost once (toy tests in
`tests/test_fx8_nuclear_in_service.py`).

Wording for 0.4: the corrected nuclear numbers may now be written ("nuclear
runs as baseload at station availability; GBP1 public2 2025: 38.3 TWh, +2.5 %
against Energy Trends 5.1"), stating that GBP1 public2 is a local revision
that is not published (A16-7).
