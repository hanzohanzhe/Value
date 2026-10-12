# Initial data and input processing

VALUE constructs an electricity-system study from demand, weather, operating assets, planned projects, technology parameters and external-market prices and flow limits. Source years identify the observed samples; the study's start year selects the operating fleet and the subsequent investment calendar. The default `value-corrected` configuration reads the following public2 packages, available from the [data page](https://value.ac/en/data/).

| Study inputs | Package | Contents |
|---|---|---|
| Great Britain, national | `value-uk-open-data-pack-public2` | Demand, representative-point weather, fleet, planning, costs and five external markets |
| Great Britain, 2025–2034 with calendar-mean weather | `value-uk-calendar-vx-trade001-public2` | R029 configuration with 2022 demand and 2020–2024 weather |
| Great Britain, 23 zones | `value-uk-research-suite-v1-public2` | National inputs, zonal demand, asset allocation, corridors and external boundaries |
| VALUE 101 | Synthetic teaching inputs | 2025–2026 studies with a full 17,520-period year and a 48-period exercise; generation rules are given below |

Input roles connect files to physical quantities. The package's `manifest.json` binds each role to its file and declares its column, unit and temporal resolution. The following table gives the R029 filenames and the variables supplied to the calculations.

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

## Model clock and units

The operating year contains 17,520 half-hours on a 365-day UTC calendar. Period zero starts at 00:00 on 1 January; February contains 28 days. Asset capacity is measured in MW, stored energy in MWh, money in GBP and electricity price in GBP/MWh. The `period_start_utc` function assigns each period its calendar time.

Demand enters as power in MW. The default national algorithm passes the values from `read_role` through `_kernel_inputs` to `run_simulation` in MW. The staged and optimisation interfaces use `build_chronology` in `canonical_psm_data` to form period energy: `series["demand.real"].values` and `series["demand.forecast"].values` hold MW, while `demand` and `forecast_demand` hold MWh per period. With zero-based period index `t`,

$$
\begin{aligned}
\mathtt{demand}[t]&=\mathtt{series}[\text{demand.real}].\mathtt{values}[t]\times\mathtt{period\_hours},\\
\mathtt{forecast\_demand}[t]&=\mathtt{series}[\text{demand.forecast}].\mathtt{values}[t]\times\mathtt{period\_hours},\\
\mathtt{period\_hours}&=0.5\ \mathrm{h},\qquad \mathtt{periods}=365\times24\times2=17{,}520.
\end{aligned}
$$

Annual demand energy is the sum of `demand`. A user-supplied column expressed in MWh per source period is divided by that period's duration in hours to obtain MW before half-hour alignment. VALUE 101 writes its synthetic power values under the column name `mwh`; those values enter the same MW-to-MWh calculation above.

## Column selection, missing values and annual alignment

Time-series loading follows the declared column and header. `read_series` uses `csv_column` with `csv_header=true`; each cell in that column must be numeric and finite. An empty sequence, a missing named column or an invalid numeric cell terminates loading. For a file with an inferred column, an integer sequence of at least three values increasing by one requires an explicit column declaration.

Header and column inference follow the contents of the file. A declared `csv_header` takes precedence. Otherwise the first row is a header when it has at least one populated cell and every populated cell is non-numeric. With a missing `csv_column`, strict reading selects the sole wholly numeric column; multiple numeric columns require an explicit selection. The user-workspace reader selects the first wholly numeric column in an ambiguous file. Declaring the column fixes this choice independently of column order.

Hourly inputs are expanded before the requested run window is selected. `align_clock` reads `interval_minutes=60` as two copies of each source value and `interval_minutes=30` as one value per half-hour. With an absent interval declaration, lengths of 8,760 and 8,784 identify hourly years. Other declared resolutions terminate loading. The hourly conversion is applied once.

Leap-year demand retains its annual energy on the 365-day model clock. After hourly expansion, a 17,568-period year loses the 48 values beginning at `(31 + 28) * 48`, corresponding to 29 February. In `normalize_half_hour_year`, `numbers` contains the source values and `reduced` the retained values. For a positive retained sum,

$$
\begin{aligned}
\mathtt{original}&=\sum\mathtt{numbers},\qquad \mathtt{retained}=\sum\mathtt{reduced},\\
\mathtt{scale}&=\mathtt{original}/\mathtt{retained},\\
\mathtt{normalize\_half\_hour\_year}(\mathtt{values})&=\bigl(\mathtt{item}\times\mathtt{scale}\ :\ \mathtt{item}\in\mathtt{reduced}\bigr).
\end{aligned}
$$

An all-zero demand series remains zero. A zero retained sum with a positive original sum terminates conversion. Other time-series roles remove the same 48 values and retain the remaining values. An explicit `leap_policy="keep"` retains the source calendar and selects the required leading periods.

The run consumes the first `periods` values of a sufficiently long aligned sequence. A shorter series repeats from its beginning when `cyclic=true`, or when its role supplies the cycling convention; external-market flows and prices have this convention. Strict package reading requires that declaration for shorter demand or investment sequences. User-workspace reading fills a short series by repetition. These rules determine the numerical input for a partial-year or full-year run.

The following sequence produces the aligned values. `path` is the bound file, `spec` contains its declarations, `policy.strictness` selects strict package reading or user-workspace reading, and `cyclic` is the role's repetition default.

```text
read = read_series(path, spec, mode="declared-v2", strictness=policy.strictness)
values = align_clock(read.values, periods, spec, mode="declared-v2",
                     strictness=policy.strictness, cyclic_default=cyclic)
return values
```

## Observed demand and missing settlement periods

The supplied GB demand shape uses NESO's 2022 half-hour actual demand and day-ahead forecast. Each of `actual_mw.csv` and `forecast_mw.csv` contains 17,520 values after UTC preprocessing. Each subsequent model year uses the same aligned 2022 actual-demand and forecast-demand sequences. Their power and energy totals are

| Series | Minimum power MW | Maximum power MW | Mean power MW | Annual energy MWh |
|---|---:|---:|---:|---:|
| Actual demand | 15,080 | 46,042 | 26,587.967637 | 232,910,596.5 |
| Day-ahead forecast | 14,240 | 46,760 | 26,611.131963 | 233,113,516 |

Demand preprocessing resolves settlement records before interpolation. Rows with the same settlement date and settlement period are ordered by publication time; the latest publication is retained, with the final row breaking a tie. UK local settlement times are then placed on the UTC half-hour axis. The 17,518 source rows yield 17,516 distinct periods, leaving four missing half-hours.

Missing demand periods are filled by linear interpolation between their adjacent known values. One missing period receives the mean of the endpoints. Two consecutive missing periods receive one-third and two-thirds of the endpoint difference added to the preceding value. The four replacements in the 2022 input occur on 30 October:

| UTC time | Forecast demand MW | Actual demand MW |
|---|---:|---:|
| 2022-10-30 09:00 | 22,638.666667 | 24,649 |
| 2022-10-30 09:30 | 22,899.333333 | 24,727 |
| 2022-10-30 23:00 | 19,063.333333 | 20,494.666667 |
| 2022-10-30 23:30 | 19,086.666667 | 19,689.333333 |

User demand timestamps are converted to UTC before the same model-year alignment. The mapping accepts UTC or Europe/London and a declared DD/MM/YYYY or MM/DD/YYYY date order. Timestamps must identify a strictly increasing sequence with a regular 30- or 60-minute step; duplicates, unresolved dates and gaps terminate mapping. The resulting row order is placed from 1 January 00:00 UTC in each model year, retaining the input's sequence of weekday and holiday effects.

## Initial operating assets

The initial renewable and battery stock is selected from the DESNZ Renewable Energy Planning Database, second quarter 2025, released in July. Its 12,977 project rows and 53 source fields yield 10,653 rows and 14 fields after technology and positive-capacity filtering. `normalize_repd` retains onshore wind, offshore wind, solar, battery and gas technologies; `capacity_mw`, `x_coordinate` and `y_coordinate` are converted to numbers, with failed conversions stored as missing values.

The normalised project table retains the information needed for date and location selection. Its fields are `project_id`, `site_name`, `technology`, `technology_source`, `capacity_mw`, `development_status`, `region`, `country`, `planning_application_submitted`, `planning_permission_granted`, `under_construction`, `operational`, `x_coordinate` and `y_coordinate`. Date strings remain available for the asset and planning readers to parse.

Operating wind, solar and battery capacity requires `Operational` status, a readable operational date at or before the study's start year, and positive installed MW. `build_repd_operational_snapshot` parses the date with day-first order and skips records with missing dates or invalid capacity. Solar and onshore projects first use the region-to-city mapping in Chapter 3. Remaining projects use geographic coordinates and the nearest representative of their technology; OSGB coordinates are converted from EPSG:27700 to EPSG:4326 when required. A project with neither a regional assignment nor usable coordinates contributes zero to the mapped initial wind or solar stock.

Initial battery MW is distributed among the storage entries other than pumped hydro. For each entry, `weighted[asset_id]` equals the larger of its `pool_limit` and 1; `weight_total` is their sum. `native_initial_state` assigns `capacity = operational_storage_mw * weighted[asset_id] / weight_total`. Its energy is `capacity * duration`, where `duration` comes from the technology catalogue. The 2025 pumped-hydro stock is specified separately as 2,828 MW and 26,700 MWh.

The R029 2025 stock contains the capacities below. Its aggregated nuclear availability is 0.723, and run-of-river generation uses 0.3487 multiplied by the seasonal shape in Chapter 5. GBP1 selects its nuclear units through the station schedule, with the station availability and retirement rules also defined in Chapter 5.

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

## Planning inputs

Project development uses technology- and region-specific success rates and technology-specific stage durations. `regional_technology_success_rates.csv` contains 46 records; `planning_timelines.json` supplies durations in months. `development_stage_timelines`, `repd_status_to_timeline` and `success_rates` are stored in the initial state and supply both existing planned projects and new investment proposals.

The input medians distinguish development from construction. Status mappings select the relevant remaining stages. The following preprocessing constructs the initial project list; Chapter 6 advances these projects and admits new investment proposals each year.

| Technology | Median development months | Median construction months |
|---|---:|---:|
| Solar | 27.8 | 4.9 |
| Onshore wind | 62.5 | 15.0 |
| Offshore wind | 110.1 | 32.2 |
| Battery | 31.3 | 10.1 |


Initial planned projects are selected by capacity, development status and recorded progress. `native_initial_state` uses the controls below; the default `planning.success_mode="expected"` is read as `success_mode="expected_capacity"`. `year` is the study's start year and `capacity` is the source project's MW.

| Parameter | Default | Use |
|---|---|---|
| `planning.minimum_project_size_mw` | 1 MW | Smallest positive project admitted |
| `planning.include_uncertain_projects` | `true` | Admit application, appeal and revised statuses |
| `planning.zombie_filter_enabled` | `true` | Apply status, progress and construction-overrun filters |
| `planning.zombie_status_stale_year` | 2015 | Latest-progress cutoff for uncertain projects |
| `planning.construction_grace_years` | 2 years | Added to the estimated construction completion year |
| `planning.max_completion_year` | 2040 | Latest admitted completion year |
| `planning.timeline_statistic` | `median` | Select median or mean stage durations |
| `planning.defer_spread_years` | 3 years | Maximum added delay for inferred completion dates |
| `planning.random_seed` | 0 | Input to project-specific success draws |
| `planning.repd_battery_assignment` | `value_proportional_split` | Allocate generic battery capacity among four storage technologies |

A replacement application supersedes its older project record. The preprocessing reads `Ref ID` and `Are they re-applying (New REPD Ref)` in the raw REPD table and excludes the old record when the replacement is a different, non-empty identifier present in that table. It also excludes capacity below `minimum_size` and non-positive or unparseable capacity.

Development-status filtering acts on stripped, lower-case labels. `terminal_statuses` always excludes `operational`, `abandoned`, `planning permission refused` and `application withdrawn`. With `zombie_filter=true`, the additional excluded labels are `application refused`, `appeal refused`, `appeal withdrawn`, `decommissioned`, `application expired` and `finished`. Setting `include_uncertain=false` retains only `under construction`, `awaiting construction` and `planning permission granted`.

The recorded progress cutoff applies to `application submitted`, `appeal lodged` and `revised`. `_date_year` extracts the first four-digit year beginning with 19 or 20 from each date string; a missing year yields `None`. `latest_progress_year` takes the latest known year across `planning_application_submitted`, `planning_permission_granted`, `under_construction` and `operational`. With the progress filter enabled, an uncertain project is excluded when this year is at or before `zombie_stale_year`; a missing progress year passes this particular filter.

The completion year first uses a recorded future year and otherwise uses the remaining stage duration. `timeline_months(source_technology, status)` selects `timeline_type` from `repd_status_to_timeline`, replaces its mean or median suffix with `timeline_statistic`, and reads the selected technology entry in `development_stage_timelines`. A missing status mapping selects `total_median` by default; a missing stage entry uses `development_timelines`, with a final fallback of 12 months. Storage components use the battery duration table.

The inferred completion date adds a deterministic delay of zero to `defer_spread_years` whole years. The following sequence uses the source `project_id` to calculate that delay; an existing future date bypasses the duration and delay calculations.

```text
completion = next((candidate for candidate in (
    _date_year(row.get("operational")),
    _date_year(row.get("under_construction")),
) if candidate is not None and candidate > year), None)
if completion is None:
    months = timeline_months(source_technology, status)
    completion = year + max(1, int(math.ceil(months / 12.0)))
    if defer_spread_years > 0:
        completion += int(
            hashlib.sha256(project_id.encode("utf-8")).hexdigest()[:8], 16
        ) % (defer_spread_years + 1)
```

Construction status receives a separate elapsed-time check. For `under construction` with a known `construction_year`, preprocessing forms `construction_end = construction_year + max(1, math.ceil(timeline_months(source_technology, status) / 12)) + construction_grace`. With `zombie_filter=true`, a value earlier than `year` excludes the project. A `completion` later than `maximum_completion` also excludes the project.

Initial project success uses a technology–region lookup. `_planning_probability` reads `technology`, `region` and `success_rate`, clamps each readable rate to [0,1] and skips unreadable rates. A missing required column yields an empty rate table. The lookup first uses the project's lower-case region, then the technology's `gb` entry, then 1.0. The calculation below gives `probability`, the dimensionless draw `draw`, and the admitted capacity; all components of one physical battery project share its draw.

```text
probability_key = "battery" if source_technology == "battery" else _technology(source_technology)
probability = success_rates.get(
    (probability_key, region.strip().lower()),
    success_rates.get((probability_key, "gb"), 1.0),
)
draw = int(
    hashlib.sha256(f"{random_seed}:{project_id}".encode("utf-8")).hexdigest()[:13], 16
) / float(16 ** 13 - 1)
realised_failure = success_mode == "seeded_stochastic" and draw > probability
components = typed_project_components(project_id, source_technology, capacity)
for component_id, technology, declared_component_capacity, assignment_method in components:
    effective_capacity = (
        declared_component_capacity * probability
        if success_mode == "expected_capacity" else declared_component_capacity
    )
```

Generic battery projects are split before their success-adjusted capacities are recorded. `typed_project_components` uses `scheme_c_storage_weights`, formed from the same positive fleet weights used for initial battery stock, to allocate source MW among `1c_battery`, `0.5c_battery`, `0.25c_battery` and `hydrogen_battery`. Each `declared_component_capacity` equals the source capacity times its weight divided by total weight. The settings `all_1c`, `all_0.5c` and `all_0.25c` assign the full capacity to one technology; `exclude_untyped` removes generic battery projects from the initial list. Projects with a specified technology retain that technology and capacity.

The expected-capacity mode multiplies each component's declared MW by its success probability. The stochastic setting `planning.success_mode="stochastic"`, read as `seeded_stochastic`, retains full declared MW and sets `phase="failed"` and `outcome="failed_planning"` when `draw > probability`; equality passes. Successful projects and expected-capacity projects receive `phase="active"` and `outcome="active"`. Storage energy is `effective_capacity * duration_hours` in MWh. `PlanningProject` stores these values with `expected_completion_year=completion`, the start year, status, technology and region for Chapter 6's annual progression.

New investment proposals use the success-rate lookup in `endogenous_planning._success_rate`. It selects the regional rate, then the technology's regional mean, then 0.75. Chapter 6 defines proposal capacity and the subsequent planning process.

## Capital costs and storage parameters

Capital costs, target returns and payback periods are supplied as distinct financial inputs. The R029 configuration reads `capital_costs.json` and `model_parameters.json`; the capital-cost material draws on BEIS Electricity Generation Costs 2020 and Arup. The table gives the financial parameters assigned to the initial assets. Annual capital recovery uses `capital_discount_rate=0.05`; the investment calculations and effective decision thresholds are defined in Chapter 6.

| Technology | Capital cost GBP/MW | `preferred_rate` | Target payback years |
|---|---:|---:|---:|
| Solar | 659,000 | 0.076 | 25 |
| Onshore wind | 1,588,000 | 0.076 | 30 |
| Offshore wind | 3,976,000 | 0.089 | 30 |
| CCGT / OCGT | 2,400,000 | 0.089 | 25 |
| Biomass and waste | 1,500,000 | 0.089 | 25 |
| 1C battery | 330,000 | 0.0825 | 10 |
| 0.5C battery | 350,000 | 0.165 | 10 |
| 0.25C battery | 415,000 | 0.0825 | 10 |
| Hydrogen storage | 600,000 | 0.01375 | 25 (default) |

Storage energy losses follow separate charging and discharging efficiencies. Round-trip efficiency is `charge_efficiency * discharge_efficiency`, giving \(0.98^2=0.9604\) for the 0.5C battery. The catalogue also supplies duration, economic lifetime and `maximum_cycles`. These values enter the storage-state and cost equations in Chapters 4 and 6; initial stored energy is specified with the operating algorithm in Chapter 4.

| Technology | Catalogue duration h | Charging efficiency | Discharging efficiency | Catalogue economic life years | Cycle parameter `maximum_cycles` |
|---|---:|---:|---:|---:|---:|
| Pumped hydro | 4 | 0.87 | 0.87 | 30 | 1,000,000 |
| 1C battery | 1 | 0.81 | 0.81 | 15 | 3,000 |
| 0.5C battery | 2 | 0.98 | 0.98 | 15 | 5,000 |
| 0.25C battery | 4 | 0.81 | 0.81 | 15 | 8,000 |
| Hydrogen storage | 250 | 0.57 | 0.57 | 10 | 1,000 |

Source price years remain attached to the numerical inputs. Storage costs and policy budgets are expressed in 2025 GBP; BEIS capital-cost inputs retain 2020 values, the European electricity samples retain their 2022 or 2021 values after currency conversion, and nuclear-policy entries carry their declared 2015 or 2024 price years. Restart costs use the conversion in Chapter 5. The currency reader converts euros to pounds using `eur_per_gbp`.

Annual policy spending uses the schedules in `mechansim cost.xlsx`. The workbook combines NESO Capacity Market and balancing-cost series, Ofgem RO/FIT/REGO material and LCCC CfD data. Chapter 6 specifies how these inputs enter annual accounts.

## External markets and zonal demand

External electricity exchange is limited by a time-varying envelope and priced by the corresponding foreign market. R029 supplies 17,520-row files for France, Belgium, the Netherlands, Norway and Ireland. Each file provides `flow_mw` and `price_gbp_per_mwh` alongside its period and source timestamps. NESO line names associate `NEMO_FLOW` with Belgium, `BRITNED_FLOW` with the Netherlands and `NSL_FLOW` with Norway.

Foreign prices use Ember's compilation of ENTSO-E day-ahead prices. France, Belgium, the Netherlands and Norway use 2022; Ireland uses 2021. An hourly EUR/MWh value is divided by 1.1 EUR/GBP and assigned to both receiving half-hours. Negative prices retain their sign. R029 stores the converted GBP/MWh values; a GBP1 file such as `Belgium_price.csv` supplies `Price (EUR/MWhe)` and receives the same conversion through `read_series`.

The positive and negative values of `flow_mw` define import and export capacity, respectively. Multiplication by `period_hours` yields signed period energy `raw_availability`, from which the two non-negative envelopes are calculated:

$$
\begin{aligned}
\mathtt{raw\_availability}[t]&=\mathtt{flow\_mw}[t]\times\mathtt{period\_hours},\\
\mathtt{import\_energy}[t]&=\max(\mathtt{raw\_availability}[t],0),\\
\mathtt{export\_energy}[t]&=\max(-\mathtt{raw\_availability}[t],0).
\end{aligned}
$$

The default national market offers imports in day-ahead clearing. Chapter 5 defines their use during clearing and balancing, and Chapter 7 applies the external-boundary capacities in the zonal model. The R029 envelope ranges and mean prices are

| Boundary | Flow range MW | Price year | Mean price GBP/MWh |
|---|---:|---:|---:|
| Belgium | −1,022 to 1,020 | 2022 | 222.292608 |
| France | −3,091 to 2,997 | 2022 | 250.789325 |
| Ireland | −987 to 998 | 2021 | 123.937076 |
| Netherlands | −1,076 to 1,062 | 2022 | 219.917959 |
| Norway | −1,263 to 1,399 | 2022 | 126.503575 |

Zonal demand uses the national study's total and the network input's spatial shares. `align_zonal_demand` matches network and study `period_ids`, which must be unique and have corresponding records. Actual and forecast input energy must be finite, non-negative and equal in length to the period list. In `scenario_scaled_zonal_shares`, `output_real` holds the study's actual MWh and `network_national` the network's national MWh at `index`:

$$
\begin{aligned}
\mathtt{scale}&=\frac{\mathtt{output\_real}[\mathtt{index}]}{\mathtt{network\_national}},\\
\mathtt{value}&=\mathtt{network\_demand\_mwh\_by\_zone}[\mathtt{zone\_id}][\mathtt{index}]\times\mathtt{scale}.
\end{aligned}
$$

The final zone receives the remaining national energy after the preceding zones have been assigned. If both national inputs equal zero, `scale=1.0`; positive study demand with zero network national demand terminates alignment. The following sequence gives the complete allocation, with `zone_ids` retaining the network's declared order:

```text
aligned = {zone_id: [] for zone_id in zone_ids}
for index, period_id in enumerate(periods):
    network_national = network_national_mwh[index]
    if network_national == 0.0 and output_real[index] == 0.0:
        scale = 1.0
    elif network_national == 0.0:
        raise ValueError("Zonal demand requires positive network national demand")
    else:
        scale = output_real[index] / network_national
    remaining = output_real[index]
    for zone_id in zone_ids[:-1]:
        value = network_demand_mwh_by_zone[zone_id][index] * scale
        aligned[zone_id].append(value)
        remaining -= value
    aligned[zone_ids[-1]].append(remaining)
```

The alternative `network_pack_absolute_demand` sets `output_real` to `network_national_mwh` and `scale=1.0`. Its forecast is `output_real[index] * forecast[index] / real[index]`. When `real[index]` is zero, both `forecast[index]` and `output_real[index]` must also be zero and the resulting forecast is zero. The same final-zone remainder rule preserves the national energy total.

## VALUE 101 synthetic inputs

VALUE 101 supplies deterministic demand, weather and investment profiles. `_demand` returns MW for zero-based half-hour index `period`; `day` and `hour` identify its day and hour. `weekday` equals 1 when `day % 7 < 5` and 0.92 otherwise. `teaching_peak` is 30 MW at `period % 48 == 31` on days 0 and 182, and zero elsewhere:

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

The day-ahead forecast is `_demand(period) + balancing_margin`, rounded to six decimal places. `balancing_margin` is 12 MW at `period % 48 == 30` on days 0 and 182, and zero elsewhere. The 12 MW addition precedes each of the two actual demand peaks by half an hour.

The solar investment coefficient multiplies daylight and seasonal terms. `_solar_profile` returns zero for `hour < 6` or `hour > 18`. During the daylight window it uses the same `day` and `hour` definitions:

$$
\begin{aligned}
\mathtt{daylight}&=\sin((\mathtt{hour}-6)\pi/12),\\
\mathtt{season}&=0.58+0.42\sin^2((\mathtt{day}-80)2\pi/365),\\
\mathtt{\_solar\_profile}(\mathtt{period})&=\operatorname{round}\bigl[\max(0,\min(\mathtt{daylight}\times\mathtt{season},1)),\ 6\bigr].
\end{aligned}
$$

The wind investment coefficient combines daily, 29-day and annual components. `_wind_profile` limits the result to 0.08–0.92 and rounds it to six decimal places:

$$
\begin{aligned}
\mathtt{within\_day}&=\mathtt{period}\bmod48,\\
\mathtt{value}={}&0.42+0.13\sin((\mathtt{within\_day}+5)2\pi/48)\\
&+0.12\sin((\mathtt{day}+17)2\pi/29)\\
&+0.08\cos((\mathtt{day}+31)2\pi/365),\\
\mathtt{\_wind\_profile}(\mathtt{period})&=\operatorname{round}\bigl[\max(0.08,\min(\mathtt{value},0.92)),\ 6\bigr].
\end{aligned}
$$

The offshore investment coefficient is 1.08 times `_wind_profile(period)`, capped at 1 and rounded to six decimal places. Solar, onshore and offshore arrays are bound to `profiles.vre_solar`, `profiles.vre_onshore` and `profiles.vre_offshore`.

The synthetic weather grid has one point at 52°N, 0°E and 8,760 hourly samples. Here `hour` is the zero-based hourly index through the year; `hourly_solar` is accumulated radiation in J/m² and `hourly_wind` is wind speed in m/s:

$$
\begin{aligned}
\mathtt{hourly\_solar}[\mathtt{hour}]&=\mathtt{\_solar\_profile}(2\mathtt{hour})\times3{,}600{,}000,\\
\mathtt{hourly\_wind}[\mathtt{hour}]&=7+2\sin((\mathtt{hour}+3)2\pi/24)\\
&\quad+1.2\sin((\lfloor\mathtt{hour}/24\rfloor+17)2\pi/29).
\end{aligned}
$$

Dispatch converts this wind speed through the wind curve and this solar series through the instantaneous-input rule in Chapter 3. Investment uses the coefficients above. The French boundary supplies a constant 12 MW import envelope and 82 GBP/MWh price; the other four boundaries have zero exchange capacity and a price input of 200 GBP/MWh. `build_value_101_packs` writes these sequences into the teaching inputs.
