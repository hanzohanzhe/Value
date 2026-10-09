# Experimental annual accounts and investment

The experimental national pathway supplies period cash and physical states to separate annual-account and investment functions. The `doctoral.investment_basis=thesis_final9.6` selection uses `build_thesis96_asset_accounts` and `evaluate_thesis96_investment_accounts` with the policy and planning rules below. Chapter 4 defines the default investment rule. The experimental PSM supports fixed-year dispatch, and its results retain `scientific_release_eligible=false` and `doctoral_annual_cem_ready=false`.

R029 names the national study and its input family. Public1 contains 8,761 hourly solar values and lacks the required interval declaration; its eligibility excludes the corrected reader and doctoral reproduction whitelist. The public2 revision removes the value at 2023-01-01 00:00 UTC and declares all three VRE curves hourly. Public2 is supplied with the VALUE 0.7.0-alpha.1 release through the [website data page](https://value.ac/en/data/) and has been used with corrected Native dispatch. The experimental calculations here take explicitly supplied annual accounts, traces and parameters.

## Annual accounts and decision groups

An asset’s operating surplus combines ahead, balancing and policy receipts, then deducts variable and fixed OPEX. `build_thesis96_asset_accounts` requires a complete year of 17,520 half-hours. Each asset supplies `annual_fixed_opex_gbp` and `annualized_capital_cost_gbp`; the period ledger supplies market income and operating cost. All amounts in the following account are GBP for that year:

```text
operating_surplus_gbp = (
    market_income_gbp + balancing_income_gbp
    + cm_income_gbp + decarb_income_gbp + ancillary_income_gbp
    - variable_operating_cost_gbp - annual_fixed_opex_gbp)
annual_profit_gbp = operating_surplus_gbp - annualized_capital_cost_gbp
```

The account stores operating surplus in `net_revenue_gbp` and post-capital profit in `net_profit_gbp`. Here the explicitly supplied fixed expenditure is deducted once. Chapter 4 gives the default wind, solar and storage treatment, where fixed OPEX is included in levelised CAPEX.

`decide_doctoral_investment` pools active positive-capacity assets by investment owner and technology. It sums annual surplus and capital, calculates capacity-weighted CAPEX per MW, takes the largest preferred rate and shortest retirement target, then allocates additions across regions by operating MW shares. Nuclear and direct electrolysis follow exogenous treatment; new natural hydro and pumped hydro require site inputs.

The evaluator reads `surplus` from `operating_surplus_gbp`, `annual_capital` from `annualized_capital_cost_gbp`, `capex` from `capital_cost_per_mw_gbp`, and `preferred` from `preferred_rate`. Positive annual capital and unit CAPEX are required. Its `profit`, annual profit rate `rate` and recommendation are:

$$
\mathtt{profit}=\mathtt{surplus}-\mathtt{annual\_capital},\qquad\mathtt{rate}=\frac{\mathtt{profit}}{\mathtt{annual\_capital}}.
$$

```text
if surplus > annual_capital * (1 + preferred):
    recommendation = "Invest_High"
elif profit > 0:
    recommendation = "Invest_Profit"
elif surplus < 0:
    recommendation = "Deplete"
else:
    recommendation = "Do_Nothing"
```

Equality at the high-return threshold enters `Invest_Profit` when profit is positive. Nonnegative surplus with nonpositive post-capital profit retains capacity. `thesis_final96_contract.json` specifies preferred rates of 0.076 for solar and onshore wind, 0.089 for offshore wind and 0.12 for storage. The evaluator uses the rate supplied in each account.

Loss-based retirement uses the explicit `target_payback_years`. The default targets are 25 years for solar, CCGT, OCGT and hydrogen storage; 30 for onshore and offshore wind; 20 for biomass; and 10 for the three battery types. The literal technology `gas` uses 20 years.

## Expansion limits and investment quantities

Experimental VRE expansion limits the number of periods in which operational VRE plus a candidate addition exceeds demand. `thesis96_vre_annual_expansion_cap` reads `demand_mwh`, `operational_vre_available_mwh` and `generation_per_mw_mwh` into `demand`, `available` and `profile`. The first two arrays are period MWh; `profile` is period MWh per MW of candidate capacity. It calculates:

$$
\mathtt{net}=\mathtt{demand}-\mathtt{available},\qquad\mathtt{already\_negative}=\#\{\mathtt{net}<0\}.
$$

`negative_threshold` defaults to 200 periods and `cap_fraction` to 0.20. When `already_negative` reaches 200, the addition limit is zero. Otherwise, positive-profile periods with nonnegative net demand provide `transitions=net/profile`. The `needed=negative_threshold−already_negative` smallest-order position gives `critical` MW, and the limit is `cap_fraction×critical`. Fewer than `needed` transitions gives zero.

Storage uses an explicit annual technology allowance in `annual_caps`. `storage_expansion_from_traces` reads accepted VRE, actual demand, charging, post-charge surplus and discharge, then applies Chapter 4’s utilisation calculation. In the standard corrected lifecycle, the experimental PSM receives zero storage headroom with `leftover_trace_unavailable`; its standalone account analysis therefore requires the selected allowance and complete traces as inputs. The account threshold for storage is 12%, and annual storage price-and-profit-cap integration remains pending in the experimental PSM’s result record.

Retained profit defines `profit_floor_mw=max(profit,0)/capex`. Here `capacity` is the group’s `current_capacity_mw`, `capacity_by_tech[tech]` is the summed MW of parsed accounts for that technology, and `caps` contains the `annual_caps` input in MW. VRE groups receive a share of their technology allowance proportional to operating capacity: `share=capacity/capacity_by_tech[tech]` and `cap_share=caps[tech]×share`. `evaluate_thesis96_investment_accounts` sets `requested_addition_mw` as follows:

|Recommendation and technology|Requested MW|
|---|---|
|`Invest_High`, VRE|`cap_share`|
|`Invest_Profit`, VRE|`min(cap_share,profit_floor_mw)`|
|`Invest_High`, CCGT, OCGT or biomass|`0.01×capacity`|
|`Invest_High`, storage|`max(caps[tech],profit_floor_mw)`|
|`Invest_Profit`, other eligible technology|`profit_floor_mw`|
|`Deplete` or `Do_Nothing`|0|

High-return storage accounts share the same technology allowance subject to their retained-profit floors. Here `high` is the set of eligible `Invest_High` accounts for one technology, and `total` sums their requested MW. The allocator first calculates:

```text
allowed = max(
    sum(row["profit_floor_mw"] for row in high),
    min(total, caps.get(tech, 0)))
```

The allocator distributes `allowed` in proportion to requested MW. Accounts whose proportional allocation falls below `profit_floor_mw` receive that floor; the remaining budget is redistributed over the other requests until every bound is met. Profit-class storage directly receives its retained-profit quantity. A loss-making account sets `retirement_mw=min(capacity,−operating_surplus_gbp×target_payback_years/capital_cost_per_mw_gbp)`.

Accepted additions determine planned retained-profit and external funding. `spent` is the capital required for `accepted_addition_mw`; `retained` is the smaller of positive annual profit and that expenditure. The remainder becomes `externally_funded_capital_gbp`:

```text
spent = accepted_addition_mw * capital_cost_per_mw_gbp
retained = min(max(annual_profit_gbp, 0), spent)
profit_funded_addition_mw = retained / capital_cost_per_mw_gbp
externally_funded_capital_gbp = spent - retained
```

The adapter allocates `addition` to each region as `region_addition=addition×region_capacity/capacity`. Storage energy follows that region’s aggregate energy-to-power ratio, and `life` takes the minimum member economic lifetime. The resulting funding record uses a 0.05 loan rate and a tenor equal to `life`; separate equity recovery and loan-draw schedules are the remaining funding-interface work.

Endogenous timing and success use the same frozen tables as Chapter 4. `decide_doctoral_investment` calls `endogenous_planning_terms(state.extensions["planning_parameters"],technology,owner,decision_year)` for each regional proposal, then records `expected_completion_year`, `success_probability`, `timeline_months` and `success_rate_source`. Gas, CCGT, OCGT and biomass use onshore-wind planning parameters; hydrogen storage uses solar parameters. Ordinary batteries use Battery parameters.

```text
terms = endogenous_planning_terms(
    state.extensions["planning_parameters"],
    technology=technology, owner=owner, decision_year=market.year)
expected_completion_year = terms["completion_year"]
success_probability = terms["success_rate"]
```

For example, a 100 MW VRE group in a 1,000 MW technology fleet has a 0.10 capacity share. At a 200 MW technology allowance, £1m/MW unit CAPEX, £10m annual capital, £11m operating surplus and 7.6% preferred rate, annual profit is £1m and the rate is 10%. The group enters `Invest_High`, requests 20 MW and records £1m retained-profit funding plus £19m external funding.

## Policy transfers and expenditure

Policy scenarios distribute declared annual budgets across eligible assets. `basic` sets transfers to zero. `with_cm`, `decarbonisation_base`, `subsidy_as_usual` and `governmental_target` activate capacity-market and ancillary-service transfers; the latter three include existing decarbonisation support in policy expenditure. Budgets are explicit inputs in 2025 GBP.

`allocate_thesis96_policy` weights capacity-market receipts by de-rated capacity. For asset `name`, `cm_weights[name]=power×factor`, where `power` is operating MW and `factor` is the technology de-rating factor. The annual capacity-market budget is £5.44bn and is divided in proportion to these weights.

|Technology|De-rating factor|
|---|---:|
|CCGT, OCGT, biomass|0.95|
|Nuclear|0.85|
|Pumped hydro|0.95|
|1C battery|0.05|
|0.5C battery|0.15|
|0.25C battery|0.60|

Hydrogen storage supplies a scenario-specific de-rating factor. Ancillary payments follow operating MW among thermal, nuclear and storage assets. `subsidy_as_usual` and `governmental_target` allocate additional decarbonisation support by eligible VRE MW; under the latter, reaching a declared technology target ends eligibility. Existing support enters policy expenditure, and additional support enters eligible investment income. A zero eligible-capacity total leaves the budget unallocated.

`build_system_cost_views` keeps resource and historical expenditure views. The resource view adds supplied capital, operation and reliability expenditure and divides by served energy. The historical view adds capital, operation, policy levies and deficit at £17,000/MWh, then divides by non-battery generation, including eligible imports. The resource reliability input follows the run’s VoLL, default £17,000/MWh.

`legacy_carbon_metric` retains supplied historical carbon scalars under `unknown_source_scalar`. `physical_carbon_view` multiplies generation MWh by explicitly supplied kgCO₂e/MWh factors and divides by 1,000 to report operational tCO₂e. Storage-carbon inventories require their own charging, discharge and source-intensity inputs. Chapter 9 gives the current factor catalogue and gas labels.

## REPD projects and exogenous schedules

REPD preprocessing builds a construction pipeline from project status, capacity, region and milestone dates. `lookup_regional_success_rate` first reads the technology-region entry, then its technology’s regional mean, then 0.75. The status table determines whether success probability applies. Expected-capacity mode scales project MW once; seeded-stochastic mode draws a project-specific outcome from name, region and technology. The planner retains this preprocessing outcome.

For REPD projects, `resolve_repd_success` determines the stochastic outcome from `project_name`, `region` and the success-technology `label`. The comparison includes equality. The configured seed is retained as metadata; the draw is fixed by those three project fields:

```text
draw = (stable_int_hash(f"{project_name}|{region}|{label}") % 1_000_000) / 1_000_000
succeeds = draw <= rate
```

`completion_year_from_months` uses `base_year`, development duration `months` and `project_key`. A project-specific `jitter` is the remainder of `stable_int_hash(project_key)` modulo 13, minus 6 months; an empty key gives zero displacement. The returned year is:

$$
\begin{aligned}\mathtt{rounded\_months}&=\operatorname{round}(\max(1,\mathtt{months}+\mathtt{jitter})),\\\mathtt{completion\_year\_from\_months}&=\mathtt{base\_year}+\left\lfloor\frac{\mathtt{rounded\_months}}{12}\right\rfloor.\end{aligned}
$$

Granted projects combine pre-construction and construction durations; dates use day-first parsing. The forward schedule also respects full development time from application, the model start year and the initial snapshot’s start-year-plus-one floor. External projects that complete exactly in the start year can receive a deterministic one-to-three-year deferral. Endogenous proposals use the decision-year-plus-one floor specified in Chapter 4.

`preprocess_doctoral_project_records` retains eligible projects of at least 1 MW with completion by 2040. Its filters cover terminal, already-operational, past-completion and stagnant records. The default stale-status year is 2015, and construction has a two-year grace period. The output provides each retained project’s timing, probability and effective capacity.

The experimental pumped-hydro schedule specifies aggregate power, energy and already-annual expenditure. `apply_thesis96_pumped_schedule` reads the following rows from `thesis_final96_contract.json` for the named pumped-hydro asset. The annual capital amount and the selected capital-recovery factor define an equivalent total capital solely for the asset's economic fields.

|Model year|MW|MWh|Annual OPEX, million GBP|Annual capital, million GBP|
|---|---:|---:|---:|---:|
|2025|2,828|26,700|85.4|377.9|
|2026–2027|2,927.9|27,400|87.8|388.5|
|2028|3,377.9|30,200|96.1|425.1|
|2029|3,587.9|31,800|99.9|441.5|
|2030|4,187.9|40,800|112.4|496.8|
|2031–2034|5,687.9|70,800|134.9|596.4|
|2035|11,387.9|195,800|241.9|1,070.8|

Nuclear follows the frozen `value_uk_nuclear_policy_v1.json` schedule. Heysham 1, Hartlepool, Heysham 2 and Torness have 1,155, 1,185, 1,230 and 1,190 MW and leave the annual asset schedule from 2031. Sizewell B has 1,198 MW and leaves from 2056. Hinkley C's two 1,630 MW units enter full model-year operation in 2031 and 2032, while Sizewell C's 3,200 MW is retained in the 2035 pipeline. In default corrected Native dispatch, a station-policy data pack additionally applies the Chapter 5 load factors and the AGR cutoff at period 4,320 of 2030.

## Physical state between experimental years

The experimental period engine carries batch ages and generator memory across a completed year. Its absolute period index continues through the year boundary, retaining each surviving batch's charging index. Existing generator memory, including cumulative natural-resource budgets, is transferred; newly introduced generators use their supplied initial states. New storage begins with empty batches.

`DoctoralPeriodEngine.advance_year` requires consecutive complete model years and storage capacities sufficient for retained inventory. Retirement of a nonempty store or a reduction below its inventory requires an explicit disposition rule supplied through a further integration step. The implemented transition therefore preserves the inventory of continuing stores without an automatic retirement write-off. Annual account preparation, physical-state continuation and investment proposals remain separate interfaces with the input requirements described above.
