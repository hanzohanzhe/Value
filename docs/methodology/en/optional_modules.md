# Perfect-foresight dispatch and natural hydrology

## Perfect-foresight single-node dispatch

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

## Available run-of-river electricity

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

## Conventional reservoir dispatch

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

## Hydrological inputs and module connection

Natural-hydrology inputs comprise the site table, asset-to-site mapping, run-of-river inflow, reservoir inflow and reservoir parameters. Sites declare technology, capacity, turbine efficiency, bus, source and licence. Pumped storage uses the electrical-storage model. Each asset is assigned to a site, with mapping shares in \((0,1]\) and total shares per asset at most 1.

Inflow CSV files provide timezone-aware timestamps, interval length, site identifiers, values and water or electrical-availability units. The adapter requires finite nonnegative values, unique timestamps and consistent units; a supplied expected chronology is checked period by period. Site, mapping and parameter tables accept JSON or CSV. The declared missing-value treatment is `none`.

The input and operating functions can be called independently. `load_hydrology_inputs_from_pack` assembles inputs, `adapt_hydrology_csv` reads inflow, `validate_site_mapping` checks mapping, `run_of_river_dispatch` calculates run-of-river electricity and `reservoir_dispatch` optimises reservoir releases. An annual market application requires an adapter connecting these inputs and outputs to its dispatch workflow, together with the relevant site, inflow, abstraction, conversion, storage and terminal parameters.
