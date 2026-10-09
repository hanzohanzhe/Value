# Transmission and network constraints

## Spatial representation of zonal redispatch

Zonal redispatch adds spatial constraints to a national ahead schedule. Each half-hour accepts upward and downward bids so that final injections satisfy zonal demand, corridor capacities and geographical boundary limits. Flow follows a lossless transport formulation with conservation and capacity constraints. The 23-zone configuration and 11-zone experiment use this representation; DC dispatch and AC feasibility use the separate methods below. These network modules operate under the corrected methodology with an eligible dataset.

Demand follows the spatial rule selected for the case. `align_zonal_demand` preserves the network pack's zonal shares for the 23-zone study and scales them to national scenario demand. Its arrays `aligned`, `output_real`, `network_demand_mwh_by_zone` and `network_national_mwh` are MWh; zone and period indices are \(z,t\):

$$
\begin{aligned}
\mathrm{scale}_t&=\frac{\mathrm{output\_real}_t}{\mathrm{network\_national\_mwh}_t},\\
\mathrm{aligned}_{z,t}&=\mathrm{network\_demand\_mwh\_by\_zone}_{z,t}\cdot \mathrm{scale}_t.
\end{aligned}
$$

The last zone receives national demand less the sum allocated to the preceding zones, preserving the total. The 11-zone experiment instead selects absolute network demand and retains the forecast-to-actual ratio from the base series:

$$
\begin{aligned}
\mathrm{output\_real}_t&=\mathrm{network\_national\_mwh}_t,\\
\mathrm{output\_forecast}_t&=\mathrm{output\_real}_t\cdot
\frac{\mathrm{research\_forecast\_mwh}_t}{\mathrm{research\_real\_mwh}_t}.
\end{aligned}
$$

A zero denominator with positive required demand is an input error. The resulting `demand_mwh_by_zone` accompanies asset locations, realised availability and interconnector import/export envelopes into `build_single_period_problem`.

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

Within a zone and at an exact primary-price tie, storage charging precedes run-of-river, wind, solar and nuclear reductions; fuel shutdown follows wind and solar and precedes nuclear. Across zones, class weights also trade against corridor-flow MWh. The primary LP uses exact prices, while copperplate balancing groups downward prices in 0.01 GBP/MWh bands. The fourth objective weights successive variables by 1, 2, … in the fixed order of bid, corridor, zone and storage identifiers.

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

All boundary constraints apply together. A corridor-specific limit additionally bounds its own flow; `absolute-flow` is at least both positive and negative signed flow. Thus 6,700 MW at B6 becomes 3,350 MWh per half-hour, and 2,200 MW on Western Link becomes 1,100 MWh. Corridors without individual limits remain constrained by zonal conservation and their boundary memberships.

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

The primary-objective difference is recorded separately as `network_constraint_bid_objective_gbp`. Forecast-error attribution compares actual-forecast and perfect-forecast network-free cases. Each comparison changes its stated spatial or forecast inputs within the same optimisation formulation.

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
    return actual injections, storage inventory, flows, shortage and costs
    pass final_soc_mwh_by_asset to the next period
```

Boundary marginal values measure the primary objective's response to transfer capacity. `boundary_marginal_values` reads the forward and reverse constraint-row duals before objective locks are added:

$$
\mathrm{value\_gbp\_per\_mwh}_b
=\mathrm{marginals}_{\mathrm{reverse\_row}_b}
-\mathrm{marginals}_{\mathrm{forward\_row}_b}.
$$

A positive value corresponds to a binding forward limit and a negative value to a binding reverse limit. Status is `computed`, `degenerate_dual` for a binding limit with zero dual, or `shared_member` when binding boundaries share a corridor and the dual allocation is non-unique. The annual sum of absolute boundary value times transfer is reported as a congestion diagnostic, separately from zonal prices, cash flows and system cost. A ledger without this calculation displays “Not computed”.

## The two zonal cases

The British 23-zone study uses the GBP1 public2 research suite, `value-uk-research-suite-v1-public2`, supplied with VALUE 0.7.0-alpha.1 through the [data page](https://value.ac/en/data/). It contains 22 computational corridors and the B6 and B7a boundaries, rated at 6,700 MW and 9,400 MW in each direction. The 2025–2034 study design holds network capacity fixed while annual demand and assets may change.

The 23-zone pack locates wind and solar by site; CCGT, OCGT, biomass, run-of-river hydro, nuclear, storage and imports are allocated to `ENGLAND_FALLBACK`. Nuclear stations created by the public2 policy enter that zone through the runtime fallback, including Torness north of B6. Import resources are named `import:<country>`, while the landing table uses `interconnector:<line>`; this mismatch also places imports in the fallback zone. `runtime_fallback_audit` records these allocations, and the resulting spatial distribution is indicative.

Staged and zonal runs declare the ledger balance boundary `full_node_v1`, enabling energy-balance assessment. The independent checks `generation_cross_path` and `demand_input_reconciliation` retain status `not_evaluated`. The default `summary` trace omits per-period solver diagnostics; the result therefore displays “Not recorded”.

The 11-zone experiment represents British regions as T1–T11 and compares transmission outcomes for a single year with fixed assets. The regions are N. Scotland, S. Scotland, N. England, N. Wales/the Mersey/the Humber, Midlands, Central England, E. Anglia, S. Wales/the Severn, S.W. England, S. England and South-East England. It uses 2022 demand and weather over 17,520 half-hours with a 2025 model background. Asset capacities remain fixed throughout the experiment, with annual investment outside its execution path.

The 11-zone network combines 13 computational corridors classified as AC assets with Western Link. Ordinary corridors connect 1–2, 2–3, 3–4, 4–5, 5–6, 5–8, 6–7, 6–8, 6–11, 8–9, 8–10, 9–10 and 10–11; Western Link connects T2→T4. The table gives geographical boundary capacities and the separate Western Link limit. The 2029 values form an independent sensitivity input, while base cases use 2025 capacities.

| Boundary | 2025 capacity in each direction, MW | 2029 sensitivity capacity, MW | Positive-flow members |
|---|---:|---:|---|
| B4 | 4,002 | 4,923 | f12 |
| B6 | 6,700 | 11,456 | f23 + fWL |
| B7a | 9,400 | 10,609 | f34 + fWL |
| B8 | 11,000 | 14,005 | f45 |
| B9 | 11,500 | 12,900 | f56 + f58 |
| EC5 | 3,300 | 5,925 | −f67 |
| LE1 | 11,223 | 13,917 | f6,11 + f10,11 |
| B13 | 3,500 | 6,575 | −f89 + f9,10 |
| Western Link | 2,200 | 2,200 | fWL |

Western Link flow consumes the stated capacity of both B6 and B7a. The 8 geographical boundaries use symmetric reverse capacities, while the Western Link input specifies a bidirectional rating. In the base reduced network, T6, T8 and T10 have identical boundary memberships, leaving modelled transfer between them without a finite upper bound. In its 14-dimensional corridor space, the nodal incidence matrix has rank 10, the geographical boundary matrix rank 8, and the matrix including the HVDC limit rank 9. The 5-dimensional constraint null space contains 3 circulation directions and 2 directions that alter nodal net transfers.

The thermal-capacity sensitivity adds separate limits to 8 southern corridors while retaining geographical boundaries. Its construction contracts known substations within each zone to the zone node, retains unknown intermediate nodes, excludes other known zones, and calculates corridor capacity by network maximum flow/minimum cut. Parallel line capacities add, while serial paths are limited by their bottlenecks; MVA is converted to MW at an assumed power factor of 1. The ordinary summer and winter inputs are shown below; separate upper-bound sensitivities use their own files.

| Corridor | Summer MW | Winter MW |
|---|---:|---:|
| T5–T6 | 19,086 | 21,052 |
| T5–T8 | 3,424 | 3,934 |
| T6–T8 | 4,436 | 5,558 |
| T6–T11 | 16,684 | 19,849 |
| T8–T9 | 8,088 | 9,217 |
| T8–T10 | 6,470 | 7,834 |
| T9–T10 | 4,434 | 5,558 |
| T10–T11 | 6,587 | 7,500 |

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

HiGHS solves all periods in one linear programme with primal and dual tolerances of \(10^{-8}\) and an equality-residual limit of \(10^{-7}\). Nodal energy-balance duals provide marginal operating prices in GBP/MWh; the displayed system price is demand weighted. Fixed assets, continuous dispatch, storage and the linear network define this full-horizon comparison.

## AC feasibility calculation

The AC module calculates steady-state power flow for a given active-power schedule. Inputs contain active and reactive demand, generator active and reactive limits, voltage setpoints, branch impedances and charging susceptance, fixed taps and phase shifts, voltage bounds and MVA ratings. Each connected island has one slack balancing asset; PV and slack buses require generation, with a common voltage setpoint for generators at one bus. Storage follows its supplied active charging and discharging schedule.

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

Nonlinear least squares solves from several initial voltage conditions. Converged solutions are checked for agreement, followed by generator active and reactive bounds, bus voltages, branch ratings and system balance among supply, charging, demand and losses. `ReferenceACFeasibilityPSM` returns the local steady-state trajectory and feasibility checks for that schedule.

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

The capital-recovery function `_crf` uses its arguments `rate` and `life`:

$$
\operatorname{\_crf}(\mathrm{rate},\mathrm{life})=
\begin{cases}
1/\mathrm{life},&\mathrm{rate}=0,\\
\dfrac{\mathrm{rate}\cdot(1+\mathrm{rate})^{\mathrm{life}}}
{(1+\mathrm{rate})^{\mathrm{life}}-1},&\mathrm{rate}>0.
\end{cases}
$$

Candidates are ordered by descending `ratio` and ascending identifier. Earliest decision year, minimum trigger utilisation, minimum benefit-cost ratio, total budget and budget-group allowance determine admission; zero annual cost gives an infinite ratio. The registered parameter defaults are 0 GBP for total annual funding and \(10^{13}\) GBP per group. Each accepted proposal deducts its complete construction cost. Expected commissioning is the decision year plus `lead_time_years` and `delay_years`.

Planning success compares a reproducible uniform draw with `success_probability`. The default seed is 0; the proposal identifier includes the run identifier, and together they define the draw. At each year's start, completed projects commission and active lines retire at commissioning year plus the ceiling of `economic_life_years`. `apply_commissioned_network_assets` inserts commissioned branches into the annual network. The 23-zone and 11-zone cases retain fixed networks; line expansion is a separately selected method.

## Data and implementation

Zonal inputs comprise `zones`, `corridors`, `cutsets`, `asset-map`, `demand`, `ratings` and `interconnector-landings`. `align_zonal_demand` applies the two demand rules, `build_single_period_problem` constructs redispatch constraints, `solve_lexicographic` solves the 4 objectives sequentially, and `ZonalRedispatchBalancing` returns actual injections, inventory and costs. The 11-zone study uses the external research scripts `build_network_data.py` and `fixed_fleet_runner.py`, with `cutsets_2025.json`, `cutsets_2029.json` and summer/winter thermal files defining its scenarios. These scripts belong to the separate fixed-asset experiment described above; the packaged British network study uses the 23-zone suite.

`network_method_rules.py` defines `network-economic-v2`. The network-free comparison is identified by `value.network-free-lp/v1`, while `zonal_results.py` assembles zonal outcomes. Each year records downward-bid assumptions in `extensions.downward_restart_economics`, using schema `value.network-downward-restart-economics/v1`; missing inputs and the resulting fallback basis accompany the calculation record.

The independent network modules use buses, branches, asset-to-bus mappings and period demand. `ReferenceDCNetworkPSM` and `validate_dc_solution` implement linear dispatch and its physical checks; `load_ac_data_from_pack`, `ReferenceACFeasibilityPSM` and `validate_ac_result` implement AC inputs, power flow and feasibility checks. `ReferenceTransmissionExpansion` reads candidates and budgets and advances construction states, while `apply_commissioned_network_assets` inserts active new lines into the network.
