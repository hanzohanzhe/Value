# Scheme C legacy simulation-result mapping

`SchemeCLegacyResultAdapter` is the only modular/production code allowed to know
the retained 41-field tuple order. The reference `compat/case3.py` and its
`compat/investment_support.py` dependency remain unchanged for parity comparison.

| Position | Named field | Existing unit/meaning |
| ---: | --- | --- |
| 0 | `prices_gbp_per_mwh` | GBP/MWh per period |
| 1 | `storage_fees_gbp` | legacy storage-fee structure |
| 2 | `storage_charge_by_period` | raw storage charge per period |
| 3 | `generation_cost_gbp_by_period` | GBP per period |
| 4-7 | storage pool/composition fields | retained kernel structures |
| 8-11 | average fee fields | retained kernel fee structures |
| 12-19 | ahead/balancing generation groups | raw period energy |
| 20 | `dispatch_by_period` | `(asset, raw period energy)` pairs |
| 21 | `curtailed_electricity_mwh_by_period` | raw period energy |
| 22 | `excess_electricity_mwh_by_period` | MWh/period |
| 23 | `total_cost_gbp_by_period` | GBP/period |
| 24 | `real_demand_mwh_by_period` | MWh/period |
| 25 | `carbon_emissions_by_period` | retained emissions series |
| 26-27 | sold/purchase fees | GBP/period |
| 28-32 | annual technology/hydrogen/capacity summaries | retained structures |
| 33 | `market_income_gbp_by_agent` | GBP by agent |
| 34-37 | excess/curtailment/hydrogen dictionaries | retained agent structures |
| 38 | `flexible_demand_mwh_by_period` | MWh/period |
| 39 | `interconnector_exports_mwh_by_period` | MWh/period |
| 40 | `blackout_mwh_by_period` | MWh/period |

The adapter preserves the pre-existing typed PSM conversion: energy found in a
dispatch pair is multiplied by `period_hours` when aggregated by asset. Demand,
excess, blackout, prices and period costs are not rescaled. This task deliberately
does not repair or reinterpret the retained kernel's historical unit conventions.
