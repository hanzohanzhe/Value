# Economic down-regulation order of the network models (R3-2 draft for methodology 0.4)

Status: draft written with construction unit R3-2 (2026-10-07), following
decisions A19, A22, A22a and A24 item (3) of `docs/dev/P0_DECISIONS.md`. It
amends section 1 of `p08_network_economics.md` (dec prices and class order of
the staged / zonal path) for gas and biomass units, and applies to the network
models the rule that `r12_economic_downward_order.md` introduced for the
default PSM. The 0.3 sources (`en/`, `zh/`) stay frozen until the 0.4 edition
is generated and reviewed (plan C26). Restart values: reference statistics
section 4 (author-reviewed in A22), file
`gridform_core/data/thermal/value_thermal_restart_v1.json` (unchanged).

## 1 What changes and why

The staged PSM (`value-staged-bid-at-cost-psm`) schedules the day ahead on a
copper plate and then balances the realised period, either on a copper plate
(`value-copperplate-balancing`) or in the zonal transport LP
(`value-zonal-redispatch-balancing`). Its balancing dec bids follow the
balancing-mechanism convention: the balancer accepts the highest dec price
first, and an accepted dec pays volume x price back.

* **P0-8b (rule set `network-economic-v1`).** A gas or biomass unit offered
  its whole ahead schedule as one dec at its avoided cost
  `c = SRMC x m_dec - support`. Since `c > 0` and an unsubsidised VRE dec is
  priced at 0, every gas or biomass unit was reduced to zero before any VRE
  was curtailed, whatever the restart cost. This is the "fuel before VRE"
  order that A19 withdrew for the default PSM.
* **R3-2 (rule set `network-economic-v2`).** The reduction of a thermal unit
  is priced by the short-run cost it avoids and by the restart cost of the
  units that must shut down, and compared with the VRE dec price on price
  alone. Neither side is assumed dearer (A19).

Corrected profile only in practice: the staged, zonal, DC and AC modules are
not available in the doctoral reproduction profile (Q3). Correction id
`r32.network-economic-downward-order`; `value-staged-bid-at-cost-psm`
1.4.0 -> 1.5.0, a method change that saved Studies must confirm (Q13).

## 2 The rule

For a gas (CCGT, OCGT) or biomass unit `k` scheduled `P_k` MWh in the ahead
stage of period t (its online capacity: an aggregate unit scheduled ahead is
online and fully loaded, as in R1-2):

| Segment | Volume (MWh) | Dec price (GBP/MWh) | Dec class |
| --- | --- | --- | --- |
| running range | `(1 - m_k) P_k` | `c_k` | `fuel` |
| shutdown, `H >= T_k` | `m_k P_k` | `a_k(H) = c_k - S_k(H) / (m_k H)` | `fuel_shutdown` |
| shutdown, `H < T_k` | `m_k P_k` | `min(a_k(H), lowest other dec band of the period - 0.01)` | `fuel_shutdown_last_resort` |

* `c_k = SRMC_k x market.dec_multiplier - support_k` is the P0-8b dec price.
* `m_k` minimum stable fraction (CCGT 0.50, OCGT 0.50, biomass 0.35),
  `S_k(H)` restart cost per MW of capacity (CCGT 110 / 130 / 150 GBP/MW hot /
  warm / cold, hot below 12 h, warm up to 48 h; OCGT 170; biomass 125),
  `T_k` minimum down time (6 h / 0.5 h / 6 h). Removing 1 MW of output at
  minimum stable generation shuts `1/m_k` MW of capacity, which costs
  `S_k / m_k` at restart and saves `c_k` per hour of downtime (A22a).
* `H` is the expected downtime: `H = (1 + n_t) x period hours`, where `n_t`
  counts the consecutive later periods whose forecast demand is covered by
  the declared VRE and nuclear availability of the staged chronology (no
  thermal output needed). The current period counts as one because it is
  being balanced down. This is the outlook of R1-2 on the staged clock; under
  zonal balancing the forecast is the aligned national forecast.
* Technology mapping: the staged technology names CCGT, OCGT, `gas`
  (CCGT unless the asset id names OCGT) and `bio*` (`bio_and_waste`); other
  fuel units (DSR, oil) keep one block at `c`; nuclear and run-of-river hydro
  are unchanged.

Ordering. The copperplate balancer sorts dec groups by the 0.01-rounded price,
then by the shared class order `fuel, import, storage, run_of_river, vre,
fuel_shutdown, nuclear, fuel_shutdown_last_resort`, then by the exact price;
the zonal LP minimises `-price x volume` and, at an exact primary tie, adds the
class weights of the physical tie phase (fuel 0, import 0.5, run-of-river 2,
VRE 3, fuel_shutdown 3.5, nuclear 4, last resort 5, against storage
throughput 1). Consequences:

* the running range (`c > 0`) is always reduced before VRE;
* a shutdown comes before VRE only when `a_k(H)` is above the VRE dec price
  (GBP 0 for merchant VRE, `-support` for supported VRE); at an equal price
  VRE goes first, so "a > 0" is strict (A22);
* because `a_k(H) < c_k`, a unit's shutdown segment is never taken before its
  own running range, also in the LP;
* below the minimum down time the shutdown is not allowed while any other
  down regulation is left (A22), but it stays available as a last resort so
  that a zone without other decs does not become infeasible (as in R1-2,
  deviation 6). Its price is the lower of its net saving and one 0.01 band
  below every other dec of the period; it is settled at that price.

Settlement and costs. An accepted dec pays volume x its bid price back, so a
shutdown at `a < 0` is paid `|a|` per MWh: the restart cost it bears net of
the fuel it saves. The physical operating cost of the period is unchanged in
kind (fuel, carbon and variable cost of the final dispatch; restart costs are
not booked, as in R1-2).

## 3 Worked examples (toys of `tests/test_r32_network_economic_dec.py`)

OCGT 20 MWh scheduled at `c = 75`, wind 30 MWh, 25 MWh to reduce:

| H | a(H) | Result |
| --- | --- | --- |
| 5 h | 75 - 170 / (0.5 x 5) = 7 | OCGT 20 -> 0, wind 30 -> 25 (restart GBP 1,700 < saving GBP 3,750) |
| 3 h | 75 - 170 / 1.5 = -38.3 | OCGT 20 -> 10 (running range only), wind 30 -> 15 |
| P0-8b | — | OCGT 20 -> 0, wind 30 -> 25 regardless of H |

The same numbers hold in a two-zone LP where the north-south boundary forces
the north down by 25 MWh while a GBP 90 southern unit covers the south, and
the independent PuLP/CBC oracle finds the same dispatch. A CCGT at `c = 55`
with H = 3 h (< 6 h) reduces its running range, then all wind, and only then
part of its shutdown segment.

## 4 Outputs

* Rule record (`market/metadata.json` `semantic_metadata.network_method_rules`
  and the year result): `rule_set_id network-economic-v2`,
  `thermal_shutdown restart_cost_vs_avoided_cost_v1`, the eight-class order,
  the restart table id and sha256, and the formulas.
* Balancing bids: the running range keeps the bid id `...:down:<asset>`; the
  shutdown segment is `...:down-shutdown:<asset>` with its net saving,
  expected downtime, start class, restart cost, minimum stable fraction and
  minimum down time in the bid provenance; both appear in the orders and
  redispatch settlement ledgers.
* Every staged market year records `extensions.downward_restart_economics`
  (`value.network-downward-restart-economics/v1`): down-regulation periods,
  mean H (of those periods and of the year), and the accepted dec MWh and
  periods by segment (thermal running range, shutdown with positive saving,
  shutdown after VRE, shutdown below the minimum down time, VRE,
  interconnector, storage, hydro, nuclear, other).

## 5 Numbers

* VALUE 101 network, staged copperplate smoke (golden C7 r13): no balancing
  dec occurs; only the rule record and the new extension change.
* VALUE 101 network, zonal day (golden C8 r15): 42 down-regulation periods,
  all VRE decs (257.1 MWh), mean H 0.93 h. The CCGT is never balanced down
  (as before); each of its 40 dec bids is now two bids (running range at
  66.5 GBP/MWh, shutdown last resort at about -373.5 GBP/MWh since H < 6 h),
  so the bid ledgers gain 40 rows. Dispatch, curtailment and costs move only
  by solver tolerance (at most 1.4e-7 MWh and 9.3e-6 GBP). Numeric reports:
  `docs/dev/p0-reports/r32-golden/`.

## 6 Edits for the 0.3 text

* `transmission.md` / `core.md` (en, zh), the dec-price table: split the
  "fuel units" row into gas/biomass (two segments, this draft) and other fuel
  units (one block at `SRMC x m_dec - support`).
* The class order sentence: insert `fuel_shutdown` after VRE and
  `fuel_shutdown_last_resort` after nuclear; physical tie weights 3.5 and 5.
* The rule-set id in the mathematical reference: `network-economic-v2`.

## 中文摘要

- 网络模型（staged copperplate 与 zonal redispatch，只在修正口径可用）原来把燃气、生物质机组的整个日前出力按避免成本 c 一次性报 dec，c > 0 而无补贴风电 dec 价为 0，所以总是先把火电降到零再弃风。R3-2 按 A19/A22/A22a 改为两段：最小稳定出力以上的不停机段仍按 c 报价，先于弃风；停机段按净节省 a(H) = c − S(H)/(m·H) 报价，与风电 dec 价（0 或 −补贴）按价格比较，同价时风电在前；H 小于最短停机时间时停机段只作最后手段，报价取 a 与“当期其他 dec 最低价位减 0.01”中的较小者。
- H 取当前时段加上其后连续“预测需求 ≤ 申报 VRE + 核电可用量”的时段数，乘以时段长度，与默认 PSM（R1-2）同一口径。
- 规则集 `network-economic-v2`，correction `r32.network-economic-downward-order`，staged PSM 1.5.0，方法改动，已保存的 Study 需显式确认（Q13）。copperplate 与 zonal 模块版本不变，它们从共享表读取两个新类别。
- VALUE 101 网络算例：C7 无下调；C8 的 42 个下调时段全是弃风，CCGT 从未被下调，新规则只让 CCGT 的 dec 报价变成两条，调度、弃电与成本只有求解器容差级别的变化。
