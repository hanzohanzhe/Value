# Weather and available generation

VALUE calculates period-specific available wind and solar energy from weather at spatial representative points and asset capacity. For asset \(i\), let capacity be \(K_i\) MW and the available-output coefficient be \(a_{i,t}\). Its available power and half-hour energy limit are

$$
P_{i,t}^{\max}=K_i a_{i,t},\qquad E_{i,t}^{\max}=K_i a_{i,t}\Delta t,\qquad \Delta t=0.5\ \mathrm{h}.
$$

The weather module supplies this physical limit, and market dispatch determines accepted generation within it. Annual wind and solar expansion rules then use either available generation or technology-average profiles, according to the selected configuration, to calculate capacity-addition limits.

## Weather sequences and representative-point sampling

R029 converts hourly ERA5 data for 2020–2024 into a 365-day climatology and reuses it in each model year. The original sequence contains 43,848 hours. Removing 48 hours from the two leap days leaves five samples for each month, day and hour; their mean gives an 8,760-hour sequence. For weather variable \(X\) at location \((\phi,\lambda)\), the calendar mean outside 29 February is

$$
\overline X(m,d,h,\phi,\lambda)=\frac{1}{5}\sum_{y=2020}^{2024}X_y(m,d,h,\phi,\lambda).
$$

Wind speed is calculated from the magnitude of the 100 m wind vector at each original hour before calendar averaging. For each original hour, \(v=\sqrt{u_{100}^2+v_{100}^2}\). The weather file stores `u100`, `v100` and `wind_speed` obtained in that order, with the generation curve preferentially using `wind_speed`. For inputs containing only vector components, the reader calculates the magnitude at the corresponding input time.

The climatology retains a 0.25° grid over Great Britain and nearby seas. The solar file represents downward solar radiation as `ssrd`, while the wind file provides 100 m wind information. Spatial and temporal array dimensions are given below.

| Input | Latitude range | Longitude range | Latitude × longitude × day × hour |
|---|---|---|---|
| Solar radiation | 45°–65°N | 14°W–4°E | 81 × 73 × 365 × 24 |
| 100 m wind | 46°–65°N | 14°W–5°E | 77 × 77 × 365 × 24 |

Each asset representative point uses weather from the nearest latitude and nearest longitude grid coordinates. For representative point \((\phi_i,\lambda_i)\) and grid coordinates \((\phi_j,\lambda_k)\),

$$
j^*=\operatorname*{arg\,min}_j|\phi_j-\phi_i|,\qquad
k^*=\operatorname*{arg\,min}_k|\lambda_k-\lambda_i|.
$$

`doctoral_weather` extracts the hourly sequence at the selected point, accepting latitude–longitude–day–hour and time–latitude–longitude layouts, and terminates loading for masked or non-finite values. Half-hour period \(t\) uses source hour \(h(t)=\lfloor t/2\rfloor\bmod H\), where \(H\) is the source-series length. Each hourly value therefore applies to two consecutive half-hours.

The original GB compatibility weather pack uses day-of-year grouping to produce a 366-day, 8,784-hour sequence, of which annual dispatch uses the first 8,760 hours. R029 aligns leap and ordinary years by month, day and hour and uses its full 8,760-hour climatology. Each study configuration retains its corresponding weather input.

## Wind and solar generation curves

The wind coefficient follows cut-in, cubic growth, rated output and cut-out segments. Let wind speed be \(v\) m/s, rated speed \(v_r\), cut-out speed \(v_o\), and cut-in speed 3 m/s. Then

$$
a_w(v)=\begin{cases}
0,&v<3\ \text{or}\ v>v_o,\\
\dfrac{v^3-27}{v_r^3-27},&3\le v<v_r,\\
1,&v_r\le v\le v_o.
\end{cases}
$$

Onshore wind uses \((v_r,v_o)=(9.7,25)\) m/s, and offshore wind uses \((10.5,30)\) m/s. The curve remains at 1 at the cut-out boundary and falls to zero for speeds strictly above it. These technology parameters and asset capacity jointly determine the weather-to-generation conversion.

At 8 m/s, the onshore coefficient is 0.5476061707. A 100 MW asset therefore has 54.76061707 MW of available power and a half-hour energy limit of 27.38030853 MWh. The retained market kernel represents wind in 20 MW units and multiplies by a capacity multiplier of \(K_i/20\), yielding the same \(K_i a_w\).

The solar coefficient is obtained by normalising hourly accumulated solar radiation. For `ssrd` value \(R\) in J/m²,

$$
a_s(R)=\begin{cases}
\dfrac{R}{3{,}600{,}000},&3{,}600<R\le36{,}000{,}000,\\
0,&\text{otherwise}.
\end{cases}
$$

At \(R=1{,}800{,}000\) J/m², \(a_s=0.5\), so 10 MW of solar provides 2.5 MWh of available energy in a half-hour. The function reaches \(a_s=10\) at its upper boundary. The maximum radiation in the R029 climatology is 3,322,188.75 J/m², corresponding to a maximum coefficient of approximately 0.9228302. The separate spatial aggregation interface requires input profiles within \([0,1]\), so new weather data must meet the profile range of the selected interface.

## Project locations, asset aggregation and zones

Wind and solar projects obtain their spatial weather correspondence through representative points of the same technology. The initial GB template contains 11 solar and 11 onshore representative points, plus 21 offshore point names. R029's 2025 operating state contains 11 solar, 11 onshore and 18 offshore assets with positive capacity. `fleet.locations` and generator names jointly specify representative-point locations.

Projects with explicit coordinates are assigned to the nearest same-technology representative point using great-circle distance. With latitudes and longitudes for project \(i\) and candidate point \(j\) expressed in radians,

$$
d(i,j)=2R_E\arcsin\sqrt{\sin^2\frac{\phi_j-\phi_i}{2}+\cos\phi_i\cos\phi_j\sin^2\frac{\lambda_j-\lambda_i}{2}},\qquad R_E=6{,}371\ \mathrm{km}.
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

Remaining unlocated projects are allocated among representative points in proportion to existing same-technology capacity. For operating capacity \(K_j\), the allocation weight is \(w_j=K_j/\sum_jK_j\). Located projects commissioned in the same year enter capacity first, followed by allocation of the remaining projects; the final point receives the floating-point remainder. Zero existing capacity selects the first representative point, and allocated shares of at most \(10^{-6}\) MW are skipped.

Assets with mixed weather sources retain the weights assigned when they enter operation. If `weather_source_weights` for asset \(i\) are \(w_{ij}\), its available-output coefficient is

$$
a_{i,t}=\sum_jw_{ij}a_{j,t},\qquad w_{ij}\ge0,\qquad \sum_jw_{ij}=1.
$$

`doctoral_weather_mapping` establishes the project-to-point correspondence, and the weather reader checks weights and technology consistency. Subsequent capacity changes retain the asset's existing weather weights.

The current national market maps annual assets onto a fixed market-agent and representative-weather topology. Mapping first uses identical asset identifiers, then selects agents of the same technology with matching region and allocates by previously mapped capacity. Zero capacity invokes template capacity and then equal allocation. Each market agent's final capacity is the sum of the annual assets assigned to it.

Zonal operation divides assets by capacity shares while retaining the original weather profile and economic owner. For asset share \(s_{iz}\) in zone \(z\),

$$
K_{iz}=K_i s_{iz},\qquad a_{iz,t}=a_{i,t},\qquad
\sum_zK_{iz}a_{iz,t}\Delta t=K_i a_{i,t}\Delta t
$$

holds when \(\sum_zs_{iz}=1\). `StagedBidAtCostPSM` applies the same share allocation to generation capacity and to storage power, energy capacity and inventory.

A separate aggregation interface combines precomputed project profiles by capacity. For project set \(G\) sharing an owner, technology and zone, `REPDERA5AggregatedWeather.build` calculates

$$
K_G=\sum_{i\in G}K_i,\qquad
 a_{G,t}=\sum_{i\in G}\frac{K_i}{K_G}a_{i,t}.
$$

This interface accepts equal-length finite profiles within \([0,1]\) and positive total capacity. The current zonal execution path uses representative-profile replication as described above. The separate aggregation interface receives source profiles already generated by its caller.

## Annual wind and solar capacity limits

The current general investment rule calculates capacity headroom from peak demand and the peak of a technology profile. Let peak actual demand be \(D^{\rm peak}\) MW, the peak CSV profile for technology \(k\) be \(a_k^{\rm peak}\), and its operating capacity be \(K_k\). Then

$$
H_k=\max\left(0,\frac{D^{\rm peak}}{\max(a_k^{\rm peak},10^{-12})}-K_k\right),\qquad
C_k^{\rm annual}=\alpha H_k,\qquad \alpha=0.20.
$$

Technology-average profiles combine 2022 ERA5 data with fleet and project assumptions. Solar `sa.csv` contains 8,761 values, of which the first 8,760 hours are used after conversion to half-hours; onshore `wa.csv` and offshore `we.csv` each contain 8,760 hourly values.

`canonical_psm_data` reads these profiles, and the annual expansion definition applies \(\alpha\). For example, \(D^{\rm peak}=1{,}000\) MW, \(a_k^{\rm peak}=0.8\) and \(K_k=300\) MW give headroom of 950 MW and an annual limit of 190 MW. A zero profile peak invokes the denominator floor of \(10^{-12}\).

R029's `thesis_final9.6` investment configuration sets capacity limits from the count of negative net-demand periods. It first constructs \(V_t\) from the physical available energy of all operating wind and solar assets, and calculates available energy per MW, \(g_{k,t}\), for each technology:

$$
V_t=\sum_k\sum_{i\in k}K_i a_{i,t}\Delta t,\qquad
 g_{k,t}=\begin{cases}
\dfrac{\sum_{i\in k}K_i a_{i,t}\Delta t}{K_k},&K_k>0,\\
0,&K_k=0.
\end{cases}
$$

Here \(g_{k,t}\) has units of MWh/MW/period. For actual demand energy \(Q_t\), net demand is \(N_t=Q_t-V_t\), and the existing count of negative net-demand periods is \(n_0=\#\{t:N_t<0\}\). The threshold \(b=200\) half-hours corresponds to 100 hours.

The expansion limit follows the order statistic of the added capacity at which net demand reaches zero. If \(n_0\ge b\), the limit is zero. Otherwise, periods with \(N_t\ge0\) and \(g_{k,t}>0\) give ratios \(r_t=N_t/g_{k,t}\). The \((b-n_0)\)-th smallest ratio defines critical capacity \(K_k^{\rm crit}\), and \(C_k^{\rm annual}=0.20K_k^{\rm crit}\). Fewer than \(b-n_0\) eligible ratios give a zero limit. Capacity equal to a particular \(r_t\) makes that period's net demand exactly zero; the strict negative-net-demand criterion remains \(N_t<0\).

```text
input: full-year demand Q, asset capacities K, half-hourly available-output coefficients a
V[t] = sum K[i] × a[i,t] × 0.5 over all operating wind and solar assets
N[t] = Q[t] − V[t]
n0 = count(N[t] < 0)
for each wind or solar technology k:
    calculate capacity-weighted available energy per MW, g[k,t]
    if n0 >= 200: annual_cap[k] = 0
    otherwise:
        ratios = N[t] / g[k,t] for periods with N[t] >= 0 and g[k,t] > 0
        if number of ratios < 200 − n0: annual_cap[k] = 0
        otherwise: annual_cap[k] = 0.20 × the (200 − n0)-th smallest ratio
output: annual capacity-addition limits by technology
```

R029 constructs these quantities from annual physical inputs and aligns total available wind and solar generation with annual market summaries. Its 2025 operating sequence contains 1,878 negative net-demand periods, giving zero annual limits under this rule for solar, onshore wind and offshore wind.

## Data and implementation

`calendar_mean_solar_2020_2024.nc` and `calendar_mean_wind_2020_2024.nc` supply the R029 calendar climatology. `doctoral_weather` extracts representative-point series and converts wind and solar inputs, while `doctoral_weather_mapping` manages project locations and mixed weather weights. `scheme_c_native_psm` aggregates capacity into national market agents, and `staged_psm` divides capacity among zones. Annual limits use the general peak rule in `canonical_psm_data` and `v2_module_definitions`, or the net-demand threshold rule in R029's `doctoral_expansion_inputs` and `doctoral_policy`.
