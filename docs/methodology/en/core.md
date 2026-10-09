# Operation and annual feedback

VALUE links half-hourly dispatch to annual investment. Projects due for commissioning enter the operating portfolio at the start of a year; their operation generates the income used for year-end additions and retirements. This chapter defines staged dispatch, storage pricing, investment and system accounts. Chapter 5 describes the default national PSM, and Chapter 6 describes the experimental national accounts.

## Model clock and annual state

A model year contains 365 days and 17,520 half-hour periods in UTC. `period_start_utc` takes the zero-based `period`, divides it into `day_index` and within-day `offset`, and adds `offset×period_hours` hours to the date returned by `model_day`. With `period_hours=0.5`, the calculation is:

$$
\mathtt{day\_index}=\left\lfloor\frac{\mathtt{period}}{48}\right\rfloor,\qquad\mathtt{offset}=\mathtt{period}\bmod48.
$$

`model_day` skips 29 February. Source series are aligned to this clock before dispatch; records declared as Europe/London are converted to UTC row by row. Output timestamps use ISO 8601 with `Z`. Period energy is measured in MWh, rated power in MW and inventory in MWh. Formulas and pseudocode below retain the names used by the corresponding functions and fields.

The annual state carries operating assets, uncommissioned projects, storage-pricing observations and cumulative financial quantities. In the annual orchestrator, `planning.advance_year` commissions due projects, `psm_input_factory` assembles the year’s demand and availability, and `psm.run` returns dispatch and income. Each expansion policy then evaluates annual capacity limits; `investment.decide` creates investment decisions and `planning.admit_projects` applies the declared success mode. `transition.apply` constructs the following year’s state.

The main annual calls use the same data objects throughout. Before transition, `transition_state` contains the operating assets, remaining active projects, cumulative metrics and annual observations:

```text
advanced = planning.advance_year(run, state)
model_input = psm_input_factory(run, advanced.operating_state)
market = psm.run(model_input)
headroom = []
for slot in sorted(expansion_policies):
    policy = expansion_policies[slot]
    headroom.append(policy.evaluate(run, advanced.operating_state, market))
investment_market = adapt_market_for_investment(
    market, advanced.operating_state)
decision = investment.decide(
    run, advanced.operating_state, investment_market, tuple(headroom))
admission = planning.admit_projects(
    run, advanced.operating_state, decision.proposals)
next_state = transition.apply(run, transition_state, admission, decision)
```

Terminal handling follows the selected study setting. `report_only` retains the final state, `pipeline_tail` advances projects already in the pipeline, and `full_extension` continues annual operation and investment.

## Ahead market and balancing

The staged PSM clears forecast demand before balancing actual demand. For each non-storage `resource`, `_ahead_offers` reads the period availability and marginal cost. `availability` is the supplied availability clipped at zero; `physical_cost` is the period-specific cost when supplied, otherwise the constant marginal cost. `multiplier`, from `market.bid_multiplier`, defaults to 1. The offered energy and price are:

$$
\begin{aligned}\mathtt{available\_mwh}&=\mathtt{resource.capacity\_mw}\times \mathtt{availability}\\&\quad\times\mathtt{model\_input.period\_hours},\\\mathtt{marginal\_cost}&=\mathtt{physical\_cost}\times \mathtt{multiplier}.\end{aligned}
$$

A storage offer is bounded by discharge power and stored energy. `soc[resource.asset_id]` is opening stored-side inventory, and `discharge_efficiency` converts it to delivered energy:

```text
available_mwh = min(
    resource.discharge_power_mw * model_input.period_hours,
    soc[resource.asset_id] * resource.discharge_efficiency
)
```

`clear_ahead` sorts offers by `price_gbp_per_mwh`, then `offer_id`. It begins with `remaining=forecast_demand_mwh`, accepts the smaller of remaining demand and each offer’s available energy, and reduces remaining demand by that quantity. The last accepted price becomes `clearing_price_gbp_per_mwh`; all accepted energy receives that price. Clearing stops at a remaining demand of 10⁻¹² MWh. Zero accepted supply has a zero clearing price; the remaining forecast shortfall enters `unserved_forecast_mwh`.

$$
\mathtt{accepted}=\min(\mathtt{remaining},\mathtt{available}),\qquad\mathtt{remaining}\leftarrow\mathtt{remaining}-\mathtt{accepted}.
$$

Balancing responds to the difference between actual demand and the ahead schedule. In `CopperplateBalancing.clear`, `final_dispatch` initially equals `schedule_mwh_by_asset`, and `gap_mwh=real_demand_mwh−sum(final_dispatch.values())`. Generation and imports offer their unused available energy upward and their scheduled energy downward. Storage can first withdraw scheduled discharge and then charge within its power, energy and efficiency limits. Exports enter as negative injections at the declared connection location and capacity.

## Downward bids and settlement

Downward settlement returns the accepted reduction multiplied by its bid price. Thus an upward adjustment has positive signed `delta`, a downward adjustment has negative `delta`, and both use `cashflow=delta×price_gbp_per_mwh`. The corrected staged and network pathways use `network-economic-v2` to construct these prices.

Thermal downward bids divide the ahead schedule into the running range and the minimum-stable-output segment. `thermal_dec_segments` sets `shutdown_mwh=min_stable_fraction×scheduled_mwh` and puts the remainder in `running_mwh`. Running-range price is avoided marginal cost after the downward multiplier and policy support. Shutdown price deducts restart expenditure spread across the expected shutdown interval. In `RestartParameters.net_saving`, `avoided_cost` is GBP/MWh, `restart_cost(horizon_h)` is GBP/MW per start, and `horizon_h` is hours:

$$
\begin{aligned}\mathtt{net\_saving}(\mathtt{avoided\_cost},\mathtt{horizon\_h})\\=\mathtt{avoided\_cost}-\frac{\mathtt{restart\_cost}(\mathtt{horizon\_h})}{\mathtt{min\_stable\_fraction}\times \mathtt{horizon\_h}}.\end{aligned}
$$

`shutdown_horizon_hours` counts the current period plus consecutive later periods whose forecast demand is covered by declared VRE and nuclear availability. Its returned duration is `(1+run_after[period])×period_hours`. When this duration is shorter than `min_down_time_h`, `last_resort_price` places the shutdown bid at least 0.01 GBP/MWh below the lowest rounded ordinary downward bid. Otherwise the shutdown price is its net saving. With an empty ordinary-bid set, net saving supplies the price.

CCGT uses a minimum stable fraction of 0.50, minimum downtime of 6 h and hot, warm and cold restart costs of 113.7, 134.4 and 155.0 GBP/MW. OCGT uses 0.50, 0.5 h and 175.7 GBP/MW; biomass uses 0.35, 6 h and 129.2 GBP/MW. CCGT selects hot starts below 12 h, warm starts from 12 through 48 h and cold starts above 48 h. These costs are in 2025 GBP. The running range precedes the unit’s shutdown segment; the shutdown segment precedes unsupported wind only when its net saving is positive. Wind precedes shutdown at a price tie.

Other downward prices use `resource_dec_price`. Imports return `marginal×dec_multiplier`; wind, solar and run-of-river hydro return `−support`; nuclear returns `marginal×dec_multiplier−support−premium`; other fuel resources return `marginal×dec_multiplier−support`. `market.dec_multiplier` defaults to 1 and is at most `market.bid_multiplier`. Unlisted policy support is zero, while nuclear’s default premium is 100 GBP/MWh. Storage uses `storage_dec_price`, bounded by its upward bid times charging and discharge efficiency and by the lowest available upward price.

Copperplate balancing ranks upward bids by increasing price, with storage after generation at a price tie; bids above VoLL remain outside the accepted set. It ranks downward bids by decreasing price rounded to 0.01 GBP/MWh, then by class, then by exact price. The class order is fuel running range, imports, storage, run-of-river hydro, VRE, thermal shutdown, nuclear and short-downtime shutdown. Equal-price bids of the same direction and class share acceptance in proportion to available energy.

For each equal-price group, `total` is available MWh and `fraction` is the smaller of the imbalance-to-available ratio and 1. The resulting `delta` changes `final_dispatch` and earns `cashflow`. Positive residual demand becomes `blackout_mwh`. Final supply plus blackout must match actual demand within 10⁻⁸ MWh. Zonal balancing applies the same schedule and bid definitions inside the Chapter 7 network constraints, with exact-price optimisation followed by physical tie-breaking.

A 50 MWh forecast illustrates the two settlements. Wind offers 30 MWh at £0/MWh and gas offers 30 MWh at £60/MWh. The ahead schedule accepts 30 MWh of wind and 20 MWh of gas, paying £3,000 at the common £60/MWh price. If actual demand is 55 MWh, gas supplies 5 MWh more and receives £300 in balancing. Gas physical expenditure is based on its final 25 MWh and equals £1,500.

## Storage inventory and bidding

Storage inventory follows final net injection in each period. In `CopperplateBalancing.clear`, `opening` is initial stored-side MWh and `dispatch` is final MWh delivered to the grid; a negative value denotes charging. The updated `soc` is:

$$
\mathtt{soc}=\begin{cases}\mathtt{opening}-\mathtt{dispatch}/\mathtt{discharge\_efficiency},&\mathtt{dispatch}\ge0,\\\mathtt{opening}-\mathtt{dispatch}\times \mathtt{charge\_efficiency},&\mathtt{dispatch}<0.\end{cases}
$$

Inventory remains between zero and `energy_capacity_mwh`, with a 10⁻⁸ MWh rounding tolerance. Zonal dispatch represents charge and discharge separately and requires at most one to exceed 10⁻⁸ MWh. Each year opens from `initial_soc_mwh`: `canonical_psm_data.py` assigns half the energy capacity to ordinary inputs and zero to the designated research-input alignment. The staged inventory carries between periods, while the following year takes its opening inventory from annual inputs. Storage-pricing observations carry between years; Chapter 6 gives the experimental dated-batch transition.

`DynamicAnnualStorageCost` divides equipment-cost recovery into cycle depreciation and holding recovery. `capital_recovery_factor` uses `discount_rate` and `lifetime_years`; at a nonpositive discount rate it returns the inverse lifetime, otherwise it uses:

$$
\begin{aligned}\mathtt{growth}&=(1+\mathtt{discount\_rate})^{\mathtt{lifetime\_years}},\\\mathtt{capital\_recovery\_factor}&=\frac{\mathtt{discount\_rate}\times \mathtt{growth}}{\mathtt{growth}-1}.\end{aligned}
$$

Annual cost is annualised asset CAPEX plus fixed maintenance. `prepare_year` takes actual asset `capital_cost_gbp`, `power_capacity_mw`, `energy_capacity_mwh` and `discharge_efficiency`. Catalogue lifetime, duration, cycle life and fixed-maintenance rate come from `spec`. The calculation keeps the asset’s declared energy-to-power ratio.

```text
capex = max(capital_cost_gbp, 0)
annualized_capital_cost_gbp = capex * capital_recovery_factor(
    discount_rate, spec.economic_lifetime_years)
annual_fixed_opex_gbp = (
    max(power_capacity_mw, 0) * 1000 * spec.fixed_opex_gbp_per_kw_year)
annual_levelized_project_cost_gbp = (
    annualized_capital_cost_gbp + annual_fixed_opex_gbp)
```

Reference annual sales use the smaller of lifetime cycles per year and physically possible charge-discharge cycles. `_reference_observation` calculates `cycles_per_year`, annual delivered sales `sold` in MWh, and reference holding time `dwell_periods` in model periods:

```python
cycles_per_year = min(
    spec.maximum_cycles / spec.economic_lifetime_years,
    8760 / (2 * spec.duration_hours)
)
sold = energy_capacity_mwh * discharge_efficiency * cycles_per_year
dwell_periods = max(spec.duration_hours / period_hours, 2)
```


The pricing basis uses previous-year sales when positive, subject to a floor tied to reference sales. `reference` is the observation returned by `_reference_observation`; it stores `sold` in `sold_energy_mwh` and its reference holding time in `average_dwell_periods`. `previous` holds the preceding year’s observation. The selected `basis_sold` is MWh and `average_dwell` is the delivered-MWh-weighted number of holding periods:

```text
observed = previous
minimum_sold = reference.sold_energy_mwh * max(utilisation_floor, 0)
if observed.sold_energy_mwh > 0:
    basis_sold = max(observed.sold_energy_mwh, minimum_sold)
    average_dwell = max(observed.average_dwell_periods, 2)
else:
    basis_sold = reference.sold_energy_mwh
    average_dwell = reference.average_dwell_periods
```

Defaults are `utilisation_floor=0` and `discount_rate=0.05`. Batteries recover cycle depreciation from delivered MWh; pumped hydro and hydrogen have a zero cycle-depreciation component.

```text
usable_cycle_output = energy_capacity_mwh * discharge_efficiency
cycle_depreciation_gbp_per_mwh = (
    capex / (usable_cycle_output * spec.maximum_cycles))
expected_cycle_recovery = cycle_depreciation_gbp_per_mwh * basis_sold
remaining_annual_recovery = max(
    annual_levelized_project_cost_gbp - expected_cycle_recovery, 0)
weighted_basis = basis_sold * max(average_dwell, 1)
holding_recovery_gbp_per_mwh_period = (
    remaining_annual_recovery / weighted_basis)
```

The cycle formula applies where `has_cycle_depreciation` is true and both denominator terms are positive. Other cases give zero cycle depreciation. Holding recovery is zero when `weighted_basis` is zero. `bid_price_gbp_per_mwh(dwell_periods)` adds cycle depreciation to nonnegative holding age times holding recovery. The corrected default PSM supplies cycle-only bids: battery bids equal `cycle_depreciation_gbp_per_mwh`, while pumped-hydro and hydrogen bids are zero. Its oldest inventory tranche is discharged first.

The staged caller passes `dwell_periods=0` and records sale ages as zero; its report labels the age source `not_tracked_staged_single_pool`. The holding component therefore contributes zero to its dynamic bid. General holding-recovery quantities remain available as investment-adequacy diagnostics. The fixed-fee alternative uses `storage_fee_gbp_per_mwh+dwell_periods×holding_fee_gbp_per_mwh_period`. The doctoral reproduction profile uses its legacy tariff configuration.

Catalogue fixed-maintenance rates in 2025 GBP/kW/year are 13.4 for pumped hydro, 6.6 for each of the 1C, 0.5C and 0.25C batteries, and 19.7 for hydrogen. The pumped-hydro catalogue capital cost is 360,000 GBP/MW. These fixed costs enter annual bid-cost recovery; wind, solar and storage fixed OPEX is recorded separately as a memo in the system cost account.

## Storage expansion limits

Corrected storage expansion uses the surplus remaining after existing stores have charged. `corrected_storage_headroom` reads `leftover_excess_mwh` from `storage_headroom_inputs` and reads `vre_accepted_mwh`, `real_demand_mwh` and `storage_discharge_mwh` from each period summary. These fields form the period-MWh arrays `leftover`, `vre`, `demand` and `discharge` respectively. The surplus supplies `excess`; the remaining VRE gap after existing discharge supplies `deficit`:

$$
\begin{aligned}\mathtt{excess}&=\max(\mathtt{leftover},0),\\\mathtt{deficit}&=\max(\mathtt{demand}-\mathtt{vre}-\mathtt{discharge},0).\end{aligned}
$$

The virtual store begins empty and has `power_mw=10⁹` MW, `energy_cap_mwh=10⁹` MWh and charging efficiency `rte=0.98`; discharge efficiency is 1. `_simulate_virtual_pool` charges before discharging in each period. In the following update, `exc` and `dfc` are period excess and deficit, and `max_period_mwh=power_mw×PERIOD_HOURS`:

```text
ch = min(exc, max_period_mwh, (energy_cap_mwh - soc) / rte)
soc += ch * rte
dis = min(dfc, max_period_mwh, soc)
soc -= dis
charge[t] = ch
discharge[t] = dis
```

`aligned_max_mw` finds the largest common charging and discharging power with at least `min_hours` of use. `hours_above_power(power_mw,p_mw)` counts periods strictly above the tested power and multiplies by 0.5 h. The search uses 64 bisection steps between zero and the smaller charging/discharging peak; an unattainable duration returns zero, and a nonpositive duration returns that peak.

`aligned_utilisation_spectrum` applies this calculation at 730, 365, 52 and 0 hours, producing `mw_730`, `mw_365`, `mw_52` and `mw_0`. Its successive MW bands are:

$$
\begin{aligned}\mathtt{daily}&=\mathtt{mw\_730},\\\mathtt{interday}&=\max(\mathtt{mw\_365}-\mathtt{mw\_730},0),\\\mathtt{weekly}&=\max(\mathtt{mw\_52}-\mathtt{mw\_365},0),\\\mathtt{seasonal}&=\max(\mathtt{mw\_0}-\mathtt{mw\_52},0).\end{aligned}
$$

Each of the three battery types receives `power_cap=cap_fraction×power_room`, where `power_room=daily+intraday` and the default `cap_fraction` is 0.20. Hydrogen receives `hydrogen_cap=cap_fraction×seasonal`. Thus 1C, 0.5C and 0.25C each have a separate 0.20 share of the same power opportunity. Owners of a common technology consume its remaining limit in stable order. Prices and investment returns are evaluated separately.

This calculation requires 17,520 half-hours and the post-charge surplus series. Partial years return zero with `partial_year_chronology`; a missing series returns zero with `leftover_trace_unavailable`. Native dispatch supplies the series. Staged dispatch, perfect-foresight LP, DC dispatch and the experimental national pathway receive zero corrected storage headroom under these checks. The doctoral reproduction profile instead derives surplus from accepted VRE minus demand; accepted VRE in that PSM stays within demand, yielding zero headroom.

## Annual investment

Investment pools assets by owner, technology and region. `adapt_market_for_investment` first assigns owner-level income to assets in proportion to their operating MW; asset-level income enters directly. `SchemeCAgentInvestmentDefinition.decide` sums `capacity_mw` into `capacity`, income into `income`, total asset CAPEX into `replacement`, and operating expenditure into `operational`.

Thermal operating expenditure is generated MWh multiplied by generation, fuel, carbon and unit-time costs. The `agent_cashflow` row provides `generated_mwh`, `generation_cost_gbp_per_mwh`, `fuel_cost_gbp_per_mwh`, `carbon_cost_gbp_per_mwh` and `unit_time_cost_gbp_per_mwh`. Wind, solar and storage use zero operating deduction in this investment rule. The group’s `net` income, unit CAPEX, `roi` and payback are:

$$
\begin{aligned}\mathtt{net}&=\mathtt{income}-\mathtt{operational},\\\mathtt{cost\_per\_mw}&=\mathtt{replacement}/\mathtt{capacity},\\\mathtt{roi}&=\mathtt{net}/\mathtt{replacement},\\\mathtt{payback}&=\begin{cases}\mathtt{replacement}/\mathtt{net},&\mathtt{net}>0,\\\infty,&\mathtt{net}\le0.\end{cases}\end{aligned}
$$

`income`, `operational`, `net` and `replacement` are GBP; `cost_per_mw` is GBP/MW; `roi` is annual return and `payback` is years. Zero replacement capital gives zero `roi`. Thermal rounding differences are absorbed by setting `net` to zero when:

$$
|\mathtt{net}|\le10^{-9}\max(|\mathtt{income}|,\mathtt{operational}).
$$

Both methodology profiles use this net-income account. `preferred` takes the largest member `preferred_rate`, `life` the shortest `economic_lifetime_years`, and `target_payback` the shortest `target_payback_years`. Defaults are 0.08, 25 years and the group lifetime respectively; zero values invoke the same defaults. Investment compares undiscounted `roi` with `preferred` and undiscounted `payback` with `target_payback`, in constant start-year GBP.

A loss-making group with positive unit CAPEX retires capacity in proportion to its members’ MW. Profitable groups receive `Invest_High` when `roi>preferred`, otherwise `Invest_Profit` when `payback≤target_payback`; the remaining groups receive `Do_Nothing`. Both investment classes request profit divided by unit CAPEX.

$$
\begin{aligned}\mathtt{requested\_retirement}&=\min\left(\mathtt{capacity},\frac{|\mathtt{net}|\times \mathtt{target\_payback}}{\mathtt{cost\_per\_mw}}\right),\\\mathtt{requested}&=\mathtt{net}/\mathtt{cost\_per\_mw},\\\mathtt{addition}&=\min(\max(\mathtt{requested},0),\max(\mathtt{allowed},0)).\end{aligned}
$$

For wind, solar, the three battery types and hydrogen, `allowed` is the remaining technology limit; concurrent policies use their minimum. CCGT, OCGT, gas and biomass use their requested quantity as `allowed` under the uncapped eligibility policy. At a price equal to their operating cost, thermal assets have zero net income and zero additions. Nuclear follows an exogenous construction schedule; hydro and pumped-hydro additions require site and hydrological inputs.

Storage investment uses booked ahead and balancing income, including ahead remuneration retained during buy-back. Under the corrected methodology, Native dispatch settles storage at each stage’s uniform marginal price. Under the doctoral reproduction profile, storage receives its own highest accepted storage bid, and periods with an empty accepted-generator set carry zero income, as specified in Chapter 5. Surplus charging is free. The investment numerator is this recorded income before cycle depreciation and fixed OPEX; `tier_roi` remains inactive.

## Construction timing and planning success

Endogenous investment enters planning with the data pack’s construction timeline and regional success rate. Both methodology profiles apply this rule. `native_initial_state` uses `freeze_planning_parameters` to store `development_stage_timelines`, `repd_status_to_timeline`, `success_rates` and `timeline_statistic` in `state.extensions["planning_parameters"]`. Annual states inherit these frozen tables. Each proposed addition calls `endogenous_planning_terms` with its `technology`, `owner` and `decision_year`.

Technology labels select both timeline and success-rate tables. Solar maps to Solar Photovoltaics, onshore wind to Wind Onshore, offshore wind to Wind Offshore, and ordinary battery types and electrolysers to Battery. Gas, CCGT, OCGT and biomass use Wind Onshore. `hydrogen_battery` follows the default Solar Photovoltaics mapping. These mappings apply to investment planning.

The development status is Application Submitted. `_timeline_months` reads that status’s timeline type, normally total median duration; `planning.timeline_statistic=mean` selects the mean. A missing technology entry uses the solar entry, and a missing total mean falls back to total median. The resulting `months` is a nonnegative duration in months. Missing solar fallback data or invalid success rates stop proposal construction.

A project-specific timing displacement is stable across runs for the same owner. `model_project_key(owner)` forms `Model Decision: <owner>`. `stable_int_hash` converts the first 64 bits of its MD5 digest to an integer; the arithmetic remainder modulo 13, minus 6, gives `jitter` between −6 and +6 months. `endogenous_planning_terms` then rounds the duration and imposes commissioning at least one year after the decision:

$$
\begin{aligned}\mathtt{rounded\_months}&=\operatorname{round}(\max(1,\mathtt{months}+\mathtt{jitter})),\\\mathtt{source\_completion}&=\mathtt{decision\_year}+\left\lfloor\frac{\mathtt{rounded\_months}}{12}\right\rfloor,\\\mathtt{completion}&=\max(\mathtt{source\_completion},\mathtt{decision\_year}+1).\end{aligned}
$$

Rounding follows Python’s ties-to-even rule, so 58.5 months becomes 58 months. The proposal stores `completion` as `expected_completion_year`, and records `timeline_months`, `timeline_jitter_months`, `timeline_months_applied` and `completion_floor_applied`. New storage inherits the group’s energy-to-power ratio.

Success probability first uses the technology label and the owner’s mapped region, then the arithmetic mean across that label’s regions, then 0.75. `source_success_region` maps solar and onshore city names to their regions, names containing offshore to All Offshore, and other owners to England. Consequently battery and thermal owners usually take the table’s technology mean when England lacks an entry. The proposal records `success_probability=terms["success_rate"]` and the lookup source in `success_rate_source`. The city mapping is Nottingham–East Midlands, Ipswich–Eastern, London–London, Newcastle–North East, Manchester–North West, Edinburgh–Scotland, Portsmouth–South East, Bournemouth–South West, Cardiff–Wales, Birmingham–West Midlands and Sheffield–Yorkshire and Humber.

`SchemeCPlanningPipelineDefinition.admit_projects` applies the success outcome to each proposal. In `expected_capacity`, `capacity=proposal.capacity_mw×probability`; energy capacity, total CAPEX and total annual costs receive that factor once. In `seeded_stochastic`, the first 52 bits of the SHA-256 calculation on `seed:proposal_id`, divided by 2⁵²−1, determine `draw` on [0,1]; a positive `probability` admits full capacity when `probability=1` or `draw<probability`. Retirements take effect the following year.

The public2 tables give a 2025 offshore decision completion in 2033 or 2034 with success probability about 0.917; onshore decisions complete in 2029–2030 with regional probabilities about 0.22–0.71; solar completes in 2026–2027 at about 0.84–0.95; batteries complete in 2027 at about 0.873; thermal plant completes in 2030 at about 0.547. VALUE 101’s short timelines and unit success rates retain 2026 commissioning for its 2025 proposals.

Annual headroom is evaluated from that year’s operation. Each year begins investment with `remaining_caps=dict(caps)` and deducts that year’s accepted additions. Earlier proposals remain in the construction pipeline, so proposals from several years can accumulate against the same expansion opportunity.

## System costs and emissions

The resource-cost headline combines annualised in-service capital, applicable fixed OPEX and physical operating expenditure. `build_cem_cost_ledger` reads total annual capital into `capital` and physical operating cost into `operating`. `excluded` contains wind, solar and storage fixed OPEX in both profiles and existing-stock run-of-river compatibility capital in the corrected profile. `non_network_capital` is the fleet capital after subtracting declared network CAPEX and fixed OPEX; `operating_sum` is the reconciled physical operating total. The retained quantities are:

```text
headline_fleet_capital = max(non_network_capital - excluded, 0)
headline_capital = capital - (non_network_capital - headline_fleet_capital)
system_cost = headline_capital + operating_sum
served = max(demand - blackout - a2_hidden_unserved_mwh(market), 0)
```

The ledger’s `cem_system_cost_gbp` combines retained capital and physical operation; `cem_system_cost_gbp_per_mwh_served` divides by `served`. Wind, solar and storage fixed OPEX appears as a memo because the model treats it as included in levelised CAPEX. Thermal fixed OPEX remains included. Run-of-river compatibility capital is a memo under the corrected profile and included under the doctoral reproduction profile.

Native physical operating cost includes final-output generation, fuel, carbon and time costs, the applicable operating start-up term, recorded blackout at VoLL, and storage cycle wear. Restart costs used to order downward bids remain in the bid calculation. Corrected VoLL comes from `market.voll_gbp_per_mwh`, default 17,000 GBP/MWh; the doctoral reproduction rule uses 17,000 GBP/MWh. `a2_hidden_unserved_mwh` deducts additional stress shortfall from served demand and returns zero for a year with no stress periods. The cost headline prices recorded blackout, while additional stress shortfall is a separate energy entry.

Operating emissions multiply generated MWh by the selected kg/MWh factor and divide by 1,000 to obtain tonnes. `carbon_ledger.py` sums these into `operational`, combines them with annualised `embodied` emissions as `total`, and reports `overall_intensity=1000×total/delivered_demand_mwh`. The denominator equals served demand. Chapter 9 lists the factor values and CO₂ or CO₂e basis. Zero served demand leaves the intensities empty.

Annual embodied emissions follow the factor’s declared units. A `tCO2e_per_MW_year` factor gives `emissions=capacity_mw×factor.value` directly. Battery factors in `kgCO2e_per_kWh_capacity` are numerically tonnes per MWh of capacity, giving `emissions=asset.energy_capacity_mwh×factor.value/economic_life`. Hydrogen power equipment uses the annual MW factor; hydrogen energy storage uses its `tCO2e_per_MWh_capacity` factor divided by the asset’s `economic_life`. Missing factor inputs leave the affected component unassessed.

Storage-carbon tracing keeps mixed `inventory_energy` in MWh and `inventory_kg` in kilograms. Charging adds efficiency-adjusted stored energy and source carbon; discharging removes stored-side energy and carbon in the same inventory proportion. Source generation supplies the system emissions total.

Network constraint costs use a matched zonal and network-free dispatch comparison with the same resource prices, storage state, export envelope and VoLL. Chapter 7 defines the resource-cost and bid-objective differences. Settlement transfers, policy expenditure, construction commitments and residual values retain separate accounts.
