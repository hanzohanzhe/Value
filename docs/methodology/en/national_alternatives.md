# National market clearing

The national market clears forecast demand and then balances actual demand at one node in each half-hour. The default module `value-bid-at-cost-psm` applies `native-corrected-v1`: generators and imports offer available power, storage offers eligible energy batches, and the realised dispatch advances the physical state to the next period.

## Inputs, agents and availability

Dispatch quantities are powers in MW, with `period_hours = 0.5`. The variables `forecast_demand`, `real_demand`, `capacity_limit`, `real_gen_energy` and `alter_limit` respectively describe forecast demand, actual demand, available output, realised output and the per-period ramp allowance. The generator index is \(i\), the time index is \(t\), and other asset indices are defined with each calculation. The UTC model year has 17,520 periods. The native kernel reads demand in MW and multiplies accepted power by `period_hours` for MWh output and settlement. The `canonical_psm_data.py` chronology supplies period MWh to staged and optimisation modules, following Chapter 2.

Generator bids combine operating cost with a start-up adder determined by the previous accepted set. Gas and biomass use `gen_cost + fuel_cost + carbon_price + unit_time_cost`; nuclear, renewables and natural-flow hydro use `gen_cost + unit_time_cost`. The input-row costs are summed into the runtime agent’s `gen_cost`, in GBP/MWh; `carbon_price` is already an expenditure per MWh. For bid multiplier \(\mathrm{bidding\_factor}\), composite operating cost \(\mathrm{gen\_cost}_i\) and start-up adder \(\mathrm{startup\_cost}_i\),

$$
\begin{aligned}
\mathrm{price}_{i,t}={}&\mathrm{bidding\_factor}\cdot \mathrm{gen\_cost}_{i}\\
&+\mathrm{startup\_cost}_{i}\cdot
\mathbf1[i\notin\mathrm{accepted\_bids\_name}_{t-1}].
\end{aligned}
$$

The bid multiplier defaults to 1. Hydro and renewables have zero start-up adders. The GB input rows give biomass a composite cost of 0.2 + 80 + 4.8 = 85 GBP/MWh and a start-up adder of 83 GBP/MWh; CCGT and OCGT composite costs are 55.07 and 74.92 GBP/MWh. Biomass receipts follow market settlement.

The annual adapter maps operating and newly commissioned assets to market agents first by name, then by technology and normalised region. Multiple matches use previously mapped capacity, constructor capacity, or equal shares in that order. `weights` and `total_weight` allocate each asset's `capacity_mw` into `generator_sources`; these capacities are MW, with \(j\) indexing market agents and \(a\) assets. `_allocate_runtime_income` distributes `raw_income` into the asset account `allocated`, both in GBP, in proportion to the mapped capacities:

$$
\begin{aligned}
\mathrm{generator\_sources}_{j,a}
&=\mathrm{capacity\_mw}_a\cdot \mathrm{weights}_j/\mathrm{total\_weight},\\
\mathrm{capacity}_j&=\sum_a\mathrm{generator\_sources}_{j,a},\\
\mathrm{allocated}_a&=\sum_j\mathrm{raw\_income}_j\cdot
\frac{\mathrm{generator\_sources}_{j,a}}{\mathrm{capacity}_j}.
\end{aligned}
$$

Wind uses a 20 MW reference unit and multiplier \(\mathrm{capacity\_mw}_j/20\); solar uses a 1 MW reference unit and multiplier \(\mathrm{capacity\_mw}_j\). Storage power and energy are aggregated by technology. `scheme_c_native_psm.py` creates the year's agents and restores prior sales and sales-weighted holding time for bidding. Each year creates storage agents with empty `stored_energy`; the preceding year's closing inventory is counted as discarded energy in `storage_year_boundary`.

Renewable availability uses the same period arrays as the canonical input adapter. `site_weather.site_cf_by_source` computes the Chapter 3 weather, loss and plane-of-array transformations, and `kernel_injection.KernelSiteInputs` supplies the resulting capacity factors \(\mathrm{cf}_{j,t}\) to the kernel:

$$
\mathrm{capacity\_limit}_{j,t}=\mathrm{capacity\_mw}_j\cdot \mathrm{cf}_{j,t}.
$$

Nuclear availability preserves each station's PRIS reference output when converting to model capacity. `nuclear_load_factor` reads `pris_load_factor`, `pris_reference_mw` and `capacity_mw`. `generation_end_period` supplies `end`, the first period after the announced end month; a station with year-round availability retains its factor throughout the year. With \(n\) indexing stations, `asset_availability` produces the station array `values`, and `kernel_availability` combines it by capacity:

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

The fixed 2019–2024 mean load factors are 0.668 for Heysham 1, 0.689 for Hartlepool, 0.752 for Heysham 2, 0.792 for Torness and 0.801 for Sizewell B. Station-policy inputs set the four AGR stations' availability to zero from period 4,320 of 2030, 1 April 00:00 UTC. Sizewell B retains full-year coverage until its declared retirement year. Fallback load factors are 0.801 for new PWR/EPR stations, 0.727 for an unspecified AGR and 0.723 for an undifferentiated national nuclear asset. GBP1 public2 applies the VALUE-UK nuclear station policy (`value_uk_nuclear_policy_v1.json`: five EDF stations and their declared generation ends), while its fleet input table contains one aggregate nuclear row; R029 retains a national aggregate and uses 0.723 under national dispatch. These parameters are supplied by `value_uk_firm_availability_v1.json` and `firm_availability.py`.

Natural-flow hydro combines the DUKES 6.3 mean annual load factor with a monthly shape derived from quarterly Energy Trends data:

$$
\mathrm{values}_t=0.3487\cdot \mathrm{monthly\_shape}_{\mathrm{month\_of\_period}(t)},
$$
$$
\begin{aligned}
\mathrm{monthly\_shape}=[&1.3851,1.3851,1.3851,0.6582,0.6582,0.6582,\\
&0.6776,0.6776,0.6776,1.2791,1.2791,1.2791].
\end{aligned}
$$

The shape has an arithmetic monthly mean of 1 and a 365-day weighted mean of 0.99883, giving a model-year availability of 0.3483. Nuclear and hydro use these fixed profiles across model years.

Nuclear begins the year in service and belongs to \(\mathrm{accepted\_bids\_name}_{-1}\); gas and biomass begin outside that set. The generator parameter rows provide opening `real_gen_energy`, and nuclear initially sets it to `capacity_limit`. Hydro and biomass initialise `have_gen_energy` to their opening `real_gen_energy`. Each period adds `add_energy` to `energy_limit`, accepts generation against the remaining budget, and returns curtailed generation to that budget. The budget quantities are MW-periods; multiplication by `period_hours` gives MWh.

## Storage offers and period positions

The storage agent records each charging period's stored-side MWh in `stored_energy`, indexed by the charging period \(k\); \(t\) denotes the current period. `Battery.charge` limits input by `power_capacity_mw`, `energy_capacity_mwh`, charging efficiency `n_1` and remaining power after the current period's earlier charging. For each battery, the implementation calculates

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

Surplus absorption first buys back the store's discharge from the same period and returns the withdrawn energy to its original batches. Further surplus can charge the store after its remaining discharge reaches zero. A store that has charged offers zero discharge in later stages. Surplus absorption processes forecast surplus before other available surplus and record sales at the closing net position. Ahead storage remuneration remains payable on bought-back output.

Self-discharge multiplies inventory by \(1-\mathrm{decay\_rate}\) each period. The values of \(\mathrm{decay\_rate}\) are 0.000021 for batteries and other default types, 0.000001 for pumped hydro and 0.000005 for hydrogen storage. Batches below 0.001 MWh are removed and included in inventory reconciliation.

The default dynamic storage-cost module uses cycle depreciation in storage bids. Batteries bid \(\mathrm{bidding\_factor}\cdot\mathrm{cycle\_depreciation\_gbp\_per\_mwh}_b\); pumped hydro and hydrogen storage bid zero. Oldest batches are offered first:

$$
\begin{aligned}
\mathrm{price}=\mathrm{bidding\_factor}\times
\begin{cases}
\mathrm{cycle\_depreciation\_gbp\_per\_mwh},&\mathrm{battery},\\
0,&\mathrm{pumped\ hydro\ or\ hydrogen}.
\end{cases}
\end{aligned}
$$

Chapter 4 defines the storage state and bid-cost calculation. Annual delivered MWh and sales-weighted holding time supply the following year's pricing inputs; Chapter 6 defines their cost treatment.

## Forecast clearing and balancing

Market clearing orders generator, import and storage-batch offers by a stable key. Within the same 0.01 £/MWh band, generation and imports precede storage; unrounded price and input order resolve further ties:

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

Interconnectors offer positive available import capacity into the ahead market at the external price multiplied by \(\mathrm{bidding\_factor}\). Their offers carry capacity limits with zero ramp and start-up adders. Balancing offers only \(\max(\mathrm{transfer\_constraint}_{k,t}-\mathrm{accepted\_mw}_{k,t},0)\). Negative transfer capacity represents export capability, accepted at positive external prices.

Surplus accounting rebuilds renewable surplus from availability minus accepted output after the ahead stage. Already-generated nuclear surplus is used first. When renewable surplus supplies storage, exports or flexible demand, it enters gross renewable generation. Recorded `vre_accepted` is therefore gross VRE output, `curtailed` is available VRE minus gross output, and `excess` is non-VRE spill. Nuclear surplus already included in ahead supply and settlement serves balancing demand once; renewable surplus entering supply during balancing receives balancing settlement.

Ahead clearing accepts successive offers until residual forecast demand reaches zero or all offers are exhausted. An ahead period with no accepted nuclear generator multiplies nuclear `real_gen_energy` by 0.99 before balancing. At the end of realisation, each generator with zero final dispatch sets `real_gen_energy` to zero; dispatched generators carry their final output into the next period.

The real-time branch compares actual and forecast demand. A lower actual value invokes surplus absorption and downward dispatch; a higher or equal value invokes upward balancing. This comparison also applies when ahead supply falls short of the forecast. In that case, the lower-demand branch still requests a reduction of \(\mathrm{forecast\_demand}_t-\mathrm{real\_demand}_t\); any remaining unmet demand enters the energy account below.

```text
accepted_bids = initial_running_rows(generators)
for period in range(periods):
    Read availability, forecast_demands[period], real_demands[period]
    Read period external_price and transfer_constraint
    ahead_market_bidding(...):
        Add add_energy to each hydro/biomass energy_limit
        Apply storage self-discharge; construct offers
        Sort by merit_key; accept forecast demand subject to physical bounds
        rebuild_surplus(...); uniform_income(...)
    realise_period(...):
        if real_demand < forecast_demand:
            curtailment_market_bidding(...):
                Buy back discharge, charge, export, supply electrolysis
                economic_downward_stack(...): reduce remaining output
        else:
            balancing_market_bidding(...):
                Use surplus; buy back discharge and charge
                Offer eligible batches, generation and residual imports
                Export remaining surplus and supply electrolysis
                Clear upward demand; record remaining blackout
        Set real_gen_energy to zero for generators with zero final output
    battery.close_period(period) for each battery
    physical_cost_terms(...): record period expenditure components
return period dispatch, prices, income, inventory and annual totals
```

Surplus absorption visits storage in ascending order of `storage_fee`, `per_storage_fee` and `n_1 * n_2` in the lower-demand branch, and in input order in upward balancing. Within each store it buys back current-period discharge before charging. Positive-price exports follow descending external price in the lower-demand branch and ascending external price in upward balancing, each bounded by the absolute negative `transfer_constraint`.

Upward clearing starts from the last ahead-accepted generator and includes later generator offers, storage batches at least two periods old, and unused import capacity. For that marginal generator, `valid_energy` is its current ramp-limited output bound less ahead-accepted MW; later generators use their full ramp-limited bounds. Hydro and biomass also retain their remaining budgets. Each accepted quantity reduces `energy_provided`, initially `real_demand - forecast_demand`; clearing ends at zero or after the final offer, and the remaining quantity becomes `blackout`.

The common electrolyser absorbs surplus as flexible demand. Its source parameters are 10 MW capacity, a 0.125 MW-per-period ramp and conversion efficiency 0.65; the data-pack parameter row supplies the selected values. Available wind and solar enter market clearing first, followed by surplus allocation to storage, exports and electrolysis. The electrolyser limit for this period is `energy_cell = min(real_energy + rampup_rate, capacity_limit)`, in MW. Its accepted `min_value` is the smaller of this limit and remaining surplus: `excess_energy + need_curtailed_energy` in the lower-demand branch, or `excess_energy` in upward balancing. It updates `real_energy = min_value` and `green_hy = min_value * energy_efficiency`.

## Economic downward order

Downward dispatch compares avoided operating expenditure after storage, exports and flexible demand absorb surplus. `ramp_floor_mw` returns the larger of zero and previous `real_gen_energy` less `alter_limit`; VRE and imports have zero floor. `avoided_cost` uses the asset's composite `gen_cost`, subtracting `NUCLEAR_DEC_PREMIUM_GBP_PER_MWH = 100` for nuclear; imports use `external_price`. Ordinary rows follow descending avoided cost rounded to two decimal places.

Gas and biomass split their accepted ahead output \(\mathrm{power}_k\) into a running range and a shutdown segment. Here \(\mathrm{power}_k\) represents the aggregate's online capacity for this ordering rule, and \(\mathrm{min\_stable\_fraction}_k\) is the minimum stable fraction:

$$
\begin{aligned}
\mathrm{stable}&=\mathrm{min\_stable\_fraction}\cdot \mathrm{power},\\
\mathrm{running}&=\max(\mathrm{power}-\max(\mathrm{floor},\mathrm{stable}),0),\\
\mathrm{shutdown}&=\max(\mathrm{power}-\mathrm{floor},0)-\mathrm{running}.
\end{aligned}
$$

The running segment avoids \(\mathrm{cost}_k\) £/MWh. The shutdown segment compares avoided expenditure over expected downtime \(\mathrm{horizon\_h}\) with restart expenditure \(\mathrm{restart\_cost}(\mathrm{horizon\_h})\), measured per MW of capacity per start:

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

`limit` is the segment's reducible MW, `item[2]` is its remaining accepted output, and `remaining` is the outstanding downward requirement. Hydro and biomass reductions return energy to cumulative budgets. Output held by the ramp floor becomes in-dispatch spill. `native_corrected.economic_downward_stack` applies these reductions. Reduction stops when `remaining` is at most \(10^{-9}\) MW or every reducible segment is exhausted.

## Settlement, displayed price and physical cost

The market dispatch pays every accepted supply category the same marginal price within each stage. Ahead settlement takes the highest accepted offer including imports and storage. `uniform_income` multiplies accepted `power_mw` by period length and the stage's `price_gbp_per_mwh`; the balancing price also includes accepted import prices. `income` is GBP, `power_mw` is MW and the price is GBP/MWh; an empty accepted category contributes zero to the maximum:

$$
\mathrm{income}_{i,t}=\mathrm{power\_mw}_{i,t}\cdot
\mathrm{period\_hours}\cdot \mathrm{price\_gbp\_per\_mwh}_t,
$$
$$
\mathrm{price\_gbp\_per\_mwh}^{\mathrm{balancing}}_t
=\max(\mathrm{max\_gen\_price}_t,\mathrm{max\_bat\_price}_t,
\max_{k\in\mathrm{imports}}\mathrm{price}_{k,t}).
$$

Storage charges are settled within the current period. Bought-back storage output retains its ahead-stage remuneration, while the physical dispatch and annual delivered-energy totals use the closing net position.

The displayed market price is labelled “Average period cost (£/MWh demand)”. If \(\mathrm{total\_gen\_cost}_t\) is the accumulator of accepted-offer, storage, downward and upward charges, its unit is GBP/hour. The price in GBP/MWh and associated period expenditure in GBP are

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

This statistic describes expenditure per MWh of actual demand. Generator and storage income are calculated from the settlement accounts above. \(\mathrm{total\_gen\_cost}_t\) includes the current period's storage fee only. Final boundary supply enters the annual generation statistic, with storage discharge reported separately.

Physical operating expenditure values realised generation at composite `gen_cost`, imports at `external_price`, and accepted starts at `startup_cost` times generated MWh. `physical_cost_terms` returns `generation_variable_gbp`, `import_variable_gbp` and `startup_adder_gbp` for each period. Chapter 6 combines these components with storage depreciation, shortage valuation and annual capital costs.

## Energy balance and annual outputs

The period energy balance includes gross accepted supply, charging, exports, flexible demand and non-VRE spill. All quantities in this section are MWh. With accepted supply \(\mathrm{accepted\_supply\_mwh}_t\), recorded blackout \(\mathrm{blackout\_mwh}_t\), actual demand \(\mathrm{real\_demand\_mwh}_t\), storage charge \(\mathrm{storage\_charge\_mwh}_t\), exports \(\mathrm{export\_mwh}_t\), flexible demand \(\mathrm{flexible\_demand\_mwh}_t\) and non-VRE spill \(\mathrm{non\_vre\_spill\_mwh}_t\), the period residual is

$$
\begin{aligned}
\mathrm{residual\_mwh}_t={}&\mathrm{accepted\_supply\_mwh}_t
+\mathrm{blackout\_mwh}_t-\mathrm{real\_demand\_mwh}_t\\
&-\mathrm{storage\_charge\_mwh}_t-\mathrm{export\_mwh}_t\\
&-\mathrm{flexible\_demand\_mwh}_t-\mathrm{non\_vre\_spill\_mwh}_t.
\end{aligned}
$$

The energy account absorbs small floating-point residuals through `compatibility_adjustment_mwh`. This numerical term is applied only within the period tolerance:

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

The energy account measures total unmet demand from the physical residual and the dispatch branch's recorded blackout:

$$
\begin{aligned}
\mathrm{unserved\_mwh}_t&=\max(0,-(\mathrm{residual\_mwh}_t-\mathrm{blackout\_mwh}_t)),\\
\mathrm{closing\_residual\_mwh}_t&=\mathrm{residual\_mwh}_t
-\mathrm{blackout\_mwh}_t+\mathrm{unserved\_mwh}_t.
\end{aligned}
$$

A period with unmet demand alone closes at \(\mathrm{closing\_residual\_mwh}_t=0\). Consecutive periods with a shortfall form one event within the year. Annual outputs contain event count, period count and unserved MWh; Chapter 6 uses served demand after subtracting each shortfall component once.

The annual output aggregates generator and import MWh, storage charge and discharge, renewable curtailment, non-renewable spill, exports, flexible demand, period prices, asset income and unserved energy. Period states carry realised generation and storage batches forward; the annual model then applies the account and investment rules in Chapter 6.
