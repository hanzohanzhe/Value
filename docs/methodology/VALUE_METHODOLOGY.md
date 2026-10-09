# VALUE runtime implementation overview

This overview describes the runtime contracts of VALUE 0.7.0-alpha.1. The [bilingual methodology, edition 0.4.1](README.md), provides the mathematical formulation, numerical parameters, pseudocode and input tables.

## 1. Scope, clock and annual sequence

VALUE connects half-hourly electricity-system operation to annual investment, planning and asset retirement. The standard clock contains 17,520 UTC half-hours in a fixed 365-day model year, with February represented by 28 days. Power uses MW, interval energy MWh, and offer prices GBP/MWh.

The default market is bid at cost. Generation, storage and external import offers participate in period clearing under the information available to the selected module. A complete operating year supplies the revenue, cost and physical evidence used by annual investment.

The annual sequence advances the planning pipeline, calculates available generation and demand, clears operating periods, assembles physical and economic accounts, evaluates expansion headroom and investment, admits new projects, and constructs the next year's asset state. A VALUE 101 one-day calculation covers 48 operating periods. An annual study supplies all 17,520 periods to the annual decision chain.

## 2. Calculation identity and methodology profiles

A calculation is defined by its Data Pack, selected Modules, Study revision and Run. Data roles specify columns, units and clocks. Module declarations specify inputs, outputs and lifecycle positions. Readiness resolves these declarations and freezes the input snapshot; annual validation subsequently checks the physical and accounting results.

The corrected profile, `value-corrected`, is the default. The compatibility profile, `doctoral-lineage-0.6.0a2`, retains thesis-era settings as implemented in VALUE 0.6.0-alpha.2. Its reference configuration uses the legacy storage tariff, doctoral carbon factors and eligible thesis-lineage modules and data. The experimental national module, `value-doctoral-national-psm`, provides fixed-year dispatch and cash records for separate annual helpers; its integrated annual-CEM readiness is false.

Both profiles apply UTC demand and interconnector alignment, declared-column reading, thermal net revenue, one storage net position per period, single accounting of downward adjustments and must-run surplus, £17,000/MWh for recorded load shedding, common shortfall and served-energy accounting, and endogenous planning from the frozen development timelines and regional success rates. Their differing bidding, weather and availability assumptions are specified beside the relevant equations in the bilingual chapters.

Default annual investment uses undiscounted return and payback. Resource-cost accounting separately annualises capital using a capital recovery factor. Wind, solar and storage use a zero variable-OPEX assumption, with their fixed OPEX included in the levelised capital-cost convention. Money follows a constant start-year-price convention, while input tables retain their original price-year declarations.

## 3. National operation and balancing

The default PSM, `value-bid-at-cost-psm`, selects `native-corrected-v1` or `native-doctoral-thesis-v1` from the methodology profile. The staged variant, `value-staged-bid-at-cost-psm`, produces an immutable national ahead schedule, followed by `value-copperplate-balancing` or `value-zonal-redispatch-balancing` under the corrected profile.

The corrected default orders offers by price rounded to £0.01/MWh, storage status, and unrounded price. Generation and import offers occupy the same non-storage class. Accepted suppliers receive the stage's uniform marginal settlement price. The staged variant exposes upward and downward flexibility bids for subsequent balancing and network relief.

| Module contract | Declaration |
| --- | --- |
| Required inputs | Forecast and realised demand, VRE availability, operating assets, import envelopes and storage bids |
| State reads | Operating assets, storage inventory and storage-cost observations |
| State writes | Period dispatch and physical storage state; annual operating evidence |
| Outputs | Accepted offers, settlement, storage flows, shortfall and cost records |
| Parameters | Bid and downward-price multipliers, trace level, `market.voll_gbp_per_mwh` and diagnostics |

The retained kernel applies a start-up bid adder and a per-period ramp allowance. Corrected downward bidding additionally uses minimum stable output, minimum downtime and restart costs to order thermal reductions. These parameters enter bidding and ordering; the dispatch state represents aggregate assets with continuous quantities.

## 4. Thermal reductions, imports and shortfall

Corrected thermal downward offers have two segments. The first reduces an accepted gas or biomass schedule to its minimum stable fraction. The second compares avoided operating cost with restart expenditure over an estimated downtime:

`RestartParameters.net_saving(avoided_cost, horizon_h)` subtracts `restart_cost(horizon_h) / min_stable_fraction / horizon_h` from avoided operating cost. `avoided_cost` is GBP/MWh, `restart_cost` returns GBP per MW of capacity, `min_stable_fraction` is the stable-output fraction, and `horizon_h` is expected downtime in hours. `economic_segments` applies the running and shutdown quantities within the ramp floor. Downtime below the technology minimum places the shutdown segment last. The compatibility profile retains its VRE-first downward order. Each accepted quantity reduces the outstanding adjustment once.

Corrected interconnectors offer positive import capability in ahead clearing at the current external price. Balancing uses the remaining envelope. Compatibility-profile imports enter balancing. Each profile aligns price and flow inputs to the model clock, with country and line identities retained through preprocessing.

The default PSM values recorded load shedding at £17,000/MWh. Its balance ledger separately records additional physical shortfall as stress events while retaining the calculated dispatch and settlement. Annual unserved energy is recorded shedding plus stress shortfall; annual served energy is demand less this total. Consecutive shortfall periods form an event, and the event ledger records duration, energy and maximum power.

## 5. Storage physics

Storage declares charge and discharge power, energy capacity, efficiencies and opening inventory. `Battery.charge(period, available_input_power_mw)` adds a dated energy batch within the free capacity and remaining period power. Discharge withdraws inventory according to discharge efficiency; the inventory-removal and self-discharge accounts record the remaining losses. Chapter 4 gives the updates using the class’s physical variables and their units.

The default PSM gives each storage asset one net position per period and shares its rated power across clearing stages. Charging uses surplus after same-period discharge has been bought back. Stored batches retain their charging period for age-dependent offers. The annual Native adapter creates fresh storage objects and records the discarded closing inventory at the year boundary.

## 6. Dynamic annual-average storage cost

`dynamic-annual-storage-cost` calculates annual project-cost recovery from CAPEX, fixed O&M, economic life, previous-year sold energy and sales-weighted dwell. Its annual cost and battery cycle-depreciation terms are:

`DynamicAnnualStorageCost.prepare_year` calculates `annualized_capital_cost_gbp` from `capex` and `capital_recovery_factor(discount_rate, lifetime_years)`. The capital-recovery function returns the standard annuity factor and uses `1 / lifetime_years` at zero discount rate. `annual_fixed_opex_gbp` is rated MW multiplied by 1,000 and the catalogue’s GBP/kW/year cost; their sum is `annual_levelized_project_cost_gbp`.

For batteries, `cycle_depreciation_gbp_per_mwh` equals `capex / (usable_cycle_output * maximum_cycles)`, with `usable_cycle_output` equal to energy capacity times discharge efficiency. Pumped hydro and hydrogen use zero cycle depreciation. The remaining annual recovery equals annual project cost less cycle depreciation times `basis_sold`, bounded below by zero. `holding_recovery_gbp_per_mwh_period` divides that amount by `basis_sold * max(average_dwell, 1.0)`. The observation step has already bounded `average_dwell` below by two periods.

The first-year reference uses annual cycles equal to the smaller of cycle-life use per economic year and the physical charge–discharge limit. `storage.cost.utilisation_floor_fraction` optionally supplies a floor relative to that reference.

The corrected default PSM sets the exact built-in `DynamicAnnualStorageCost` object to `cycle_only`: batteries bid cycle depreciation, and pumped hydro and hydrogen bid zero. Holding recovery remains a project-cost-adequacy diagnostic. User-formula, legacy and external storage-cost modules supply their own bids.

The compatibility rule and the staged dynamic-cost path use `bid_price_gbp_per_mwh(dwell_periods)`, which adds `cycle_depreciation_gbp_per_mwh` to nonnegative `dwell_periods` times `holding_recovery_gbp_per_mwh_period`. The staged adapter calls this function at 0.0 and labels dwell as `not_tracked_staged_single_pool`. Fixed O&M in `annual_levelized_project_cost_gbp` is part of the pricing calculation; wind, solar and storage FOM appears as a memo item in headline resource-cost accounting.

`value-legacy-storage-tariff` supplies the fixed-plus-dwell tariff used by the compatibility configuration. `storage-cost-audit.json` records the selected bid basis, annual costs, sales, dwell and recovery difference.

## 7. Expansion headroom and investment

`vre-expansion-cap` calculates separate ceilings for solar, onshore wind and offshore wind from demand, technology profiles, installed capacity and the expansion fraction. Corrected `value-storage-expansion-policy` uses surplus remaining after existing storage has charged. Each of the three battery types receives its own power ceiling equal to the default fraction 0.2 times the calculated power headroom. The compatibility rule retains zero storage leftover headroom.

`agent-investment` evaluates each owner and technology-region group once per year. Four policy tiers use realised net income divided by total CAPEX, payback and negative income to select investment, waiting or retirement. The technology headroom is consumed once across eligible proposals. Thermal investment income deducts generation, fuel, carbon and time-based operating costs; biomass revenue follows electricity-market settlement. Wind, solar and storage use the stated gross-revenue profit convention.

Storage investment uses annual market income divided by total CAPEX, with zero procurement cost for surplus charging. The physical utilisation rule supplies its expansion ceiling. Successful proposals retain owner, technology, capacity, location, CAPEX, FOM and life. Site-dependent hydro proposals require their declared site, hydrology and cost inputs.

## 8. Planning and annual state

`agent-investment` obtains each endogenous proposal’s `completion_year` and `success_rate` from `endogenous_planning_terms`, using the planning tables frozen in `state.extensions["planning_parameters"]`. Technology labels determine the development timeline and regional success-rate lookup. Thermal plant and biomass use Wind Onshore; hydrogen storage uses Solar Photovoltaics. The default duration uses the stage-1 total median, with a deterministic owner-specific displacement from −6 to +6 months and commissioning from the following year onward.

`planning-pipeline` advances existing projects and admits the proposals with their supplied timing and probability. Expected-capacity mode scales power, energy and total costs once; seeded-stochastic mode admits full capacity according to the seeded draw. Commissioned assets inherit project identity, economic ownership and spatial allocation. Annual headroom uses operating assets while pending proposals retain their individual development schedules.

`value-annual-state-transition` writes the following year's operating assets, planning projects, economic records and storage-cost observations. Partial retirement scales physical and economic capacity together. Completed year boundaries receive checkpoints; an interrupted operating year is recalculated from its opening state.

## 9. Resource cost and carbon

The headline definition `value.cem-system-resource-cost/v1` is assembled by cost ledger v2:

`system_cost = headline_capital + operating_sum`

In `build_cem_cost_ledger`, `headline_capital` includes the declared annualised capital and thermal FOM, and `operating_sum` sums the physical operating-cost entries. Wind, solar and storage FOM is a memo item under the model's capital-cost convention. Run-of-river compatibility capital is a memo item in the corrected profile and contributes to the compatibility-profile headline.

Physical operating cost includes final thermal resource use, start-up adders, imports, storage cycle depreciation and recorded load shedding valued at VoLL. Settlement and policy transfers have separate accounts. The average resource cost divides by demand less recorded shedding and stress shortfall. Zonal transmission-constraint cost is constrained physical cost minus the matched network-free LP physical cost, recorded as an attribution within the total.

Physical carbon accounting separates direct generation emissions, external-import emissions and annualised equipment-construction emissions. Generation includes the electricity supplied to storage charging. Delivered-electricity intensity uses the same served-energy denominator as cost. The compatibility carbon scenario retains its historical scalar units with the status `not_physically_interpretable`.

## 10. Hydrology and optional domains

Natural-flow hydro, reservoir hydro and pumped storage use distinct input roles. Corrected default run-of-river availability is the declared statistical load factor 0.3487 multiplied by its seasonal shape. An activated hydrology extension instead supplies inflow or availability series and, for reservoirs, water stock, bounds and terminal assumptions.

A Study activates an optional domain by selecting its compatible module and resolving all conditional inputs. The reference DC network uses phase-angle flow equations and expands multi-bus asset allocations by their shares. Perfect-foresight dispatch solves its declared horizon jointly and labels the electricity value `Balance shadow price`.

## 11. Fixed zonal transport and redispatch

The fixed zonal method is a post-thesis extension representing lossless power transport through directed corridors and simultaneous boundary cutsets. A Network Pack supplies zones, corridor limits, rating profiles, asset allocations, demand shares and interconnector landings. `scenario_scaled_zonal_shares` allocates the base pack's national demand among zones; `network_pack_absolute_demand` instead uses the Network Pack's absolute demand.

The GBP1 public2 23-zone research suite supplies spatial positions for wind and solar. Other supplied technologies and imports use `ENGLAND_FALLBACK`, including the runtime fallback for Torness and country-named import resources. Its zonal results have indicative spatial scope.

Each period's linear programme balances zonal supply, demand, storage, imports and transfers. Corridors have separate forward and reverse limits. Cutsets constrain signed sums of corridor flows, with period ratings applied to their transfer envelopes.

Solver contract v4 first minimises redispatch bid cost plus VoLL-valued unserved energy. It then locks the primary solution's total unserved energy and applies a separate numerical cap to its bid-cost component. Three subsequent phases minimise absolute schedule deviation, weighted physical throughput and a stable tie-break, preserving the preceding locks.

Corrected downward bids use avoidable economic cost, including two thermal segments. Equal-price acceptance is proportional within a class. The eight-class tie order is fuel turndown, imports, storage, run-of-river hydro, VRE, thermal shutdown, nuclear, then thermal shutdown below minimum downtime. The mathematical chapters give the sign conventions, class weights and objective tolerances.

Upward and downward adjustments settle pay as bid. Ahead settlement, redispatch payments and resource costs occupy separate accounts. The primary-stage boundary dual records the local marginal value of a transfer constraint under the declared LP. Storage uses actual redispatched flows for SOC, and external links retain their landing zones and remaining envelopes.

Curtailment equals available VRE less final VRE use. Redispatch curtailment impact is constrained final curtailment minus the matched network-free counterfactual. The comparison uses identical demand, availability, storage openings and economic bids.

### State reads and state writes

The zonal module reads the ahead schedule, realised demand and availability, flexibility bids, network inputs and opening SOC. It writes final dispatch, corridor flows, accepted redispatch, load shedding, curtailment, settlement, physical cost, solver diagnostics and closing SOC.

### Known limitations

The zonal result establishes feasibility under transfer limits; it is not a security analysis. AC voltage, reactive power, dynamic stability and contingency assessment require their corresponding electrical models. The annual investment chain evaluates agent rules, with results conditional on inputs, policy assumptions and planning outcomes.

## 12. Results and implementation references

Annual economic publication follows the selected profile's validation policy. Corrected runs require every applicable gate to pass. Compatibility runs require all raw invariants to pass. Pending or withheld summaries retain their period ledgers and inspection records.

Price labels follow the producing calculation: the default PSM reports average period cost, staged ahead clearing reports uniform marginal settlement price, the LP reports balance shadow price, and the experimental national pathway reports its ahead settlement price. Wind and solar capacity factors are compared with DUKES alongside the declared weather conversion and loss assumptions.

The reproducible record contains the Study revision, methodology profile, selected module versions, input roles and source files, parameter tables, annual checkpoints and physical and economic ledgers. Result timestamps use the UTC model clock. Source and data rights accompany their respective inputs.

Module declarations are in `gridform_core/manifests`, public interfaces in `gridform_core/v2`, and cost and carbon accounting in `cost_ledger.py` and `carbon_ledger.py`. `zonal_redispatch.py`, `zonal_contracts.py` and `zonal_solver_contract.py` implement network redispatch. The bilingual chapters pair each calculation with its specific functions and data tables.
