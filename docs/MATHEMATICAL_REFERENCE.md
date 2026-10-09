# VALUE mathematical and algorithmic reference

Version 0.7.0-alpha.1, October 2026. Methodology edition 0.4.1, 9 October 2026.

The nine chapters below contain the English methodology used by the website and downloadable documents. The [Chinese chapters](methodology/README.md) follow the same calculations, variable names and sequence.


## 1. Model framework

VALUE links electricity-system operation to annual changes in the asset fleet. Generation, storage and external electricity exchange participate in market clearing under specified demand and weather. Annual operating revenues, costs and expansion headroom then enter investment and retirement rules. Outputs include generation and storage operation, unserved energy, system resource cost, carbon emissions, operating capacity and construction projects.

### Temporal and spatial representation

VALUE uses a 0.5-hour operating interval and a fixed 365-day model year containing 17,520 intervals. The clock is UTC, with February represented by 28 days. Power is measured in MW and interval energy in MWh; interval energy equals power multiplied by interval duration. Investment decisions follow a complete operating year.

The national model represents Great Britain's electricity system as a single supply–demand node, with interconnectors represented by external boundary offers. The zonal model additionally specifies resource and demand locations, corridor capacities and boundary constraints. The network mappings, demand allocation and capacities jointly define the spatial system. Chapter 7 gives its constraints and solution method.

### Methodology profiles

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

### Annual calculation

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

### Data and results

Model inputs comprise demand, weather, initial assets, techno-economic parameters, construction projects and external electricity exchange. Chapter 2 specifies input files, time coverage, units and profile eligibility. Chapter 3 converts weather to available generation. Dataset and function names follow the corresponding calculations so that readers can locate their implementation.

Annual economic results enter the results page after the required physical and accounting checks pass. The corrected profile applies the selected pathway's validation gates, while the doctoral-reproduction profile checks every raw invariant. Period ledgers retain dispatch, storage, shortfall and cost records. Chapter 4 describes their relationship to annual results, and Chapter 9 gives carbon-accounting parameters.


## 2. Initial data and input processing

VALUE combines demand, weather, assets, planning data and external-market inputs on a common model clock. The source year determines the demand or weather sample; the model year determines asset operation and investment. The data package and methodology profile jointly determine the reading rules.

| Data configuration | Package | Coverage and availability |
|---|---|---|
| VALUE 101 | `value-101-baseline-v1` | Bundled synthetic teaching data for 2025–2026, with 17,520 half-hours per year and a 48-period exercise |
| GBP1 public1 | `value-uk-open-data-pack-v1` | Published GB inputs; eligible for the doctoral reproduction profile |
| GBP1 public2 | `value-uk-open-data-pack-public2` | Revision for the corrected methodology, published with VALUE 0.7.0-alpha.1 ([download](https://value.ac/en/data/)) |
| R029 public2 | `value-uk-calendar-vx-trade001-public2` | Revision for the corrected methodology, published with VALUE 0.7.0-alpha.1 ([download](https://value.ac/en/data/)); study window 2025–2034, 2022 demand and 2020–2024 weather |

The corrected GB studies require the declared columns, source units and time resolutions supplied by the public2 revisions or an eligible user workspace package. R029 public1 (`value-uk-calendar-vx-trade001`) is outside the doctoral reproduction whitelist; its 8,761-value solar investment profile also fails the corrected reader's annual-length requirement. Chapter 3 describes the revised profile. GB 23-zone network studies use the GBP1 public2 research suite, `value-uk-research-suite-v1-public2`, available from the [data page](https://value.ac/en/data/). It supplies the compatible national and spatial inputs for the corrected methodology.

### Temporal resolution and input roles

The national model balances half-hourly energy. In `canonical_psm_data`, the arrays in `series` contain demand power in MW; multiplication by `period_hours` gives actual `demand` and forecast `forecast_demand` in MWh per period. Annual energy is the sum of the period values:

$$
\begin{aligned}
\mathtt{demand}[t]&=\mathtt{series}[\text{demand.real}].\mathtt{values}[t]\times\mathtt{period\_hours},\\
\mathtt{forecast\_demand}[t]&=\mathtt{series}[\text{demand.forecast}].\mathtt{values}[t]\times\mathtt{period\_hours},\\
\mathtt{period\_hours}&=0.5\ \mathrm{h},\qquad \mathtt{periods}=365\times24\times2=17{,}520.
\end{aligned}
$$

The model year consists of 365 days on a fixed UTC clock, with 28 days in February. Declared leap-year demand is reduced to this calendar while preserving annual energy, as defined below and in Chapter 4. Capacity is measured in MW, inventory in MWh, money in GBP and electricity prices in GBP/MWh.

Demand enters the model as MW and is multiplied by the period duration for dispatch. VALUE 101 retains a `mwh` column name and MWh/period package label for values that are read as MW in both profiles. User-mapped demand instead follows its declared source unit: MWh/period is divided by the source-period duration in hours to obtain MW.

Data bindings assign physical files to defined computational roles. Demand files supply actual demand and the day-ahead forecast, the fleet table supplies technology, capacity and representative location, and planning tables supply project status and dates. Weather and technology-average profiles support spatial available generation and the corresponding investment rules, respectively.

| Input role | Main data or fields | Computational use |
|---|---|---|
| Actual and forecast demand | `demand_mw` in `actual_mw.csv`; `forecast_mw` in `forecast_mw.csv` | Real-time balancing, day-ahead clearing and demand error |
| Fleet and initial assets | `fleet.json`, annual `operating_state` | Technology parameters, representative locations and dispatch capacities |
| Projects and planning | `repd_projects_normalized.csv`, `regional_technology_success_rates.csv`, `planning_timelines.json` | Initial operational assets, project success rates and stage durations |
| Weather | `calendar_mean_solar_2020_2024.nc`, `calendar_mean_wind_2020_2024.nc` | Available wind and solar generation at representative points |
| Technology-average profiles | `sa.csv`, `wa.csv`, `we.csv` | Technology-average investment inputs for solar, onshore wind and offshore wind |
| Capital and policy | `capital_costs.json`, `model_parameters.json`, `mechansim cost.xlsx` | Investment costs, financial parameters and policy expenditure |
| External markets | Country-specific `flow_mw`, `price_gbp_per_mwh` | Available interconnector exchanges and external offers |
| Zonal network | Zones, corridors, boundaries, asset mapping and zonal demand | Spatial supply–demand balance and transmission constraints |

### Declared reading and annual alignment

Both profiles read a declared `csv_column` under its declared `csv_header` convention. An implicitly selected integer index column terminates loading. R029 demand and boundary series use this shared reader through `data_method.read_role` and `data_method.read_boundary`.

The corrected methodology uses `declared-v2`. Without a header declaration, the first row is treated as a header only when all its cells are non-numeric. Without a column declaration, strict reading requires a single wholly numeric column. The source interval is read from `interval_minutes`, or inferred as hourly for 8,760 or 8,784 values. Each hourly value then supplies two half-hours.

A 17,568-period leap-year demand series loses the 48 periods on 29 February and rescales the remainder to preserve annual energy. `normalize_half_hour_year` reads the source as `numbers` and stores the retained values as `reduced`. With a positive retained total, it returns

$$
\begin{aligned}
\mathtt{original}&=\sum\mathtt{numbers},\qquad \mathtt{retained}=\sum\mathtt{reduced},\\
\mathtt{scale}&=\mathtt{original}/\mathtt{retained},\\
\mathtt{normalize\_half\_hour\_year}(\mathtt{values})&=\bigl(\mathtt{item}\times\mathtt{scale}\ :\ \mathtt{item}\in\mathtt{reduced}\bigr).
\end{aligned}
$$

A zero retained sum with a non-zero original sum terminates reading; an all-zero series remains zero. Other roles remove the leap day without energy rescaling. The binding may explicitly retain the leap day through `leap_policy=keep`, in which case the run takes its required leading periods.

Strict reading truncates a sufficiently long series to the run length and repeats a shorter series only when cycling is declared or supplied by the role convention. Boundary roles use this cycling convention. Corrected non-workspace packages use strict reading; user workspace packages use lenient reading and repeat a shorter sequence from the beginning. Mapping requires confirmation of that repetition.

```text
read = read_series(path, spec, mode=policy.reader_mode,
                   strictness=policy.strictness, legacy_header=header)
values = align_clock(read.values, periods, spec, mode=policy.clock_mode,
                     strictness=policy.strictness,
                     hourly_repeat=hourly_repeat, cyclic_default=cyclic)
return values
```

The doctoral reproduction profile uses `legacy-v1`: its role-specific header settings, largest-numeric-column selection and short-series repetition remain active alongside declared-column reading. In GBP1 public1, the headerless forecast's first value, 21,560, is consumed as a header, so forecast values lead the actual series by one period. The corrected reader retains this first value as data.

### Demand series and calendar processing

R029 uses NESO's 2022 day-ahead half-hourly demand forecasts and corresponding actual demand as the base demand shapes for model years. GBP1 demand uses the same UTC preprocessing rules in both profiles. `actual_mw.csv` and `forecast_mw.csv` each contain 17,520 rows. Their initial statistics are given below; subsequent scenario scaling acts on these base shapes.

| Series | Minimum power MW | Maximum power MW | Mean power MW | Annual energy MWh |
|---|---:|---:|---:|---:|
| Actual demand | 15,080 | 46,042 | 26,587.967637 | 232,910,596.5 |
| Day-ahead forecast | 14,240 | 46,760 | 26,611.131963 | 233,113,516 |

Demand preprocessing identifies duplicate records by settlement date and period, then converts UK local dates to a UTC time axis. For a given settlement period, it retains the latest publication; equal publication times are resolved by retaining the last row. The original 17,518 rows become 17,516 after duplicate consolidation, and four missing half-hours are filled by linear interpolation in UTC.

Linear interpolation divides the difference between the two known endpoint values into equal increments. A gap of one half-hour receives the endpoint mean. A gap of two half-hours receives the values one-third and two-thirds of the way from the preceding observation to the following observation.

Each gap in the 2022 input contains at most two consecutive periods, and all filled values occur on 30 October. The table reports MW values to six decimal places.

| UTC time | Forecast demand MW | Actual demand MW |
|---|---:|---:|
| 2022-10-30 09:00 | 22,638.666667 | 24,649 |
| 2022-10-30 09:30 | 22,899.333333 | 24,727 |
| 2022-10-30 23:00 | 19,063.333333 | 20,494.666667 |
| 2022-10-30 23:30 | 19,086.666667 | 19,689.333333 |

### Initial assets and planned projects

Initial wind, solar and storage assets are determined jointly by REPD technology, operational status, commissioning year and capacity. The input uses the second-quarter 2025 edition of the DESNZ Renewable Energy Planning Database, released in July. The source table contains 12,977 projects and 53 fields; normalisation retains 10,653 projects and 14 fields.

Normalisation retains recognised technologies with positive capacity and standardises technology names, numerical fields and dates. The 14 fields cover project identifier, site name, standardised and source technology names, MW capacity, development status, region, country, application date, permission date, construction date, operational date and two coordinates. Failed numerical conversions and missing source dates remain missing for subsequent filtering. Standardised technologies include onshore wind, offshore wind, solar, batteries and gas.

Initial operating capacity comprises assets commissioned by the study's starting year. `build_repd_operational_snapshot` selects wind, solar and storage projects with `Operational` status, a commissioning year at or before the starting year, and positive capacity, then maps them to representative assets. Battery capacity is allocated according to storage-template `pool_limit` weights. Nuclear capacity follows a separate station policy and annual commissioning and retirement schedule.

The R029 2025 initial asset specification contains the capacities below. The table describes its configured starting stock, with aggregated nuclear, gas and several other technologies. In the corrected default pathway, GBP1 studies with station policies use station-level nuclear availability and monthly retirement; R029 aggregated nuclear capacity uses an availability factor of 0.723. Run-of-river output uses a load factor of 0.3487 multiplied by seasonal shape (Chapter 5). The doctoral reproduction profile retains availability of 100%; the separate experimental R029 pathway also retains that input convention.

| Technology | Asset rows | Power MW | Stored energy MWh |
|---|---:|---:|---:|
| Combined-cycle gas turbine CCGT | 1 | 28,000 | — |
| Run-of-river hydro | 1 | 2,000 | — |
| Nuclear | 1 | 5,958 | — |
| Open-cycle gas turbine OCGT | 1 | 4,146 | — |
| Biomass and waste | 1 | 4,762 | — |
| Offshore wind | 18 | 14,679 | — |
| Onshore wind | 11 | 14,711.65 | — |
| Solar | 11 | 10,066.98 | — |
| 0.25C battery | 1 | 299.984165 | 1,199.936659 |
| 0.5C battery | 1 | 2,465.869834 | 4,931.739667 |
| 1C battery | 1 | 74.996041 | 74.996041 |
| Hydrogen storage | 1 | 0.749960 | 187.490103 |
| Pumped hydro | 1 | 2,828 | 26,700 |

Planning inputs specify success probabilities by technology and region and duration distributions by technology and stage. `regional_technology_success_rates.csv` contains 46 records; `planning_timelines.json` supplies stage durations in months. Both tables govern REPD projects and endogenous investment. The model freezes `development_stage_timelines`, `repd_status_to_timeline` and `success_rates` in the initial state.

Endogenous proposals obtain their development duration and probability from these frozen tables under both methodology profiles. Technology labels, regional matching, deterministic month displacement, commissioning dates and expected-capacity or seeded-stochastic admission follow Chapters 4 and 6. `endogenous_planning._success_rate` takes the rate for the technology label and region, then the mean across that label's regions, then 0.75. The input development and construction medians are

| Technology | Median development months | Median construction months |
|---|---:|---:|
| Solar | 27.8 | 4.9 |
| Onshore wind | 62.5 | 15.0 |
| Offshore wind | 110.1 | 32.2 |
| Battery | 31.3 | 10.1 |

### Costs and storage parameters

Investment inputs specify unit capital costs, payback targets and technical operating parameters separately. R029 uses `capital_costs.json` and `model_parameters.json` from its study configuration. Upstream capital-cost sources include BEIS Electricity Generation Costs 2020 and Arup material; the table reports the parameters adopted by the model. The default rate for annual capital recovery is 0.05; investment decisions compare undiscounted return and payback. The table gives the base-configuration payback targets and `preferred_rate` parameters. R029's investment rule sets the effective threshold for all four expandable storage technologies to 0.12; Chapter 6 defines its profit ratio and decision rules.

| Technology | Capital cost GBP/MW | `preferred_rate` | Target payback years |
|---|---:|---:|---:|
| Solar | 659,000 | 0.076 | 25 |
| Onshore wind | 1,588,000 | 0.076 | 30 |
| Offshore wind | 3,976,000 | 0.089 | 30 |
| CCGT / OCGT | 2,400,000 | 0.089 | 25 |
| Biomass and waste | 1,500,000 | 0.089 | 20 |
| 1C battery | 330,000 | 0.0825 | 10 |
| 0.5C battery | 350,000 | 0.165 | 10 |
| 0.25C battery | 415,000 | 0.0825 | 10 |
| Hydrogen storage | 600,000 | 0.01375 | 25 (default) |

Storage parameters assign charging efficiency, discharging efficiency, duration and lifetime to inventory and cost calculations. Round-trip efficiency is `charge_efficiency * discharge_efficiency`; for example, the 0.5C battery uses \(0.98^2=0.9604\). Catalogue economic lifetimes and the payback targets above enter the calculations as separate parameters. The cycle parameter `maximum_cycles` determines reference annual cycles. The three battery technologies also use it for cycle depreciation. The dynamic storage-cost module uses time recovery for pumped hydro and hydrogen storage; the corrected default dispatch uses the cycle-only offer rule described in Chapter 5.

| Technology | Catalogue duration h | Charging efficiency | Discharging efficiency | Catalogue economic life years | Cycle parameter `maximum_cycles` |
|---|---:|---:|---:|---:|---:|
| Pumped hydro | 4 | 0.87 | 0.87 | 30 | 1,000,000 |
| 1C battery | 1 | 0.81 | 0.81 | 15 | 3,000 |
| 0.5C battery | 2 | 0.98 | 0.98 | 15 | 5,000 |
| 0.25C battery | 4 | 0.81 | 0.81 | 15 | 8,000 |
| Hydrogen storage | 250 | 0.57 | 0.57 | 10 | 1,000 |

Annual asset schedules can specify storage power and energy directly. The 2025 pumped-hydro asset state therefore uses 2,828 MW and 26,700 MWh.

Initial stored energy follows the dispatch pathway. The experimental R029 chronology starts from zero; general chronological inputs default to 50% of maximum inventory unless specified. The default national PSM constructs storage objects at each annual boundary, as described in Chapter 5.

Financial calculations select time parameters by computational purpose and technology configuration. Biomass uses an economic life of 25 years and a payback target of 20 years. The gas prototype has a 20-year payback target, while the R029 run configuration sets CCGT and OCGT to 25 years.

Amounts are interpreted in constant start-year money; the supplied studies begin in 2025. The storage catalogue, pumped-hydro capital cost and policy budgets explicitly use 2025 GBP. Fuel and carbon prices are treated on that basis, while restart costs use the conversion documented in Chapter 5. BEIS 2020 costs, the 2022 euro price series and nuclear-policy entries labelled 2015 or 2024 retain their source-year values after any currency conversion. Thus the common monetary convention includes inputs of different price vintages; the reader applies the declared currency conversion.

Policy expenditure inputs combine historical aggregation with forward assumptions. `mechansim cost.xlsx` assembles NESO Capacity Market and balancing-cost data, Ofgem RO/FIT/REGO material and LCCC CfD data for annual policy expenditure calculations.

### Interconnectors and zonal demand

External market inputs describe cross-border exchange opportunities through flow limits and prices for each half-hour. R029 provides one 17,520-row file for each of France, Belgium, the Netherlands, Norway and Ireland, binding each file to both flow and price roles. Fields include `period`, `flow_mw`, `price_gbp_per_mwh`, the source price hour, a half-hour marker, and source row numbers for flows and prices.

Boundary prices use European day-ahead prices assembled by Ember from ENTSO-E data. France, Belgium, the Netherlands and Norway use 2022 prices, while Ireland uses 2021. Each hourly price is repeated twice and saved in GBP/MWh after dividing EUR/MWh by 1.1 EUR/GBP. The corrected methodology preserves negative boundary prices. The doctoral reproduction profile clips general chronological prices at zero; the experimental R029 pathway preserves negative prices.

Each boundary uses its NESO line identity. `NEMO_FLOW` supplies Belgium, `BRITNED_FLOW` the Netherlands and `NSL_FLOW` Norway. The registered GBP1 file `Belgium_price.csv` supplies its `Price (EUR/MWhe)` column as hourly EUR/MWh. `read_series` divides `values` by `spec.eur_per_gbp = 1.1` once and repeats each converted hour into two half-hours. The kernel reads the flow corresponding to each period.

These rules apply to both profiles. GBP1 flow values are read as MW despite their retained MWh/period labels.

Boundary flows provide exogenous exchange limits in source-period order. The field `flow_mw` uses positive values for imports and negative values for exports. `canonical_psm_data` converts it to signed MWh as `raw_availability`; the non-negative energy limits `import_energy` and `export_energy` are

$$
\begin{aligned}
\mathtt{raw\_availability}[t]&=\mathtt{flow\_mw}[t]\times\mathtt{period\_hours},\\
\mathtt{import\_energy}[t]&=\max(\mathtt{raw\_availability}[t],0),\\
\mathtt{export\_energy}[t]&=\max(-\mathtt{raw\_availability}[t],0).
\end{aligned}
$$

The corrected default national PSM offers import capacity in day-ahead clearing; the doctoral reproduction profile offers it only in balancing (Chapter 5). The public2 revisions retain the declared sign convention, positive for import and negative for export, with status `declared_unverified`: source verification of country-level annual net flow remains pending. The input ranges and mean prices below describe the R029 files.

| Boundary | Flow range MW | Price year | Mean price GBP/MWh |
|---|---:|---:|---:|
| Belgium | −1,022 to 1,020 | 2022 | 222.292608 |
| France | −3,091 to 2,997 | 2022 | 250.789325 |
| Ireland | −987 to 998 | 2021 | 123.937076 |
| Netherlands | −1,076 to 1,062 | 2022 | 219.917959 |
| Norway | −1,263 to 1,399 | 2022 | 126.503575 |

Zonal studies allocate national study demand using the network pack's period-specific regional shares. In `align_zonal_demand`, mode `scenario_scaled_zonal_shares` sets `output_real` to study actual demand and reads `network_national` from the network pack at each `index`. All demand quantities are MWh per period. Each zone receives `value`, appended to `aligned[zone_id]`:

$$
\begin{aligned}
\mathtt{scale}&=\frac{\mathtt{output\_real}[\mathtt{index}]}{\mathtt{network\_national}},\\
\mathtt{value}&=\mathtt{network\_demand\_mwh\_by\_zone}[\mathtt{zone\_id}][\mathtt{index}]\times\mathtt{scale}.
\end{aligned}
$$

The final zone receives national demand minus the sum of the other zones, conserving the spatial total. Loading terminates if network national demand is zero while study demand is non-zero. The alternative `network_pack_absolute_demand` uses network national demand directly and adjusts the forecast using the original forecast-to-actual ratio. Zone, corridor and asset-mapping constraints are defined in the transmission chapter.

### VALUE 101 synthetic inputs

VALUE 101 generates daily peaks, seasonal variation and two local demand disturbances with deterministic functions in `build_value_101_packs`. The function `_demand` returns demand power in MW. It calculates `day` and `hour` from half-hour index `period`, and combines the following morning, evening, overnight and winter terms. `weekday` is 1 when `day % 7 < 5` and 0.92 otherwise; `teaching_peak` is 30 MW when `day` is 0 or 182 and `period % 48 == 31`, and zero otherwise:

$$
\begin{aligned}
\mathtt{day}&=\lfloor\mathtt{period}/48\rfloor,\qquad
\mathtt{hour}=(\mathtt{period}\bmod48)/2,\\
\mathtt{morning}&=9\exp\bigl[-((\mathtt{hour}-8)/2.2)^2\bigr],\\
\mathtt{evening}&=19\exp\bigl[-((\mathtt{hour}-19)/2.5)^2\bigr],\\
\mathtt{overnight}&=2\exp\bigl[-((\mathtt{hour}-1)/3.5)^2\bigr],\\
\mathtt{winter}&=1+0.16\cos(2\pi\mathtt{day}/365).
\end{aligned}
$$

$$
\begin{aligned}
\mathtt{\_demand}(\mathtt{period})=\operatorname{round}\bigl[&
(22+\mathtt{morning}+\mathtt{evening}+\mathtt{overnight})\\
&\times\mathtt{winter}\times\mathtt{weekday}+\mathtt{teaching\_peak},\ 6\bigr].
\end{aligned}
$$

The forecast function `_forecast_demand` adds `balancing_margin` to `_demand(period)` and rounds to six decimal places. `balancing_margin` is 12 MW when `day` is 0 or 182 and `period % 48 == 30`; it is zero in the other periods.

The solar investment profile `_solar_profile` multiplies daylight and seasonal factors. It returns zero for `hour < 6` or `hour > 18`. Within that daylight window, using the same `day` and `hour` definitions,

$$
\begin{aligned}
\mathtt{daylight}&=\sin((\mathtt{hour}-6)\pi/12),\\
\mathtt{season}&=0.58+0.42\sin^2((\mathtt{day}-80)2\pi/365),\\
\mathtt{\_solar\_profile}(\mathtt{period})&=\operatorname{round}\bigl[\max(0,\min(\mathtt{daylight}\times\mathtt{season},1)),\ 6\bigr].
\end{aligned}
$$

The wind investment profile `_wind_profile` combines daily, 29-day and annual components and limits the coefficient to 0.08–0.92:

$$
\begin{aligned}
\mathtt{within\_day}&=\mathtt{period}\bmod48,\\
\mathtt{value}={}&0.42+0.13\sin((\mathtt{within\_day}+5)2\pi/48)\\
&+0.12\sin((\mathtt{day}+17)2\pi/29)\\
&+0.08\cos((\mathtt{day}+31)2\pi/365),\\
\mathtt{\_wind\_profile}(\mathtt{period})&=\operatorname{round}\bigl[\max(0.08,\min(\mathtt{value},0.92)),\ 6\bigr].
\end{aligned}
$$

Offshore investment availability is 1.08 times `_wind_profile(period)`, capped at 1 and rounded to six decimal places. The three sequences are saved under `profiles.vre_solar`, `profiles.vre_onshore` and `profiles.vre_offshore`.

Teaching weather is specified separately on one grid point at 52°N, 0°E for 8,760 hours. In this calculation, `hour` is the zero-based index through the year. The solar array `hourly_solar` is in J/m² and the wind-speed array `hourly_wind` in m/s:

$$
\begin{aligned}
\mathtt{hourly\_solar}[\mathtt{hour}]&=\mathtt{\_solar\_profile}(2\mathtt{hour})\times3{,}600{,}000,\\
\mathtt{hourly\_wind}[\mathtt{hour}]&=7+2\sin((\mathtt{hour}+3)2\pi/24)\\
&\quad+1.2\sin((\lfloor\mathtt{hour}/24\rfloor+17)2\pi/29).
\end{aligned}
$$

The weather wind speed passes through the generation curve for dispatch; the technology profiles supply the investment rule. The French boundary has a 12 MW import limit and a price of 82 GBP/MWh. The other four boundaries have zero exchange capacity and placeholder prices of 200 GBP/MWh. `build_value_101_packs` writes these demand, weather and market sequences into the teaching package.

### Data eligibility and user mappings

Package validation separates structural validity, chronology and physical plausibility. Structure determines whether a package can be installed. Chronology checks boundary identity, price currency, local-time demand, known row-order issues, forecast alignment and declared timestamps. Plausibility checks use the ranges in `value_data_plausibility_v1.json`.

The `profile_eligibility` decision combines those findings with the profile's package whitelist. In the corrected methodology, chronology findings for non-workspace packages and plausibility failures for scientific reference packages block preflight. They remain warnings under doctoral reproduction, whose whitelist separately excludes user workspaces and the VALUE 101 network package. Successful package validation is followed by role-specific reading; VRE investment-profile clock requirements are checked at that stage.

User demand mappings declare columns, units and, when provided, timestamps in UTC or Europe/London. Local timestamps are converted row by row to UTC. Declared day/month order resolves dates as DD/MM/YYYY or MM/DD/YYYY; otherwise it is inferred. Unreadable, duplicate, decreasing, gapped or irregular timestamps block submission.

Mapped sequences enter the model in row order from 1 January 00:00 UTC and repeat in each model year. A differing source year generates a notice; the reader preserves row order, weekdays and holidays from the input. Hourly demand identified by 8,760 or 8,784 rows or a 60-minute timestamp interval expands to half-hours after source-unit conversion. Short inputs require confirmation of repetition. A mapped demand total above 1.5 times or below 0.67 times the replaced annual total generates a notice containing both energy totals.

Mapped euro prices use the declared exchange rate and its annual-average, monthly-average or fixed-rate basis. The declared price year is recorded, and a year other than 2025 generates a notice; only the currency conversion is applied.

### Data and implementation

NESO supplies the demand source, DESNZ REPD supplies projects, Copernicus ERA5 single levels supplies weather, and Ember's ENTSO-E compilation supplies boundary prices. `import_scheme_c_1000twh` normalises project data. `series_reader.py` and `data_method` read time series; `interconnector_identity` assigns boundary series; `known_data_objects_v1.json` associates recognised input files with their declarations and row transformations. `data_validation_layers` evaluates package eligibility, `model_clock` defines UTC periods, and `zonal_demand_alignment` distributes national demand among zones.


## 3. Weather and available generation

VALUE calculates each asset's available wind and solar energy from its capacity and representative-point weather. The dispatch fields `available_mw` and `available_mwh` denote available power in MW and period energy in MWh; `capacity_mw` is installed power, `availability` is the weather-derived dimensionless output coefficient, and `period_hours` is the period duration. For each asset and period,

$$
\begin{aligned}
\mathtt{available\_mw}&=\mathtt{capacity\_mw}\times\mathtt{availability},\\
\mathtt{available\_mwh}&=\mathtt{available\_mw}\times\mathtt{period\_hours},\\
\mathtt{period\_hours}&=0.5\ \mathrm{h}.
\end{aligned}
$$

Market clearing accepts generation up to this available-energy limit. Annual expansion uses the technology-average investment profiles or the experimental physical-availability rule specified below.

### Weather sequences and representative-point sampling

R029 averages the 2020–2024 ERA5 hourly observations by calendar month, day and hour and reuses the resulting 365-day climatology in each model year. The original sequence contains 43,848 hours. Removing 48 hours on 29 February leaves five observations for every retained calendar hour; their arithmetic mean gives 8,760 hours.

Wind speed is calculated from the 100 m wind-vector magnitude at each original hour before calendar averaging: `wind_speed` is the square root of `u100` squared plus `v100` squared. The files retain all three fields. `hourly_unit_cf` preferentially reads `wind_speed`; for a file containing only `u100` and `v100`, it calculates the vector magnitude at the input time.

The climatology retains a 0.25° grid over Great Britain and nearby seas. The solar file represents downward solar radiation as `ssrd`, while the wind file provides 100 m wind information. Spatial and temporal array dimensions are given below.

| Input | Latitude range | Longitude range | Latitude × longitude × day × hour |
|---|---|---|---|
| Solar radiation | 45°–65°N | 14°W–4°E | 81 × 73 × 365 × 24 |
| 100 m wind | 46°–65°N | 14°W–5°E | 77 × 77 × 365 × 24 |

Each representative point uses the nearest latitude and nearest longitude in the weather grid. `point_series` selects `lat_index` and `lon_index` from the coordinate arrays `lats` and `lons`, with site coordinates `latitude` and `longitude` in degrees:

$$
\begin{aligned}
\mathtt{lat\_index}&=\operatorname*{arg\,min}_{j}|\mathtt{lats}[j]-\mathtt{latitude}|,\\
\mathtt{lon\_index}&=\operatorname*{arg\,min}_{k}|\mathtt{lons}[k]-\mathtt{longitude}|.
\end{aligned}
$$

`point_series` accepts latitude–longitude–day–hour and time–latitude–longitude arrays and flattens the selected point into an hourly sequence. The corrected profile reads `time_convention`; a field labelled `GRIB_stepType=accum` uses hourly interval-end accumulation, while a field lacking both declarations uses the instantaneous convention. `hour_index` produces `index` for zero-based half-hour index `t` and source length `hours`:

$$
\mathtt{index}[t]=\begin{cases}
(\lfloor t/2\rfloor+1)\bmod\mathtt{hours},&\text{accumulation\_end\_of\_hour},\\
\lfloor(t+1)/2\rfloor\bmod\mathtt{hours},&\text{instantaneous}.
\end{cases}
$$

The accumulated convention assigns the radiation for the hour ending at 01:00 to periods beginning at 00:00 and 00:30. Solar geometry uses the midpoint of each receiving period. The instantaneous convention assigns the 00:00 sample to period 00:00 and the 01:00 sample to periods 00:30 and 01:00.

The doctoral reproduction profile uses `index = (t // 2) % hours`, repeating each source value for two half-hours. Original GBP1 weather groups by day of year into 366 days, or 8,784 hours, and uses the first 8,760 hours. R029's 8,760-hour calendar climatology carries the instantaneous convention in its current metadata. The experimental R029 dispatch pathway retains the hourly-repeat clock and raw generation curves.

### Wind conversion and losses

Wind availability follows cut-in, cubic growth, rated output and cut-out segments. `wind_unit_output` expresses the power curve on a 20-unit scale; `hourly_unit_cf` divides its result by 20 to obtain the dimensionless hourly coefficient `hourly`. Wind speed `speed`, rated speed `rated` and cut-out speed `cut_out` are in m/s:

$$
\mathtt{wind\_unit\_output}(\mathtt{speed})=\begin{cases}
0,&\mathtt{speed}<3\ \text{or}\ \mathtt{speed}>\mathtt{cut\_out},\\
20\dfrac{\mathtt{speed}^3-27}{\mathtt{rated}^3-27},&3\le\mathtt{speed}<\mathtt{rated},\\
20,&\mathtt{rated}\le\mathtt{speed}\le\mathtt{cut\_out}.
\end{cases}
$$

Onshore wind uses `rated = 9.7` and `cut_out = 25`; offshore wind uses `rated = 10.5` and `cut_out = 30`. The corrected profile multiplies `hourly[index]` by `multiplier`, the product of the wake, energy-availability and electrical factors in `value_uk_vre_loss_factors_v1.json`.

| Technology | Wake factor | Energy-availability factor | Electrical factor | `multiplier` |
|---|---|---|---|---|
| Onshore wind | 0.95 | 0.97 | 0.98 | 0.90307 |
| Offshore wind | 0.88 | 0.945 | 0.98 | 0.814968 |

At 8 m/s, the onshore raw coefficient is 0.5476061707 and its corrected coefficient is approximately 0.49453. A 100 MW asset therefore supplies approximately 49.453 MW of available power. The doctoral reproduction profile uses the raw curve with a multiplier of 1. The separate experimental R029 pathway also retains the raw curve.

### Solar radiation and array-plane conversion

The corrected profile converts accumulated horizontal ERA5 radiation to irradiance on a south-facing tilted plane, then applies a performance ratio of 0.83 and a coefficient ceiling of 1. `hourly_unit_cf` reads `ssrd` into `raw` in J/m² and converts each value to `hourly` in kW/m²:

$$
\mathtt{hourly}=\begin{cases}
\mathtt{raw}/3{,}600{,}000,&3{,}600<\mathtt{raw}\le36{,}000{,}000,\\
0,&\text{otherwise}.
\end{cases}
$$

Array tilt follows latitude. In `optimal_tilt_jacobson_jadhav`, `phi` is latitude in degrees north; the function applies the 0°–65°N polynomial from [Jacobson and Jadhav (2018), Solar Energy 169, 55–66](https://web.stanford.edu/group/efmh/jacobson/Articles/I/TiltAngles.pdf). Its returned value becomes `tilt`, in degrees, in `plane_of_array`:

$$
\mathtt{tilt}=1.3793+\mathtt{phi}\times\bigl[1.2011+\mathtt{phi}\times(-0.014404+0.000080509\mathtt{phi})\bigr].
$$

Solar geometry uses each half-hour midpoint. `period_clock` produces `day_of_year` and `utc_hours` from zero-based period index `t`; `day_angle` gives the annual angle `g`. The functions `declination`, `equation_of_time_minutes` and `eccentricity_factor` use the following implemented coefficients. Their outputs are declination `decl` in radians, the time correction in minutes and a dimensionless orbital-distance factor:

$$
\begin{aligned}
\mathtt{day\_of\_year}&=(\lfloor t/48\rfloor\bmod365)+1,\\
\mathtt{utc\_hours}&=(t\bmod48)/2+0.25,\\
\mathtt{g}&=2\pi(\mathtt{day\_of\_year}-1)/365.
\end{aligned}
$$

$$
\begin{aligned}
\mathtt{decl}={}&0.006918-0.399912\cos\mathtt{g}+0.070257\sin\mathtt{g}\\
&-0.006758\cos2\mathtt{g}+0.000907\sin2\mathtt{g}\\
&-0.002697\cos3\mathtt{g}+0.00148\sin3\mathtt{g}.
\end{aligned}
$$

$$
\begin{aligned}
\mathtt{equation\_of\_time\_minutes}({}&\mathtt{day\_of\_year})=\\
229.18\bigl(&0.000075+0.001868\cos\mathtt{g}-0.032077\sin\mathtt{g}\\
&-0.014615\cos2\mathtt{g}-0.04089\sin2\mathtt{g}\bigr).
\end{aligned}
$$

$$
\begin{aligned}
\mathtt{eccentricity\_factor}({}&\mathtt{day\_of\_year})=\\
&1.000110+0.034221\cos\mathtt{g}+0.001280\sin\mathtt{g}\\
&+0.000719\cos2\mathtt{g}+0.000077\sin2\mathtt{g}.
\end{aligned}
$$

Longitude and the time correction determine `solar_time` and hour angle `omega`. The function `incidence_cosines` converts latitude and tilt to radians as `phi` and `beta`; its outputs become `cos_z` and `cos_theta`, the cosines of zenith angle and incidence angle:

$$
\begin{aligned}
\mathtt{solar\_time}={}&\mathtt{utc\_hours}+\mathtt{longitude\_deg}/15\\
&+\mathtt{equation\_of\_time\_minutes}(\mathtt{day\_of\_year})/60,\\
\mathtt{omega}={}&\pi(\mathtt{solar\_time}-12)/12,\\
\mathtt{cos\_z}={}&\sin(\mathtt{phi})\times\sin(\mathtt{decl})\\
&+\cos(\mathtt{phi})\times\cos(\mathtt{decl})\times\cos(\mathtt{omega}),\\
\mathtt{cos\_theta}={}&\sin(\mathtt{phi}-\mathtt{beta})\times\sin(\mathtt{decl})\\
&+\cos(\mathtt{phi}-\mathtt{beta})\times\cos(\mathtt{decl})\times\cos(\mathtt{omega}).
\end{aligned}
$$

The horizontal irradiance `ghi` is separated into beam and diffuse components using the hourly relation of [Erbs, Klein and Duffie (1982), Solar Energy 28(4), 293–302](https://www.sciencedirect.com/science/article/pii/0038092X82903024). `extraterrestrial_normal` equals 1.361 kW/m² times `eccentricity_factor(day_of_year)`. For positive `ghi` and zenith below 87°, the clearness index `kt` and diffuse fraction `kd` are

$$
\mathtt{kt}=\min\left(1,\max\left(0,\frac{\mathtt{ghi}}{\mathtt{extraterrestrial\_normal}\times\mathtt{cos\_z}}\right)\right),
$$

$$
\begin{aligned}
\mathtt{middle}={}&0.9511-0.1604\mathtt{kt}+4.388\mathtt{kt}^2\\
&-16.638\mathtt{kt}^3+12.336\mathtt{kt}^4,\\
\mathtt{kd}={}&\begin{cases}
1-0.09\mathtt{kt},&\mathtt{kt}\le0.22,\\
\mathtt{middle},&0.22<\mathtt{kt}\le0.80,\\
0.165,&\mathtt{kt}>0.80.
\end{cases}
\end{aligned}
$$

The [Hay–Davies (1980) transposition](https://pvlib-python.readthedocs.io/en/stable/reference/generated/pvlib.irradiance.haydavies.html) combines beam, anisotropic sky-diffuse and ground-reflected irradiance. `dhi`, `bhi` and `dni` denote diffuse horizontal, beam horizontal and direct normal irradiance in kW/m²; `anisotropy`, `beam_ratio`, `sky_view` and `ground_view` are dimensionless. With `albedo = 0.2`, the array-plane irradiance `poa` is

$$
\begin{aligned}
\mathtt{dhi}&=\mathtt{kd}\times\mathtt{ghi},\qquad \mathtt{bhi}=\mathtt{ghi}-\mathtt{dhi},\\
\mathtt{dni}&=\mathtt{bhi}/\mathtt{cos\_z},\\
\mathtt{anisotropy}&=\min(1,\max(0,\mathtt{dni}/\mathtt{extraterrestrial\_normal})),\\
\mathtt{beam\_ratio}&=\max(\mathtt{cos\_theta},0)/\mathtt{cos\_z},\\
\mathtt{sky\_view}&=(1+\cos\mathtt{beta})/2,\\
\mathtt{ground\_view}&=(1-\cos\mathtt{beta})/2,\\
\mathtt{beam}&=\mathtt{bhi}\times\mathtt{beam\_ratio},\\
\mathtt{sky\_diffuse}&=\mathtt{dhi}\times\bigl[\mathtt{anisotropy}\times\mathtt{beam\_ratio}\\
&\qquad +(1-\mathtt{anisotropy})\times\mathtt{sky\_view}\bigr],\\
\mathtt{ground}&=\mathtt{ghi}\times\mathtt{albedo}\times\mathtt{ground\_view},\\
\mathtt{poa}&=\mathtt{beam}+\mathtt{sky\_diffuse}+\mathtt{ground}.
\end{aligned}
$$

For zenith at or above 87° or zero `ghi`, the calculation sets `kd = 1`, `dhi = ghi`, `bhi = 0`, `dni = 0`, `anisotropy = 0` and `beam_ratio = 0`. The same array-plane sum retains diffuse and ground-reflected irradiance. For corrected accumulated inputs, `site_cf_by_source` converts `poa` into the output coefficient `values`:

$$
\mathtt{values}=\min(0.83\mathtt{poa},1).
$$

The accumulated-input convention selects array-plane conversion. Corrected instantaneous inputs, including the current R029 calendar climatology and VALUE 101 synthetic input, apply 0.83 directly to horizontal irradiance. The doctoral reproduction profile and experimental R029 pathway retain horizontal conversion with a multiplier of 1. The following pseudocode uses the implemented function and variable names:

```text
hourly, evidence = hourly_unit_cf(ds, technology, latitude, longitude, binding)
index = hour_index(periods, len(hourly), method.clock, evidence["time_convention"])
values = hourly[index]
poa_applied = False
if technology == "solar" and method.plane_of_array:
    poa_applied, reason = plane_of_array_applies(method, evidence["time_convention"])
    if poa_applied:
        values, poa_evidence = plane_of_array(values, latitude_deg=latitude,
            longitude_deg=longitude, parameters=plane_of_array_parameters())
multiplier = method.multiplier(technology)
values = values * multiplier
if poa_applied:
    values = minimum(values, 1.0)
return values
```

### Comparison with observed load factors

The GBP1 representative-point weather calculation can be compared with national load factors from [DUKES Table 6.3](https://www.gov.uk/government/statistics/renewable-sources-of-energy-chapter-6-digest-of-united-kingdom-energy-statistics-dukes). The model values below are unweighted means across representative points, each evaluated over 17,520 half-hours before curtailment. DUKES divides national generation by the mean of installed capacity at the beginning and end of the year and by annual hours. These definitions determine the scope of the comparison.

| Technology | GBP1 corrected | DUKES 2019–2024 mean | DUKES 2020–2024 mean | Corrected / 2020–2024 mean | GBP1 doctoral reproduction |
|---|---|---|---|---|---|
| Onshore wind | 0.4026 | 0.2593 | 0.2582 | 1.56 | 0.4458 |
| Offshore wind | 0.4913 | 0.4016 | 0.4009 | 1.23 | 0.6028 |
| Solar PV | 0.1065 | 0.1033 | 0.1025 | 1.04 | 0.1201 |

The corrected wind values remain above the observed national averages. The calculation combines unadjusted ERA5 wind speeds, one power curve for each wind technology and fixed loss multipliers. DUKES measures realised fleet generation, including the effects of dispatch and the operating fleet's composition. The table provides an external comparison for the specified parameterisation.

The solar calculation uses a climatological radiation series followed by nonlinear decomposition and transposition. For the GBP1 representative points, the calculated diffuse share is approximately 0.63–0.75 and the ratio of array-plane to horizontal irradiation is approximately 1.05–1.10. These quantities describe the adopted climatology and transformation; year-specific simulations require year-specific weather inputs.

### Project locations, asset aggregation and zones

Wind and solar projects obtain their spatial weather correspondence through representative points of the same technology. The initial GB template contains 11 solar and 11 onshore representative points, plus 21 offshore point names. R029's 2025 initial specification contains 11 solar, 11 onshore and 18 offshore assets with positive capacity. `fleet.locations` and generator names jointly specify representative-point locations.

Projects with explicit coordinates use the nearest same-technology representative point. `nearest_site` converts project latitude and longitude to radians as `lat1` and `lon1`, and candidate coordinates as `lat2` and `lon2`. Its great-circle distance is

$$
\begin{aligned}
\mathtt{a}&=\sin^2\frac{\mathtt{lat2}-\mathtt{lat1}}{2}\\
&\quad+\cos(\mathtt{lat1})\times\cos(\mathtt{lat2})\times\sin^2\frac{\mathtt{lon2}-\mathtt{lon1}}{2},\\
\mathtt{distance}&=2\arcsin\sqrt{\mathtt{a}}\times6{,}371\ \mathrm{km}.
\end{aligned}
$$

Equal distances retain the first point in the candidate list. Solar and onshore projects without an explicit location first use the REPD region mapping below.

| REPD region | Representative point |
|---|---|
| East Midlands | Nottingham |
| Eastern | Ipswich |
| London | London |
| North East | Newcastle |
| North West | Manchester |
| Scotland | Edinburgh |
| South East | Portsmouth |
| South West | Bournemouth |
| Wales | Cardiff |
| West Midlands | Birmingham |
| Yorkshire and Humber | Sheffield |

Remaining unlocated projects are distributed in proportion to existing same-technology capacity. In `commissioned_project_weather`, `stock[name]` is the operating capacity at a representative point and `total_stock` is its sum across the technology. Located projects entering operation in the same year are included first. Each remaining point receives `total_new * stock[name] / total_stock` MW, with the final point receiving the remainder. Zero total capacity selects the first representative point; assigned amounts at or below 0.000001 MW have zero weather weight.

Assets retain the `weather_source_weights` fixed at commissioning. `source_weights` supplies the mapping `weights`; `_map_lineages` combines each source curve `values` with its associated `weight`. The resulting dimensionless curve `combined` is

$$
\mathtt{combined}[t]=\sum_{\mathtt{name}}\mathtt{weights}[\mathtt{name}]\times\mathtt{values}_{\mathtt{name}}[t].
$$

The weather reader checks source technology and finite, non-negative weights. The weights sum to 1 apart from the bounded effect of the 0.000001 MW allocation rule. Subsequent capacity changes retain these weights.

The current national market maps annual assets onto a fixed market-agent and representative-weather topology. Mapping first uses identical asset identifiers, then selects agents of the same technology with matching region and allocates by previously mapped capacity. Zero capacity invokes template capacity and then equal allocation. Each market agent's final capacity is the sum of the annual assets assigned to it.

Zonal operation divides asset capacity by `zone_share`, retaining its weather curve and economic owner. `StagedBidAtCostPSM` sets each regional resource's `capacity_mw` to the original `resource.capacity_mw` multiplied by `share`; the shares sum to 1. It applies the same multiplication to storage `charge_power_mw`, `discharge_power_mw`, `energy_capacity_mwh` and `initial_soc_mwh`, preserving their national totals.

The separate aggregation interface `REPDERA5AggregatedWeather.build` combines precomputed project profiles within each owner–technology–zone group. For allocation records `rows`, `total` is their summed `capacity_mw` in MW. Each source curve becomes `values`, and the group curve `weighted` is

$$
\begin{aligned}
\mathtt{total}&=\sum_{\mathtt{row}\in\mathtt{rows}}\mathtt{row.capacity\_mw},\\
\mathtt{weighted}[t]&=\sum_{\mathtt{row}\in\mathtt{rows}}\mathtt{values}_{\mathtt{row}}[t]\times\frac{\mathtt{row.capacity\_mw}}{\mathtt{total}}.
\end{aligned}
$$

The aggregation accepts equal-length finite profiles within [0,1] and positive total capacity. Its caller supplies the project profiles. The current zonal execution pathway copies the representative profile to each allocated portion of an asset.

### Annual wind and solar capacity limits

The general investment rule derives capacity headroom from peak demand and the peak of each technology's CSV profile. In `canonical_psm_data`, `demand` is period energy in MWh, `period_hours` is 0.5 h, `availability` is the dimensionless technology profile and `capacity_by_technology` is operating MW. The `vre-expansion-cap` module multiplies the resulting `headroom` by `expansion.vre_cap_fraction`, recorded as `fraction`, to obtain annual limits `limits` in MW:

$$
\begin{aligned}
\mathtt{peak}&=\max_t\mathtt{availability}[t],\\
\mathtt{headroom}[\mathtt{technology}]&=\max\left(0,\frac{\max_t\mathtt{demand}[t]}{\mathtt{period\_hours}\times\max(\mathtt{peak},10^{-12})}\right.\\
&\qquad\left.-\mathtt{capacity\_by\_technology}[\mathtt{technology}]\right),\\
\mathtt{limits}[\mathtt{technology}]&=\mathtt{fraction}\times\mathtt{headroom}[\mathtt{technology}],\\
\mathtt{fraction}&=0.20.
\end{aligned}
$$

Technology-average investment profiles combine 2022 ERA5 data with fleet and project assumptions. The original solar `sa.csv` has 8,761 rows, with a final zero at `2023-01-01T00:00:00`; onshore `wa.csv` and offshore `we.csv` each have 8,760 rows. Public2 removes the final solar row and declares `interval_minutes=60`. Repeating each remaining value for two half-hours preserves the values formerly obtained by annual truncation. The investment reader retains the CSV row order and ERA5 interval-end timestamps; these profiles supply the investment calculation directly, while dispatch uses the weather-clock, loss and solar-plane transformations above.

For a peak demand of 1,000 MW, `peak = 0.8` and operating capacity of 300 MW, `headroom` is 950 MW and the annual limit is 190 MW. A zero profile peak uses the denominator floor 0.000000000001.

The experimental function `thesis96_vre_annual_expansion_cap` sets an annual addition limit from the number of negative net-demand periods. It takes three full-year inputs: `demand_mwh`, actual demand energy per period; `operational_vre_available_mwh`, the physical available energy of all operating wind and solar assets; and `generation_per_mw_mwh`, available energy per MW of the technology being expanded. The first two are in MWh/period and the third in MWh/MW/period. The technology curve is the available energy of its operating assets divided by their total MW; zero technology capacity gives a zero curve.

The function subtracts available renewable energy from demand as `net` and counts `already_negative`, the periods with `net < 0`. The default `negative_threshold = 200` half-hours represents 100 hours. Reaching this count gives an addition limit of zero; otherwise each eligible period contributes a capacity transition `net / profile`, where `profile` is the supplied `generation_per_mw_mwh`. The algorithm selects the required order statistic and multiplies it by `cap_fraction = 0.20`:

```text
demand = demand_mwh
available = operational_vre_available_mwh
profile = generation_per_mw_mwh
net = demand - available
already_negative = count_nonzero(net < 0)
if already_negative >= negative_threshold:
    return 0.0
transitions = net[(net >= 0) & (profile > 0)] / profile[(net >= 0) & (profile > 0)]
needed = negative_threshold - already_negative
if len(transitions) < needed:
    return 0.0
critical = partition(transitions, needed - 1)[needed - 1]
return cap_fraction * critical
```

`critical` is the `needed`-th smallest transition in MW. At a transition, the corresponding net demand equals zero; a larger addition makes it negative. A shortage of eligible transitions gives zero under this function's convention. The R029 public2 package published with VALUE 0.7.0-alpha.1 supplies demand, assets and weather for constructing these inputs. Chapter 6 specifies the experimental pathway's execution coverage.

### Data and implementation

`calendar_mean_solar_2020_2024.nc` and `calendar_mean_wind_2020_2024.nc` provide the R029 calendar climatology. `site_weather` reads representative-point series and applies the selected clock and conversion; `solar_irradiance` calculates array-plane radiation. `value_uk_vre_loss_factors_v1.json` supplies conversion parameters, and `value_uk_vre_cf_disclosure_v1.json` records the load-factor comparison. `doctoral_weather` provides the frozen conversion for the experimental pathway, while `doctoral_weather_mapping` manages locations and mixed weather weights.

`scheme_c_native_psm` aggregates capacity into national market agents, and `staged_psm` divides capacity among zones. Annual limits use the general peak rule in `canonical_psm_data` and `v2_module_definitions`. The experimental net-demand threshold function `thesis96_vre_annual_expansion_cap` is defined in `doctoral_policy`.


## 4. Operation and annual feedback

VALUE links half-hourly dispatch to annual investment. Projects due for commissioning enter the operating portfolio at the start of a year; their operation generates the income used for year-end additions and retirements. This chapter defines staged dispatch, storage pricing, investment and system accounts. Chapter 5 describes the default national PSM, and Chapter 6 describes the experimental national accounts.

### Model clock and annual state

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

### Ahead market and balancing

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

### Downward bids and settlement

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

### Storage inventory and bidding

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

### Storage expansion limits

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

### Annual investment

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

### Construction timing and planning success

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

### System costs and emissions

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


## 5. National dispatch algorithms

The default national power-system model, Native (`value-bid-at-cost-psm`), clears a single national node every half-hour. The methodology profile selects its market rule set: `native-corrected-v1` for the default corrected methodology and `native-doctoral-thesis-v1` for the doctoral reproduction profile. The experimental national pathway (`value-doctoral-national-psm`) has its own dispatch engine and input conventions. Its experimental annual accounts are described in Chapter 6.

### Inputs, agents and availability

Dispatch quantities are powers in MW, with `period_hours = 0.5`. The variables `forecast_demand`, `real_demand`, `capacity_limit`, `real_gen_energy` and `alter_limit` respectively describe forecast demand, actual demand, available output, realised output and the per-period ramp allowance. Asset and time subscripts index these quantities. The UTC model year has 17,520 periods. `canonical_psm_data.py` converts demand to period MWh by multiplying each MW value by `period_hours`, following Chapter 2.

Generator bids combine operating cost with a start-up adder determined by the previous accepted set. Gas and biomass use `gen_cost + fuel_cost + carbon_price + unit_time_cost`; nuclear, renewables and natural-flow hydro use `gen_cost + unit_time_cost`. The input-row costs are summed into the runtime agent’s `gen_cost`, in GBP/MWh; `carbon_price` is already an expenditure per MWh. For bid multiplier \(\mathrm{bidding\_factor}\), composite operating cost \(\mathrm{gen\_cost}_i\) and start-up adder \(\mathrm{startup\_cost}_i\),

$$
\begin{aligned}
\mathrm{price}_{i,t}={}&\mathrm{bidding\_factor}\cdot \mathrm{gen\_cost}_{i}\\
&+\mathrm{startup\_cost}_{i}\cdot
\mathbf1[i\notin\mathrm{accepted\_bids\_name}_{t-1}].
\end{aligned}
$$

The multiplier defaults to 1. Hydro and renewables have zero start-up adders; physical operating expenditure uses the composite `gen_cost` directly. In the supplied GB parameter rows, biomass has a cost of 0.2 + 80 + 4.8 = 85 £/MWh and an £83/MWh start-up adder; CCGT and OCGT have costs of £55.07/MWh and £74.92/MWh. Biomass revenue contains market receipts; CfD and ROC subsidies lie outside that revenue specification. At these costs, corrected GBP1 public2 and R029 public2 calculations produced approximately 0.01 TWh from 4,762 MW of biomass in 2025. Both revised packs are supplied with VALUE 0.7.0-alpha.1 ([data downloads](https://value.ac/en/data/)).

Native maps operating and newly commissioned assets to market agents first by name, then by technology and normalised region. Multiple matches use previously mapped capacity, constructor capacity, or equal shares in that order. `weights` and `total_weight` allocate each asset's `capacity_mw` into `generator_sources`; these capacities are MW. `_allocate_runtime_income` distributes `raw_income` into the asset account `allocated`, both in GBP, in proportion to the mapped capacities:

$$
\begin{aligned}
\mathrm{generator\_sources}_{j,a}
&=\mathrm{capacity\_mw}_a\cdot \mathrm{weights}_j/\mathrm{total\_weight},\\
\mathrm{capacity}_j&=\sum_a\mathrm{generator\_sources}_{j,a},\\
\mathrm{allocated}_a&=\sum_j\mathrm{raw\_income}_j\cdot
\frac{\mathrm{generator\_sources}_{j,a}}{\mathrm{capacity}_j}.
\end{aligned}
$$

Wind uses a 20 MW reference unit and multiplier \(\mathrm{capacity\_mw}_j/20\); solar uses a 1 MW reference unit and multiplier \(\mathrm{capacity\_mw}_j\). Storage power and energy are aggregated by technology. `scheme_c_native_psm.py` creates the year's agents and restores prior sales and sales-weighted holding time for bidding. Each year's physical inventory follows its new agent's initial state; the closing inventory of the preceding objects is recorded as discarded energy in `storage_year_boundary`.

Corrected availability uses the same period arrays as the canonical input adapter. `site_weather.site_cf_by_source` computes the Chapter 3 weather, loss and plane-of-array transformations, and `kernel_injection.KernelSiteInputs` supplies the resulting capacity factors \(\mathrm{cf}_{j,t}\) to the kernel:

$$
\mathrm{capacity\_limit}_{j,t}=\mathrm{capacity\_mw}_j\cdot \mathrm{cf}_{j,t}.
$$

In the doctoral reproduction profile, the kernel uses the frozen weather clock and the Chapter 3 wind and solar curves, with each hourly value serving two half-hours. Both profiles take interconnector prices and available transfer capacity from the corresponding model period.

Corrected nuclear availability preserves each station's PRIS reference output when converting to model capacity. `nuclear_load_factor` reads `pris_load_factor`, `pris_reference_mw` and `capacity_mw`. `generation_end_period` supplies `end`, the first period after the announced end month; a station with year-round availability retains its factor throughout the year. `asset_availability` produces the station array `values`, and `kernel_availability` combines it by capacity:

$$
\begin{aligned}
\mathrm{factor}_n&=\min\left(1,
\frac{\mathrm{pris\_load\_factor}_n\cdot \mathrm{pris\_reference\_mw}_n}
{\mathrm{capacity\_mw}_n}\right),\\
\mathrm{values}_{n,t}&=\mathrm{factor}_n\cdot \mathbf1[t<\mathrm{end}_n],\\
\mathrm{weighted}_{\mathrm{Nuclear},t}
&=\sum_n\mathrm{capacity\_mw}_n\cdot \mathrm{values}_{n,t},\\
\mathrm{kernel\_availability}_{\mathrm{Nuclear},t}
&=\frac{\mathrm{weighted}_{\mathrm{Nuclear},t}}{\sum_n\mathrm{capacity\_mw}_n}.
\end{aligned}
$$

The fixed 2019–2024 mean load factors are 0.668 for Heysham 1, 0.689 for Hartlepool, 0.752 for Heysham 2, 0.792 for Torness and 0.801 for Sizewell B. Station-policy inputs set the four AGR stations' availability to zero from period 4,320 of 2030, 1 April 00:00 UTC. Sizewell B retains full-year coverage until its declared retirement year. Fallback load factors are 0.801 for new PWR/EPR stations, 0.727 for an unspecified AGR and 0.723 for an undifferentiated national nuclear asset. GBP1 public2 applies the VALUE-UK nuclear station policy (`value_uk_nuclear_policy_v1.json`: five EDF stations and their declared generation ends), while its fleet input table contains one aggregate nuclear row; R029 retains a national aggregate and uses 0.723 under corrected Native dispatch. These parameters are supplied by `value_uk_firm_availability_v1.json` and `firm_availability.py`.

Corrected natural-flow hydro combines the DUKES 6.3 mean annual load factor with a monthly shape derived from quarterly Energy Trends data:

$$
\mathrm{values}_t=0.3487\cdot \mathrm{monthly\_shape}_{\mathrm{month\_of\_period}(t)},
$$
$$
\begin{aligned}
\mathrm{monthly\_shape}=[&1.3851,1.3851,1.3851,0.6582,0.6582,0.6582,\\
&0.6776,0.6776,0.6776,1.2791,1.2791,1.2791].
\end{aligned}
$$

The shape has an arithmetic monthly mean of 1 and a 365-day weighted mean of 0.99883, giving a model-year availability of 0.3483. Nuclear and hydro use these fixed profiles across model years. In the doctoral reproduction profile, their availability is 1.

Corrected Native dispatch starts each model year with nuclear in service, so nuclear belongs to \(\mathrm{accepted\_bids\_name}_{-1}\). An accepted restart after a period outside the accepted set incurs the start-up adder for that period. Gas and biomass begin outside the accepted set. In the doctoral reproduction profile, \(\mathrm{accepted\_bids\_name}_{-1}=\varnothing\): the GBP1 nuclear bid is initially £500/MWh, then falls to its operating cost after acceptance. The 500 MW-per-period ramp allowance in the GBP1 row retains output through subsequent low-demand periods, while unaccepted nuclear memory decays by 0.99 per period. Annual nuclear output therefore depends on when the unit first enters the accepted set.

### Native storage batches and net positions

Native records each charging period's stored-side MWh in `stored_energy`. `Battery.charge` limits input by `power_capacity_mw`, `energy_capacity_mwh`, charging efficiency `n_1` and remaining power after the current period's earlier charging. For each battery, the implementation calculates

$$
\begin{aligned}
\mathrm{stored\_total}&=\sum_k\mathrm{stored\_energy}_{k},\\
\mathrm{remaining\_input\_power}
&=\max\left(\frac{\mathrm{energy\_capacity\_mwh}-\mathrm{stored\_total}}
{\mathrm{n\_1}\cdot \mathrm{period\_hours}},0\right),\\
\mathrm{already\_charged\_power}
&=\frac{\mathrm{stored\_energy}_{t}}{\mathrm{n\_1}\cdot \mathrm{period\_hours}},\\
\mathrm{period\_power\_headroom}
&=\max(\mathrm{power\_capacity\_mw}-\mathrm{already\_charged\_power},0),\\
\mathrm{input\_power}&=\min(\max(\mathrm{available\_input\_power\_mw},0),\\
&\qquad\mathrm{remaining\_input\_power},\mathrm{period\_power\_headroom}),\\
\mathrm{stored\_energy}_t&\leftarrow\mathrm{stored\_energy}_t
+\mathrm{input\_power}\cdot \mathrm{n\_1}\cdot \mathrm{period\_hours}.
\end{aligned}
$$

`Battery.discharge` withdraws `output_power * period_hours / n_2` MWh from the selected batch, where `n_2` is discharging efficiency. All batches and stages share rated power. Ahead offers use existing batches; upward balancing uses batches aged at least two periods. The period book's `discharged_mw` and `charged_mw`, and the sum of `stored_energy`, satisfy

$$
\begin{aligned}
0&\le\mathrm{discharged\_mw}\le\mathrm{power\_capacity\_mw},\\
0&\le\mathrm{charged\_mw}\le\mathrm{power\_capacity\_mw},\\
\mathrm{discharged\_mw}\cdot \mathrm{charged\_mw}&=0,\\
0&\le\mathrm{stored\_total}\le\mathrm{energy\_capacity\_mwh}.
\end{aligned}
$$

Surplus absorption first buys back the store's discharge from the same period and returns the withdrawn energy to its original batches. Further surplus can charge the store after its remaining discharge reaches zero. A store that has charged offers zero discharge in later stages. Both profiles process forecast surplus before other available surplus and record sales at the closing net position. Ahead storage remuneration remains payable on bought-back output.

Self-discharge multiplies inventory by \(1-\mathrm{decay\_rate}\) each period. The values of \(\mathrm{decay\_rate}\) are 0.000021 for batteries and other default types, 0.000001 for pumped hydro and 0.000005 for hydrogen storage. Batches below 0.001 MWh are removed and included in inventory reconciliation.

The default dynamic storage-cost module uses cycle depreciation in corrected bids. Batteries bid \(\mathrm{bidding\_factor}\cdot\mathrm{cycle\_depreciation\_gbp\_per\_mwh}_b\); pumped hydro and hydrogen storage bid zero. Oldest batches are offered first:

$$
\begin{aligned}
\mathrm{price}=\mathrm{bidding\_factor}\times
\begin{cases}
\mathrm{cycle\_depreciation\_gbp\_per\_mwh},&\mathrm{battery},\\
0,&\mathrm{pumped\ hydro\ or\ hydrogen}.
\end{cases}
\end{aligned}
$$

The module calculates cycle depreciation from the annual cost-recovery inputs in Chapter 4. Legacy tariffs, user formulas and external storage-cost modules supply their own bid functions. In the doctoral reproduction profile, the selected storage module retains its age-dependent bid; the legacy form is

$$
\begin{aligned}
\mathrm{price}=\mathrm{bidding\_factor}\cdot\bigl(&\mathrm{storage\_fee\_gbp\_per\_mwh}\\
&+(t-k)\cdot \mathrm{holding\_fee\_gbp\_per\_mwh\_period}\bigr).
\end{aligned}
$$

Positive holding fees make newer batches cheaper, and equal prices preserve batch order. Annual observations retain delivered MWh and MWh multiplied by age for the following year's pricing inputs.

### Native forecast clearing and balancing

Corrected Native dispatch orders generator, import and storage-batch offers by a stable key. Within the same 0.01 £/MWh band, generation and imports precede storage; unrounded price and input order resolve further ties:

$$
\mathrm{merit\_key}(\mathrm{offer})=
(\operatorname{round}(\mathrm{price},2),
\mathbf1[\mathrm{is\_storage\_offer}(\mathrm{offer})],\ \mathrm{price}).
$$

An ordinary generator serves residual forecast demand up to

$$
\min(\mathrm{real\_gen\_energy}_{i,t-1}+\mathrm{alter\_limit}_i,
\mathrm{capacity\_limit}_{i,t}).
$$

Hydro and biomass also obey their remaining cumulative budget \(\mathrm{energy\_limit}_i-\mathrm{have\_gen\_energy}_i\), expressed in MW-periods and converted to MWh by \(\mathrm{period\_hours}\). Nuclear acceptance can exceed residual demand \(\mathrm{forecast\_demand}\): when its upper limit is larger than \(\mathrm{forecast\_demand}\), it supplies \(\max(\mathrm{real\_gen\_energy}_{i,t-1}-\mathrm{alter\_limit}_i,\mathrm{forecast\_demand})\). This excess becomes already-generated, inflexible surplus. Renewable availability above accepted demand is retained as available surplus.

Corrected interconnectors offer positive available import capacity into the ahead market at the external price multiplied by \(\mathrm{bidding\_factor}\). Their offers carry capacity limits with zero ramp and start-up adders. Balancing offers only \(\max(\mathrm{transfer\_constraint}_{k,t}-\mathrm{accepted\_mw}_{k,t},0)\). Negative transfer capacity represents export capability, accepted at positive external prices. In the doctoral reproduction profile, imports enter only the upward-balancing branch and serve the remaining actual-minus-forecast requirement.

Corrected surplus accounting rebuilds renewable surplus from availability minus accepted output after the ahead stage. Already-generated nuclear surplus is used first. When renewable surplus supplies storage, exports or flexible demand, it enters gross renewable generation. Recorded `vre_accepted` is therefore gross VRE output, `curtailed` is available VRE minus gross output, and `excess` is non-VRE spill. Nuclear surplus already included in ahead supply and settlement serves balancing demand once; renewable surplus entering supply during balancing receives balancing settlement.

The real-time branch compares actual and forecast demand. A lower actual value invokes surplus absorption and downward dispatch; a higher or equal value invokes upward balancing. This comparison also applies when ahead supply falls short of the forecast. In that case, the lower-demand branch still requests a reduction of \(\mathrm{forecast\_demand}_t-\mathrm{real\_demand}_t\); any resulting unmet demand is recorded by the stress-event account below.

```text
for each half-hour:
    Read availability, demand and boundary inputs
    Update budgets and self-discharge
    Form generator, import and eligible storage-batch offers
    ahead_market_bidding(...): clear forecast demand in merit order
    rebuild_surplus(...): reconstruct renewable and already-generated surplus
    if actual demand < forecast demand:
        Buy back storage discharge using forecast surplus, then existing surplus
        Charge storage after its net discharge reaches zero
        Accept positive-price exports in descending external-price order
        Supply flexible electrolysis
        economic_downward_stack(...): reduce remaining output
    else:
        Use existing surplus for demand and offer the remainder to storage
        Merge remaining generation, eligible batches and residual imports
        balancing_market_bidding(...): serve upward demand; record blackout
    close_battery_period(...); uniform_income(...); physical_cost_terms(...)
```

The common electrolyser is flexible demand, with source defaults of 10 MW, a 0.125 MW-per-period ramp and efficiency 0.65; data-pack parameters may replace these values. The corrected pathway routes available VRE through clearing and subsequent surplus allocation. In the doctoral reproduction profile, each VRE agent first diverts \(\min(\mathrm{real\_energy}+\mathrm{rampup\_rate},\mathrm{electrolyzer\_limit})\) to direct electrolysis. The diversion and any amount exceeding available VRE are recorded separately. This profile also uses stable unrounded-price sorting and its surplus-node balance boundary.

### Economic downward order

Corrected downward dispatch compares avoided operating expenditure after storage, exports and flexible demand absorb surplus. `ramp_floor_mw` returns the larger of zero and previous `real_gen_energy` less `alter_limit`; VRE and imports have zero floor. `avoided_cost` uses the asset's composite `gen_cost`, subtracting `NUCLEAR_DEC_PREMIUM_GBP_PER_MWH = 100` for nuclear; imports use `external_price`. Ordinary rows follow descending avoided cost rounded to two decimal places.

Gas and biomass split their accepted ahead output \(\mathrm{power}_k\) into a running range and a shutdown segment. Here \(\mathrm{power}_k\) represents the aggregate's online capacity for this ordering rule, and \(\mathrm{min\_stable\_fraction}_k\) is the minimum stable fraction:

$$
\begin{aligned}
\mathrm{stable}&=\mathrm{min\_stable\_fraction}\cdot \mathrm{power},\\
\mathrm{running}&=\max(\mathrm{power}-\max(\mathrm{floor},\mathrm{stable}),0),\\
\mathrm{shutdown}&=\max(\mathrm{power}-\mathrm{floor},0)-\mathrm{running}.
\end{aligned}
$$

The running range avoids \(\mathrm{cost}_k\) £/MWh. The shutdown segment compares avoided expenditure over expected downtime \(\mathrm{horizon\_h}\) with restart expenditure \(\mathrm{restart\_cost}(\mathrm{horizon\_h})\), measured per MW of capacity per start:

$$
\begin{aligned}
\mathrm{net\_saving}(\mathrm{cost},\mathrm{horizon\_h})
&=\mathrm{cost}-\frac{\mathrm{restart\_cost}(\mathrm{horizon\_h})}
{\mathrm{min\_stable\_fraction}\cdot \mathrm{horizon\_h}},\\
\mathrm{horizon\_h}&=(1+\mathrm{run\_after}_t)\cdot \mathrm{period\_hours}.
\end{aligned}
$$

`SurplusOutlook.run_after` counts consecutive periods after the current one with forecast demand no greater than forecast wind, solar and nuclear availability. The current downward period adds one period. Without injected availability arrays, `horizon_h = 0.5` h. Removing one MW at the stable fraction shuts `1 / min_stable_fraction` MW of capacity; the restart comparison divides restart cost by that fraction and by the expected downtime.

A shutdown segment with \(\mathrm{horizon\_h}\ge \mathrm{min\_down\_time\_h}_k\) enters the same descending net-saving order as other resources. Positive \(\mathrm{saving}_k\) precedes zero-cost VRE; zero or negative \(\mathrm{saving}_k\) follows VRE, including ties after rounding. A segment with \(\mathrm{horizon\_h}<\mathrm{min\_down\_time\_h}_k\) follows all other reducible resources. These quantities define a continuous dispatch-ordering rule; the physical cost account uses the start-up bid adder \(\mathrm{startup\_cost}_i\) defined above.

|Technology|Restart cost: hot / warm / cold, 2025 GBP/MW|Minimum stable fraction|Minimum downtime, h|
|---|---:|---:|---:|
|CCGT|113.7 / 134.4 / 155.0|0.50|6|
|OCGT|175.7 / 175.7 / 175.7|0.50|0.5|
|Biomass|129.2 / 129.2 / 129.2|0.35|6|

CCGT uses the hot value for \(\mathrm{horizon\_h}<12\) h, warm for \(12\le \mathrm{horizon\_h}\le48\) h, and cold for \(\mathrm{horizon\_h}>48\) h. `value_thermal_restart_v1.json` combines cycling-wear estimates from [Kumar et al. (2012)](https://docs.nrel.gov/docs/fy12osti/55433.pdf) with GB start-up fuel and carbon estimates from [Staffell and Green (2016)](https://doi.org/10.1109/TPWRS.2015.2407613). Its minimum-load and downtime assumptions draw on Elexon declarations and the technical sources recorded with the table. The table converts the selected 2024 GBP values to 2025 GBP using [ONS CPI D7BT](https://www.ons.gov.uk/economy/inflationandpriceindices/timeseries/d7bt/mm23), \(138.4/133.9\), and rounds restart costs to one decimal place; the recorded conversion factor is 1.0336.

`RestartParameters.break_even_hours` divides restart cost by `min_stable_fraction` times avoided operating cost. At the supplied GB costs, break-even times are 4.13 h for hot-start CCGT, 4.69 h for OCGT and 4.34 h for biomass. Thus eligible CCGT and biomass shutdowns at 6 h have positive net savings; OCGT first has positive savings at 5 h on the half-hour grid. The CCGT six-hour cost threshold is 113.7 / (0.5 × 6) = 37.9 £/MWh.

Equal rounded savings use class ranks thermal 0, imports 0.5, hydro and biomass 1, VRE 2, shutdown segments 2.5 and nuclear 3, followed by name and input order. Each accepted reduction consumes the remaining requirement once:

$$
\begin{aligned}
\mathrm{take}&=\min(\mathrm{limit},\mathrm{item}[2],\mathrm{remaining}),\\
\mathrm{item}[2]&\leftarrow\mathrm{item}[2]-\mathrm{take},\\
\mathrm{remaining}&\leftarrow\mathrm{remaining}-\mathrm{take}.
\end{aligned}
$$

`limit` is the segment's reducible MW, `item[2]` is its remaining accepted output, and `remaining` is the outstanding downward requirement. Hydro and biomass reductions return energy to cumulative budgets. Output held by the ramp floor becomes in-dispatch spill. `native_corrected.economic_downward_stack` applies these reductions.

In the doctoral reproduction profile, downward rows follow ascending `curtail_cost`, placing zero-cost wind ahead of gas. Hydro reductions return to its budget. Both profiles stop reductions when the remaining requirement reaches zero.

### Settlement, displayed price and physical cost

Corrected Native dispatch pays every accepted supply category the same marginal price within each stage. Ahead settlement takes the highest accepted offer including imports and storage. `uniform_income` multiplies accepted `power_mw` by period length and the stage's `price_gbp_per_mwh`; the balancing price also includes accepted import prices:

$$
\mathrm{income}_{i,t}=\mathrm{power\_mw}_{i,t}\cdot
\mathrm{period\_hours}\cdot \mathrm{price\_gbp\_per\_mwh}_t,
$$
$$
\mathrm{price\_gbp\_per\_mwh}^{\mathrm{balancing}}_t
=\max(\mathrm{max\_gen\_price}_t,\mathrm{max\_bat\_price}_t,
\max_{k\in\mathrm{imports}}\mathrm{price}_{k,t}).
$$

Storage charges are settled within the current period. In the doctoral reproduction profile, generation and storage each use their own highest accepted bid; an empty accepted generator set yields an empty income mapping, including periods supplied solely by storage. Its final balancing storage fee also enters subsequent downward-period expenditure.

The displayed Native price is labelled “Average period cost (£/MWh demand)”. If \(\mathrm{total\_gen\_cost}_t\) is the accumulator of accepted-offer, storage, downward and upward charges, its value and associated period expenditure are

$$
\begin{aligned}
\mathrm{avg\_price}_t&=\begin{cases}
\mathrm{total\_gen\_cost}_t/\mathrm{real\_demand}_t,&\mathrm{real\_demand}_t>0,\\
0,&\mathrm{real\_demand}_t=0,
\end{cases}\\
\mathrm{retained\_period\_cost\_gbp}_t
&=\mathrm{period\_hours}\cdot \mathrm{total\_gen\_cost}_t.
\end{aligned}
$$

This statistic describes expenditure per MWh of actual demand. Generator and storage income are calculated from the settlement accounts above. Corrected \(\mathrm{total\_gen\_cost}_t\) includes the current period's storage fee only. Final boundary supply enters the annual generation statistic, while Native reports storage discharge separately.

Physical operating expenditure values realised generation at composite `gen_cost`, imports at `external_price`, and qualifying starts at `startup_cost` times generated MWh. `physical_cost_terms` returns `generation_variable_gbp`, `import_variable_gbp` and `startup_adder_gbp`; the annual account adds recorded-blackout cost and current storage cycle depreciation. The year index is \(y\); `operating` and `cycle_wear` are the implementation's annual totals in GBP:

$$
\begin{aligned}
\mathrm{operating}_y={}&
\sum_t(\mathrm{generation\_variable\_gbp}_t
+\mathrm{import\_variable\_gbp}_t\\
&\qquad+\mathrm{startup\_adder\_gbp}_t)\\
&+\mathrm{voll\_gbp\_per\_mwh}\cdot\sum_t\mathrm{blackout\_mwh}_t
+\mathrm{cycle\_wear}_y.
\end{aligned}
$$

Here \(\mathrm{import\_mwh}_{k,t}\) is imported MWh, \(\mathrm{blackout\_mwh}_t\) is recorded blackout MWh, and \(\mathrm{cycle\_wear}_y\) is the sum of each storage asset's `current_cycle_depreciation_gbp`. Market settlement transfers are reported separately from these resource components. The cost account uses \(\mathrm{voll\_gbp\_per\_mwh}=17{,}000\) £/MWh, equivalent to £8,500 per MW-half-hour. Corrected Native reads `market.voll_gbp_per_mwh`, with an allowed range of 0–1,000,000; the doctoral reproduction rule set uses the constant 17,000. In Native this parameter values recorded blackout in the cost account. Stress shortfalls are reported separately and reduce the served-energy denominator used in Chapter 4.

### Energy balance and result qualification

The corrected Native balance includes gross accepted supply, charging, exports, flexible demand and non-VRE spill. All quantities in this section are MWh. With accepted supply \(\mathrm{accepted\_supply\_mwh}_t\), recorded blackout \(\mathrm{blackout\_mwh}_t\), actual demand \(\mathrm{real\_demand\_mwh}_t\), storage charge \(\mathrm{storage\_charge\_mwh}_t\), exports \(\mathrm{export\_mwh}_t\), flexible demand \(\mathrm{flexible\_demand\_mwh}_t\) and non-VRE spill \(\mathrm{non\_vre\_spill\_mwh}_t\), the `native_corrected_full_node_v1` residual is

$$
\begin{aligned}
\mathrm{residual\_mwh}_t={}&\mathrm{accepted\_supply\_mwh}_t
+\mathrm{blackout\_mwh}_t-\mathrm{real\_demand\_mwh}_t\\
&-\mathrm{storage\_charge\_mwh}_t-\mathrm{export\_mwh}_t\\
&-\mathrm{flexible\_demand\_mwh}_t-\mathrm{non\_vre\_spill\_mwh}_t.
\end{aligned}
$$

The doctoral reproduction profile uses `default_psm_surplus_node_v1`. Its out-of-dispatch renewable surplus supplied to storage, exports or electrolysis is \(\mathrm{u\_out\_mwh}_t\), and its already-accepted surplus finally spilled is \(\mathrm{w\_in\_mwh}_t\):

$$
\begin{aligned}
\mathrm{residual\_mwh}_t={}&\mathrm{accepted\_supply\_mwh}_t
+\mathrm{blackout\_mwh}_t\\
&+\mathrm{u\_out\_mwh}_t-\mathrm{w\_in\_mwh}_t\\
&-\mathrm{real\_demand\_mwh}_t-\mathrm{storage\_charge\_mwh}_t\\
&-\mathrm{export\_mwh}_t-\mathrm{flexible\_demand\_mwh}_t.
\end{aligned}
$$

The compatibility adjustment absorbs numerical noise within the declared tolerance. Native uses

$$
\begin{aligned}
\mathrm{tolerance\_mwh}_t=\max\bigl(&10^{-6},\\
&10^{-9}\max(\mathrm{real\_demand\_mwh}_t,\mathrm{accepted\_supply\_mwh}_t)\bigr),\\
\mathrm{compatibility\_adjustment\_mwh}_t
&=\begin{cases}
-\mathrm{residual\_mwh}_t,&10^{-9}<|\mathrm{residual\_mwh}_t|\le\mathrm{tolerance\_mwh}_t,\\
0,&\mathrm{otherwise}.
\end{cases}
\end{aligned}
$$

The corresponding LP tolerances are \(10^{-5}\) and \(10^{-7}\). Residuals outside this tolerance remain in the physical balance. `native_balance_audit.py`, `energy_balance_contract.py` and `energy_balance_oracle.py` connect the ledger's supply boundary to these checks.

The energy account books the full unmet-demand quantity before distinguishing recorded blackout from additional stress shortfall:

$$
\begin{aligned}
\mathrm{unserved\_mwh}_t&=\max(0,-(\mathrm{residual\_mwh}_t-\mathrm{blackout\_mwh}_t)),\\
\mathrm{closing\_residual\_mwh}_t&=\mathrm{residual\_mwh}_t
-\mathrm{blackout\_mwh}_t+\mathrm{unserved\_mwh}_t.
\end{aligned}
$$

A period whose sole imbalance is unmet demand closes with \(\mathrm{closing\_residual\_mwh}_t=0\) and is recorded as a stress period. Consecutive stress periods within a year form one event. Annual reporting gives event count, period count and shortfall MWh. The additional stress quantity used with recorded blackout follows the account's separation, so Chapter 4 subtracts each unmet-demand component once from demand.

Annual qualification checks three groups: run invariants; energy balance and ledger consistency, including surplus conservation and \(\sum_t|\mathrm{compatibility\_adjustment\_mwh}_t|/\sum_t\mathrm{real\_demand\_mwh}_t\le10^{-6}\); and storage throughput, inventory bounds and batch reconciliation. Corrected annual economic results require all three groups to pass. Doctoral reproduction results require all raw invariants to pass for display on result pages. Stress events are reported as reliability outcomes. The annual state record also retains the Native inventory reset and the profile's surplus-boundary definition.

### Experimental pathway inputs

The experimental national pathway uses frozen v1 weather, unit availability for nuclear and natural-flow hydro, and raw boundary prices under either methodology profile. The weather transformation uses its original radiation convention and unity loss factors. `doctoral_market_factory.py` builds agents from complete rows of costs, efficiencies, ramps, opening output, downward prices and natural budgets. A new asset may reuse a row through `doctoral_parameter_source_id`, retaining the row's ramp and budget values. Direct renewable electrolysis and the common electrolyser have zero capacity in this pathway.

The module supports fixed-year dispatch and experimental annual cash accounts. It records `scientific_release_eligible=false` and `doctoral_annual_cem_ready=false`. Integration with `agent-investment` requires the `value.agent-cashflow/v1` account contract for eligible thermal decisions; this experimental PSM currently publishes `doctoral_cashflow_inputs`, so that combination stops at the investment-account requirement. The following equations describe the implemented period engine.

### Experimental batch inventory

The experimental kernel stores batches in `stored_energy` as raw power-equivalent quantities: multiplying a batch by `period_hours = 0.5` gives internal MWh. `pool_limit` bounds the sum of these raw quantities, `per_pool_limit` is delivered MW, and `n_1`, `n_2` are charge and discharge efficiencies. Self-discharge uses the rates above. A batch charged at `charge_period` and offered at `period` has price

$$
\begin{aligned}
\mathrm{price}=\mathrm{bidding\_factor}\cdot\bigl(&\mathrm{storage\_fee}\\
&+(\mathrm{period}-\mathrm{charge\_period})\cdot \mathrm{per\_storage\_fee}\bigr).
\end{aligned}
$$

The prototype values are supplied by `config.py`, with complete parameter rows bound for each run by `doctoral_market_factory.py`:

|Prototype technology|`n_1`|`n_2`|`storage_fee`|`per_storage_fee`|
|---|---:|---:|---:|---:|
|Pumped hydro|0.87|0.87|0|1.1008|
|1C battery|0.81|0.81|0|1.0558|
|0.25C battery|0.81|0.81|0|0.7369|
|0.5C battery|0.98|0.98|135.26|0.1736|
|Hydrogen storage|0.57|0.57|884.4|0.0055|

All batches and both clearing stages share the battery's delivered-power limit. Ahead clearing reads the already delivered MW as `delivered` from `gen_list`, then limits the offered raw batch quantity `item[3]` by the remaining power divided by `n_2`. A smaller remaining `forecast_demand` withdraws that demand divided by `n_2`; balancing applies the same rule to `energy_provided`. Ahead offers use all existing batches, while balancing uses batches aged at least two periods. Raw balances below 0.001 are removed, corresponding to at most 0.0005 MWh per batch.

Charging orders batteries by `storage_fee`, `per_storage_fee` and the product `n_1 * n_2`. For each battery, `store_service_three` first absorbs forecast surplus `need_curtailed_energy`, then other `excess_energy`. Its first pass uses

$$
\begin{aligned}
\mathrm{limit}&=\max(0,\mathrm{per\_pool\_limit}-\mathrm{stored\_energy}_t/\mathrm{n\_1}),\\
\mathrm{energy}&=\min(\mathrm{limit},\mathrm{need\_curtailed\_energy},
\mathrm{pool\_limit}-\sum_k\mathrm{stored\_energy}_k),\\
\mathrm{stored\_energy}_t&\leftarrow\mathrm{stored\_energy}_t+\mathrm{n\_1}\cdot \mathrm{energy}.
\end{aligned}
$$

The second pass substitutes `excess_energy` for the forecast surplus. Raw inventory room directly limits grid-side charging power. For the 0.5C prototype, four periods of holding give a price of 135.26 + 4 × 0.1736 = 135.9544 GBP/MWh. A 10 MWh batch has raw quantity 20; delivery of 10 MW over 0.5 h withdraws 5 / 0.98 = 5.1020408 MWh and earns £679.772 when settled at that price. Raw expenditure diagnostics use raw withdrawal times bid price; cash settlement uses delivered MWh.

### Experimental planning and realisation

`DoctoralPeriodEngine` forms the ahead plan on a copy of opening physical state. It updates natural budgets and self-discharge, then calls `ahead_market_bidding`. Generator and storage offers follow stable price order. Conventional generation obeys ramp limits; hydro and biomass also obey remaining budgets. Nuclear retains output down to previous `real_gen_energy` less `alter_limit` when that exceeds remaining forecast demand. Nuclear memory decays by 0.99 in a period without acceptance. The engine records unaccepted renewable availability separately from already-generated nuclear surplus.

Realisation compares actual demand with scheduled supply after removing the ahead stage's already-generated non-renewable surplus. In `realise_period`, `actual` and `scheduled_load` are MW:

$$
\mathrm{scheduled\_load}
=\sum_{(\mathrm{generator},\mathrm{amount})\in\mathrm{ahead}[10]}
\mathrm{amount}-\mathrm{already\_generated\_surplus}.
$$

When `actual < scheduled_load`, the difference enters `curtailment_market_bidding`. It charges storage, processes existing surplus, accepts positive-price exports in descending price order, then reduces generation in configured downward-price order. `_curtail_thermal_bid` limits each reduction using the accepted MW `bid[2]`, the earlier `previous_energy` and `generator.alter_limit`:

```text
if bid[2] - previous_energy == generator.alter_limit:
    max_curtail_energy = min(2 * generator.alter_limit, bid[2])
elif previous_energy >= generator.alter_limit:
    max_curtail_energy = bid[2] - (previous_energy - generator.alter_limit)
else:
    max_curtail_energy = bid[2]
curtailed = min(need_curtailed_energy,
                max(0, min(bid[2], max_curtail_energy)))
bid[2] -= curtailed
```

Hydro and biomass return the reduction to their used budgets, and previous output is read by generator object identity. Remaining non-renewable output held by ramp constraints becomes `non_vre_spill`.

When `actual >= scheduled_load`, `balancing_market_bidding` first uses existing surplus and offers the remainder to storage. It then combines the last ahead-accepted generator and subsequent generators with eligible storage batches and imports. With an empty ahead generator set, this search starts at the first offer. The marginal generator's `valid_energy` is its ramp-limited available output less its ahead-accepted MW; later generators offer their full ramp-limited availability. Hydro and biomass retain budget limits. Imports use `external_price`; this branch accepts positive-price exports in ascending price order. Remaining demand becomes blackout.

The engine checks final physical balance before advancing state. `total`, `actual`, `charge`, `exported`, `non_vre_spill` and `blackout` are MW in this calculation; `residual` is MWh:

$$
\begin{aligned}
\mathrm{missing}&=\mathrm{actual}+\mathrm{charge}+\mathrm{exported}
+\mathrm{non\_vre\_spill}-\mathrm{total},\\
\mathrm{blackout}&=\max(0,\mathrm{missing}),\\
\mathrm{residual}&=0.5(\mathrm{total}+\mathrm{blackout}-\mathrm{actual}
-\mathrm{charge}-\mathrm{exported}-\mathrm{non\_vre\_spill}).
\end{aligned}
$$

State advancement requires an absolute `residual` at most \(10^{-7}\) MWh, nonnegative generation and renewable output within availability. The storage calculation separately reconciles `opening`, grid-side `charged`, grid-side `delivered`, self-discharge `decay`, conversion loss `conversion` and small-batch removal `discard`, all in MWh:

$$
\begin{aligned}
&\mathrm{conversion}=\mathrm{charged}\cdot(1-\mathrm{n\_1})
+\mathrm{delivered}\cdot(1/\mathrm{n\_2}-1),\\
&\mathrm{next\_state.storage\_energy\_mwh}(\mathrm{battery.name})\\
&\quad=\mathrm{opening}+\mathrm{charged}-\mathrm{delivered}\\
&\qquad-\mathrm{decay}-\mathrm{conversion}-\mathrm{discard}.
\end{aligned}
$$

`commit_period` passes closing storage batches, generator memory and the accepted-generator set to the next period. Generation routed to storage and exports is allocated back to its renewable source.

### Experimental settlement and annual expenditure

The experimental engine settles generators and storage at their separate highest accepted bids in ahead and upward markets. `acm_income` books ahead cash before downward realisation changes dispatch, multiplying accepted MW by `period_hours` and either `max_gen_price` or `max_bat_price`. Storage-only supply receives its storage settlement. `acm_income_balance` applies the same category prices to upward supply.

Downward cash retains the sign of the configured price. For each accepted action, `quantity` is MW and `price` is GBP/MWh. The engine computes `raw_gbp = quantity * 0.5 * price`, adding it to `down_cash` for thermal, biomass and hydro assets; nuclear, wind, solar and storage amounts enter `legacy_down` as diagnostic values. Each asset's `income_balance` is its `income_up` plus `down_cash`, while `income_ahead` remains separate.

Variable operating expenditure values final generation at `gen_cost` and imports at `external_price`; storage variable operating expenditure is zero. Fuel, carbon and other costs divide this total into components. Export receipts and import procurement retain their separate cash directions.

Annual system expenditure adds variable expenditure, explicit fixed costs, annualised capital and shortage valuation. `DoctoralNationalPSM` uses the variables `variable`, `fixed` and `capital` from asset records and period totals:

$$
\mathrm{total\_system\_cost\_gbp}
=\mathrm{variable}+\mathrm{fixed}+\mathrm{capital}
+\mathrm{blackout\_mwh}\cdot \mathrm{voll\_gbp\_per\_mwh}.
$$

Fixed and capital expenditure enter complete 17,520-period annual summaries; both are zero in shorter diagnostic runs. Annual generation includes storage discharge and boundary supply. The displayed “Ahead settlement price” uses the ahead generator price. The reliability coefficient reads `market.voll_gbp_per_mwh`, default £17,000/MWh. Chapter 6 describes the annual account and investment helpers that can use these complete experimental cash records.


## 6. Experimental annual accounts and investment

The experimental national pathway supplies period cash and physical states to separate annual-account and investment functions. The `doctoral.investment_basis=thesis_final9.6` selection uses `build_thesis96_asset_accounts` and `evaluate_thesis96_investment_accounts` with the policy and planning rules below. Chapter 4 defines the default investment rule. The experimental PSM supports fixed-year dispatch, and its results retain `scientific_release_eligible=false` and `doctoral_annual_cem_ready=false`.

R029 names the national study and its input family. Public1 contains 8,761 hourly solar values and lacks the required interval declaration; its eligibility excludes the corrected reader and doctoral reproduction whitelist. The public2 revision removes the value at 2023-01-01 00:00 UTC and declares all three VRE curves hourly. Public2 is supplied with the VALUE 0.7.0-alpha.1 release through the [website data page](https://value.ac/en/data/) and has been used with corrected Native dispatch. The experimental calculations here take explicitly supplied annual accounts, traces and parameters.

### Annual accounts and decision groups

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

### Expansion limits and investment quantities

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

### Policy transfers and expenditure

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

### REPD projects and exogenous schedules

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

### Physical state between experimental years

The experimental period engine carries batch ages and generator memory across a completed year. Its absolute period index continues through the year boundary, retaining each surviving batch's charging index. Existing generator memory, including cumulative natural-resource budgets, is transferred; newly introduced generators use their supplied initial states. New storage begins with empty batches.

`DoctoralPeriodEngine.advance_year` requires consecutive complete model years and storage capacities sufficient for retained inventory. Retirement of a nonempty store or a reduction below its inventory requires an explicit disposition rule supplied through a further integration step. The implemented transition therefore preserves the inventory of continuing stores without an automatic retirement write-off. Annual account preparation, physical-state continuation and investment proposals remain separate interfaces with the input requirements described above.


## 7. Transmission and network constraints

### Spatial representation of zonal redispatch

Zonal redispatch adds spatial constraints to a national ahead schedule. Each half-hour accepts upward and downward bids so that final injections satisfy zonal demand, corridor capacities and geographical boundary limits. Flow follows a lossless transport formulation with conservation and capacity constraints. The 23-zone configuration and 11-zone experiment use this representation; DC dispatch and AC feasibility use the separate methods below. These network modules operate under the corrected methodology with an eligible dataset.

Demand follows the spatial rule selected for the case. `align_zonal_demand` preserves the network pack's zonal shares for the 23-zone study and scales them to national scenario demand. Its arrays `aligned`, `output_real`, `network_demand_mwh_by_zone` and `network_national_mwh` are MWh; zone and period indices are \(z,t\):

$$
\begin{aligned}
\mathrm{scale}_t&=\frac{\mathrm{output\_real}_t}{\mathrm{network\_national\_mwh}_t},\\
\mathrm{aligned}_{z,t}&=\mathrm{network\_demand\_mwh\_by\_zone}_{z,t}\cdot \mathrm{scale}_t.
\end{aligned}
$$

The last zone receives national demand less the sum allocated to the preceding zones, preserving the total. The 11-zone experiment instead selects absolute network demand and retains the forecast-to-actual ratio from the base series:

$$
\begin{aligned}
\mathrm{output\_real}_t&=\mathrm{network\_national\_mwh}_t,\\
\mathrm{output\_forecast}_t&=\mathrm{output\_real}_t\cdot
\frac{\mathrm{research\_forecast\_mwh}_t}{\mathrm{research\_real\_mwh}_t}.
\end{aligned}
$$

A zero denominator with positive required demand is an input error. The resulting `demand_mwh_by_zone` accompanies asset locations, realised availability and interconnector import/export envelopes into `build_single_period_problem`.

### Adjustment objectives and operating constraints

Redispatch solves four linear objectives in sequence: bid expenditure including shortage cost, adjustment volume, weighted physical throughput and stable variable order. `SinglePeriodProblem` stores their coefficient arrays as `primary_objective`, `secondary_objective`, `physical_tie_objective` and `stable_tie_objective`. Each objective is its array's dot product with `values`, the period decision vector returned by `solve_lexicographic`.

The decision vector uses the implementation's variable labels. `bid:<bid_id>` is accepted nonnegative bid MWh; `flow:<corridor_id>` is signed corridor MWh; `load-shedding:<zone_id>` is unmet demand; `storage-charge:<asset_id>` and `storage-discharge:<asset_id>` are grid-side storage MWh; `absolute-flow:<corridor_id>` bounds the absolute corridor flow. In the equations, array subscripts carry these existing identifiers.

The primary objective uses the sign of each bid direction. An upward bid contributes its `price_gbp_per_mwh` times accepted MWh; a downward bid contributes the negative of that payment. Shortage is valued at `voll_gbp_per_mwh`, default 17,000 GBP/MWh:

$$
\begin{aligned}
\mathrm{primary\_objective}^{\mathsf T}\cdot\mathrm{values}={}&
\sum_{k:\mathrm{direction}=\mathrm{up}}
\mathrm{price\_gbp\_per\_mwh}_k\cdot \mathrm{values}_{\mathrm{bid}:k}\\
&-\sum_{k:\mathrm{direction}=\mathrm{down}}
\mathrm{price\_gbp\_per\_mwh}_k\cdot \mathrm{values}_{\mathrm{bid}:k}\\
&+\mathrm{voll\_gbp\_per\_mwh}\cdot
\sum_z\mathrm{values}_{\mathrm{load\mbox{-}shedding}:z}.
\end{aligned}
$$

The second objective sums accepted bid MWh and shortage MWh. The third assigns weight 1 to storage charge, storage discharge and absolute corridor flow, plus the class weight of each non-storage downward bid. `physical_dec_weight` supplies the weights below; `bid_dec_rank` selects the class:

|Downward class|Weight|
|---|---:|
|Fuel plant running range|0|
|Import|0.5|
|Run-of-river hydro|2|
|Wind and solar|3|
|Fuel shutdown|3.5|
|Nuclear|4|
|Fuel shutdown before its minimum downtime|5|

Within a zone and at an exact primary-price tie, storage charging precedes run-of-river, wind, solar and nuclear reductions; fuel shutdown follows wind and solar and precedes nuclear. Across zones, class weights also trade against corridor-flow MWh. The primary LP uses exact prices, while copperplate balancing groups downward prices in 0.01 GBP/MWh bands. The fourth objective weights successive variables by 1, 2, … in the fixed order of bid, corridor, zone and storage identifiers.

Final asset injection adds signed accepted bids to the ahead schedule. `final_dispatch_mwh_by_asset` and `schedule_mwh_by_asset` are MWh. The index \(k\) identifies a bid; its `asset_id` selects asset \(a\), and `asset_zone_id_by_asset` selects the zone \(z\):

$$
\begin{aligned}
\mathrm{final\_dispatch\_mwh\_by\_asset}_a={}&
\mathrm{schedule\_mwh\_by\_asset}_a\\
&+\sum_{k:\mathrm{asset\_id}_k=a,\ \mathrm{direction}=\mathrm{up}}\mathrm{values}_{\mathrm{bid}:k}\\
&-\sum_{k:\mathrm{asset\_id}_k=a,\ \mathrm{direction}=\mathrm{down}}\mathrm{values}_{\mathrm{bid}:k}.
\end{aligned}
$$

Zonal conservation equates final supply and incoming transfer to demand and outgoing transfer. Corridor direction follows its declared `from_zone_id` and `to_zone_id`:

$$
\begin{aligned}
&\sum_{a:\mathrm{asset\_zone\_id\_by\_asset}_a=z}\mathrm{final\_dispatch\_mwh\_by\_asset}_a
+\mathrm{values}_{\mathrm{load\mbox{-}shedding}:z}\\
&\quad+\sum_{l:\mathrm{to\_zone\_id}=z}\mathrm{values}_{\mathrm{flow}:l}
=\mathrm{demand\_mwh\_by\_zone}_z
+\sum_{l:\mathrm{from\_zone\_id}=z}\mathrm{values}_{\mathrm{flow}:l}.
\end{aligned}
$$

Bid capacity bounds accepted MWh between zero and `bid_capacity`; MW bids are multiplied by `period_hours = 0.5`. Shortage lies between zero and zonal demand. Generator injection lies between zero and `realised_availability_mw_by_asset` times period hours. Interconnector injection lies between negative `export_capacity_mwh` and positive `import_capacity_mwh`.

Equal-price non-storage bids share free acceptance proportionally. Upward groups share zone, direction, network effect and price; downward groups also share downward class. `_forced_down_by_bid` first sets aside the reduction required by actual availability or the interconnector envelope. For a bid and the first bid in its group, the implementation uses

$$
\begin{aligned}
\mathrm{free}&=\mathrm{bid\_capacity}_{k}-\mathrm{forced},\\
\mathrm{first\_free}&=\mathrm{bid\_capacity}_{k_0}-\mathrm{first\_forced},\\
(\mathrm{values}_{\mathrm{bid}:k}-\mathrm{forced})\cdot \mathrm{first\_free}
&=(\mathrm{values}_{\mathrm{bid}:k_0}-\mathrm{first\_forced})\cdot \mathrm{free}.
\end{aligned}
$$

Each geographical boundary limits signed flow across its member corridors. `coefficient` is the member's direction coefficient; `forward_capacity` and `reverse_capacity` are period MWh after converting any MW input:

$$
-\mathrm{reverse\_capacity}_b
\le\sum_{l\in b}\mathrm{coefficient}_{b,l}\cdot \mathrm{values}_{\mathrm{flow}:l}
\le\mathrm{forward\_capacity}_b.
$$

All boundary constraints apply together. A corridor-specific limit additionally bounds its own flow; `absolute-flow` is at least both positive and negative signed flow. Thus 6,700 MW at B6 becomes 3,350 MWh per half-hour, and 2,200 MW on Western Link becomes 1,100 MWh. Corridors without individual limits remain constrained by zonal conservation and their boundary memberships.

Storage redispatch determines final internal inventory from realised charge and discharge. `opening` is `initial_soc_mwh_by_asset`; `capacity` is `energy_capacity_mwh`. For each store,

$$
\begin{aligned}
\mathrm{values}_{\mathrm{storage\mbox{-}discharge}:s}
-\mathrm{values}_{\mathrm{storage\mbox{-}charge}:s}
&=\mathrm{final\_dispatch\_mwh\_by\_asset}_s,\\
\mathrm{final\_soc\_mwh\_by\_asset}_s={}&\mathrm{opening}_s\\
&+\mathrm{charge\_efficiency}_s\cdot
\mathrm{values}_{\mathrm{storage\mbox{-}charge}:s}\\
&-\mathrm{values}_{\mathrm{storage\mbox{-}discharge}:s}/
\mathrm{discharge\_efficiency}_s.
\end{aligned}
$$

Charging and discharging lie between zero and their respective power limits times `period_hours`; final inventory lies between zero and `capacity`. Storage bids use `convex_net_power_v1`, with at most one bid per direction and a downward price at most the upward price plus \(10^{-8}\) GBP/MWh. Final simultaneous charging and discharging must be at most \(10^{-8}\) MWh. Final inventory becomes the next period's opening inventory; the national schedule and submitted bids provide the current intertemporal valuation.

Physical resource expenditure is calculated separately from bid payments. `resource_cost_gbp_per_mwh_by_asset` multiplies positive final injection, and shortage incurs VoLL:

$$
\begin{aligned}
\mathrm{physical\_resource\_cost\_gbp}={}&
\sum_a\max(\mathrm{final\_dispatch\_mwh\_by\_asset}_a,0)\\
&\qquad\cdot\mathrm{resource\_cost\_gbp\_per\_mwh\_by\_asset}_a\\
&+\mathrm{voll\_gbp\_per\_mwh}\cdot
\sum_z\mathrm{values}_{\mathrm{load\mbox{-}shedding}:z}.
\end{aligned}
$$

Network constraint cost compares this result with the same LP collapsed to one node, removing corridors and boundaries. `solve_network_free_counterfactual` retains bids, export arbitrage, import/export envelopes, storage physics, shortage valuation and solver settings. Both cases use the same period unit-cost table: supplied time-varying resource cost, otherwise annual marginal cost, storage cycle depreciation and zero export resource cost. Negative import prices can give negative period resource expenditure.

The primary-objective difference is recorded separately as `network_constraint_bid_objective_gbp`. Forecast-error attribution compares actual-forecast and perfect-forecast network-free cases. Each comparison changes its stated spatial or forecast inputs within the same optimisation formulation.

### Numerical solution and boundary marginal values

The solver locks total shortage from the primary optimum before bounding its bid-cost component. `lock_primary_shedding` sets every shortage variable to zero when the primary total is zero; otherwise their sum is bounded above by that primary total. `bid_cost_coefficients` supplies the bid-only objective for the next bound.

Objective locks use a scale-aware floating-point tolerance. `compute_lock_tolerance` reads the objective `coefficients`, the preceding `optimum`, a `unit_floor` and the effective `solver_tolerance`. It computes

$$
\begin{aligned}
\mathrm{absolute\_term\_scale}&=\sum_i|
\mathrm{coefficients}_i\cdot \mathrm{optimum}_i|,\\
\mathrm{coefficient\_one\_norm}&=\sum_i|\mathrm{coefficients}_i|,\\
\mathrm{gamma\_n}&=\frac{\mathrm{nonzero\_terms}\cdot \mathrm{epsilon}}
{1-\mathrm{nonzero\_terms}\cdot \mathrm{epsilon}},\\
\mathrm{tolerance}=\max\bigl\{&\mathrm{unit\_floor},\\
&\mathrm{solver\_tolerance}\cdot\max(1,\mathrm{absolute\_term\_scale}),\\
&\mathrm{gamma\_n}\cdot \mathrm{absolute\_term\_scale},\\
&\mathrm{coefficient\_one\_norm}\cdot \mathrm{solver\_tolerance}\bigr\}.
\end{aligned}
$$

Here `nonzero_terms` counts nonzero coefficients and `epsilon` is machine precision. The effective tolerance takes the larger of the applicable solver and bound-canonicalisation tolerances. The bid-cost lock uses a \(10^{-8}\) GBP floor and default solver tolerance \(10^{-9}\); MWh locks use a \(10^{-9}\) MWh floor and solver floor \(10^{-8}\). The bid-cost acceptance ceiling is 1 GBP per period. Each later solve retains the preceding objective bounds. HiGHS dual simplex with presolve uses primal and dual tolerances of \(10^{-9}\); final equality, inequality and bound violations must be at most \(10^{-7}\).

```text
for period in the half-hour chronology:
    align_zonal_demand(...): obtain zonal demand
    build_single_period_problem(...): build bids and physical constraints
    solve_lexicographic(problem):
        minimise primary_objective; retain primary boundary marginals
        lock_primary_shedding(...); bound bid_cost_coefficients(problem)
        minimise secondary_objective; retain its objective bound
        minimise physical_tie_objective; retain its objective bound
        minimise stable_tie_objective; validate_solution(...)
    solve_network_free_counterfactual(...): compute matched comparison
    return actual injections, storage inventory, flows, shortage and costs
    pass final_soc_mwh_by_asset to the next period
```

Boundary marginal values measure the primary objective's response to transfer capacity. `boundary_marginal_values` reads the forward and reverse constraint-row duals before objective locks are added:

$$
\mathrm{value\_gbp\_per\_mwh}_b
=\mathrm{marginals}_{\mathrm{reverse\_row}_b}
-\mathrm{marginals}_{\mathrm{forward\_row}_b}.
$$

A positive value corresponds to a binding forward limit and a negative value to a binding reverse limit. Status is `computed`, `degenerate_dual` for a binding limit with zero dual, or `shared_member` when binding boundaries share a corridor and the dual allocation is non-unique. The annual sum of absolute boundary value times transfer is reported as a congestion diagnostic, separately from zonal prices, cash flows and system cost. A ledger without this calculation displays “Not computed”.

### The two zonal cases

The British 23-zone study uses the GBP1 public2 research suite, `value-uk-research-suite-v1-public2`, supplied with VALUE 0.7.0-alpha.1 through the [data page](https://value.ac/en/data/). It contains 22 computational corridors and the B6 and B7a boundaries, rated at 6,700 MW and 9,400 MW in each direction. The 2025–2034 study design holds network capacity fixed while annual demand and assets may change.

The 23-zone pack locates wind and solar by site; CCGT, OCGT, biomass, run-of-river hydro, nuclear, storage and imports are allocated to `ENGLAND_FALLBACK`. Nuclear stations created by the public2 policy enter that zone through the runtime fallback, including Torness north of B6. Import resources are named `import:<country>`, while the landing table uses `interconnector:<line>`; this mismatch also places imports in the fallback zone. `runtime_fallback_audit` records these allocations, and the resulting spatial distribution is indicative.

Staged and zonal runs declare the ledger balance boundary `full_node_v1`, enabling energy-balance assessment. The independent checks `generation_cross_path` and `demand_input_reconciliation` retain status `not_evaluated`. The default `summary` trace omits per-period solver diagnostics; the result therefore displays “Not recorded”.

The 11-zone experiment represents British regions as T1–T11 and compares transmission outcomes for a single year with fixed assets. The regions are N. Scotland, S. Scotland, N. England, N. Wales/the Mersey/the Humber, Midlands, Central England, E. Anglia, S. Wales/the Severn, S.W. England, S. England and South-East England. It uses 2022 demand and weather over 17,520 half-hours with a 2025 model background. Asset capacities remain fixed throughout the experiment, with annual investment outside its execution path.

The 11-zone network combines 13 computational corridors classified as AC assets with Western Link. Ordinary corridors connect 1–2, 2–3, 3–4, 4–5, 5–6, 5–8, 6–7, 6–8, 6–11, 8–9, 8–10, 9–10 and 10–11; Western Link connects T2→T4. The table gives geographical boundary capacities and the separate Western Link limit. The 2029 values form an independent sensitivity input, while base cases use 2025 capacities.

| Boundary | 2025 capacity in each direction, MW | 2029 sensitivity capacity, MW | Positive-flow members |
|---|---:|---:|---|
| B4 | 4,002 | 4,923 | f12 |
| B6 | 6,700 | 11,456 | f23 + fWL |
| B7a | 9,400 | 10,609 | f34 + fWL |
| B8 | 11,000 | 14,005 | f45 |
| B9 | 11,500 | 12,900 | f56 + f58 |
| EC5 | 3,300 | 5,925 | −f67 |
| LE1 | 11,223 | 13,917 | f6,11 + f10,11 |
| B13 | 3,500 | 6,575 | −f89 + f9,10 |
| Western Link | 2,200 | 2,200 | fWL |

Western Link flow consumes the stated capacity of both B6 and B7a. The 8 geographical boundaries use symmetric reverse capacities, while the Western Link input specifies a bidirectional rating. In the base reduced network, T6, T8 and T10 have identical boundary memberships, leaving modelled transfer between them without a finite upper bound. In its 14-dimensional corridor space, the nodal incidence matrix has rank 10, the geographical boundary matrix rank 8, and the matrix including the HVDC limit rank 9. The 5-dimensional constraint null space contains 3 circulation directions and 2 directions that alter nodal net transfers.

The thermal-capacity sensitivity adds separate limits to 8 southern corridors while retaining geographical boundaries. Its construction contracts known substations within each zone to the zone node, retains unknown intermediate nodes, excludes other known zones, and calculates corridor capacity by network maximum flow/minimum cut. Parallel line capacities add, while serial paths are limited by their bottlenecks; MVA is converted to MW at an assumed power factor of 1. The ordinary summer and winter inputs are shown below; separate upper-bound sensitivities use their own files.

| Corridor | Summer MW | Winter MW |
|---|---:|---:|
| T5–T6 | 19,086 | 21,052 |
| T5–T8 | 3,424 | 3,934 |
| T6–T8 | 4,436 | 5,558 |
| T6–T11 | 16,684 | 19,849 |
| T8–T9 | 8,088 | 9,217 |
| T8–T10 | 6,470 | 7,834 |
| T9–T10 | 4,434 | 5,558 |
| T10–T11 | 6,587 | 7,500 |

### DC network dispatch

The DC network module jointly selects generation, storage operation and nodal voltage angles over the complete chronology. `ReferenceDCNetworkPSM` builds the variable blocks `generation`, `charge`, `discharge`, `soc`, `blackout`, `angle` and `flow` in `layout`. Their solved values carry those names in the equations: the first five are MWh, `angle` is radians and `flow` is MW. Resource, storage, bus, branch and period indices are \(i,s,n,l,t\). `marginal_costs`, `variable_degradation_gbp_per_mwh_discharged` and `voll_gbp_per_mwh` are GBP/MWh. With fixed assets, operating expenditure is

$$
\begin{aligned}
\min\quad&\sum_{i,t}\mathrm{marginal\_costs}_{i,t}\cdot \mathrm{generation}_{i,t}\\
&+\sum_{s,t}\mathrm{variable\_degradation\_gbp\_per\_mwh\_discharged}_s\cdot
\mathrm{discharge}_{s,t}\\
&+\mathrm{voll\_gbp\_per\_mwh}\cdot\sum_{n,t}\mathrm{blackout}_{n,t}.
\end{aligned}
$$

Assets mapped to several buses become independent location-specific units through `expand_share_mappings`. The mapping field `share` sums to 1 for each asset and scales its generation capacity, storage charge and discharge power, energy capacity and initial inventory. The solver dispatches these units at their assigned buses and aggregates their outputs by original asset. VoLL reads `market.voll_gbp_per_mwh`, default 17,000 GBP/MWh.

Nodal conservation converts branch power to energy using `period_hours`. For units located at bus \(n\),

$$
\begin{aligned}
&\sum_{i\in n}\mathrm{generation}_{i,t}
+\sum_{s\in n}(\mathrm{discharge}_{s,t}-\mathrm{charge}_{s,t})
+\mathrm{blackout}_{n,t}\\
&\quad+\mathrm{period\_hours}\cdot\sum_{l:\mathrm{to\_bus}=n}\mathrm{flow}_{l,t}
=\mathrm{demand\_mwh\_by\_bus}_{n,t}
+\mathrm{period\_hours}\cdot\sum_{l:\mathrm{from\_bus}=n}\mathrm{flow}_{l,t}.
\end{aligned}
$$

Resource bounds multiply `capacity_mw`, `share`, `availability` and `period_hours`. Storage obeys the charging, discharging and inventory constraints in Chapter 8 with the same mapping share; its transition is

$$
\begin{aligned}
\mathrm{soc}_{s,t}={}&\mathrm{soc}_{s,t-1}
+\mathrm{charge\_efficiency}_s\cdot \mathrm{charge}_{s,t}\\
&-\mathrm{discharge}_{s,t}/\mathrm{discharge\_efficiency}_s.
\end{aligned}
$$

The terminal rule is free, cyclic at initial inventory, or fixed at a declared target. `allow_blackout` bounds shortage between zero and bus demand when enabled and fixes it at zero otherwise. Availability lies in \([0,1]\), and marginal resource costs are nonnegative.

AC lines and transformers use the declared equivalent reactance and angle difference. `base_mva` defaults to 100 MVA, `tap` to 1, and `phase` converts `phase_shift_degrees` to radians:

$$
\begin{aligned}
\mathrm{susceptance}_l&=\frac{\mathrm{base\_mva}}
{\mathrm{reactance\_pu}_l\cdot \mathrm{tap}_l},\\
\mathrm{flow}_{l,t}&=\mathrm{susceptance}_l\cdot
(\mathrm{angle}_{\mathrm{from\_bus},t}
-\mathrm{angle}_{\mathrm{to\_bus},t}-\mathrm{phase}_l),\\
|\mathrm{flow}_{l,t}|&\le\mathrm{thermal\_rating\_mw}_l\cdot \mathrm{circuits}_l.
\end{aligned}
$$

Circuit count scales thermal capacity; the declared equivalent reactance sets the angle equation. Each connected island has one reference bus at zero angle, with other angles bounded by \([-\pi,\pi]\). Out-of-service branches have zero flow. DC links enter nodal balance as controllable flows within their declared bounds.

HiGHS solves all periods in one linear programme with primal and dual tolerances of \(10^{-8}\) and an equality-residual limit of \(10^{-7}\). Nodal energy-balance duals provide marginal operating prices in GBP/MWh; the displayed system price is demand weighted. Fixed assets, continuous dispatch, storage and the linear network define this full-horizon comparison.

### AC feasibility calculation

The AC module calculates steady-state power flow for a given active-power schedule. Inputs contain active and reactive demand, generator active and reactive limits, voltage setpoints, branch impedances and charging susceptance, fixed taps and phase shifts, voltage bounds and MVA ratings. Each connected island has one slack balancing asset; PV and slack buses require generation, with a common voltage setpoint for generators at one bus. Storage follows its supplied active charging and discharging schedule.

Nodal complex injection follows the solved voltage and nodal admittance matrix. `vm` is per-unit voltage magnitude, `theta` is radians, `voltage` is complex per-unit voltage, and `injection` contains MW and Mvar. `ybus` is per-unit admittance on the `base_mva` base, and \(j^2=-1\):

$$
\begin{aligned}
\mathrm{voltage}_n&=\mathrm{vm}_n\cdot e^{j\cdot\mathrm{theta}_n},\\
\mathrm{injection}_n&=\mathrm{base\_mva}\cdot \mathrm{voltage}_n\cdot
\overline{\sum_m\mathrm{ybus}_{nm}\cdot \mathrm{voltage}_m}.
\end{aligned}
$$

Each branch uses a π impedance representation. `_ybus` computes `series` as the reciprocal of `resistance_pu` plus \(j\) times `reactance_pu`; `charging` is half the imaginary charging susceptance; and `tap` is the tap ratio multiplied by the complex phase-shift factor. The terminal admittances are

$$
\begin{aligned}
\mathrm{yff}&=(\mathrm{series}+\mathrm{charging})/|\mathrm{tap}|^2,\\
\mathrm{yft}&=-\mathrm{series}/\overline{\mathrm{tap}},\qquad
\mathrm{ytf}=-\mathrm{series}/\mathrm{tap},\\
\mathrm{ytt}&=\mathrm{series}+\mathrm{charging}.
\end{aligned}
$$

The solver fits active balance at non-slack buses and reactive balance at PQ buses, holding PV and slack voltage magnitudes fixed. The slack asset supplies residual active power and network losses. Nodal reactive generation is checked against the sum of generator limits at that bus. Complex powers `s_from` and `s_to` contain MW and Mvar; `losses` is MW. They use the declared endpoints \(f,t\):

$$
\begin{aligned}
\mathrm{s\_from}&=\mathrm{base\_mva}\cdot \mathrm{voltage}_f\cdot
\overline{\mathrm{yff}\cdot \mathrm{voltage}_f+\mathrm{yft}\cdot \mathrm{voltage}_t},\\
\mathrm{s\_to}&=\mathrm{base\_mva}\cdot\mathrm{voltage}_t\cdot
\overline{\mathrm{ytf}\cdot\mathrm{voltage}_f+\mathrm{ytt}\cdot\mathrm{voltage}_t},\\
\mathrm{losses}_l&=\operatorname{Re}(\mathrm{s\_from}+\mathrm{s\_to}).
\end{aligned}
$$

Apparent power at both terminals is limited by `apparent_power_rating_mva` times `circuits`. Every in-service branch enters the admittance matrix with its declared impedance. Topology and device settings remain fixed.

Nonlinear least squares solves from several initial voltage conditions. Converged solutions are checked for agreement, followed by generator active and reactive bounds, bus voltages, branch ratings and system balance among supply, charging, demand and losses. `ReferenceACFeasibilityPSM` returns the local steady-state trajectory and feasibility checks for that schedule.

### Optional line expansion

Line expansion screens externally specified candidates using observed congestion and declared annual benefits. Candidate records contain endpoints, circuit numbers, branch parameters and limits, construction cost, fixed operation and maintenance, lifetime, discount rate, lead time, delay, planning success and budget group. `ReferenceTransmissionExpansion.propose` computes peak `utilisation`, `annual_cost` and benefit-cost `ratio`:

$$
\begin{aligned}
\mathrm{utilisation}&=\max_{t,l\in\mathrm{trigger\_branch\_ids}}
\frac{|\mathrm{branch\_flow\_mw}_{l,t}|}{\mathrm{trigger\_branch\_rating\_mw}},\\
\mathrm{annual\_cost}&=\operatorname{\_crf}(\mathrm{discount\_rate},\mathrm{economic\_life\_years})\\
&\qquad\cdot\mathrm{total\_capex\_gbp\_per\_build}
+\mathrm{annual\_fixed\_opex\_gbp\_per\_build},\\
\mathrm{ratio}&=\mathrm{declared\_annual\_benefit\_gbp}/\mathrm{annual\_cost}.
\end{aligned}
$$

The capital-recovery function `_crf` uses its arguments `rate` and `life`:

$$
\operatorname{\_crf}(\mathrm{rate},\mathrm{life})=
\begin{cases}
1/\mathrm{life},&\mathrm{rate}=0,\\
\dfrac{\mathrm{rate}\cdot(1+\mathrm{rate})^{\mathrm{life}}}
{(1+\mathrm{rate})^{\mathrm{life}}-1},&\mathrm{rate}>0.
\end{cases}
$$

Candidates are ordered by descending `ratio` and ascending identifier. Earliest decision year, minimum trigger utilisation, minimum benefit-cost ratio, total budget and budget-group allowance determine admission; zero annual cost gives an infinite ratio. The registered parameter defaults are 0 GBP for total annual funding and \(10^{13}\) GBP per group. Each accepted proposal deducts its complete construction cost. Expected commissioning is the decision year plus `lead_time_years` and `delay_years`.

Planning success compares a reproducible uniform draw with `success_probability`. The default seed is 0; the proposal identifier includes the run identifier, and together they define the draw. At each year's start, completed projects commission and active lines retire at commissioning year plus the ceiling of `economic_life_years`. `apply_commissioned_network_assets` inserts commissioned branches into the annual network. The 23-zone and 11-zone cases retain fixed networks; line expansion is a separately selected method.

### Data and implementation

Zonal inputs comprise `zones`, `corridors`, `cutsets`, `asset-map`, `demand`, `ratings` and `interconnector-landings`. `align_zonal_demand` applies the two demand rules, `build_single_period_problem` constructs redispatch constraints, `solve_lexicographic` solves the 4 objectives sequentially, and `ZonalRedispatchBalancing` returns actual injections, inventory and costs. The 11-zone study uses the external research scripts `build_network_data.py` and `fixed_fleet_runner.py`, with `cutsets_2025.json`, `cutsets_2029.json` and summer/winter thermal files defining its scenarios. These scripts belong to the separate fixed-asset experiment described above; the packaged British network study uses the 23-zone suite.

`network_method_rules.py` defines `network-economic-v2`. The network-free comparison is identified by `value.network-free-lp/v1`, while `zonal_results.py` assembles zonal outcomes. Each year records downward-bid assumptions in `extensions.downward_restart_economics`, using schema `value.network-downward-restart-economics/v1`; missing inputs and the resulting fallback basis accompany the calculation record.

The independent network modules use buses, branches, asset-to-bus mappings and period demand. `ReferenceDCNetworkPSM` and `validate_dc_solution` implement linear dispatch and its physical checks; `load_ac_data_from_pack`, `ReferenceACFeasibilityPSM` and `validate_ac_result` implement AC inputs, power flow and feasibility checks. `ReferenceTransmissionExpansion` reads candidates and budgets and advances construction states, while `apply_commissioned_network_assets` inserts active new lines into the network.


## 8. Perfect-foresight dispatch and natural hydrology

### Perfect-foresight single-node dispatch

The perfect-foresight module schedules generation, imports and storage jointly over the complete input chronology at fixed asset capacities. `PerfectForesightPSM.run` reads `PSMInput.chronology`; the outer annual model supplies investment and the resulting capacities. Each period contains demand, resource availability and marginal costs. Storage inputs give power, energy capacity, efficiencies and initial inventory.

The objective minimises operating resource expenditure, storage degradation and shortage cost. The equations retain the implementation names: `resource_period`, `charge_period`, `discharge_period`, `soc_period` and `blackout` are MWh arrays, indexed by resource \(i\), storage asset \(s\) and period \(t\). `resource_marginal_costs` and `variable_degradation_gbp_per_mwh_discharged` are GBP/MWh. With `voll_gbp_per_mwh` as the shortage valuation, the objective is

$$
\begin{aligned}
\min\quad&\sum_{i,t}\mathrm{resource\_marginal\_costs}_{i,t}\cdot
\mathrm{resource\_period}_{i,t}\\
&+\sum_{s,t}\mathrm{variable\_degradation\_gbp\_per\_mwh\_discharged}_{s}\cdot
\mathrm{discharge\_period}_{s,t}\\
&+\mathrm{voll\_gbp\_per\_mwh}\cdot\sum_t\mathrm{blackout}_{t}.
\end{aligned}
$$

The single-node balance supplies demand and charging from available resources, storage discharge and recorded shortage:

$$
\begin{aligned}
&\sum_i\mathrm{resource\_period}_{i,t}
+\sum_s\mathrm{discharge\_period}_{s,t}+\mathrm{blackout}_{t}\\
&\qquad=\mathrm{demand\_mwh}_{t}+\sum_s\mathrm{charge\_period}_{s,t}.
\end{aligned}
$$

Storage inventory records internal energy. `charge_efficiency` multiplies electricity absorbed from the grid, while delivered electricity is divided by `discharge_efficiency`:

$$
\begin{aligned}
\mathrm{soc\_period}_{s,t}={}&\mathrm{soc\_period}_{s,t-1}
+\mathrm{charge\_efficiency}_s\cdot \mathrm{charge\_period}_{s,t}\\
&-\mathrm{discharge\_period}_{s,t}/\mathrm{discharge\_efficiency}_s.
\end{aligned}
$$

Capacity bounds use `period_hours` to convert MW into period MWh:

$$
\begin{aligned}
0&\le\mathrm{resource\_period}_{i,t}
\le\mathrm{capacity\_mw}_{i}\cdot \mathrm{availability}_{i,t}\cdot \mathrm{period\_hours},\\
0&\le\mathrm{charge\_period}_{s,t}
\le\mathrm{charge\_power\_mw}_{s}\cdot \mathrm{period\_hours},\\
0&\le\mathrm{discharge\_period}_{s,t}
\le\mathrm{discharge\_power\_mw}_{s}\cdot \mathrm{period\_hours},\\
0&\le\mathrm{soc\_period}_{s,t}\le\mathrm{energy\_capacity\_mwh}_{s}.
\end{aligned}
$$

Initial and terminal inventory determine net storage energy exchange across the horizon. The first transition starts from `initial_soc_mwh`. The default `terminal_soc_rule = cyclic` equates final and initial inventory; `fixed` uses `terminal_soc_mwh_by_asset`; `free` leaves final inventory within its bounds. With `allow_blackout`, shortage lies between zero and `demand_mwh`; otherwise its upper bound is zero. Defaults are `period_hours = 0.5`, `voll_gbp_per_mwh = 17000` and zero degradation cost. The Study parameter `market.voll_gbp_per_mwh` accepts 0–1,000,000 GBP/MWh and enters the dispatch objective.

A second linear programme minimises storage throughput within the first solution's cost tolerance. `primary.fun` is the first-stage minimum in GBP; the second stage retains all physical constraints and adds

$$
\begin{aligned}
\mathrm{primary\_tolerance}&=\max(10^{-7},10^{-10}|\mathrm{primary.fun}|),\\
\mathrm{objective}^{\mathsf T}\cdot\mathrm{solution}
&\le\mathrm{primary.fun}+\mathrm{primary\_tolerance},\\
\min\quad&\sum_{s,t}(\mathrm{charge\_period}_{s,t}+\mathrm{discharge\_period}_{s,t}).
\end{aligned}
$$

Both stages use HiGHS with primal and dual feasibility tolerances of \(10^{-8}\). The returned physical trajectory is `secondary.x`. The maximum simultaneous charge and discharge, `simultaneous`, must be at most \(10^{-6}\) MWh. Unused renewable energy is availability less accepted resource supply.

The displayed “Balance shadow price” is the first-stage marginal operating cost of period demand. Revenue multiplies the demand-balance dual in GBP/MWh by accepted MWh; storage earns the dual multiplied by discharge less charge. Consumer payment uses supplied demand. System cost adds annualised capital and the fixed operation and maintenance of non-wind, non-solar and non-storage assets to variable expenditure, degradation and shortage cost. The fixed-cost input is `annual_fixed_opex_gbp`; wind, solar and storage fixed operation and maintenance remains a memo line under Chapter 4.

```text
PerfectForesightPSM.run(model_input):
    data = model_input.chronology
    validate_chronology(data, model_input.period_hours)
    _availability(...) and _marginal_costs(...): expand inputs to every period
    _layout(data): allocate resource, charge, discharge, soc and blackout
    assemble objective, throughput_objective, equality, rhs and bounds
    primary = linprog(objective, A_eq=equality, b_eq=rhs,
                      bounds=bounds, method="highs")
    primary_tolerance = max(1e-7, abs(primary.fun) * 1e-10)
    secondary = linprog(
        throughput_objective, A_ub=objective.reshape(1, -1),
        b_ub=[primary.fun + primary_tolerance], A_eq=equality, b_eq=rhs,
        bounds=bounds, method="highs")
    extract resource_period, charge_period and discharge_period
    extract soc_period and blackout
    check balance and simultaneous storage operation
    return costs and demand duals
```

Resource availability accepts a single-element series or a complete series, with finite values in \([0,1]\). Marginal cost accepts a scalar, a single-element series or a complete series, with finite nonnegative values. The adapter checks chronology length and requires charging and discharging efficiencies in \((0,1]\). Hydro supplied here is a resource with declared electrical availability. The hydrological functions below construct availability from inflow or optimise a conventional reservoir.

### Available run-of-river electricity

The natural-hydrology method derives available electricity from an inflow series and site parameters. `run_of_river_dispatch` reads `HydroSite` and `CanonicalInflow`; the default national PSM uses the statistical load factor and seasonal profile in Chapter 5.

A normalised electrical availability input scales installed power over the period. With `inflow.unit = p.u.`, `inflow.values` lies in \([0,1]\), `capacity_mw` is MW and `interval_hours` is hours:

$$
\begin{aligned}
\mathrm{maximum}&=\mathrm{capacity\_mw}\cdot \mathrm{interval\_hours},\\
\mathrm{available}_t&=\mathrm{maximum}\cdot \mathrm{inflow.values}_t.
\end{aligned}
$$

A water-volume input is converted through the site's turbine efficiency and MWh per water unit, then limited by electric power:

$$
\begin{aligned}
\mathrm{available}_t=\min\bigl(&\mathrm{maximum},\\
&\mathrm{inflow.values}_t\cdot \mathrm{conversion\_mwh\_per\_water\_unit}\cdot
\mathrm{turbine\_efficiency}\bigr).
\end{aligned}
$$

Accepted generation lies between zero and `available`; the default accepts all available electricity. `curtailed` is the remaining electrical potential. These arrays become `available_energy_mwh`, `accepted_generation_mwh` and `curtailed_energy_mwh` in the returned result. A 10 MW site over 0.5 h with factors \([0,0.5,1]\) supplies \([0,2.5,5]\) MWh. This calculation operates independently in each period.

### Conventional reservoir dispatch

A conventional reservoir allocates water across the complete inflow and electricity-value chronology to maximise generation value. `reservoir_dispatch` uses four period variables: turbine release `q`, ecological `bypass`, `spill` and end-period `storage`. All four use the declared water unit; the first three are volumes within the period. The conversion to electricity is

$$
\mathrm{conversion}=\mathrm{conversion\_mwh\_per\_water\_unit}\cdot
\mathrm{turbine\_efficiency},\qquad
\mathrm{generation}_t=\mathrm{q}_t\cdot \mathrm{conversion}.
$$

The linear programme minimises the negative value of generation plus a small spill penalty. `energy_value_gbp_per_mwh` is an externally supplied electricity-value series:

$$
\begin{aligned}
\min\quad&-\sum_t\mathrm{energy\_value\_gbp\_per\_mwh}_t\cdot
\mathrm{conversion}\cdot \mathrm{q}_t+10^{-9}\sum_t\mathrm{spill}_t.
\end{aligned}
$$

Water continuity links successive inventories and inflows. The first period starts from `initial_volume`:

$$
\begin{aligned}
\mathrm{storage}_t={}&\mathrm{storage}_{t-1}+\mathrm{inflow.values}_t
-\mathrm{q}_t-\mathrm{bypass}_t-\mathrm{spill}_t,\\
\mathrm{min\_volume}&\le\mathrm{storage}_t\le\mathrm{max\_volume}.
\end{aligned}
$$

Turbine, ordinary-release and ecological bounds restrict the use of water:

$$
\begin{aligned}
0&\le\mathrm{q}_t\le\mathrm{max\_turbine\_release\_per\_period},\\
0&\le\mathrm{bypass}_t\le\mathrm{max\_total\_release\_per\_period},\qquad
\mathrm{spill}_t\ge0,\\
\mathrm{minimum\_environmental\_release\_per\_period}
&\le\mathrm{q}_t+\mathrm{bypass}_t
\le\mathrm{max\_total\_release\_per\_period}.
\end{aligned}
$$

The ordinary-release bound and ecological minimum apply to turbine release plus bypass; spill enters water balance separately. A supplied `terminal_volume` fixes final inventory. The parameter check requires maximum total release to be at least maximum turbine release and electricity from maximum turbine release to be at most `turbine_capacity_mw` multiplied by `interval_hours`, with tolerance \(10^{-9}\) MWh.

The solver reads the complete inflow and value series, solves one SciPy/HiGHS linear programme and returns water trajectories, generation and conservation residuals. `objective_gbp` includes the small spill penalty. The input labels `myopic`, `rolling_horizon` and `perfect_foresight` all call this full-horizon algorithm and are returned as metadata.

```text
reservoir_dispatch(parameters, inflow, energy_value_gbp_per_mwh):
    inflow.validate(); parameters.validate(inflow.interval_hours)
    conversion = (parameters.conversion_mwh_per_water_unit
                  * parameters.turbine_efficiency)
    allocate q, bypass, spill and storage for every period
    assemble objective, water equalities, release inequalities and bounds
    use parameters.terminal_volume as the final storage bound when supplied
    solved = linprog(objective, A_ub=inequalities, b_ub=upper,
                     A_eq=equalities, b_eq=rhs, bounds=bounds, method="highs")
    generation = q * conversion
    check previous + inflow.values[period] - q - bypass - spill - storage
    return generation, water trajectories and residuals
```

### Hydrological inputs and module connection

Natural-hydrology inputs comprise the site table, asset-to-site mapping, run-of-river inflow, reservoir inflow and reservoir parameters. Sites declare technology, capacity, turbine efficiency, bus, source and licence. Pumped storage uses the electrical-storage model. Each asset is assigned to a site, with mapping shares in \((0,1]\) and total shares per asset at most 1.

Inflow CSV files provide timezone-aware timestamps, interval length, site identifiers, values and water or electrical-availability units. The adapter requires finite nonnegative values, unique timestamps and consistent units; a supplied expected chronology is checked period by period. Site, mapping and parameter tables accept JSON or CSV. The declared missing-value treatment is `none`.

The input and operating functions can be called independently. `load_hydrology_inputs_from_pack` assembles inputs, `adapt_hydrology_csv` reads inflow, `validate_site_mapping` checks mapping, `run_of_river_dispatch` calculates run-of-river electricity and `reservoir_dispatch` optimises reservoir releases. An annual market application requires an adapter connecting these inputs and outputs to its dispatch workflow, together with the relevant site, inflow, abstraction, conversion, storage and terminal parameters.


## 9. Carbon accounting parameters

VALUE calculates operational emissions and equipment-construction emissions separately before combining them under the selected accounting scenario. Operational emissions vary with generation and imported electricity, while construction emissions vary with installed capacity and the annualisation rule. Current physical accounting uses the `value_current_authoritative_v1` factor set. The doctoral-reproduction reference configuration selects `doctoral_reproduction_2026_07_18`, retaining historical storage scalars in their original units and recording the carbon result as `not_physically_interpretable`.

### Generation and imported electricity

Operational emissions multiply generated or imported electricity by its selected factor. In `build_operational_carbon_ledger`, `activity` is the MWh read from `generation_mwh_by_asset` for each `asset_id`; `kg` is the factor converted to kg/MWh. Each `emissions_tco2e` entry records the resulting tonnes, and `operational` sums these entries:

$$
\begin{aligned}
\mathtt{emissions\_tco2e}_{\mathtt{asset\_id}}
&=\frac{\mathtt{activity}_{\mathtt{asset\_id}}\times
\mathtt{kg}_{\mathtt{asset\_id}}}{1000},\\
\mathtt{operational}&=\sum_{\mathtt{asset\_id}}\mathtt{emissions\_tco2e}_{\mathtt{asset\_id}}.
\end{aligned}
$$

The result is in tonnes, retaining the CO₂ or CO₂e definition of the selected factor. Zero values in the table refer to the direct operational generation boundary. Equipment-construction emissions are calculated using the capacity-based emissions factors in the next section. Import factors use fixed national averages or fallback values.

|Generation technology or import source|Factor kg/MWh|Gas basis|Data basis|
|---|---|---|---|
|Combined-cycle gas|394|CO₂|NESO regional carbon-intensity methodology 2024|
|Open-cycle gas|651|CO₂|NESO regional carbon-intensity methodology 2024|
|Biomass|120|CO₂e|NESO regional carbon-intensity methodology 2024|
|Wind Solar Nuclear Conventional hydro Pumped hydro|0|CO₂|NESO generation boundary|
|Imports from France|53|CO₂|NESO fixed fallback factor|
|Imports from the Netherlands|474|CO₂|NESO fixed fallback factor|
|Imports from Belgium|179|CO₂|NESO fixed fallback factor|
|Imports from Ireland|458|CO₂|NESO fixed fallback factor|
|Imports from Norway|11.9|CO₂e|NVE annual mean for physical electricity delivery in 2024|

The source factors are converted to kg/MWh, with 1 g/kWh numerically equal to 1 kg/MWh. The original unit of Norway's factor is gCO₂e/kWh.

The biomass calculation uses the fixed factor of 120 kgCO₂e/MWh in the table. Its source reports an uncertainty range of ±120 gCO₂/kWh.

### Construction emissions annualised by power capacity

Construction emissions are annualised for each operating asset. In `_asset_embodied_lines`, `capacity_mw` is operating power in MW and `factor.value` is its selected annual factor in tCO₂e/(MW·year). The per-asset value `emissions` becomes `line.emissions_tco2e`; `embodied` sums the construction entries:

$$
\begin{aligned}
\mathtt{emissions}&=\mathtt{capacity\_mw}\times\mathtt{factor.value},\\
\mathtt{embodied}&=\sum\mathtt{line.emissions\_tco2e}.
\end{aligned}
$$

The following annual factors are those used in the research postprocessing input `embodied_factors_desnz_unece.csv`. The study configuration fixes the factor selection. Open-cycle gas uses the combined-cycle gas construction factor, and the electrolyser uses the literature proxy recorded in that input table.

|Technology|Annual factor tCO₂e/(MW·year)|
|---|---|
|Solar|38.544|
|Onshore wind|47.304|
|Offshore wind|96.1848|
|Nuclear|43.362|
|Conventional hydro|61.32|
|Pumped hydro|98.55|
|Combined-cycle gas|16.2936|
|Open-cycle gas|16.2936|
|Biomass|22.0752|
|Electrolyser|1.25|

### Storage emissions measured by energy capacity

Battery manufacturing emissions are annualised by rated energy capacity and equipment life. The selected factor is 89 kgCO₂e/kWh of capacity, the midpoint applied in the Longfield Solar Farm environmental statement of 2022. `_asset_embodied_lines` reads `asset.energy_capacity_mwh` in MWh and `economic_life` in years from `economic_lifetime_years`. Annual manufacturing emissions are

$$
\mathtt{emissions}
=\frac{89\times\mathtt{asset.energy\_capacity\_mwh}}
{\mathtt{economic\_life}}
\quad\mathrm{tCO_2e/year}.
$$

Hydrogen storage accounts separately for power equipment and energy storage. The energy-storage component uses a lifetime factor of 0.0006 tCO₂e/MWh of capacity, annualised over the asset's declared economic life. It is stored as `ch4_h2_store_lifetime` in `factor_catalog.csv`, with the original thesis Chapter 4 storage parameters and their 10-year source lifetime retained in the factor record. The electrolyser power component uses the annual factor in the preceding section.

### Data and implementation

`factor_catalog.csv` stores the factors, units, accounting boundaries and source locations, while `sources.csv` stores source names. `CarbonFactorDatabase` reads `value_carbon_factors.sqlite`. `build_operational_carbon_ledger` connects dispatched electricity and operating assets to the selected factor set, and `_asset_embodied_lines` calculates annualised equipment-construction emissions.


## Ensemble interpretation

Weather, demand and planning seeds define child runs with fixed inputs. Aggregation reports completed members, missing members and their statistics. A comparison identifies the units, denominator, horizon, terminal policy and factor scenario for each case. Probability statements require a specified sampling design; a small set of chosen scenarios describes those scenarios.


## Executable module inventory

The 18 shipped manifest identifiers are:

- `agent-investment`
- `dynamic-annual-storage-cost`
- `planning-pipeline`
- `reference-transmission-expansion`
- `user-formula-storage-cost`
- `value-annual-state-transition`
- `value-bid-at-cost-psm`
- `value-copperplate-balancing`
- `value-doctoral-national-psm`
- `value-legacy-storage-tariff`
- `value-perfect-foresight-lp`
- `value-reference-dc-network`
- `value-repd-era5-aggregated-weather`
- `value-representative-point-weather`
- `value-staged-bid-at-cost-psm`
- `value-storage-expansion-policy`
- `value-zonal-redispatch-balancing`
- `vre-expansion-cap`

[generated/MODULES.md](generated/MODULES.md) gives versions and entry points; [generated/PARAMETERS.md](generated/PARAMETERS.md) gives parameter defaults and fixed or editable classifications. Natural hydrology uses independent domain functions. The experimental AC method remains unregistered by default.


## Solver-contract notation

The solver contract expresses the Chapter 7 objective lock with its published
notation. `U_k` is `absolute_term_scale`, `C_k` is `coefficient_one_norm`, `n` is
`nonzero_terms`, `epsilon_effective` is the effective `solver_tolerance`, and
`tau_k` is the returned `tolerance` in `compute_lock_tolerance`. `c_i` and
`x_i*` are the entries of `coefficients` and `optimum`; `unit_floor_k` is
`unit_floor`. The numerical relationships are:

```text
U_k     = sum(abs(c_i * x_i*))
C_k     = sum(abs(c_i))
gamma_n = n * epsilon / (1 - n * epsilon)
epsilon_effective = max(solver_tolerance_k, bound_canonicalisation_tolerance)
tau_k   = max(unit_floor_k, epsilon_effective * max(1, U_k), gamma_n * U_k, C_k * epsilon_effective)
objective_k(x) <= objective_k(x*) + tau_k
```

Here `solver_tolerance_k` is the applicable phase tolerance and `objective_k`
is the dot product for the locked objective. Energy balance, inventory, transfer
capacity and settlement identities remain hard constraints. The solver-contract
requirement is “numerical tolerance does not relax physical feasibility”.

The validated ceilings per half-hour are `1.0 GBP`, `0.001 MWh` schedule
deviation and `0.001 MWh` throughput. Recorded reference thresholds are
`1.0 GBP`, `0.01 MWh` and `0.01 MWh` respectively. Classification uses
`max(computed_tolerance, observed_degradation) / validated_ceiling`: up to 10%
is `GO`; above 10% and up to 100% is `GO_WITH_NUMERICAL_WARNING`; above 100%
is `COMPLETED_WITH_NUMERICAL_WARNING`. These thresholds classify numerical
evidence; each declared physical feasibility constraint still applies.
