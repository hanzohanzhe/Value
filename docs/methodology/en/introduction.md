# Model framework

VALUE links electricity-system operation to annual changes in the asset fleet. Generation, storage and external electricity exchange participate in market clearing under specified demand and weather. Annual operating revenues, costs and expansion headroom then enter investment and retirement rules. Outputs include generation and storage operation, unserved energy, system resource cost, carbon emissions, operating capacity and construction projects.

## Temporal and spatial representation

VALUE uses a 0.5-hour operating interval and a fixed 365-day model year containing 17,520 intervals. The clock is UTC, with February represented by 28 days. Power is measured in MW and interval energy in MWh; interval energy equals power multiplied by interval duration. Investment decisions follow a complete operating year.

The national model represents Great Britain's electricity system as a single supply–demand node, with interconnectors represented by external boundary offers. The zonal model additionally specifies resource and demand locations, corridor capacities and boundary constraints. The network mappings, demand allocation and capacities jointly define the spatial system. Chapter 7 gives its constraints and solution method.

## Methodology profiles

The corrected profile, `value-corrected`, supplies VALUE's default settings and the principal formulation described in this document. The default national dispatch module, `value-bid-at-cost-psm`, applies the `native-corrected-v1` rule set. The staged dispatch module, `value-staged-bid-at-cost-psm`, connects a national schedule to subsequent balancing or zonal redispatch. Chapters 4, 5 and 7 specify the bidding, settlement and storage calculations for these operating pathways.

The doctoral-reproduction profile, `doctoral-lineage-0.6.0a2`, is a compatibility configuration retaining thesis-era settings as implemented in VALUE 0.6.0-alpha.2. It applies `native-doctoral-thesis-v1` and retains the earlier weather conversion, downward ordering and storage pricing. Both profiles share UTC demand and interconnector alignment, declared-column reading, thermal net revenue, one storage net position per period, single entries for downward adjustments and must-run surplus, a recorded-blackout value of £17,000/MWh, cost ledger v2 with physical operating expenditure, validation reports, and common definitions of shortfall and served energy. Endogenous proposals in both profiles use the development timelines and regional success rates frozen from the data pack. Each chapter states the compatibility values beside the relevant formulation.

The experimental national pathway, `value-doctoral-national-psm`, defines a separate national clearing and annual-accounting interface. It supplies fixed-year dispatch and experimental cash records; integrated annual-CEM readiness is false. Chapters 5 and 6 describe its operating algorithm and separate annual helpers. The profile and dispatch-module selections jointly identify the method used by a calculation.

The interface identifies the methodology profile separately from the dispatch module. The following names connect the calculation described here to the Study editor.

|Document term|English interface label|Chinese interface label|Module or profile|
|---|---|---|---|
|Corrected profile|Corrected methodology (default)|修正口径（默认）|`value-corrected`|
|Compatibility profile|Doctoral reproduction|论文复现口径|`doctoral-lineage-0.6.0a2`|
|Native national dispatch|National single node|全国单节点|VALUE live bid-at-cost PSM; `value-bid-at-cost-psm`|
|Experimental national pathway|Doctoral national physical PSM (experimental)|Doctoral national physical PSM (experimental)|`value-doctoral-national-psm`|

## Annual calculation

The default annual pathway uses the initial fleet, construction projects, demand and weather to determine annual operation. Existing construction projects advance at the beginning of the year, followed by preparation of available generation and external-exchange inputs. The dispatch module calculates annual operation. Operating results, investment rules and development times then determine the following year's assets and projects.

```text
state = initial_state
for year in range(initial_state.year, run.end_year + 1):
    advanced = self.planning.advance_year(run, state)
    model_input = self.psm_input_factory(run, advanced.operating_state)
    market = self.psm.run(model_input)
    headroom = []
    for slot in sorted(self.expansion_policies):
        policy = self.expansion_policies[slot]
        value = policy.evaluate(run, advanced.operating_state, market)
        headroom.append(value)
    investment_market = adapt_market_for_investment(
        market, advanced.operating_state)
    decision = self.investment.decide(
        run, advanced.operating_state, investment_market, tuple(headroom))
    decision = inherit_frozen_zone_shares(decision, advanced.operating_state)
    admission = self.planning.admit_projects(
        run, advanced.operating_state, decision.proposals)
    transition_state = YearState(
        year, advanced.operating_state.assets, advanced.active_projects,
        cumulative_metrics=state.cumulative_metrics,
        extensions=transition_extensions)
    next_state = self.transition.apply(
        run, transition_state, admission, decision)
    state = next_state
```

`run` contains the selected modules, parameters and model years. `state` holds operating assets and construction projects; `advanced.operating_state` is the fleet after the beginning-of-year planning update. `market` contains dispatch and annual accounts, `headroom` contains the technology expansion limits, and `decision.proposals` contains the new investment proposals. `transition_extensions` carries the annual storage-cost observations and solver-validation state into `next_state`. These names and calls follow the default annual sequence in `gridform_core/v2/orchestrator.py`; selected network-expansion modules add their own annual steps.


Default investment uses annual-income-based return and payback criteria, while annualised capital accounting uses a capital recovery factor. Gas and biomass investment income deducts generation, fuel, carbon and time-based operating costs. Wind, solar and storage treat gross revenue as investment profit, with fixed operating expenditure included in the capital-cost convention. Chapter 4 defines these default calculations; Chapter 6 gives the separate experimental account and investment interfaces.

Monetary calculations adopt a constant start-year-price convention, with 2025 as the default start year. Input tables also retain their original price years for technology costs, imported electricity and policy parameters. Chapter 2 lists price sources and conversions, and Chapter 5 gives restart costs in 2025 GBP.

## Data and results

Model inputs comprise demand, weather, initial assets, techno-economic parameters, construction projects and external electricity exchange. Chapter 2 specifies input files, time coverage, units and profile eligibility. Chapter 3 converts weather to available generation. Dataset and function names follow the corresponding calculations so that readers can locate their implementation.

Annual economic results enter the results page after the required physical and accounting checks pass. The corrected profile applies the selected pathway's validation gates, while the doctoral-reproduction profile checks every raw invariant. Period ledgers retain dispatch, storage, shortfall and cost records. Chapter 4 describes their relationship to annual results, and Chapter 9 gives carbon-accounting parameters.
