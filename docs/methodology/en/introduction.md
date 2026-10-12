# Model framework

VALUE simulates half-hourly electricity-system operation and annual changes in its assets. Generation, storage and imported electricity enter market clearing through offers. Annual asset income, operating cost and expansion headroom determine investment and retirement proposals. Development times and regional success rates determine when projects enter the operating fleet. Outputs include generation, storage charging and discharging, electricity shortfall, prices, system cost, carbon emissions and operating capacity by technology.

## Time, units and space

The operating interval is half an hour in UTC. Each model year has 365 days and 17,520 intervals, with 28 days in February. Power is measured in MW and interval energy in MWh: 1 MW supplies 0.5 MWh in a half-hour. A complete operating year supplies the annual investment calculation; commissioning and retirement update the fleet between years.

The national single-node model clears aggregate demand and supply in Great Britain, with interconnectors offering external electricity. The zonal model forms an electricity balance for each zone from resource locations and demand shares, subject to line and boundary constraints. Chapter 7 specifies the 23-zone inputs, resource allocation, network constraints and numerical solution.

Monetary calculations use constant start-year prices as a scenario convention, with 2025 as the default start year. Input tables retain the price years of technology costs, imported electricity and policy parameters. Chapter 2 lists the inputs and conversions; Chapter 5 gives generator restart costs in 2025 GBP.

## Operating methods

Default national operation uses the `value-corrected` configuration and `value-bid-at-cost-psm` module. Its Native kernel uses `native-corrected-v1` to determine offer ordering, uniform marginal settlement, storage operation and thermal downward adjustments. Each period first schedules supply against forecast demand and availability, then balances realised demand and availability using the remaining flexibility. Chapter 5 develops the algorithm in this order.

`value-staged-bid-at-cost-psm` passes the national schedule to a separate balancing module. `value-copperplate-balancing` calculates single-node balancing, while `value-zonal-redispatch-balancing` calculates zonal redispatch subject to network constraints. Chapter 4 connects scheduling, balancing and storage state; Chapter 7 defines the zonal objective functions, constraints and settlement.

Perfect-foresight dispatch uses the complete demand and availability sequences within its solution window to optimise generation, imports and storage jointly. Chapter 8 defines the objective, time-coupled constraints and terminal storage condition of `value-perfect-foresight-lp`. It also specifies the run-of-river and reservoir calculations from natural inflows to available hydroelectricity.

## Initial conditions and annual sequence

A calculation is defined by its input data pack, start and end years, selected modules and numerical parameters. `native_initial_state` constructs `initial_state` from the fleet, REPD projects, costs, development timelines and regional success rates. Operating assets carry technology, region, power capacity, storage energy capacity, costs and lifetime. Planned projects carry capacity, status and expected commissioning year. Chapter 2 specifies the input fields, values and initialisation rules.

Each year advances the planning projects, operates the annual market and constructs the following year's assets and projects. `AnnualModelOrchestratorV2.run` calls the modules in the order below. The corresponding chapters develop each calculation, including its equations, initial values and boundary conditions.

|Order|Calculation|Variables and functions|Chapter|
|---|---|---|---|
|1|Update the operating fleet from project commissioning years|`planning.advance_year` produces `advanced.operating_state`|6|
|2|Prepare demand, weather, availability and external exchange|`psm_input_factory` produces `model_input`|2, 3|
|3|Clear operating periods and aggregate their results|`psm.run` produces `market`|4, 5, 7, 8|
|4|Calculate expansion headroom from annual demand, availability and storage use|`policy.evaluate` produces `headroom`|6|
|5|Evaluate income by owner and technology-region group|`adapt_market_for_investment` assembles accounts; `investment.decide` produces `decision.proposals`|6|
|6|Admit investment projects using development times and success rates|`planning.admit_projects` produces `admission`|6|
|7|Update asset age, retirement and new projects|`transition.apply` produces `next_state`|6|

Storage inventory updates within operating periods, while cost observations update annually. National operation creates storage objects for each operating year. The previous year's sold energy and dwell time enter the following year's dynamic storage cost. Chapters 4 and 5 specify opening inventory, efficiencies, self-discharge, period power limits and year-end treatment.

Annual investment uses realised income, total capital expenditure, target payback and preferred return. Gas and biomass investment income deducts operating costs; wind, solar and storage use revenue to calculate investment returns. Chapter 6 gives the cost components, four decision tiers, development times, success rates and asset-update pseudocode.

Annual outputs sum period results or weight them by electricity volumes. Served energy equals demand less unserved energy, system cost aggregates operating and annualised capital expenditure, and carbon accounting uses generation, imported electricity and equipment capacity. Chapters 5, 6 and 9 define these quantities, their units and denominators.
