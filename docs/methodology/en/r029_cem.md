# Annual accounting and investment

VALUE updates operating capacity once per model year. Annual dispatch supplies electricity sales, operating costs and renewable surplus; these quantities determine investment and retirement. Accepted additions enter a construction pipeline and become operating assets in their completion year. The annual calculation therefore links the current fleet, market income, construction time and future capacity.

## Annual inputs and calculation order

The annual input `YearState` contains the year, operating assets, planning projects and storage-cost observations. Each asset has `capacity_mw` in MW, optional `energy_capacity_mwh` in MWh, technology, region and investment owner. Its economic fields contain total capital `total_capex_gbp`, annual fixed cost `annual_fixed_opex_gbp`, annualised capital `annualized_capital_cost_gbp`, lifetime `economic_lifetime_years`, required annual return `preferred_rate` and target payback `target_payback_years`. Chapter 2 specifies the initial fleet, project list and input values.

Projects enter operation before that year's dispatch. `SchemeCPlanningPipelineDefinition.advance_year` takes each successful project whose `expected_completion_year≤state.year`, adds its capacity and economic fields to the fleet, and removes it from the active pipeline. Later projects remain in the pipeline. Hydro projects enter operation when their site and hydrological inputs are complete. Failed projects contribute zero operating capacity.

Dispatch produces `market`, the annual `MarketYearResult`. Its period summaries contain actual demand, accepted VRE, storage charge and discharge, blackout energy and prices; its asset accounts contain generated MWh and market income. The annual algorithm then computes technology expansion limits, investment quantities, planning admission and the next state in this order:

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
decision = inherit_frozen_zone_shares(decision, advanced.operating_state)
admission = planning.admit_projects(
    run, advanced.operating_state, decision.proposals)
```

Here `advanced.operating_state` is the fleet available for the year, `headroom` contains permitted additions in MW by technology, `decision` contains new proposals and asset retirements, and `admission.next_pipeline` contains continuing and newly admitted projects. The input factory applies Chapters 2–3 to the updated fleet; Chapters 4–5 and 7–8 define the selected dispatch calculation. The final state update is given below.

## Asset capital and annual system cost

Asset capital is annualised over its economic lifetime with a capital-recovery factor. `build_asset_economic_extensions` reads `total_capex` in GBP, `life` in years and `discount_rate`, then sets `annualized_capital_cost_gbp=total_capex×crf`. The factor `crf=capital_recovery_factor(discount_rate,life)` uses the equation in Chapter 4; the default rate is 0.05. Generation capital is capacity times GBP/MW. Storage capital and fixed maintenance follow the technology catalogue and its declared power or energy basis in Chapter 2.

Annual system cost sums the resource costs of operating assets. The dispatch result supplies `total_levelized_capital_cost_gbp`, containing annualised capital and fixed maintenance, and `total_operational_cost_gbp`, containing physical operation. For Native, physical operation comprises the generation and import cost terms in Chapter 5, recorded blackout energy valued at `market.voll_gbp_per_mwh` (default 17,000 GBP/MWh), and storage cycle depreciation. The restart cost used to rank a downward bid enters that bid's price calculation. Network asset capital and fixed maintenance enter the annual resource account when network expansion is selected.

The system-cost account treats wind, solar and storage fixed maintenance as included in their levelised capital. Their separately recorded maintenance amounts are retained as memorandum items. Existing run-of-river capital recorded under `existing_stock_compatibility_capital_gbp` is also a memorandum item. Thermal fixed maintenance and commissioned network resource costs enter the cost total.

`build_cem_cost_ledger` reads the supplied capital total as `capital` and subtracts the two memorandum amounts as `excluded`. `network_capex` and `network_fom` are annual network capital and maintenance; `operating_sum` is the sum of the named physical operating components. All costs below are GBP per model year. `demand`, `blackout` and `served` are annual MWh:

```text
network_resource_cost = network_capex + network_fom
non_network_capital = max(capital - network_resource_cost, 0)
excluded = vre_storage_fom + compatibility
headline_fleet_capital = max(non_network_capital - excluded, 0)
headline_capital = capital - (non_network_capital - headline_fleet_capital)
system_cost = headline_capital + operating_sum
served = max(demand - blackout - a2_hidden_unserved_mwh(market), 0)
```

The variables `vre_storage_fom` and `compatibility` hold the wind/solar/storage maintenance memorandum and the existing run-of-river capital memorandum respectively. `a2_hidden_unserved_mwh` reads additional unserved energy from the annual energy-balance account; it is zero when that account records zero additional shortfall. The output `cem_system_cost_gbp=system_cost`, and `cem_system_cost_gbp_per_mwh_served=system_cost/served` for positive served demand. At zero served demand, cost per MWh is left empty. Market payments, policy transfers, construction commitments and residual values have separate accounts; the operating-resource sum uses the physical expenditure terms above.

## Annual income and investment groups

Investment groups combine positive-capacity assets with the same owner, technology and region. Owner identity comes from `investment_owner_id`, then `source_agent_id`, then the existing asset's identifier. An asset marked `investment_eligible=False` remains in dispatch and contributes zero endogenous investment. `SchemeCAgentInvestmentDefinition.decide` processes groups in sorted `(owner,technology,region)` order.

The investment calculation uses the annual market income attributable to each asset. Native distributes an agent's income over its mapped assets as specified in Chapter 5. For an owner-level settlement, `adapt_market_for_investment` allocates the owner's `income` in proportion to operating MW: `allocated[asset.asset_id]=income×asset.capacity_mw/capacity`, where `capacity` is that owner's summed MW. Direct asset-level accounts enter the investment calculation as supplied.

Thermal investment income deducts generated electricity times generation, fuel, carbon and unit-time cost. The asset's `agent_cashflow` row supplies `generated_mwh` and the four costs in GBP/MWh. Their product gives `operating_cost_gbp`; `operational` is the sum over the group's assets. Wind, solar and the three battery types and hydrogen use `operational=0`. Thus storage investment uses booked ahead and balancing income, including ahead remuneration retained during buy-back. Surplus charging has zero purchase cost, and cycle depreciation and fixed maintenance enter their respective resource-cost accounts above.

For each group, `capacity` sums operating MW, `income` sums annual GBP income and `replacement` sums `total_capex_gbp`. Unit capital cost `cost_per_mw` is GBP/MW, `roi` is annual net income divided by capital, and `payback` is years:

$$
\begin{aligned}
\mathtt{net}&=\mathtt{income}-\mathtt{operational},\\
\mathtt{cost\_per\_mw}&=\mathtt{replacement}/\mathtt{capacity},\\
\mathtt{roi}&=\mathtt{net}/\mathtt{replacement},\\
\mathtt{payback}&=\begin{cases}
\mathtt{replacement}/\mathtt{net},&\mathtt{net}>0,\\
\infty,&\mathtt{net}\le0.
\end{cases}
\end{aligned}
$$

Zero replacement capital gives `roi=0`. Thermal `net` is set to zero when `abs(net)≤10⁻⁹×max(abs(income),operational)`, absorbing the difference between sums of the same cashflows. `preferred` is the largest member `preferred_rate`, `life` is the shortest member `economic_lifetime_years`, and `target_payback` is the shortest member `target_payback_years`. Missing or zero values use 0.08, 25 years and `life` respectively. The initial default asset construction sets biomass, CCGT and OCGT target payback to 25 years. Other initial values are given in Chapter 2. The decision compares the annual input amounts directly through `roi` and `payback`.

## Annual wind and solar expansion limits

Wind and solar expansion is bounded by peak demand and the technology's available-output profile. In `canonical_psm_data`, `demand` is the half-hour energy demand in MWh, `period_hours=0.5`, `availability` is the dimensionless technology profile, and `capacity_by_technology[technology]` is its operating MW. The input uses the investment profiles prepared in Chapter 3. The maximum profile value is `peak`, and additional capacity headroom is:

$$
\begin{aligned}
\mathtt{peak}&=\max_t\mathtt{availability}[t],\\
\mathtt{headroom}[\mathtt{technology}]&=\max\left(0,
\frac{\max_t\mathtt{demand}[t]}
{\mathtt{period\_hours}\times\max(\mathtt{peak},10^{-12})}
\right.\\
&\qquad\left.-\mathtt{capacity\_by\_technology}[\mathtt{technology}]
\right),\\
\mathtt{limits}[\mathtt{technology}]&=
\mathtt{fraction}\times\mathtt{headroom}[\mathtt{technology}].
\end{aligned}
$$

`SchemeCVREExpansionPolicyDefinition.evaluate` reads `fraction` from `expansion.vre_cap_fraction`, default 0.20, and returns `limits` in MW. For a 1,000 MW peak demand, `peak=0.8` and 300 MW operating capacity, `headroom=950` MW and the annual limit is 190 MW. A zero profile peak uses the denominator floor 10⁻¹². These limits are calculated separately for solar, onshore wind and offshore wind.

## Annual storage expansion limits

Storage expansion uses the renewable surplus remaining after the operating stores have charged. `corrected_storage_headroom` reads `leftover_excess_mwh` from `storage_headroom_inputs` into `leftover`, and each period's `vre_accepted_mwh`, `real_demand_mwh` and `storage_discharge_mwh` into `vre`, `demand` and `discharge`. These arrays are MWh per period. Surplus available to an additional store and the remaining demand gap are:

$$
\begin{aligned}
\mathtt{excess}&=\max(\mathtt{leftover},0),\\
\mathtt{deficit}&=\max(\mathtt{demand}-\mathtt{vre}-\mathtt{discharge},0).
\end{aligned}
$$

A virtual store converts these series into charging and discharging profiles. `_simulate_virtual_pool` begins with `soc=0`, has `power_mw=10⁹` MW and `energy_cap_mwh=10⁹` MWh, and places the round-trip efficiency `rte=0.98` entirely on charging. `PERIOD_HOURS=0.5`; `exc`, `dfc`, `ch` and `dis` are period MWh. Charging precedes discharging in each period:

```text
max_period_mwh = power_mw * PERIOD_HOURS
soc = 0
charge = zeros(len(excess))
discharge = zeros(len(excess))
for t in range(len(excess)):
    exc = excess[t]
    dfc = deficit[t]
    if exc > 1e-9 and soc < energy_cap_mwh - 1e-9:
        ch = min(exc, max_period_mwh, (energy_cap_mwh - soc) / max(rte, 1e-9))
        soc += ch * rte
        charge[t] = ch
    if dfc > 1e-9 and soc > 1e-9:
        dis = min(dfc, max_period_mwh, soc)
        soc -= dis
        discharge[t] = dis
```

Charging and discharging energy divided by 0.5 h give `charge_mw` and `discharge_mw`. `aligned_max_mw` finds the largest power exceeded for at least `min_hours` in both profiles. `hours_above_power(power_mw,p_mw)` counts values strictly above `p_mw` and multiplies by 0.5 h. The upper search bound `peak` is the smaller charging/discharging peak. Zero peak or insufficient hours above zero gives a zero result; `min_hours≤0` gives `peak`. For positive attainable duration, the search starts at `lo=0`, `hi=peak` and performs 64 bisection steps:

```text
for _ in range(64):
    mid = 0.5 * (lo + hi)
    if (hours_above_power(charge_mw, mid) >= min_hours
            and hours_above_power(discharge_mw, mid) >= min_hours):
        lo = mid
    else:
        hi = mid
return lo
```

`aligned_utilisation_spectrum` applies the search at 730, 365, 52 and 0 hours, producing `mw_730`, `mw_365`, `mw_52` and `mw_0`. The successive capacity bands, all in MW, are:

$$
\begin{aligned}
\mathtt{daily}&=\mathtt{mw\_730},\\
\mathtt{interday}&=\max(\mathtt{mw\_365}-\mathtt{mw\_730},0),\\
\mathtt{weekly}&=\max(\mathtt{mw\_52}-\mathtt{mw\_365},0),\\
\mathtt{seasonal}&=\max(\mathtt{mw\_0}-\mathtt{mw\_52},0).
\end{aligned}
$$

The output stores `daily` under `daily_loop` and `interday` under `intraday`. `corrected_storage_headroom` reads the latter into `intraday`, calculates `power_room=max(daily+intraday,0)`, and sets `power_cap=fraction×power_room`. Each of `1c_battery`, `0.5c_battery` and `0.25c_battery` receives this separate technology limit. Hydrogen receives `hydrogen_cap=fraction×max(seasonal,0)`. Here `fraction` comes from `expansion.storage_cap_fraction`, default 0.20; the weekly band remains a reported quantity. The same year's groups consume their technology's remaining limit in the order defined above.

The storage calculation takes a complete 17,520-period year and its post-charge surplus series. Native dispatch supplies this series. The returned storage limits are zero for a shorter chronology, a period length other than 0.5 h, or an absent post-charge series. This zero rule also defines the storage-investment result when staged, LP or DC dispatch supplies the annual operating result without that series.

## Investment quantities and retirement

Each technology follows the eligibility mode in `investment_eligibility.json`. Solar, onshore wind, offshore wind, the three battery types and hydrogen use `headroom_required`. CCGT, OCGT, `gas` and `bio_and_waste` use `explicit_uncapped`. Nuclear capacity follows the external project and retirement schedule. Pumped hydro and run-of-river hydro follow site-based projects; the generic profit rule supplies zero proposals for these technologies.

Concurrent expansion rules combine through the smallest limit for each technology. `caps` holds that minimum, and each year starts with `remaining_caps=dict(caps)`. Earlier projects remain in the construction pipeline; only additions proposed in the current year's investment pass reduce `remaining_caps`. Several decision years can consequently retain pending projects against the same capacity opportunity.

A group with `net<0` and positive `cost_per_mw` retires capacity. Its retirement is limited by the group's existing MW and allocated to members in proportion to their MW. For other groups, `roi>preferred` selects `Invest_High`; otherwise `payback≤target_payback` selects `Invest_Profit`; the remaining groups receive `Do_Nothing`. Both investment classes request `net/cost_per_mw`. The requested retirement and permitted positive addition are:

$$
\begin{aligned}
\mathtt{requested\_retirement}&=\min\left(\mathtt{capacity},
\frac{|\mathtt{net}|\times\mathtt{target\_payback}}
{\mathtt{cost\_per\_mw}}\right),\\
\mathtt{requested}&=\mathtt{net}/\mathtt{cost\_per\_mw},\\
\mathtt{addition}&=\min\left(\max(\mathtt{requested},0),
\max(\mathtt{allowed},0)\right).
\end{aligned}
$$

For `headroom_required`, `allowed=remaining_caps.get(technology,0)` and a positive `addition` reduces that remaining limit. For `explicit_uncapped`, `allowed=requested`. `Do_Nothing`, nonpositive unit capital cost and nonpositive `addition` produce zero new capacity. As a numerical example, a 100 MW group with £100 million total capital, £10 million net income, `preferred=0.08` and 20 MW remaining headroom has `roi=0.10`, `payback=10` years and `requested=10` MW; the resulting proposal is 10 MW before planning success is applied.

New storage retains the group's energy-to-power ratio. For members with energy capacity, `duration=sum(asset.energy_capacity_mwh)/capacity` hours and `proposal_energy=addition×duration` MWh. The proposal's economic fields are constructed from technology capital parameters and `life`; non-storage fixed maintenance is allocated as `fixed_om×addition/capacity`. Storage capital and maintenance use the catalogue. The proposal retains its investment owner, so its later dispatch income joins that owner's group. In zonal runs, `inherit_frozen_zone_shares` assigns the new proposal the members' capacity-weighted zone shares.

## Construction timing and planning success

Each endogenous addition enters planning at the Application Submitted stage. Initial loading copies `development_stage_timelines`, `repd_status_to_timeline`, `success_rates` and `timeline_statistic` into `state.extensions["planning_parameters"]`; subsequent years use the same tables. `endogenous_planning_terms` reads these tables with the proposal's `technology`, `owner` and `decision_year`.

Technology determines the planning-table labels. Solar uses Solar Photovoltaics, onshore wind uses Wind Onshore, offshore wind uses Wind Offshore, and ordinary batteries and electrolysers use Battery. Gas, CCGT, OCGT and biomass use Wind Onshore. `hydrogen_battery` uses Solar Photovoltaics. The corresponding timeline keys are `solar`, `onshore`, `offshore` and `battery`.

The stage table supplies development duration `months`. `_timeline_months` normally reads total median duration for Application Submitted; `planning.timeline_statistic=mean` selects the corresponding mean. A missing technology timeline uses the `solar` entry, and an absent total mean uses total median. Required durations are finite and nonnegative. The data and initial-project timing rules are specified in Chapter 2.

The duration includes an owner-specific displacement from −6 to +6 months. `model_project_key(owner)` returns `Model Decision: <owner>`, and `stable_int_hash` converts its MD5 result to an integer using the first 16 hexadecimal digits. The following implemented arithmetic gives the completed year. `round` uses ties to even, so 58.5 months rounds to 58:

```text
key = model_project_key(owner)
jitter = (stable_int_hash(key) % 13) - 6
rounded_months = int(round(max(1, months + jitter)))
year = int(decision_year)
source_completion = year + rounded_months // 12
completion = max(source_completion, year + 1)
```

The proposal stores `completion` as `expected_completion_year`. Thus the earliest endogenous commissioning is the year after the investment decision. For the public2 tables, 2025 offshore proposals complete in 2033 or 2034, onshore in 2029–2030, solar in 2026–2027, ordinary batteries in 2027, and thermal plant in 2030. The VALUE 101 tables use shorter durations, giving 2026 commissioning for 2025 proposals.

Success probability is read by technology label and region. `source_success_region` maps the solar and onshore owner names' cities to regions: Nottingham–East Midlands, Ipswich–Eastern, London–London, Newcastle–North East, Manchester–North West, Edinburgh–Scotland, Portsmouth–South East, Bournemouth–South West, Cardiff–Wales, Birmingham–West Midlands and Sheffield–Yorkshire and Humber. An owner name containing offshore maps to All Offshore; other owners map to England. `_success_rate` first takes the matching region, then the arithmetic mean across that technology's regional entries, then 0.75. Probabilities lie in [0,1].

The public2 offshore probability is approximately 0.917; onshore regional values are approximately 0.22–0.71 and solar values 0.84–0.95. Ordinary battery owners use approximately 0.873 and thermal owners approximately 0.547 through the technology-mean fallback. VALUE 101 uses success probability 1. These probabilities apply when the new proposal is admitted into planning.

The default `planning.success_mode=expected` selects `mode=expected_capacity` and admits `capacity=proposal.capacity_mw×probability`. Energy capacity, total capital, annualised capital and annual fixed cost receive the same factor once; unit prices, lifetime and return parameters retain their values. A zero probability gives zero admission. Subsequent years commission the admitted capacity at its scheduled time.

`planning.success_mode=stochastic` selects `mode=seeded_stochastic` and admits the full proposal when a deterministic draw is below its probability. `seed` comes from `planning.random_seed`, default 0. The proposal identifier combines `run.run_id`, the decision year, owner and the zero-based index of the sorted investment group. The same input fields yield the same draw; changing the run identifier changes it:

```text
proposal_id = f"{run.run_id}:{market.year}:{owner}:{index}"
digest = hashlib.sha256(f"{seed}:{proposal_id}".encode("utf-8")).hexdigest()
draw = int(digest[:13], 16) / float(16 ** 13 - 1)
success = probability > 0 and (probability == 1 or draw < probability)
capacity = proposal.capacity_mw if success else 0
```

`SchemeCPlanningPipelineDefinition.admit_projects` appends admitted projects to the active pipeline. At the start of a later year, a due project becomes an asset named `commissioned:<project_id>`, carrying its admitted MW, MWh, owner and economic fields. Run-of-river projects require `hydrology_profile_id`, `capital_cost_scope=new_build` and `new_build_cost_source_id`; pumped hydro additionally requires `site_constraint_id` and `energy_capacity_mwh`. A due project with missing site fields remains deferred in the pipeline.

## State update and annual outputs

Retirements change the following year's capacity and economic quantities. `SchemeCStateTransitionDefinition.apply` sets `next_year=current_state.year+1`. If an asset's declared `model_unavailable_from_year` has been reached, the full asset retires; otherwise the requested retirement applies. `resize_asset_economics` limits capacity at zero and scales energy capacity, fixed maintenance and capital with the surviving asset:

```text
new_capacity = max(capacity_mw, 0)
ratio = new_capacity / old_capacity
new_energy = old_energy * ratio
total_capex = (capital_cost_per_mw * new_capacity
               + capital_cost_per_mwh * new_energy)
annual_fixed_opex_gbp *= ratio
annualized_capital_cost_gbp = total_capex * capital_recovery_factor(
    capital_discount_rate, economic_lifetime_years)
```

Here `capacity_mw` is old capacity less requested retirement, `old_capacity` and `new_capacity` are MW, and `old_energy` and `new_energy` are MWh for storage. For a project-level capital amount with both unit capital fields equal to zero, `total_capex` is its previous capital multiplied by `ratio`. A zero remaining capacity sets the asset status to `retired`. Economic lifetime determines annualisation and the investment payback fallback; scheduled retirement uses the declared unavailable year or the loss-based retirement quantity above.

The next `YearState` contains surviving assets, `admission.next_pipeline` and the year's storage-cost observations. `transition_state` supplies the commissioned operating fleet, continuing projects and updated observations to `transition.apply`; its output year advances by one. Physical storage restarts from the Chapter 4 opening conditions, while sales observations feed the next annual cost calculation.

Annual outputs contain dispatch energy, income, system cost, technology limits, investment proposals, planning admissions and next-year capacity. Cost per served MWh uses the account above. Chapter 9 defines operational and embodied emissions, storage-carbon tracing and the construction emissions of optional network additions. At the study horizon, `report_only` returns the final state, `pipeline_tail` advances projects already in the pipeline, and `full_extension` continues annual operation and investment.
