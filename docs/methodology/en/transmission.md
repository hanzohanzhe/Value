# Transmission and network constraints

## Spatial representation of zonal redispatch

Zonal redispatch determines generation adjustments, storage operation and transfers that serve each zone after a national ahead market. Each half-hour uses a lossless transport model: final injections satisfy zonal demand, corridor limits and geographical boundary capacities. The British input contains 23 zones and 22 computational corridors. The DC and AC formulations below use bus and branch inputs.

The British network inputs are supplied in `value-uk-research-suite-v1-public2`. The `zones` table defines the regions, `corridors` gives directed connections, `cutsets` assigns corridors to geographical boundaries, `ratings` supplies time-dependent limits, `asset-map` assigns resources to zones, `demand` supplies zonal MWh, and `interconnector-landings` assigns import/export assets to landing zones. B6 and B7a have symmetric capacities of 6,700 and 9,400 MW. The supplied 2025–2034 configuration holds these capacities fixed.

Asset location follows a fixed precedence. `_zone_shares_with_source` first uses `frozen_zone_shares`, then matches `asset_id` in `asset-map`, then matches it in `interconnector-landings`, and finally assigns the asset to the single zone marked `is_unconstrained_fallback`. Shares sum to 1 within a tolerance of \(10^{-8}\). An asset occupying several zones becomes a physical unit in each zone with capacity, storage power, energy and opening inventory multiplied by its share; all units retain their original investment owner.

The supplied mapping places wind and solar by site and assigns CCGT, OCGT, biomass, run-of-river hydro, nuclear, storage and imports to `ENGLAND_FALLBACK`. The fallback node connects to the declared central transport zone. Nuclear stations created from the station policy enter through that fallback, including Torness, whose geographical location is north of B6. Import resource names use `import:<country>`, while landing-table names use `interconnector:<line>`; exact identifier matching therefore sends these imports to the fallback node. These assignments determine the injections subject to the B6 and B7a constraints.

Demand follows the spatial rule selected for the case. `align_zonal_demand` preserves the network pack's zonal shares for the 23-zone study and scales them to national scenario demand. Its arrays `aligned`, `output_real`, `network_demand_mwh_by_zone` and `network_national_mwh` are MWh; zone and period indices are \(z,t\):

$$
\begin{aligned}
\mathrm{scale}_t&=\frac{\mathrm{output\_real}_t}{\mathrm{network\_national\_mwh}_t},\\
\mathrm{aligned}_{z,t}&=\mathrm{network\_demand\_mwh\_by\_zone}_{z,t}\cdot \mathrm{scale}_t.
\end{aligned}
$$

The last zone receives national demand less the sum allocated to the preceding zones. When both national totals are zero, the scale is 1; a positive scenario demand requires a positive network total. The resulting `demand_mwh_by_zone` enters the period problem with asset locations, realised availability and interconnector import/export envelopes.

## Ahead schedule and adjustment bids

The network module builds its ahead schedule from period resource availability and opening storage inventory. `_ahead_offers` gives each resource `capacity_mw * availability * period_hours` MWh at its period marginal cost multiplied by `market.bid_multiplier`, default 1. Storage offers the smaller of its discharge-power limit over the period and `soc * discharge_efficiency`, at `bid_price_gbp_per_mwh(0.0)` multiplied by the same factor. `clear_ahead` orders by `price_gbp_per_mwh` and then `offer_id`, accepts the smaller of available and remaining forecast MWh, and stops when the remaining requirement is at most `1e-12` MWh or all offers are exhausted. The last accepted price settles the ahead schedule.

Resource adjustment volumes are measured relative to `schedule_mwh_by_asset`. `_flexibility_bids` offers upward MWh equal to the positive part of available MWh less scheduled MWh and downward MWh up to the scheduled quantity. Upward prices use marginal cost times `market.bid_multiplier`. The `network-economic-v2` downward rules use `market.dec_multiplier`, default 1, and the per-technology support and nuclear-premium inputs:

|Resource|Downward price, GBP/MWh|
|---|---|
|Fuel generation|Marginal cost × downward multiplier − policy support|
|Imports|Period import price × downward multiplier|
|Wind, solar and run-of-river hydro|− policy support|
|Nuclear|Marginal cost × downward multiplier − policy support − inflexibility premium|

`resource_dec_price` reads policy support from `market.policy_support_gbp_per_mwh_by_technology`, default zero, and the premium from `network.inflexible_dec_premium_gbp_per_mwh_by_technology`, default 100 GBP/MWh for nuclear. Gas and biomass split scheduled MWh into `running_mwh` and `shutdown_mwh`: the latter equals scheduled MWh times `min_stable_fraction`. `thermal_dec_segments` retains the running price and gives the shutdown segment the `net_saving` calculation and restart table in Chapter 5. The downtime forecast includes the current period and consecutive subsequent periods whose forecast demand is covered by declared wind, solar and nuclear availability, each lasting `period_hours`. A shutdown shorter than `min_down_time_h` receives the smaller of its net saving and a price 0.01 GBP/MWh below every other downward price band.

Storage adjustment bids cover the change from scheduled discharge to final discharge or charging. `maximum_discharge` is the smaller of `discharge_power_mw * period_hours` and `soc * discharge_efficiency`; upward volume is `max(maximum_discharge - scheduled, 0)`. Downward volume is scheduled MWh plus the smaller of charging power over the period and remaining internal capacity divided by charging efficiency. `storage_dec_price` takes the minimum of the storage upward price, that price times round-trip efficiency, and the lowest available upward price in the period when such a bid exists. A declared export envelope adds a downward withdrawal bid at the nonnegative part of its export price.

Storage starts at `initial_soc_mwh`; each solved final inventory becomes the next period's opening inventory. Generation follows the period availability and accepted adjustment bounds below. The algorithm processes the supplied chronology once in time order, returning final injections, charge, discharge, inventory, corridor flows, unmet demand and settlement for every period.

## Adjustment objectives and operating constraints

Redispatch solves four linear objectives in sequence: bid expenditure including shortage cost, adjustment volume, weighted physical throughput and stable variable order. `SinglePeriodProblem` stores their coefficient arrays as `primary_objective`, `secondary_objective`, `physical_tie_objective` and `stable_tie_objective`. Each objective is its array's dot product with `values`, the period decision vector returned by `solve_lexicographic`.

The decision vector uses the implementation's variable labels. `bid:<bid_id>` is accepted nonnegative bid MWh; `flow:<corridor_id>` is signed corridor MWh; `load-shedding:<zone_id>` is unmet demand; `storage-charge:<asset_id>` and `storage-discharge:<asset_id>` are grid-side storage MWh; `absolute-flow:<corridor_id>` bounds the absolute corridor flow. In the equations, array subscripts carry these existing identifiers.

The primary objective uses the sign of each bid direction. An upward bid contributes its `price_gbp_per_mwh` times accepted MWh; a downward bid contributes the negative of that payment. Shortage is valued at `voll_gbp_per_mwh`, default 17,000 GBP/MWh:

$$
\begin{aligned}
\mathrm{primary\_objective}^{\mathsf T}\cdot\mathrm{values}={}&
\sum_{k:\mathrm{direction}=\mathrm{up}}
\mathrm{price\_gbp\_per\_mwh}_k\cdot \mathrm{values}_{\mathrm{bid}:k}\\
&-\sum_{k:\mathrm{direction}=\mathrm{down}}
\mathrm{price\_gbp\_per\_mwh}_k\cdot \mathrm{values}_{\mathrm{bid}:k}\\
&+\mathrm{voll\_gbp\_per\_mwh}\cdot
\sum_z\mathrm{values}_{\mathrm{load\mbox{-}shedding}:z}.
\end{aligned}
$$

The second objective sums accepted bid MWh and shortage MWh. The third assigns weight 1 to storage charge, storage discharge and absolute corridor flow, plus the class weight of each non-storage downward bid. `physical_dec_weight` supplies the weights below; `bid_dec_rank` selects the class:

|Downward class|Weight|
|---|---:|
|Fuel plant running range|0|
|Import|0.5|
|Run-of-river hydro|2|
|Wind and solar|3|
|Fuel shutdown|3.5|
|Nuclear|4|
|Fuel shutdown before its minimum downtime|5|

Within a zone and at an exact primary-price tie, storage charging precedes run-of-river, wind, solar and nuclear reductions; fuel shutdown follows wind and solar and precedes nuclear. Across zones, class weights also trade against corridor-flow MWh. The primary LP uses exact prices. The fourth objective weights successive variables by 1, 2, … in the fixed order of bid, corridor, zone and storage identifiers.

Final asset injection adds signed accepted bids to the ahead schedule. `final_dispatch_mwh_by_asset` and `schedule_mwh_by_asset` are MWh. The index \(k\) identifies a bid; its `asset_id` selects asset \(a\), and `asset_zone_id_by_asset` selects the zone \(z\):

$$
\begin{aligned}
\mathrm{final\_dispatch\_mwh\_by\_asset}_a={}&
\mathrm{schedule\_mwh\_by\_asset}_a\\
&+\sum_{k:\mathrm{asset\_id}_k=a,\ \mathrm{direction}=\mathrm{up}}\mathrm{values}_{\mathrm{bid}:k}\\
&-\sum_{k:\mathrm{asset\_id}_k=a,\ \mathrm{direction}=\mathrm{down}}\mathrm{values}_{\mathrm{bid}:k}.
\end{aligned}
$$

Zonal conservation equates final supply and incoming transfer to demand and outgoing transfer. Corridor direction follows its declared `from_zone_id` and `to_zone_id`:

$$
\begin{aligned}
&\sum_{a:\mathrm{asset\_zone\_id\_by\_asset}_a=z}\mathrm{final\_dispatch\_mwh\_by\_asset}_a
+\mathrm{values}_{\mathrm{load\mbox{-}shedding}:z}\\
&\quad+\sum_{l:\mathrm{to\_zone\_id}=z}\mathrm{values}_{\mathrm{flow}:l}
=\mathrm{demand\_mwh\_by\_zone}_z
+\sum_{l:\mathrm{from\_zone\_id}=z}\mathrm{values}_{\mathrm{flow}:l}.
\end{aligned}
$$

Bid capacity bounds accepted MWh between zero and `bid_capacity`; MW bids are multiplied by `period_hours = 0.5`. Shortage lies between zero and zonal demand. Generator injection lies between zero and `realised_availability_mw_by_asset` times period hours. Interconnector injection lies between negative `export_capacity_mwh` and positive `import_capacity_mwh`.

Equal-price non-storage bids share free acceptance proportionally. Upward groups share zone, direction, network effect and price; downward groups also share downward class. `_forced_down_by_bid` first sets aside the reduction required by actual availability or the interconnector envelope. For a bid and the first bid in its group, the implementation uses

$$
\begin{aligned}
\mathrm{free}&=\mathrm{bid\_capacity}_{k}-\mathrm{forced},\\
\mathrm{first\_free}&=\mathrm{bid\_capacity}_{k_0}-\mathrm{first\_forced},\\
(\mathrm{values}_{\mathrm{bid}:k}-\mathrm{forced})\cdot \mathrm{first\_free}
&=(\mathrm{values}_{\mathrm{bid}:k_0}-\mathrm{first\_forced})\cdot \mathrm{free}.
\end{aligned}
$$

Each geographical boundary limits signed flow across its member corridors. `coefficient` is the member's direction coefficient; `forward_capacity` and `reverse_capacity` are period MWh after converting any MW input:

$$
-\mathrm{reverse\_capacity}_b
\le\sum_{l\in b}\mathrm{coefficient}_{b,l}\cdot \mathrm{values}_{\mathrm{flow}:l}
\le\mathrm{forward\_capacity}_b.
$$

All boundary constraints apply together. A corridor-specific limit additionally bounds its own flow; `absolute-flow` is at least both positive and negative signed flow. Thus 6,700 MW at B6 becomes 3,350 MWh per half-hour. Corridors without individual limits remain constrained by zonal conservation and their boundary memberships.

Storage redispatch determines final internal inventory from realised charge and discharge. `opening` is `initial_soc_mwh_by_asset`; `capacity` is `energy_capacity_mwh`. For each store,

$$
\begin{aligned}
\mathrm{values}_{\mathrm{storage\mbox{-}discharge}:s}
-\mathrm{values}_{\mathrm{storage\mbox{-}charge}:s}
&=\mathrm{final\_dispatch\_mwh\_by\_asset}_s,\\
\mathrm{final\_soc\_mwh\_by\_asset}_s={}&\mathrm{opening}_s\\
&+\mathrm{charge\_efficiency}_s\cdot
\mathrm{values}_{\mathrm{storage\mbox{-}charge}:s}\\
&-\mathrm{values}_{\mathrm{storage\mbox{-}discharge}:s}/
\mathrm{discharge\_efficiency}_s.
\end{aligned}
$$

Charging and discharging lie between zero and their respective power limits times `period_hours`; final inventory lies between zero and `capacity`. Storage bids use `convex_net_power_v1`, with at most one bid per direction and a downward price at most the upward price plus \(10^{-8}\) GBP/MWh. Final simultaneous charging and discharging must be at most \(10^{-8}\) MWh. Final inventory becomes the next period's opening inventory; the national schedule and submitted bids provide the current intertemporal valuation.

Physical resource expenditure is calculated separately from bid payments. `resource_cost_gbp_per_mwh_by_asset` multiplies positive final injection, and shortage incurs VoLL:

$$
\begin{aligned}
\mathrm{physical\_resource\_cost\_gbp}={}&
\sum_a\max(\mathrm{final\_dispatch\_mwh\_by\_asset}_a,0)\\
&\qquad\cdot\mathrm{resource\_cost\_gbp\_per\_mwh\_by\_asset}_a\\
&+\mathrm{voll\_gbp\_per\_mwh}\cdot
\sum_z\mathrm{values}_{\mathrm{load\mbox{-}shedding}:z}.
\end{aligned}
$$

Network constraint cost compares this result with the same LP collapsed to one node, removing corridors and boundaries. `solve_network_free_counterfactual` retains bids, export arbitrage, import/export envelopes, storage physics, shortage valuation and solver settings. Both cases use the same period unit-cost table: supplied time-varying resource cost, otherwise annual marginal cost, storage cycle depreciation and zero export resource cost. Negative import prices can give negative period resource expenditure.

The primary-objective difference is returned as `network_constraint_bid_objective_gbp`. It measures the change in accepted bid payments and shortage valuation; `physical_resource_cost_gbp` measures resource expenditure.

## Numerical solution and boundary marginal values

The solver locks total shortage from the primary optimum before bounding its bid-cost component. `lock_primary_shedding` sets every shortage variable to zero when the primary total is zero; otherwise their sum is bounded above by that primary total. `bid_cost_coefficients` supplies the bid-only objective for the next bound.

Objective locks use a scale-aware floating-point tolerance. `compute_lock_tolerance` reads the objective `coefficients`, the preceding `optimum`, a `unit_floor` and the effective `solver_tolerance`. It computes

$$
\begin{aligned}
\mathrm{absolute\_term\_scale}&=\sum_i|
\mathrm{coefficients}_i\cdot \mathrm{optimum}_i|,\\
\mathrm{coefficient\_one\_norm}&=\sum_i|\mathrm{coefficients}_i|,\\
\mathrm{gamma\_n}&=\frac{\mathrm{nonzero\_terms}\cdot \mathrm{epsilon}}
{1-\mathrm{nonzero\_terms}\cdot \mathrm{epsilon}},\\
\mathrm{tolerance}=\max\bigl\{&\mathrm{unit\_floor},\\
&\mathrm{solver\_tolerance}\cdot\max(1,\mathrm{absolute\_term\_scale}),\\
&\mathrm{gamma\_n}\cdot \mathrm{absolute\_term\_scale},\\
&\mathrm{coefficient\_one\_norm}\cdot \mathrm{solver\_tolerance}\bigr\}.
\end{aligned}
$$

Here `nonzero_terms` counts nonzero coefficients and `epsilon` is machine precision. The effective tolerance takes the larger of the applicable solver and bound-canonicalisation tolerances. The bid-cost lock uses a \(10^{-8}\) GBP floor and default solver tolerance \(10^{-9}\); MWh locks use a \(10^{-9}\) MWh floor and solver floor \(10^{-8}\). The bid-cost acceptance ceiling is 1 GBP per period. Each later solve retains the preceding objective bounds. HiGHS dual simplex with presolve uses primal and dual tolerances of \(10^{-9}\); final equality, inequality and bound violations must be at most \(10^{-7}\).

```text
for period in the half-hour chronology:
    align_zonal_demand(...): obtain zonal demand
    build_single_period_problem(...): build bids and physical constraints
    solve_lexicographic(problem):
        minimise primary_objective; retain primary boundary marginals
        lock_primary_shedding(...); bound bid_cost_coefficients(problem)
        minimise secondary_objective; retain its objective bound
        minimise physical_tie_objective; retain its objective bound
        minimise stable_tie_objective; validate_solution(...)
    solve_network_free_counterfactual(...): compute matched comparison
    record actual injections, storage inventory, flows, shortage and costs
    pass final_soc_mwh_by_asset to the next period
return all period results
```

Boundary marginal values measure the primary objective's response to transfer capacity. `boundary_marginal_values` reads the forward and reverse constraint-row duals before objective locks are added:

$$
\mathrm{value\_gbp\_per\_mwh}_b
=\mathrm{marginals}_{\mathrm{reverse\_row}_b}
-\mathrm{marginals}_{\mathrm{forward\_row}_b}.
$$

A positive boundary value corresponds to a binding forward limit and a negative value to a binding reverse limit. Where binding boundaries share a corridor, several dual allocations can represent the same optimum. The annual output also sums absolute boundary value multiplied by transferred MWh as a congestion measure.

## DC network dispatch

The DC network module jointly selects generation, storage operation and nodal voltage angles over the complete chronology. `ReferenceDCNetworkPSM` builds the variable blocks `generation`, `charge`, `discharge`, `soc`, `blackout`, `angle` and `flow` in `layout`. Their solved values carry those names in the equations: the first five are MWh, `angle` is radians and `flow` is MW. Resource, storage, bus, branch and period indices are \(i,s,n,l,t\). `marginal_costs`, `variable_degradation_gbp_per_mwh_discharged` and `voll_gbp_per_mwh` are GBP/MWh. With fixed assets, operating expenditure is

$$
\begin{aligned}
\min\quad&\sum_{i,t}\mathrm{marginal\_costs}_{i,t}\cdot \mathrm{generation}_{i,t}\\
&+\sum_{s,t}\mathrm{variable\_degradation\_gbp\_per\_mwh\_discharged}_s\cdot
\mathrm{discharge}_{s,t}\\
&+\mathrm{voll\_gbp\_per\_mwh}\cdot\sum_{n,t}\mathrm{blackout}_{n,t}.
\end{aligned}
$$

Assets mapped to several buses become independent location-specific units through `expand_share_mappings`. The mapping field `share` sums to 1 for each asset and scales its generation capacity, storage charge and discharge power, energy capacity and initial inventory. The solver dispatches these units at their assigned buses and aggregates their outputs by original asset. VoLL reads `market.voll_gbp_per_mwh`, default 17,000 GBP/MWh.

Nodal conservation converts branch power to energy using `period_hours`. For units located at bus \(n\),

$$
\begin{aligned}
&\sum_{i\in n}\mathrm{generation}_{i,t}
+\sum_{s\in n}(\mathrm{discharge}_{s,t}-\mathrm{charge}_{s,t})
+\mathrm{blackout}_{n,t}\\
&\quad+\mathrm{period\_hours}\cdot\sum_{l:\mathrm{to\_bus}=n}\mathrm{flow}_{l,t}
=\mathrm{demand\_mwh\_by\_bus}_{n,t}
+\mathrm{period\_hours}\cdot\sum_{l:\mathrm{from\_bus}=n}\mathrm{flow}_{l,t}.
\end{aligned}
$$

Resource bounds multiply `capacity_mw`, `share`, `availability` and `period_hours`. Storage obeys the charging, discharging and inventory constraints in Chapter 8 with the same mapping share; its transition is

$$
\begin{aligned}
\mathrm{soc}_{s,t}={}&\mathrm{soc}_{s,t-1}
+\mathrm{charge\_efficiency}_s\cdot \mathrm{charge}_{s,t}\\
&-\mathrm{discharge}_{s,t}/\mathrm{discharge\_efficiency}_s.
\end{aligned}
$$

The terminal rule is free, cyclic at initial inventory, or fixed at a declared target. `allow_blackout` bounds shortage between zero and bus demand when enabled and fixes it at zero otherwise. Availability lies in \([0,1]\), and marginal resource costs are nonnegative.

AC lines and transformers use the declared equivalent reactance and angle difference. `base_mva` defaults to 100 MVA, `tap` to 1, and `phase` converts `phase_shift_degrees` to radians:

$$
\begin{aligned}
\mathrm{susceptance}_l&=\frac{\mathrm{base\_mva}}
{\mathrm{reactance\_pu}_l\cdot \mathrm{tap}_l},\\
\mathrm{flow}_{l,t}&=\mathrm{susceptance}_l\cdot
(\mathrm{angle}_{\mathrm{from\_bus},t}
-\mathrm{angle}_{\mathrm{to\_bus},t}-\mathrm{phase}_l),\\
|\mathrm{flow}_{l,t}|&\le\mathrm{thermal\_rating\_mw}_l\cdot \mathrm{circuits}_l.
\end{aligned}
$$

Circuit count scales thermal capacity; the declared equivalent reactance sets the angle equation. Each connected island has one reference bus at zero angle, with other angles bounded by \([-\pi,\pi]\). Out-of-service branches have zero flow. DC links enter nodal balance as controllable flows within their declared bounds.

HiGHS solves all periods in one linear programme with primal and dual tolerances of \(10^{-8}\). Completion requires an optimal solver status and an equality-residual limit of \(10^{-7}\). Nodal energy-balance duals provide marginal operating prices in GBP/MWh; the displayed system price is demand weighted. The output contains period dispatch, storage inventory, nodal prices and branch flows for the complete horizon.

## AC feasibility calculation

The AC module calculates steady-state power flow for a given active-power schedule. Inputs contain active and reactive demand, generator active and reactive limits, voltage setpoints, branch impedances and charging susceptance, fixed taps and phase shifts, voltage bounds and MVA ratings. Each connected island has one slack balancing asset; PV and slack buses require generation, with a common voltage setpoint for generators at one bus. Storage follows its supplied active charging and discharging schedule. PQ buses solve for voltage magnitude and angle from specified active and reactive injections; PV buses hold voltage magnitude and active power; each slack bus holds its voltage magnitude and zero angle while balancing the island.

Nodal complex injection follows the solved voltage and nodal admittance matrix. `vm` is per-unit voltage magnitude, `theta` is radians, `voltage` is complex per-unit voltage, and `injection` contains MW and Mvar. `ybus` is per-unit admittance on the `base_mva` base, and \(j^2=-1\):

$$
\begin{aligned}
\mathrm{voltage}_n&=\mathrm{vm}_n\cdot e^{j\cdot\mathrm{theta}_n},\\
\mathrm{injection}_n&=\mathrm{base\_mva}\cdot \mathrm{voltage}_n\cdot
\overline{\sum_m\mathrm{ybus}_{nm}\cdot \mathrm{voltage}_m}.
\end{aligned}
$$

Each branch uses a π impedance representation. `_ybus` computes `series` as the reciprocal of `resistance_pu` plus \(j\) times `reactance_pu`; `charging` is half the imaginary charging susceptance; and `tap` is the tap ratio multiplied by the complex phase-shift factor. The terminal admittances are

$$
\begin{aligned}
\mathrm{yff}&=(\mathrm{series}+\mathrm{charging})/|\mathrm{tap}|^2,\\
\mathrm{yft}&=-\mathrm{series}/\overline{\mathrm{tap}},\qquad
\mathrm{ytf}=-\mathrm{series}/\mathrm{tap},\\
\mathrm{ytt}&=\mathrm{series}+\mathrm{charging}.
\end{aligned}
$$

The solver fits active balance at non-slack buses and reactive balance at PQ buses, holding PV and slack voltage magnitudes fixed. The slack asset supplies residual active power and network losses. Nodal reactive generation is checked against the sum of generator limits at that bus. Complex powers `s_from` and `s_to` contain MW and Mvar; `losses` is MW. They use the declared endpoints \(f,t\):

$$
\begin{aligned}
\mathrm{s\_from}&=\mathrm{base\_mva}\cdot \mathrm{voltage}_f\cdot
\overline{\mathrm{yff}\cdot \mathrm{voltage}_f+\mathrm{yft}\cdot \mathrm{voltage}_t},\\
\mathrm{s\_to}&=\mathrm{base\_mva}\cdot\mathrm{voltage}_t\cdot
\overline{\mathrm{ytf}\cdot\mathrm{voltage}_f+\mathrm{ytt}\cdot\mathrm{voltage}_t},\\
\mathrm{losses}_l&=\operatorname{Re}(\mathrm{s\_from}+\mathrm{s\_to}).
\end{aligned}
$$

Apparent power at both terminals is limited by `apparent_power_rating_mva` times `circuits`. Every in-service branch enters the admittance matrix with its declared impedance. Topology and device settings remain fixed.

The AC solve starts from flat voltage and from an alternative state with angles spread from 0.01 to 0.03 radians and PQ voltages at the midpoint of their bounds; a declared initial voltage adds a third start. Each start is clipped to the angle and voltage bounds. `least_squares` uses `xtol = ftol = gtol = 1e-12` and `max_nfev = 2000`. A solution requires successful termination and maximum mismatch at most `residual_tolerance`, default \(10^{-7}\) MW or Mvar; the acceptable start with the smallest residual is selected.

Accepted AC solutions have start-to-start voltage/angle differences at most \(10^{-5}\) and Jacobian condition number at most \(10^{12}\). Active and reactive generation, voltage and terminal apparent power remain within declared limits to `equipment_tolerance`, default \(10^{-6}\) in their respective units. Each period returns voltages, generation, terminal flows and losses. Solving continues through the chronology; an unsuccessful period terminates the calculation.

## Optional line expansion

Line expansion screens externally specified candidates using observed congestion and declared annual benefits. Candidate records contain endpoints, circuit numbers, branch parameters and limits, construction cost, fixed operation and maintenance, lifetime, discount rate, lead time, delay, planning success and budget group. `ReferenceTransmissionExpansion.propose` computes peak `utilisation`, `annual_cost` and benefit-cost `ratio`:

$$
\begin{aligned}
\mathrm{utilisation}&=\max_{t,l\in\mathrm{trigger\_branch\_ids}}
\frac{|\mathrm{branch\_flow\_mw}_{l,t}|}{\mathrm{trigger\_branch\_rating\_mw}},\\
\mathrm{annual\_cost}&=\operatorname{\_crf}(\mathrm{discount\_rate},\mathrm{economic\_life\_years})\\
&\qquad\cdot\mathrm{total\_capex\_gbp\_per\_build}
+\mathrm{annual\_fixed\_opex\_gbp\_per\_build},\\
\mathrm{ratio}&=\mathrm{declared\_annual\_benefit\_gbp}/\mathrm{annual\_cost}.
\end{aligned}
$$

The capital-recovery function `_crf` uses annual discount fraction `rate` and lifetime `life` in years; `annual_cost` is GBP/year, `total_capex_gbp_per_build` is GBP, and `ratio` is dimensionless:

$$
\operatorname{\_crf}(\mathrm{rate},\mathrm{life})=
\begin{cases}
1/\mathrm{life},&\mathrm{rate}=0,\\
\dfrac{\mathrm{rate}\cdot(1+\mathrm{rate})^{\mathrm{life}}}
{(1+\mathrm{rate})^{\mathrm{life}}-1},&\mathrm{rate}>0.
\end{cases}
$$

Candidates already commissioned or in the planning queue are excluded from the next decision. Remaining candidates are ordered by descending `ratio` and ascending identifier. Earliest decision year, minimum trigger utilisation, minimum benefit-cost ratio, total budget and budget-group allowance determine admission; zero annual cost gives an infinite ratio. The registered parameter defaults are 0 GBP for total annual funding and \(10^{13}\) GBP per group. Each accepted proposal deducts its complete construction cost. Expected commissioning is the decision year plus `lead_time_years` and `delay_years`.

Planning success in `ReferenceTransmissionExpansion.admit` accepts a proposal when its reproducible draw `draw` is at most `success_probability`. `seed` reads `network.expansion.random_seed`, default 0. The proposal identifier is `network-proposal:{run_id}:{year}:{candidate_id}`. These inputs determine `draw` through the following calculation:

```text
digest = hashlib.sha256(
    f"{seed}:{proposal.proposal_id}".encode()
).hexdigest()
draw = int(digest[:13], 16) / float(16 ** 13 - 1)
if draw <= candidate.success_probability:
    admit the proposal into the planning queue
```

At each year's start, completed projects commission and active lines retire at commissioning year plus the ceiling of `economic_life_years`. `apply_commissioned_network_assets` inserts commissioned branches into the annual network. Line expansion is selected with its candidate table and annual budgets; the supplied 23-zone configuration keeps its network fixed.
