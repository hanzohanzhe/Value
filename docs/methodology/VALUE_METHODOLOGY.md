# VALUE runtime implementation overview

VALUE 0.7.0-alpha.1 connects half-hourly electricity-system operation to annual investment, planning and asset retirement. The [bilingual methodology, edition 0.5](README.md), gives the complete equations, numerical parameters, pseudocode and input tables. This overview identifies the runtime functions that perform those calculations.

## 1. Inputs and initial state

The model clock contains 17,520 UTC half-hours in a fixed 365-day year, with February represented by 28 days. Power uses MW, interval energy MWh and offers GBP/MWh. A complete operating year supplies the annual investment calculation.

`native_initial_state` reads fleet assets, REPD projects, technical costs, development timelines and regional success rates from the selected data pack. Assets carry capacity, technology, location, cost and economic life. Projects carry development status, capacity and commissioning year. Demand and import inputs are aligned to the model's UTC clock; the weather module converts wind and radiation to available generation.

The default configuration is `value-corrected`. `value-bid-at-cost-psm` uses the `native-corrected-v1` rule set for national operation. The public2 data packs provide the operational inputs; the `value-uk-research-suite-v1-public2` suite supplies the 23-zone network configuration.

## 2. Market operation and storage

National operation is bid at cost. Each half-hour schedules supply against the forecast and balances realised demand and availability. Offers are ordered by price rounded to £0.01/MWh, storage status and unrounded price. Accepted suppliers receive the stage's uniform marginal settlement price.

Thermal downward adjustments first use the output above the minimum stable level. A further shutdown segment compares avoided operating expenditure with restart expenditure over the estimated downtime. Recorded load shedding is valued at £17,000/MWh. The period balance also records additional physical shortfall; their sum enters annual unserved energy.

`Battery.charge`, `Battery.discharge`, `Battery.buy_back` and `Battery.apply_self_discharge` update stored energy, dated batches, charging and discharge losses, and self-discharge. Each asset has one net position per period and shares its rated power across clearing stages. The annual national adapter creates fresh storage objects at the beginning of each year.

The dynamic annual-average storage cost uses capital expenditure, fixed operating cost, economic life and the previous year's sold energy and dwell. `DynamicAnnualStorageCost.prepare_year` calculates annualised project cost and battery cycle depreciation. Default national bidding uses the battery cycle-depreciation component; pumped hydro and hydrogen have zero cycle-depreciation bids. The staged path evaluates `bid_price_gbp_per_mwh` at zero dwell.

## 3. Annual accounts, investment and planning

Annual accounts aggregate generation, storage sales, market revenue and physical costs. Gas and biomass investment profit deducts operating expenditure from income. Wind, solar and storage use gross revenue for the investment decision. Resource-cost accounting separately annualises capital expenditure with `capital_recovery_factor`.

`vre-expansion-cap` and `value-storage-expansion-policy` calculate technology expansion headroom from annual demand, generation profiles and storage use. The storage rule uses the surplus remaining after existing storage charging. Each battery type receives its own ceiling from this calculation.

`agent-investment` evaluates owner and technology-region groups using realised income, capital expenditure, preferred return and target payback. Its four decision tiers select investment, waiting or retirement. Development times and regional success rates come from the tables stored in the initial state. The headroom calculation counts the operating fleet; pending projects retain their individual commissioning schedules.

The planning pipeline admits proposals as expected capacity or as seeded stochastic outcomes. `planning.advance_year` commissions due projects at the start of the year; `planning.admit_projects` admits newly proposed projects at year end. `transition.apply` advances asset age, applies retirement and constructs the next year's state. The previous year's storage-cost observations accompany this state.

## 4. Balancing and network constraints

`value-staged-bid-at-cost-psm` creates the national ahead schedule. `value-copperplate-balancing` balances a single node; `value-zonal-redispatch-balancing` applies fixed zonal network constraints and pay-as-bid redispatch. `scenario_scaled_zonal_shares` distributes the study demand across zones.

Zonal redispatch applies electricity balance, resource availability, storage bounds, directed corridor capacities and signed boundary constraints. The solver minimises four objectives in sequence: adjustment bid cost including shortage valuation; accepted upward and downward MWh plus shortage MWh; weighted physical throughput; and stable variable order. Each subsequent solve retains the preceding objective bounds within the calculated numerical tolerances.

The 23-zone suite assigns explicit locations to wind and solar. Other supplied resources use `ENGLAND_FALLBACK`, including the runtime nuclear station allocation and the country-level import assets. These assignments define the spatial input to the zonal calculation.

The DC network method calculates line power from voltage angles and branch reactance, with thermal capacity equal to the line rating times its circuit count. The AC calculation additionally solves voltage magnitudes, reactive-power balance and branch apparent-power limits. Chapter 7 specifies each formulation and its numerical stopping conditions.

## 5. Perfect foresight, hydrology and carbon

`value-perfect-foresight-lp` jointly optimises generation, imports, load shedding and storage over the declared time window. Storage inventory connects consecutive periods, and the terminal policy fixes or bounds its closing inventory. The independent functions `run_of_river_dispatch` and `reservoir_dispatch` calculate available run-of-river electricity and reservoir generation from inflows; reservoir dispatch also returns water storage, turbine release and spill.

`build_operational_carbon_ledger` multiplies generation and imported electricity by the selected emission factors. `_asset_embodied_lines` annualises construction emissions using power capacity or storage energy capacity and economic life. Total emissions combine these components; carbon intensity divides by served electricity. Chapter 9 gives the factors, units and storage-carbon inventory calculation.

## 6. Implementation locations

`gridform_core/v2/orchestrator.py` defines the annual sequence. `canonical_psm_data.py` constructs initial assets and projects; `v2_module_definitions.py` supplies the default annual investment and planning modules. `cost_ledger.py` and `carbon_ledger.py` aggregate economic and emissions accounts.

`zonal_redispatch.py`, `zonal_contracts.py` and `zonal_solver_contract.py` define network redispatch and numerical solution. Module declarations are in `gridform_core/manifests`. The bilingual chapters place the specific function names and input fields beside each calculation.
