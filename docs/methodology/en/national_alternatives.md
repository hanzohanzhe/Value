# National dispatch algorithms

The default national power-system model, Native (`value-bid-at-cost-psm`), clears a single national node every half-hour. The methodology profile selects its market rule set: `native-corrected-v1` for the default corrected methodology and `native-doctoral-thesis-v1` for the doctoral reproduction profile. The experimental national pathway (`value-doctoral-national-psm`) has its own dispatch engine and input conventions. Its experimental annual accounts are described in Chapter 6.

## Inputs, agents and availability

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

## Native storage batches and net positions

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

## Native forecast clearing and balancing

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

## Economic downward order

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

## Settlement, displayed price and physical cost

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

## Energy balance and result qualification

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

## Experimental pathway inputs

The experimental national pathway uses frozen v1 weather, unit availability for nuclear and natural-flow hydro, and raw boundary prices under either methodology profile. The weather transformation uses its original radiation convention and unity loss factors. `doctoral_market_factory.py` builds agents from complete rows of costs, efficiencies, ramps, opening output, downward prices and natural budgets. A new asset may reuse a row through `doctoral_parameter_source_id`, retaining the row's ramp and budget values. Direct renewable electrolysis and the common electrolyser have zero capacity in this pathway.

The module supports fixed-year dispatch and experimental annual cash accounts. It records `scientific_release_eligible=false` and `doctoral_annual_cem_ready=false`. Integration with `agent-investment` requires the `value.agent-cashflow/v1` account contract for eligible thermal decisions; this experimental PSM currently publishes `doctoral_cashflow_inputs`, so that combination stops at the investment-account requirement. The following equations describe the implemented period engine.

## Experimental batch inventory

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

## Experimental planning and realisation

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

## Experimental settlement and annual expenditure

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
