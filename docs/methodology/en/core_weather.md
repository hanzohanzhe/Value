# Weather and available generation

Wind and solar availability is calculated for each asset from its installed capacity and the weather assigned to its representative location. `capacity_mw` is installed MW, `availability` is the dimensionless weather conversion coefficient, `available_mw` is available power, and `available_mwh` is energy available in one operating period:

$$
\begin{aligned}
\mathtt{available\_mw}&=\mathtt{capacity\_mw}\times\mathtt{availability},\\
\mathtt{available\_mwh}&=\mathtt{available\_mw}\times\mathtt{period\_hours},\\
\mathtt{period\_hours}&=0.5\ \mathrm{h}.
\end{aligned}
$$

The weather calculation produces an upper supply limit for clearing. Dispatch determines the accepted energy in Chapters 4, 5 and 7. Annual investment uses the technology-average profiles described at the end of this chapter and the capacity limits in Chapter 6.

## Weather inputs and spatial sampling

R029 represents each calendar hour by the mean of the 2020–2024 ERA5 observations for that month, day and hour. The source contains 43,848 hourly records. Removing the two leap days removes 48 hours, leaving five observations for each of 8,760 retained calendar hours. The resulting annual sequence is reused in each model year.

Wind speed is averaged after calculation of the vector magnitude at each source hour. The preprocessing first takes the square root of `u100` squared plus `v100` squared, then forms its calendar mean as `wind_speed`; it also retains `u100` and `v100`. The solar file contains accumulated downward horizontal radiation `ssrd`. The R029 files are `calendar_mean_wind_2020_2024.nc` and `calendar_mean_solar_2020_2024.nc`.

The weather grid covers Great Britain and adjacent seas at 0.25° resolution. The files have the following coordinate extents and array sizes:

| Input | Latitude range | Longitude range | Latitude × longitude × day × hour |
|---|---|---|---|
| Solar radiation | 45°–65°N | 14°W–4°E | 81 × 73 × 365 × 24 |
| 100 m wind | 46°–65°N | 14°W–5°E | 77 × 77 × 365 × 24 |

A representative site receives the nearest grid latitude and longitude. In `point_series`, site coordinates `latitude` and `longitude` and grid arrays `lats` and `lons` are in degrees. `lat_index` and `lon_index` select the smallest absolute coordinate differences; a tie selects the first grid-array entry:

$$
\begin{aligned}
\mathtt{lat\_index}&=\operatorname*{arg\,min}_{j}|\mathtt{lats}[j]-\mathtt{latitude}|,\\
\mathtt{lon\_index}&=\operatorname*{arg\,min}_{k}|\mathtt{lons}[k]-\mathtt{longitude}|.
\end{aligned}
$$

Spatial extraction accepts latitude–longitude–day–hour arrays and time–latitude–longitude arrays. The selected point is flattened in source order to an hourly sequence. An empty sequence, masked value, non-finite value or other array layout terminates weather loading. Each site's `lat` and `lon` are supplied by `fleet.locations`; `representative_sites` matches those locations to the generator names in `fleet.json`.

## Hourly weather and half-hour dispatch

Weather values are assigned according to the physical meaning of their timestamps. The default weather method has `clock="v2"`. A binding's `time_convention` takes precedence; otherwise `GRIB_stepType="accum"` denotes an accumulation ending at the timestamp, and other fields use the instantaneous convention. `hour_index` maps zero-based half-hour index `t` to source index `index`, wrapping after `hours` source values:

$$
\mathtt{index}[t]=\begin{cases}
(\lfloor t/2\rfloor+1)\bmod\mathtt{hours},&\text{accumulation\_end\_of\_hour},\\
\lfloor(t+1)/2\rfloor\bmod\mathtt{hours},&\text{instantaneous}.
\end{cases}
$$

An hourly accumulation ending at 01:00 supplies the periods beginning at 00:00 and 00:30. The instantaneous rule assigns the sample at 00:00 to the period beginning at 00:00, and the sample at 01:00 to the periods beginning at 00:30 and 01:00. Solar geometry is evaluated at each receiving period's midpoint.

The R029 calendar-mean files declare instantaneous inputs, so they use the second row of the index rule. The supported `clock="v1"` setting instead uses `index = (t // 2) % hours`: each source value serves two consecutive half-hours. These index rules apply to the declared source order, including the wrap from the final source hour to the first.

## Wind power curve and losses

Wind availability follows a cut-in speed of 3 m/s, cubic growth to rated output, constant rated output and a cut-out limit. `hourly_unit_cf` reads `wind_speed` when that variable is present; otherwise it forms the magnitude from `u100` and `v100`. `wind_unit_output` uses a 20-unit output scale and its result is divided by 20 to obtain the dimensionless hourly coefficient `hourly`. For speed `speed`, rated speed `rated` and cut-out speed `cut_out`, all in m/s,

$$
\mathtt{wind\_unit\_output}(\mathtt{speed})=\begin{cases}
0,&\mathtt{speed}<3\ \text{or}\ \mathtt{speed}>\mathtt{cut\_out},\\
20\dfrac{\mathtt{speed}^3-27}{\mathtt{rated}^3-27},&3\le\mathtt{speed}<\mathtt{rated},\\
20,&\mathtt{rated}\le\mathtt{speed}\le\mathtt{cut\_out}.
\end{cases}
$$

Onshore wind uses `rated=9.7` and `cut_out=25`; offshore wind uses `rated=10.5` and `cut_out=30`. Output equals the rated value at the cut-out speed and falls to zero above it. The cubic segment is bounded to the 0–20 range before conversion to `hourly`.

The delivered wind coefficient multiplies the assigned `hourly[index]` by the product of wake, energy-availability and electrical factors. `method.multiplier(technology)` reads the following values from `value_uk_vre_loss_factors_v1.json` when `loss_factors=true`, the default setting:

| Technology | Wake factor | Energy-availability factor | Electrical factor | `multiplier` |
|---|---|---|---|---|
| Onshore wind | 0.95 | 0.97 | 0.98 | 0.90307 |
| Offshore wind | 0.88 | 0.945 | 0.98 | 0.814968 |

At 8 m/s the onshore curve gives 0.5476061707. Multiplication by 0.90307 gives approximately 0.49453, corresponding to 49.453 MW of available power from 100 MW of installed capacity. The supported setting `loss_factors=false` sets `multiplier=1.0` and uses the curve output directly.

## Horizontal radiation and solar conversion

Solar conversion first expresses each source-hour radiation value as irradiance. `hourly_unit_cf` reads `ssrd` as `raw` in J/m² and returns `hourly` in kW/m². The input filter and unit conversion are

$$
\mathtt{hourly}=\begin{cases}
\mathtt{raw}/3{,}600{,}000,&3{,}600<\mathtt{raw}\le36{,}000{,}000,\\
0,&\text{otherwise}.
\end{cases}
$$

The default solar method uses `plane_of_array=true` and a performance ratio of 0.83. Array-plane conversion applies when `clock="v2"` and `time_convention="accumulation_end_of_hour"`; it evaluates horizontal irradiance on a south-facing tilted surface at each half-hour midpoint. Instantaneous sources, including R029 and VALUE 101, use horizontal irradiance multiplied by 0.83. With `plane_of_array=false`, all sources use that horizontal calculation. `loss_factors=false` replaces the performance ratio by 1.0.

Array tilt is a function of site latitude. The default `tilt_rule="jacobson-jadhav-2018"` evaluates the 0°–65°N polynomial of [Jacobson and Jadhav (2018), Solar Energy 169, 55–66](https://web.stanford.edu/group/efmh/jacobson/Articles/I/TiltAngles.pdf). In `optimal_tilt_jacobson_jadhav`, `phi` is latitude in degrees north; the returned degrees become `tilt` in `plane_of_array`:

$$
\mathtt{tilt}=1.3793+\mathtt{phi}\times\bigl[1.2011+\mathtt{phi}\times(-0.014404+0.000080509\mathtt{phi})\bigr].
$$

The tilt parameter also supports `tilt_rule="site_latitude"`, giving the absolute latitude in degrees, and `tilt_rule="fixed"`, using `fixed_tilt_deg` in [0,90]. The radiation plane faces south under all three rules. `PlaneOfArrayParameters` supplies `albedo=0.2`, `solar_constant_w_m2=1361` and `max_zenith_deg=87`. Supported parameter ranges are [0,1] for albedo, 1,300–1,400 W/m² for the solar constant and [80,90) degrees for the zenith threshold.

## Solar geometry

Solar geometry follows the UTC midpoint of the operating period. `period_clock` returns the calendar day `day_of_year` and hour `utc_hours`; `day_angle` calculates the annual angle `g` in radians. For zero-based period `t`,

$$
\begin{aligned}
\mathtt{day\_of\_year}&=(\lfloor t/48\rfloor\bmod365)+1,\\
\mathtt{utc\_hours}&=(t\bmod48)/2+0.25,\\
\mathtt{g}&=2\pi(\mathtt{day\_of\_year}-1)/365.
\end{aligned}
$$

Declination and orbital corrections use the following coefficients in `declination`, `equation_of_time_minutes` and `eccentricity_factor`. The resulting `decl` is in radians, the time correction is in minutes and the distance factor is dimensionless:

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

Longitude and the time correction give local solar time and hour angle. `longitude_deg` is positive eastward, `solar_time` is in hours and `omega` is in radians. `incidence_cosines` converts latitude and tilt to radians as `phi` and `beta`, returning `cos_z` and `cos_theta` for the zenith and incidence angles:

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

## Diffuse radiation and array-plane irradiance

The horizontal irradiance is decomposed into diffuse and beam components. `plane_of_array` sets `ghi` to the non-negative part of `ghi_kw_m2`, in kW/m², and calculates `extraterrestrial_normal` as `parameters.solar_constant_w_m2 / 1000.0 * eccentricity_factor(day_of_year)`; the default multiplier is 1.361 kW/m². For positive `ghi` and zenith below 87°, the clearness index is

$$
\mathtt{kt}=\min\left(1,\max\left(0,\frac{\mathtt{ghi}}{\mathtt{extraterrestrial\_normal}\times\mathtt{cos\_z}}\right)\right),
$$

The diffuse fraction follows the hourly relation of [Erbs, Klein and Duffie (1982), Solar Energy 28(4), 293–302](https://www.sciencedirect.com/science/article/pii/0038092X82903024). The coefficient `kd` depends on the dimensionless clearness index `kt`; `middle` is the polynomial value for its central interval:

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

The [Hay–Davies (1980) transposition](https://pvlib-python.readthedocs.io/en/stable/reference/generated/pvlib.irradiance.haydavies.html) combines beam, sky-diffuse and ground-reflected irradiance. `dhi`, `bhi` and `dni` denote diffuse horizontal, beam horizontal and direct normal irradiance in kW/m². `anisotropy`, `beam_ratio`, `sky_view` and `ground_view` are dimensionless; the default `albedo` is 0.2. The array-plane irradiance `poa` is

$$
\begin{aligned}
\mathtt{dhi}&=\mathtt{kd}\times\mathtt{ghi},\qquad \mathtt{bhi}=\mathtt{ghi}-\mathtt{dhi},\\
\mathtt{dni}&=\mathtt{bhi}/\mathtt{cos\_z},\\
\mathtt{anisotropy}&=\min(1,\max(0,\mathtt{dni}/\mathtt{extraterrestrial\_normal})),\\
\mathtt{beam\_ratio}&=\max(\mathtt{cos\_theta},0)/\mathtt{cos\_z},\\
\mathtt{cos\_beta}&=\cos(\pi\mathtt{tilt}/180),\\
\mathtt{sky\_view}&=(1+\mathtt{cos\_beta})/2,\\
\mathtt{ground\_view}&=(1-\mathtt{cos\_beta})/2,\\
\mathtt{beam}&=\mathtt{bhi}\times\mathtt{beam\_ratio},\\
\mathtt{sky\_diffuse}&=\mathtt{dhi}\times\bigl[\mathtt{anisotropy}\times\mathtt{beam\_ratio}\\
&\qquad +(1-\mathtt{anisotropy})\times\mathtt{sky\_view}\bigr],\\
\mathtt{ground}&=\mathtt{ghi}\times\mathtt{albedo}\times\mathtt{ground\_view},\\
\mathtt{poa}&=\mathtt{beam}+\mathtt{sky\_diffuse}+\mathtt{ground}.
\end{aligned}
$$

Periods with zenith at or above 87° or with zero `ghi` have `kt=0`, `kd=1`, `dhi=ghi`, `bhi=0`, `dni=0`, `anisotropy=0` and `beam_ratio=0`. Their `poa` retains the diffuse and ground-reflected terms. The selected `max_zenith_deg` replaces 87° in this condition when its parameter is changed.

Array-plane irradiance is converted to generation by the performance ratio and a coefficient ceiling of 1. Under the default parameters, `site_cf_by_source` returns the dimensionless coefficient `values` as

$$
\mathtt{values}=\min(0.83\mathtt{poa},1).
$$

The coefficient ceiling is applied after the array-plane step. Horizontal conversion applies the performance ratio to `hourly[index]` directly. The following algorithm covers wind, instantaneous solar and accumulated solar. `ds` is the opened NetCDF input, `binding` declares its time convention, `periods` is the requested number of half-hours, and `method` contains `clock`, `loss_factors` and `plane_of_array`:

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
    values = np.minimum(values, 1.0)
return values
```

## Project locations and weather mixtures

Assets obtain their representative weather from technology and location. The GB template lists 11 solar and 11 onshore points and 21 offshore point names; the R029 2025 stock has 11 solar, 11 onshore and 18 offshore assets with positive capacity. Operating stock is mapped during the initial selection in Chapter 2. Planned projects receive a representative point before commissioning.

A planned project's explicit location takes precedence. `attach_project_weather` first uses its `latitude` and `longitude`, then searches the source REPD row by `physical_project_id`, then uses the site name when coordinates remain missing. Finite coordinates are assigned to the nearest representative of the same technology. `nearest_site` converts project coordinates to radians as `lat1`, `lon1` and representative coordinates as `lat2`, `lon2`; the distance in kilometres is

$$
\begin{aligned}
\mathtt{a}&=\sin^2\frac{\mathtt{lat2}-\mathtt{lat1}}{2}\\
&\quad+\cos(\mathtt{lat1})\times\cos(\mathtt{lat2})\times\sin^2\frac{\mathtt{lon2}-\mathtt{lon1}}{2},\\
\mathtt{distance}&=2\arcsin\sqrt{\mathtt{a}}\times6{,}371\ \mathrm{km}.
\end{aligned}
$$

Equal distances select the first representative in the declared order. Solar and onshore planned projects with missing coordinates use their REPD region and the following city mapping. The initial operating-stock reader also uses this table, with the region taking precedence over coordinates at that earlier step.

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

Unlocated projects share a capacity-weighted weather mixture when they enter operation. `commissioned_project_weather` first accumulates each representative's operating capacity as `stock[name]` and adds all explicitly located projects due in that year. It then groups the remaining projects by technology. `total_stock` is the corresponding stock in MW, `total_new` is the new MW and `names` is the list of that technology's representatives:

```text
total_stock = sum(stock[name] for name in names)
total_new = sum(p.capacity_mw for p in projects)
if total_new <= 0 or total_stock <= 0:
    weights = {names[0]: 1.0}
else:
    names.sort()
    remaining, weights = total_new, {}
    for i, name in enumerate(names):
        amount = remaining if i == len(names) - 1 else total_new * stock[name] / total_stock
        remaining -= amount
        weights[name] = amount / total_new if amount > 1e-6 else 0.0
```

Each project in the unlocated group receives the same `weights`. Positive allocations above 0.000001 MW become `amount / total_new`; smaller allocations have zero weather weight. Alphabetical ordering and the final-point remainder fix the floating-point allocation order. With zero total stock, the first representative receives weight 1.

The stored `weather_source_weights` remain attached to the asset after commissioning. `source_weights` uses this explicit mapping first, then a single `weather_source_asset_id`, then an identity match through the asset, assigned generator, investment owner, source agent or base asset. Source names must identify representatives of the same technology. Weights must be finite and non-negative, with their sum at most 1 plus 0.000000000001. If `deficit = 1.0 - sum(weights.values())` exceeds that tolerance, `cohort` is the positive finite `weather_allocation_cohort_mw` and `skipped` counts zero weights; acceptance requires `deficit <= skipped * 1e-6 / cohort + 1e-12`.

The asset's availability is the weighted sum of its source curves. `_map_lineages` applies the mapping `weights` to each source's `values`; using subscript `name` to select the source array, the resulting `combined` is

$$
\mathtt{combined}[t]=\sum_{\mathtt{name}}\mathtt{weights}[\mathtt{name}]\times\mathtt{values}_{\mathtt{name}}[t].
$$

Zonal allocation preserves the weather curve while dividing the asset's physical capacity. `StagedBidAtCostPSM` multiplies `capacity_mw` by each `share`; the shares sum to 1. It multiplies storage `charge_power_mw`, `discharge_power_mw`, `energy_capacity_mwh` and `initial_soc_mwh` by the same share. Chapter 7 defines the asset-to-zone mapping and network constraints.

The optional `REPDERA5AggregatedWeather.build` interface combines caller-supplied project curves within each owner–technology–zone group. For allocation records `rows`, `total` is total MW, `values` is a project's dimensionless curve and `weighted` is the group's curve:

$$
\begin{aligned}
\mathtt{total}&=\sum_{\mathtt{row}\in\mathtt{rows}}\mathtt{row.capacity\_mw},\\
\mathtt{weighted}[t]&=\sum_{\mathtt{row}\in\mathtt{rows}}\mathtt{values}_{\mathtt{row}}[t]\times\frac{\mathtt{row.capacity\_mw}}{\mathtt{total}}.
\end{aligned}
$$

This aggregation requires equal-length, finite project curves in [0,1] and positive `total`. Multiplication of `weighted` by total MW gives the sum of the projects' available power. The zonal dispatch interface can instead use the representative curve directly for each allocated portion of an asset.

## Technology-average investment profiles

Annual expansion calculations use one technology-average profile for solar, onshore wind and offshore wind. These inputs combine 2022 ERA5 data with the fleet and project assumptions embodied in `sa.csv`, `wa.csv` and `we.csv`. Each public2 file contains 8,760 hourly values and declares `interval_minutes=60`; each value supplies two consecutive half-hours in source row order.

The resulting `availability` is dimensionless and supplies `peak` and annual capacity headroom in Chapter 6. These investment profiles enter that rule directly. Dispatch availability follows the site sampling, time assignment, conversion and losses defined above.
