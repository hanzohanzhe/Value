# Initial data and input processing

VALUE selects demand, weather, initial assets, planned projects and external market data through the study configuration, then converts these inputs into capacities and period energies on a common time axis. Teaching, national and zonal studies use the combinations below. Model years represent the evolution of assets and markets; the demand shape and weather sample years are specified separately by the data configuration.

| Study configuration | Data combination | Time coverage and purpose |
|---|---|---|
| VALUE 101 | `value-101-baseline-v1` | Bundled synthetic teaching inputs; the full course covers 2025–2026 with 17,520 half-hours per year, alongside a 48-period exercise |
| R029 national study | `value-uk-calendar-vx-trade001` | Simulates 2025–2034; the demand shape is from 2022 and weather is the 2020–2024 calendar climatology |
| Current GB zonal study | `value-uk-open-data-pack-v1`, with the 23-zone network pack | Simulates 2025–2034; national inputs retain the compatibility time series, while network inputs provide a 23-zone spatial allocation |

## Temporal resolution and input roles

The national model balances supply and demand using half-hourly energy. For power \(P_t\) in MW and time step \(\Delta t=0.5\) h, period energy \(E_t\) and annual energy \(E_y\) are

$$
E_t=P_t\Delta t,\qquad E_y=\sum_{t=0}^{T-1}E_t,\qquad T=365\times24\times2=17{,}520.
$$

Capacity is expressed in MW, stored energy in MWh, monetary costs in GBP and electricity prices in GBP/MWh. Demand CSV values are loaded as MW and multiplied by the time step before dispatch. VALUE 101 demand columns that retain `mwh` in their names follow the same numerical convention.

Data bindings assign physical files to defined computational roles. Demand files supply actual demand and the day-ahead forecast, the fleet table supplies technology, capacity and representative location, and planning tables supply project status and dates. Weather and technology-average profiles support spatial available generation and the corresponding investment rules, respectively.

| Input role | Main data or fields | Computational use |
|---|---|---|
| Actual and forecast demand | `demand_mw` in `actual_mw.csv`; `forecast_mw` in `forecast_mw.csv` | Real-time balancing, day-ahead clearing and demand error |
| Fleet and initial assets | `fleet.json`, annual `operating_state` | Technology parameters, representative locations and dispatch capacities |
| Projects and planning | `repd_projects_normalized.csv`, `regional_technology_success_rates.csv`, `planning_timelines.json` | Initial operational assets, project success rates and stage durations |
| Weather | `calendar_mean_solar_2020_2024.nc`, `calendar_mean_wind_2020_2024.nc` | Available wind and solar generation at representative points |
| Technology-average profiles | `sa.csv`, `wa.csv`, `we.csv` | Compatibility investment inputs for solar, onshore wind and offshore wind |
| Capital and policy | `capital_costs.json`, `model_parameters.json`, `mechansim cost.xlsx` | Investment costs, financial parameters and policy expenditure |
| External markets | Country-specific `flow_mw`, `price_gbp_per_mwh` | Available interconnector exchanges and external offers |
| Zonal network | Zones, corridors, boundaries, asset mapping and zonal demand | Spatial supply–demand balance and transmission constraints |

R029 demand loading uses fixed column names, MW units and a complete 17,520-period time axis. `doctoral_demand` preserves the decimal precision of the input sequence. The interconnector reader also checks consecutive periods and two price records per hour, placing demand, flows and prices in a defined computational order.

The current general-purpose reader accepts teaching and compatibility inputs through numerical-column selection and length adjustment. `canonical_psm_data` selects the column with the most valid numbers, repeats hourly profiles into half-hours, and cycles or truncates sequences to the required period count in the following order.

```text
read_series(file, header):
    attempt numerical conversion of each column
    select the column with the most valid numbers; select the first column in a tie
    remove rows that fail conversion; terminate loading if finite values are absent

align(values, T, hourly_repeat):
    if length equals T: return the original sequence
    if hourly_repeat and 2 × length >= T: repeat each value twice, then take the first T values
    if length is less than T: cycle to T values
    otherwise: take the first T values

actual_energy = align(read_series(actual_demand_file, header=0), T, false) × 0.5
forecast_energy = align(read_series(forecast_file, header=0), T, false) × 0.5
technology_profile = clip(align(read_series(profile_file, header=None), T, true), 0, 1)
```

This reading rule determines the effective sequences in the original GB compatibility pack: the first forecast value, 21,560, is treated as a header, and the first 17,520 of the remaining 26,203 values are used; the actual-demand file contains 26,204 values after its header. R029 uses the paired UTC demand files described above, so each configuration's temporal input follows its own data and loading procedure.

## Demand series and calendar processing

R029 uses NESO's 2022 day-ahead half-hourly demand forecasts and corresponding actual demand as the base demand shapes for model years. `actual_mw.csv` and `forecast_mw.csv` each contain 17,520 rows. Their initial statistics are given below; subsequent scenario scaling acts on these base shapes.

| Series | Minimum power MW | Maximum power MW | Mean power MW | Annual energy MWh |
|---|---:|---:|---:|---:|
| Actual demand | 15,080 | 46,042 | 26,587.967637 | 232,910,596.5 |
| Day-ahead forecast | 14,240 | 46,760 | 26,611.131963 | 233,113,516 |

Demand preprocessing identifies duplicate records by settlement date and period, then converts UK local dates to a UTC time axis. For a given settlement period, it retains the latest publication; equal publication times are resolved by retaining the last row. The original 17,518 rows become 17,516 after duplicate consolidation, and four missing half-hours are filled by linear interpolation in UTC.

Linear interpolation distributes the difference between the known endpoint values evenly across each gap. For endpoint values \(x_a\) and \(x_b\), with \(m\) missing values between them,

$$
x_{a+j}=x_a+\frac{j}{m+1}(x_b-x_a),\qquad j=1,\ldots,m.
$$

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

R029 enters dispatch in 2025 with the capacities listed below. Asset rows represent operational model assets; nuclear, gas and several other technologies use aggregate representations.

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

Planning inputs specify project success rates by technology and region, and duration distributions by technology and stage. `regional_technology_success_rates.csv` contains 46 records. The general input pathway matches technology and region, then the GB aggregate, and finally a default success rate of 1, with probabilities restricted to \([0,1]\). Chapter 6 describes R029's regional success-rate rule. `planning_timelines.json` supplies historical stage durations in months. Development and construction medians are shown below; project entry, progression and commissioning rules are presented in the annual investment chapter.

| Technology | Median development months | Median construction months |
|---|---:|---:|
| Solar | 27.8 | 4.9 |
| Onshore wind | 62.5 | 15.0 |
| Offshore wind | 110.1 | 32.2 |
| Battery | 31.3 | 10.1 |

## Costs and storage parameters

Investment inputs specify unit capital costs, payback targets and technical operating parameters separately. R029 uses `capital_costs.json` and `model_parameters.json` from its study configuration. Upstream capital-cost sources include BEIS Electricity Generation Costs 2020 and Arup material; the table reports the parameters adopted by the model. The default capital discount rate is 0.05. The table gives the base-configuration payback targets and `preferred_rate` parameters. R029's investment rule sets the effective threshold for all four expandable storage technologies to 0.12; Chapter 6 defines its profit ratio and decision rules.

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

Storage parameters assign charging efficiency, discharging efficiency, duration and lifetime to inventory and cost calculations. Round-trip efficiency is \(\eta_c\eta_d\); for example, the 0.5C battery uses \(0.98^2=0.9604\). Catalogue economic lifetimes and the payback targets above enter the calculations as separate parameters. The cycle parameter \(N_{max}\) determines reference annual cycles. The three battery technologies also use it for cycle depreciation, while pumped hydro and hydrogen storage use time recovery.

| Technology | Catalogue duration h | Charging efficiency | Discharging efficiency | Catalogue economic life years | Cycle parameter \(N_{max}\) |
|---|---:|---:|---:|---:|---:|
| Pumped hydro | 4 | 0.87 | 0.87 | 30 | 1,000,000 |
| 1C battery | 1 | 0.81 | 0.81 | 15 | 3,000 |
| 0.5C battery | 2 | 0.98 | 0.98 | 15 | 5,000 |
| 0.25C battery | 4 | 0.81 | 0.81 | 15 | 8,000 |
| Hydrogen storage | 250 | 0.57 | 0.57 | 10 | 1,000 |

Annual asset schedules can specify storage power and energy directly. The 2025 pumped-hydro asset state therefore uses 2,828 MW and 26,700 MWh.

Initial stored energy depends on the operating configuration. It is zero in the doctoral-aligned configuration and defaults to 50% of maximum inventory in the general chronology configuration.

Financial calculations select time parameters by computational purpose and technology configuration. Biomass uses an economic life of 25 years and a payback target of 20 years. The gas prototype has a 20-year payback target, while the R029 run configuration sets CCGT and OCGT to 25 years.

Policy expenditure inputs combine historical aggregation with forward assumptions. `mechansim cost.xlsx` assembles NESO Capacity Market and balancing-cost data, Ofgem RO/FIT/REGO material and LCCC CfD data for annual policy expenditure calculations.

## Interconnectors and zonal demand

External market inputs describe cross-border exchange opportunities through flow limits and prices for each half-hour. R029 provides one 17,520-row file for each of France, Belgium, the Netherlands, Norway and Ireland, binding each file to both flow and price roles. Fields include `period`, `flow_mw`, `price_gbp_per_mwh`, the source price hour, a half-hour marker, and source row numbers for flows and prices.

Boundary prices use European day-ahead prices assembled by Ember from ENTSO-E data. France, Belgium, the Netherlands and Norway use 2022 prices, while Ireland uses 2021. Each hourly price is repeated twice and saved in GBP/MWh after conversion using \(p_{\rm GBP}=p_{\rm EUR}/1.1\). R029 retains negative input prices; the current general chronology resources apply \(\max(p,0)\).

Boundary flows enter the model as exogenous exchange limits ordered by period index. For file value \(F_t\) in MW, positive values assign import capacity and negative values assign export capacity. The corresponding half-hour energy limits are

$$
I_t^{\max}=\max(F_t,0)\Delta t,\qquad
X_t^{\max}=\max(-F_t,0)\Delta t.
$$

This configuration combines mixed price years with flows arranged by index, and its temporal interpretation follows those input conventions. Flow ranges and mean prices are reported below.

| Boundary | Flow range MW | Price year | Mean price GBP/MWh |
|---|---:|---:|---:|
| Belgium | −1,022 to 1,020 | 2022 | 222.292608 |
| France | −3,091 to 2,997 | 2022 | 250.789325 |
| Ireland | −987 to 998 | 2021 | 123.937076 |
| Netherlands | −1,076 to 1,062 | 2022 | 219.917959 |
| Norway | −1,263 to 1,399 | 2022 | 126.503575 |

Zonal studies distribute scenario-level national demand using the network pack's period-specific regional shares. With network demand \(D^{\rm net}_{z,t}\) and study demand \(D^{\rm run}_t\), `scenario_scaled_zonal_shares` applies

$$
s_{z,t}=\frac{D^{\rm net}_{z,t}}{\sum_zD^{\rm net}_{z,t}},\qquad
D^{\rm run}_{z,t}=D^{\rm run}_t s_{z,t}.
$$

The final zone receives national demand minus the sum of the other zones, conserving the spatial total. Loading terminates if network national demand is zero while study demand is non-zero. The alternative `network_pack_absolute_demand` uses network national demand directly and adjusts the forecast using the original forecast-to-actual ratio. Zone, corridor and asset-mapping constraints are defined in the transmission chapter.

## VALUE 101 synthetic inputs

VALUE 101 generates daily peaks, seasonal variation and local supply–demand disturbances with deterministic functions. Let the half-hour index be \(t\), day index \(d=\lfloor t/48\rfloor\), and hour of day \(h=(t\bmod48)/2\). The base daily demand shape is

$$
B(h)=22+9e^{-((h-8)/2.2)^2}+19e^{-((h-19)/2.5)^2}+2e^{-((h-1)/3.5)^2}.
$$

The weekday factor is \(w_d=1\), with \(w_d=0.92\) when \(d\bmod7\ge5\). A disturbance \(q_t\) equals 30 MW when \(d\in\{0,182\}\) and \(t\bmod48=31\), and zero otherwise. Actual demand is then

$$
D_t=\operatorname{round}_6\left[B(h)\left(1+0.16\cos\frac{2\pi d}{365}\right)w_d+q_t\right].
$$

Forecast demand exceeds actual demand by 12 MW at \(t\bmod48=30\) on those same two days, and equals actual demand in the remaining periods.

The teaching solar profile multiplies a daylight shape by a seasonal factor. Define \(\operatorname{clip}(x,l,u)=\min(u,\max(l,x))\). Then

$$
a_{s,t}=\begin{cases}
\operatorname{clip}\left(\sin\frac{(h-6)\pi}{12}\left[0.58+0.42\sin^2\frac{(d-80)2\pi}{365}\right],0,1\right),&6\le h\le18,\\
0,&\text{otherwise}.
\end{cases}
$$

The teaching wind technology profiles combine daily, 29-day and annual components. Onshore and offshore coefficients are

$$
a_{w,t}=\operatorname{clip}\left(0.42+0.13\sin\frac{(t\bmod48+5)2\pi}{48}+0.12\sin\frac{(d+17)2\pi}{29}+0.08\cos\frac{(d+31)2\pi}{365},0.08,0.92\right),
$$

$$
a_{o,t}=\min(1.08a_{w,t},1).
$$

Technology profiles are saved to six decimal places. The teaching weather files separately define one grid point at 52°N, 0°E with 8,760 hours. Solar irradiation in hour \(q\) is \(a_{s,2q}\times3{,}600{,}000\) J/m², and wind speed is

$$
v_q=7+2\sin\frac{(q+3)2\pi}{24}+1.2\sin\frac{(\lfloor q/24\rfloor+17)2\pi}{29}.
$$

Weather wind speed is converted through the generation curve for dispatch, while the preceding wind technology profiles serve the corresponding investment inputs. The French boundary has a 12 MW import limit and a price of 82 GBP/MWh. The other four boundaries have zero exchange capacity and placeholder prices of 200 GBP/MWh. `build_value_101_packs` writes the demand, weather and market inputs generated by these functions into the teaching pack.

## Data and implementation

Demand comes from NESO's Day-ahead half-hourly demand forecast performance dataset, projects from the DESNZ REPD, weather from Copernicus ERA5 single levels, and boundary prices from Ember's compilation of ENTSO-E data. `import_scheme_c_1000twh` normalises REPD inputs, `doctoral_demand` and `doctoral_interconnectors` load R029 time series, `canonical_psm_data` assembles general inputs, and `zonal_demand_alignment` aligns zonal demand. Subsequent chapters describe weather transformations, operational dispatch and annual investment.
