# Biomass dispatch without support revenue (R3-3 draft for methodology 0.4)

Status: draft written with construction unit R3-3 (2026-10-07), following
decision A24 item (2) of `docs/dev/P0_DECISIONS.md`: disclosure only. Neither
profile changes its behaviour; support revenue for biomass (CfD, ROC) is the
next round's work under review finding P4-07. The 0.3 sources (`en/`, `zh/`)
stay frozen until the 0.4 edition is generated and reviewed (plan C26).

## 1 What the model does

The GB parameter sets shipped with VALUE (GBP1 and R029; the `bio_and_waste`
row of `fleet__generators/fleet.json`, identical in both packs and in the
thesis configuration) give biomass a generation cost of 0.2, a fuel cost of
80 and a carbon cost of 4.8 GBP/MWh. Both market kernels add these
(`BiomassGenerator.gen_cost = gen_cost + carbon_price + fuel_cost +
unit_time_cost`, `runtime_compat/modular_simulation_model.py` and
`doctoral_market_kernel.py`), and the day-ahead offer is that cost times the
bid multiplier (1.0): **85.0 GBP/MWh**, plus the thesis start-up adder of
83 GBP/MWh in a period after one in which the unit was not accepted.

The other thermal plants offer at CCGT 0.1 + 39.21 + 15.76 = 55.07 GBP/MWh and
OCGT 0.1 + 48.78 + 26.04 = 74.92 GBP/MWh. Biomass is therefore the most
expensive thermal plant in the merit order, and its start-up adder keeps it
out once it has stopped. With 28 GW of CCGT available it is accepted only in
the rare periods in which everything cheaper is exhausted.

VALUE has **no support revenue for biomass**: no Contract for Difference
top-up and no Renewables Obligation Certificates. Nothing lowers its offer
below its fuel and carbon cost, and its investment account contains market
income only. Large GB biomass units (Drax, Lynemouth) run on such support;
without it the model does not reproduce their output.

## 2 What a reader sees

| Run (2025, one year) | Biomass capacity | Biomass generation | Source |
|---|---:|---:|---|
| GBP1 public2, corrected profile (local acceptance run) | 4,762 MW | 0.01 TWh (0.05 TWh before FX8) | `docs/dev/GBP1_CORRECTED_LOCAL_ACCEPTANCE.md` sections 7 and 10 |
| R029 public2, corrected profile (golden C10) | 4,762 MW | 0.006 TWh | `docs/dev/p0-reports/R3-1-solar-8761.md` section 4 |

The capacity factor is below 0.1 % in both. The doctoral reproduction profile
uses the same offer rule (Q1) and is affected in the same way.

Consequences for interpretation: the generation mix shows almost no biomass
where GB statistics show a substantial contribution, and the energy is
supplied by the cheaper plants of the merit order (mainly gas); biomass
market income and net revenue are close to zero, so its investment account
says nothing about the economics of supported biomass. None of this is a
numerical error of the market: it follows from offering at full short-run
cost without support.

## 3 Result advisory

Every Run whose frozen fleet contains a biomass asset (asset class
`biomass_and_waste`, e.g. `bio_and_waste`), in either profile, carries the
read-time advisory `VALUE-ADV-BIOMASS-SUPPORT-NOT-MODELLED` (severity medium,
`data/methodology/advisories.json`, predicate `fleet_assets`):

> Biomass without support revenue. VALUE does not model CfD or ROC support
> revenue for biomass (review finding P4-07, planned for the next round).
> Biomass therefore offers at its full fuel and carbon cost (85 GBP/MWh in
> the shipped GB parameters, above CCGT 55.07 and OCGT 74.92) and is rarely
> dispatched (GBP1 and R029 2025: about 0.01 TWh from 4,762 MW). Generation
> mix, emissions, prices and the biomass investment account should be read
> with this in mind.

A Run without biomass (VALUE 101) does not show it; a Run whose fleet cannot
be read shows it (fail towards disclosure, as for the other asset-filtered
advisories). The advisory is read-time presentation only: it is not part of
the method identity and changes no result.

## 4 0.3 text to change in the 0.4 edition

* `en/national_alternatives.md` / `zh/national_alternatives.md`, operating
  cost paragraph ("Gas and biomass unit costs combine `gen_cost + fuel_cost +
  carbon_price + unit_time_cost`"): add that biomass receives no CfD/ROC
  support revenue, so it offers at that full cost, is the most expensive
  thermal plant and is rarely dispatched; reference P4-07 as future work.
* The limitations list of the model card and of chapter 1: add "no support
  revenue for biomass (CfD, ROC)".

## 中文摘要

两个口径都没有生物质的 CfD/ROC 补贴收入（P4-07，下一轮处理），行为不变，本轮只披露。随模型发布的 GB 参数中，生物质按全额短期成本报价：0.2 + 燃料 80 + 碳 4.8 = 85 £/MWh；上一时段未被接受时再加 83 £/MWh 启动加价。它高于 CCGT（55.07）和 OCGT（74.92），在火电中排在最后，因此几乎不被调度：GBP1 public2 与 R029 public2 的 2025 年修正口径运行中，4,762 MW 生物质只发约 0.01 TWh，负荷率低于 0.1%。凡冻结机组中含生物质的 Run，无论哪个口径，都显示 advisory `VALUE-ADV-BIOMASS-SUPPORT-NOT-MODELLED`（medium，只用于展示，不进方法身份）。
