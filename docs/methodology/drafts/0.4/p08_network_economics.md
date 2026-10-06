# Network economics of the staged zonal path (P0-8 draft for methodology 0.4)

Status: draft written with the P0-8b construction (2026-10-06); to be merged
into `transmission.md` and `core.md` (en, zh) when the 0.4 edition is
generated. The staged PSM and the zonal, DC and AC modules are not available
in the doctoral reproduction profile (decision Q3), so every rule below applies
to the corrected profile only in practice.

## 1. Dec (down-regulation) prices

Balancing bids follow the balancing-mechanism convention: an accepted up bid
is paid volume x price; an accepted down (dec) bid pays volume x price back,
so the balancing objective counts a dec as `-price x volume` and accepts the
highest dec first. Before P0-8b every dec was priced at GBP 0; whether a gas
unit or a wind farm was decremented then depended on the asset identifier, and
a decremented gas unit kept its ahead income without returning the fuel it did
not burn (review P2-05, P3-04).

| Resource | Dec price (GBP/MWh) |
| --- | --- |
| fuel units (gas, coal, biomass, oil) | `SRMC x m_dec - support` |
| imports | `period price x m_dec` |
| wind, solar, run-of-river hydro | `-support` |
| nuclear | `SRMC x m_dec - support - premium` (premium GBP 100 by default) |
| storage (charge more / discharge less) | `min(own up price x eta_c x eta_d, lowest up price of the period)` |

`m_dec` is `market.dec_multiplier` (default 1, never above
`market.bid_multiplier`); `support` comes from
`market.policy_support_gbp_per_mwh_by_technology` (technologies not listed are
merchant, 0); the nuclear premium from
`network.inflexible_dec_premium_gbp_per_mwh_by_technology`. The premium and the
class order (fuel units, storage charging, wind and solar, nuclear) are the
same down-regulation table the corrected default PSM uses. With these prices
the decremented gas unit pays back exactly the running cost it avoided, so its
profit equals its profit without the dec.

Bids at the same price and of the same class share the accepted volume in
proportion to their available energy (zonal LP and the copperplate balancer
1.1.0), so renaming an asset never moves dispatch. Between classes the order
depends on the direction:

* up (more output): ascending price; at an equal price storage comes after
  generation (decision Q8);
* down (less output): descending dec price rounded to GBP 0.01, then the
  shared class order fuel units, imports, storage charging, run-of-river
  hydro, wind and solar, nuclear, then the exact price.

The storage dec price is capped at the lowest up price of the period, and a
wind or solar up bid (GBP 0) exists whenever realised renewable output exceeds
its ahead schedule, so the cap is often GBP 0 and storage ties with merchant
wind. The class order resolves that tie in favour of charging: storage absorbs
a surplus before wind is curtailed (review of M6; a battery of 5 MW with 3 MWh
of surplus and a 5 MWh GBP 0 wind up bid charges 3 MWh and wind keeps its
schedule). The same holds for pumped hydro and hydrogen storage, whose dec
price is 0. In the zonal LP the class order is a term of the physical
tie-break phase (per MWh of non-storage dec: fuel 0, imports 0.5, run-of-river
2, wind and solar 3, nuclear 4, against storage throughput 1), and a down
bid's pro-rata group carries its class; within one zone this reproduces the
copperplate order exactly, across zones the class weight is traded against
corridor flow MWh. The LP's primary phase uses exact prices, so two decs less
than GBP 0.01 apart are ordered by price there but by class in copperplate.
(Edit for `transmission.md` 0.3: the pro-rata group of an up bid is keyed by
zone, direction, network effect and price, without the resource class since
solver contract v4; a down bid's key also carries its dec class.)

## 2. Network constraint cost

The cost of the network in a period is

    C_net = C(zonal) - C(network-free)

where both cases are the same linear programme: same bids (including export
bids and their arbitrage), interconnector envelopes, storage physics,
VOLL-priced load shedding, solver settings and lexicographic phases; the
network-free case simply has one node and no corridors or boundaries. Both
cases, the resource rows and the agents' running cost are priced with one
unit-cost table per period (a resource's period cost profile, for example an
hourly import price, otherwise its annual marginal cost; storage cycle
degradation; exports 0). The forecast-error component compares the
network-free cases with the realised and with a perfect forecast.

Consequences, each tested: a national shortfall is valued at VOLL in every
case and is never network cost (before: VOLL x 1 MWh = GBP 17,000 booked as
network cost); a time-varying import price creates no network cost (before:
+-GBP 30 to 120 per period); an export arbitrage on an unconstrained network
appears in both cases (before: GBP 248 and a spurious "redispatch avoided
curtailment"). Each period checks `J1(zonal) >= J1(network-free) - tol` on the
primary objective (accepted bids plus VOLL x shedding) and reports that
difference as `network_constraint_bid_objective_gbp`. A case cost may be
negative (negative import prices).

## 3. Boundary marginal value

The boundary marginal value is the dual of the boundary limit in the primary
linear programme, read before any lock row is added (the later phases optimise
tie-breaks and their duals have no economic meaning):

    lambda_b = -dJ1/dF_b = m_b(reverse) - m_b(forward)

in GBP per MWh of boundary transfer, positive when the forward limit binds and
negative when the reverse limit binds. In the VALUE 101 network Study (two_year_smoke)
the binding boundary VALUE101-NC gives GBP 66.5/MWh, the value an independent
re-solve and a finite difference give.
Status `degenerate_dual` marks a boundary at its limit in the primary solution
with a zero dual; `shared_member` a binding boundary that shares a corridor
with another binding boundary, where the split of the dual is not unique (the
reported value lies between the one-sided derivatives). The annual
`boundary_congestion_rent_diagnostic_gbp` is the sum over periods and
boundaries of |lambda x transfer|. It is a diagnostic: not a zonal price, not a
cash flow and not part of the system cost. Ledgers written before P0-8b stored
a constant 0.0, which is shown as "Not computed".

## 4. Records of older Runs

Older zonal ledgers are not rewritten. Readers derive known defects from their
metadata: `p08.staged-dec-zero-pricing` (P2-05/P3-04),
`p08.copperplate-counterfactual-mismatch` (P2-02/P2-03/P2-04) and
`p08.boundary-shadow-not-computed` (P2-06/F3-05), next to
`p08.zonal-v3-gbp1-lock` for solver contract v3.

## 中文摘要

- 下调（dec）报价：燃料机组为 SRMC×m_dec−补贴，进口为当期价×m_dec，风光与径流水电为 −补贴，核电再减去不灵活溢价（默认 100 英镑/MWh），储能为 min(自身上调价×充放效率, 当期最低上调价)。被下调的燃气机组退回其节省的运行成本，不再获得横财；同价资产按可用电量比例分配，改名不改变调度。
- 网络约束成本 = 分区解 − 无网络解。无网络解是同一个线性规划去掉网络（单节点），报价、出口、储能、VOLL、求解器和逐期单价表完全相同，因此全国性缺电、逐期进口价、出口套利都不再计为网络成本；每期检查 primary 目标的顺序不变式。
- 边界边际价值取自 primary 阶段的对偶值，按正向取符号，单位为英镑/MWh；退化或共享成员时带状态标注。年度键改为 boundary_congestion_rent_diagnostic_gbp（诊断量，不是现金成本）。P0-8b 之前的账本值从未计算，显示为“未计算”。
