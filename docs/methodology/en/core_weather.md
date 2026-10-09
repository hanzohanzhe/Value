# Weather and available generation

VALUE calculates each asset's available wind and solar energy from its capacity and representative-point weather. The dispatch fields `available_mw` and `available_mwh` denote available power in MW and period energy in MWh; `capacity_mw` is installed power, `availability` is the weather-derived dimensionless output coefficient, and `period_hours` is the period duration. For each asset and period,

$$
\begin{aligned}
\mathtt{available\_mw}&=\mathtt{capacity\_mw}\times\mathtt{availability},\\
\mathtt{available\_mwh}&=\mathtt{available\_mw}\times\mathtt{period\_hours},\\
\mathtt{period\_hours}&=0.5\ \mathrm{h}.
\end{aligned}
$$

Market clearing accepts generation up to this available-energy limit. Annual expansion uses the technology-average investment profiles or the experimental physical-availability rule specified below.

## Weather sequences and representative-point sampling

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

## Wind conversion and losses

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

## Solar radiation and array-plane conversion

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

## Comparison with observed load factors

The GBP1 representative-point weather calculation can be compared with national load factors from [DUKES Table 6.3](https://www.gov.uk/government/statistics/renewable-sources-of-energy-chapter-6-digest-of-united-kingdom-energy-statistics-dukes). The model values below are unweighted means across representative points, each evaluated over 17,520 half-hours before curtailment. DUKES divides national generation by the mean of installed capacity at the beginning and end of the year and by annual hours. These definitions determine the scope of the comparison.

| Technology | GBP1 corrected | DUKES 2019–2024 mean | DUKES 2020–2024 mean | Corrected / 2020–2024 mean | GBP1 doctoral reproduction |
|---|---|---|---|---|---|
| Onshore wind | 0.4026 | 0.2593 | 0.2582 | 1.56 | 0.4458 |
| Offshore wind | 0.4913 | 0.4016 | 0.4009 | 1.23 | 0.6028 |
| Solar PV | 0.1065 | 0.1033 | 0.1025 | 1.04 | 0.1201 |

The corrected wind values remain above the observed national averages. The calculation combines unadjusted ERA5 wind speeds, one power curve for each wind technology and fixed loss multipliers. DUKES measures realised fleet generation, including the effects of dispatch and the operating fleet's composition. The table provides an external comparison for the specified parameterisation.

The solar calculation uses a climatological radiation series followed by nonlinear decomposition and transposition. For the GBP1 representative points, the calculated diffuse share is approximately 0.63–0.75 and the ratio of array-plane to horizontal irradiation is approximately 1.05–1.10. These quantities describe the adopted climatology and transformation; year-specific simulations require year-specific weather inputs.

## Project locations, asset aggregation and zones

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

## Annual wind and solar capacity limits

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

## Data and implementation

`calendar_mean_solar_2020_2024.nc` and `calendar_mean_wind_2020_2024.nc` provide the R029 calendar climatology. `site_weather` reads representative-point series and applies the selected clock and conversion; `solar_irradiance` calculates array-plane radiation. `value_uk_vre_loss_factors_v1.json` supplies conversion parameters, and `value_uk_vre_cf_disclosure_v1.json` records the load-factor comparison. `doctoral_weather` provides the frozen conversion for the experimental pathway, while `doctoral_weather_mapping` manages locations and mixed weather weights.

`scheme_c_native_psm` aggregates capacity into national market agents, and `staged_psm` divides capacity among zones. Annual limits use the general peak rule in `canonical_psm_data` and `v2_module_definitions`. The experimental net-demand threshold function `thesis96_vre_annual_expansion_cap` is defined in `doctoral_policy`.
