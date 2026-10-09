# Initial data and input processing

VALUE combines demand, weather, assets, planning data and external-market inputs on a common model clock. The source year determines the demand or weather sample; the model year determines asset operation and investment. The data package and methodology profile jointly determine the reading rules.

| Data configuration | Package | Coverage and availability |
|---|---|---|
| VALUE 101 | `value-101-baseline-v1` | Bundled synthetic teaching data for 2025–2026, with 17,520 half-hours per year and a 48-period exercise |
| GBP1 public1 | `value-uk-open-data-pack-v1` | Published GB inputs; eligible for the doctoral reproduction profile |
| GBP1 public2 | `value-uk-open-data-pack-public2` | Revision for the corrected methodology, published with VALUE 0.7.0-alpha.1 ([download](https://value.ac/en/data/)) |
| R029 public2 | `value-uk-calendar-vx-trade001-public2` | Revision for the corrected methodology, published with VALUE 0.7.0-alpha.1 ([download](https://value.ac/en/data/)); study window 2025–2034, 2022 demand and 2020–2024 weather |

The corrected GB studies require the declared columns, source units and time resolutions supplied by the public2 revisions or an eligible user workspace package. R029 public1 (`value-uk-calendar-vx-trade001`) is outside the doctoral reproduction whitelist; its 8,761-value solar investment profile also fails the corrected reader's annual-length requirement. Chapter 3 describes the revised profile. GB 23-zone network studies use the GBP1 public2 research suite, `value-uk-research-suite-v1-public2`, available from the [data page](https://value.ac/en/data/). It supplies the compatible national and spatial inputs for the corrected methodology.

## Temporal resolution and input roles

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

## Declared reading and annual alignment

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

## Demand series and calendar processing

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

## Initial assets and planned projects

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

## Costs and storage parameters

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

## Interconnectors and zonal demand

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

## VALUE 101 synthetic inputs

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

## Data eligibility and user mappings

Package validation separates structural validity, chronology and physical plausibility. Structure determines whether a package can be installed. Chronology checks boundary identity, price currency, local-time demand, known row-order issues, forecast alignment and declared timestamps. Plausibility checks use the ranges in `value_data_plausibility_v1.json`.

The `profile_eligibility` decision combines those findings with the profile's package whitelist. In the corrected methodology, chronology findings for non-workspace packages and plausibility failures for scientific reference packages block preflight. They remain warnings under doctoral reproduction, whose whitelist separately excludes user workspaces and the VALUE 101 network package. Successful package validation is followed by role-specific reading; VRE investment-profile clock requirements are checked at that stage.

User demand mappings declare columns, units and, when provided, timestamps in UTC or Europe/London. Local timestamps are converted row by row to UTC. Declared day/month order resolves dates as DD/MM/YYYY or MM/DD/YYYY; otherwise it is inferred. Unreadable, duplicate, decreasing, gapped or irregular timestamps block submission.

Mapped sequences enter the model in row order from 1 January 00:00 UTC and repeat in each model year. A differing source year generates a notice; the reader preserves row order, weekdays and holidays from the input. Hourly demand identified by 8,760 or 8,784 rows or a 60-minute timestamp interval expands to half-hours after source-unit conversion. Short inputs require confirmation of repetition. A mapped demand total above 1.5 times or below 0.67 times the replaced annual total generates a notice containing both energy totals.

Mapped euro prices use the declared exchange rate and its annual-average, monthly-average or fixed-rate basis. The declared price year is recorded, and a year other than 2025 generates a notice; only the currency conversion is applied.

## Data and implementation

NESO supplies the demand source, DESNZ REPD supplies projects, Copernicus ERA5 single levels supplies weather, and Ember's ENTSO-E compilation supplies boundary prices. `import_scheme_c_1000twh` normalises project data. `series_reader.py` and `data_method` read time series; `interconnector_identity` assigns boundary series; `known_data_objects_v1.json` associates recognised input files with their declarations and row transformations. `data_validation_layers` evaluates package eligibility, `model_clock` defines UTC periods, and `zonal_demand_alignment` distributes national demand among zones.
