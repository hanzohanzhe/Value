# Operation and storage

VALUE resolves demand and supply in half-hour periods, with generation, imports, exports and storage subject to their physical capacities. This chapter defines the operating clock, staged market clearing and storage-cost calculation. Chapter 5 gives the national Native dispatch algorithm, Chapter 7 adds network constraints, and Chapter 6 links annual operating results to investment.

## Operating clock and initial storage

A model year contains 365 days and 17,520 half-hour periods in UTC. `period_start_utc` takes the zero-based `period`, divides it into `day_index` and within-day `offset`, and adds `offset×period_hours` hours to the date returned by `model_day`. With `period_hours=0.5`, the calculation is:

$$
\mathtt{day\_index}=\left\lfloor\frac{\mathtt{period}}{48}\right\rfloor,\qquad\mathtt{offset}=\mathtt{period}\bmod48.
$$

`model_day` skips 29 February. Source series are aligned to this clock before dispatch; records declared as Europe/London are converted to UTC row by row. Output timestamps use ISO 8601 with `Z`. Period energy is measured in MWh, rated power in MW and inventory in MWh.

Storage has a specified opening inventory at each model-year boundary. Native creates each year's storage agents with empty `stored_energy`; Chapter 5 defines the within-year batch updates. The chronological input used by staged, LP and DC dispatch assigns `initial_soc_mwh=0.5×energy_capacity_mwh`. These opening conditions apply each year. The preceding year's delivered sales and holding-time observations are retained for storage-cost preparation.

## Ahead market and balancing

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

## Downward bids and settlement

Downward settlement returns the accepted reduction multiplied by its bid price. Thus an upward adjustment has positive signed `delta`, a downward adjustment has negative `delta`, and both use `cashflow=delta×price_gbp_per_mwh`. The staged and network pathways construct these prices with `network-economic-v2`.

Thermal downward bids divide the ahead schedule into the running range and the minimum-stable-output segment. `thermal_dec_segments` sets `shutdown_mwh=min_stable_fraction×scheduled_mwh` and puts the remainder in `running_mwh`. Running-range price is avoided marginal cost after the downward multiplier and policy support. Shutdown price deducts restart expenditure spread across the expected shutdown interval. In `RestartParameters.net_saving`, `avoided_cost` is GBP/MWh, `restart_cost(horizon_h)` is GBP/MW per start, and `horizon_h` is hours:

$$
\begin{aligned}\mathtt{net\_saving}(\mathtt{avoided\_cost},\mathtt{horizon\_h})\\=\mathtt{avoided\_cost}-\frac{\mathtt{restart\_cost}(\mathtt{horizon\_h})}{\mathtt{min\_stable\_fraction}\times \mathtt{horizon\_h}}.\end{aligned}
$$

`shutdown_horizon_hours` counts the current period plus consecutive later periods whose forecast demand is covered by declared VRE and nuclear availability. Its returned duration is `(1+run_after[period])×period_hours`. When this duration is shorter than `min_down_time_h`, `last_resort_price` places the shutdown bid at least 0.01 GBP/MWh below the lowest rounded ordinary downward bid. Otherwise the shutdown price is its net saving. With an empty ordinary-bid set, net saving supplies the price.

CCGT uses a minimum stable fraction of 0.50, minimum downtime of 6 h and hot, warm and cold restart costs of 113.7, 134.4 and 155.0 GBP/MW. OCGT uses 0.50, 0.5 h and 175.7 GBP/MW; biomass uses 0.35, 6 h and 129.2 GBP/MW. CCGT selects hot starts below 12 h, warm starts from 12 through 48 h and cold starts above 48 h. These costs are in 2025 GBP. The running range precedes the unit’s shutdown segment; the shutdown segment precedes unsupported wind only when its net saving is positive. Wind precedes shutdown at a price tie.

Other downward prices use `resource_dec_price`. Imports return `marginal×dec_multiplier`; wind, solar and run-of-river hydro return `−support`; nuclear returns `marginal×dec_multiplier−support−premium`; other fuel resources return `marginal×dec_multiplier−support`. `market.dec_multiplier` defaults to 1 and is at most `market.bid_multiplier`. Unlisted policy support is zero, while nuclear’s default premium is 100 GBP/MWh. Storage values downward adjustment at its upward bid multiplied by round-trip efficiency. `storage_dec_price` also applies the lowest available upward price and the store's own upward price as bounds; all prices in this calculation are GBP/MWh:

```text
value = up_price_gbp_per_mwh * charge_efficiency * discharge_efficiency
if lowest_inc_price_gbp_per_mwh is not None:
    value = min(value, lowest_inc_price_gbp_per_mwh)
value = min(value, up_price_gbp_per_mwh)
```

Copperplate balancing ranks upward bids by increasing price, with storage after generation at a price tie; bids above VoLL remain outside the accepted set. It ranks downward bids by decreasing price rounded to 0.01 GBP/MWh, then by class, then by exact price. The class order is fuel running range, imports, storage, run-of-river hydro, VRE, thermal shutdown, nuclear and short-downtime shutdown. Equal-price bids of the same direction and class share acceptance in proportion to available energy.

For each equal-price group, `total` is available MWh and `fraction` is the smaller of the imbalance-to-available ratio and 1. The resulting `delta` changes `final_dispatch` and earns `cashflow`. Positive residual demand becomes `blackout_mwh`. Final supply plus blackout must match actual demand within 10⁻⁸ MWh. Zonal balancing applies the same schedule and bid definitions inside the Chapter 7 network constraints, with exact-price optimisation followed by physical tie-breaking.

A 50 MWh forecast illustrates the two settlements. Wind offers 30 MWh at £0/MWh and gas offers 30 MWh at £60/MWh. The ahead schedule accepts 30 MWh of wind and 20 MWh of gas, paying £3,000 at the common £60/MWh price. If actual demand is 55 MWh, gas supplies 5 MWh more and receives £300 in balancing. Gas physical expenditure is based on its final 25 MWh and equals £1,500.

## Storage inventory and bidding

Storage inventory follows final net injection in each period. In `CopperplateBalancing.clear`, `opening` is initial stored-side MWh and `dispatch` is final MWh delivered to the grid; a negative value denotes charging. The updated `soc` is:

$$
\mathtt{soc}=\begin{cases}\mathtt{opening}-\mathtt{dispatch}/\mathtt{discharge\_efficiency},&\mathtt{dispatch}\ge0,\\\mathtt{opening}-\mathtt{dispatch}\times \mathtt{charge\_efficiency},&\mathtt{dispatch}<0.\end{cases}
$$

Inventory remains between zero and `energy_capacity_mwh`, with a 10⁻⁸ MWh rounding tolerance. Charging and discharging respect `charge_power_mw×period_hours` and `discharge_power_mw×period_hours`. Zonal dispatch represents these directions separately and requires at most one to exceed 10⁻⁸ MWh. The closing inventory becomes the next period's `opening`; the annual opening conditions are specified above.

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

Reference annual sales use the smaller of lifetime cycles per year and physically possible charge-discharge cycles. `_reference_observation` calculates `life_cycles_per_year` from cycle life, `physical_cycles_per_year` from charge-discharge duration, and their minimum `cycles_per_year`. It then obtains annual delivered sales `sold` in MWh and holding time `dwell_periods` in model periods:

```text
life_cycles_per_year = spec.maximum_cycles / spec.economic_lifetime_years
physical_cycles_per_year = 8760 / max(2 * spec.duration_hours, 1e-9)
cycles_per_year = min(life_cycles_per_year, physical_cycles_per_year)
sold = (max(energy_capacity_mwh, 0) * max(discharge_efficiency, 0)
        * cycles_per_year)
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

The cycle term is zero when `has_cycle_depreciation` is false or either denominator factor is zero. The holding-recovery term is zero when `weighted_basis=0`. Under Native's `cycle_only` bid setting, `bid_price_gbp_per_mwh` returns `cycle_depreciation_gbp_per_mwh`: the three battery types bid their cycle wear, while pumped hydro and hydrogen bid zero. Equal-priced storage batches are released in charging order, oldest first.

The storage-cost calculation also reports recovery per holding period. The linear holding-price calculation is `cycle_depreciation_gbp_per_mwh + max(dwell_periods,0)×holding_recovery_gbp_per_mwh_period`. Staged dispatch passes `dwell_periods=0`, so its holding-price contribution is zero. The catalogue provides the life, cycle and maintenance parameters listed in Chapter 2; fixed maintenance is 13.4 GBP/kW/year for pumped hydro, 6.6 for the three battery types and 19.7 for hydrogen.

Sales update the following year's cost basis. `record_sale` takes delivered MWh and the number of periods since charging, and accumulates sales and sales-weighted holding time in `current`. Its `average_dwell_periods` is the weighted total divided by sales when sales are positive, and zero otherwise:

```text
delivered = max(delivered_mwh, 0)
dwell = max(dwell_periods, 0)
current.sold_energy_mwh += delivered
current.dwell_weighted_sold_mwh_periods += delivered * dwell
```

At year-end, `storage_cost_observations` records these quantities by storage agent. The next annual preparation takes them as `previous`, calculates the new recovery amounts and resets `current` to zero. This observation update supplies the cost calculation while the physical inventory follows the opening conditions and dispatch updates given above.
