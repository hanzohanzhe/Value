# Transmission and network constraints

## Spatial representation of zonal redispatch

Zonal redispatch adds spatial constraints to the schedule produced by the national market. Each half-hour retains the national ahead schedule and accepts upward and downward bids across zones so that final injections satisfy zonal demand, corridor limits and geographical boundary limits. The formulation represents a lossless transport network, with flows determined by nodal conservation and the declared capacity constraints. Both the 23-zone case and the 11-zone transmission experiment use this representation. DC network dispatch and AC feasibility calculations are separate optional modules defined later in this chapter.

Redispatch uses period energy as its decision quantity. Let the period length be \(\Delta t=0.5\) h, with zones, corridors, geographical boundaries, assets, bids and storage indexed by \(z,l,b,a,k,s\), respectively. Zonal demand \(D_z\), scheduled asset injection \(q_a^0\) and accepted bid magnitude \(x_k\ge0\) are measured in MWh. The direction sign is \(\sigma_k=1\) for upward adjustments and \(\sigma_k=-1\) for downward adjustments; \(p_k\) is the bid price in GBP/MWh. Corridor energy \(f_l\) is positive from the declared origin to the destination, and \(u_z\) is unserved energy. The incidence matrix \(A_{zl}\) takes 1 at the origin and −1 at the destination, so \(\sum_l A_{zl}f_l\) is net outflow from the zone.

Demand enters the model through the spatial rule selected for the case. The 23-zone case preserves the zonal shares of the network data and scales the original series \(\widetilde D_{z,t}\) to national scenario demand \(D_t\). The 11-zone experiment uses absolute demand from the network data and retains the forecast-to-actual ratio in the base demand series:

$$
D_{z,t}=D_t\frac{\widetilde D_{z,t}}{\sum_z\widetilde D_{z,t}}
\qquad\text{(23-zone)},
$$

$$
D_t=\sum_z D^{\mathrm{network}}_{z,t},\qquad
\widehat D_t=D_t\frac{\widehat D^{\mathrm{base}}_t}{D^{\mathrm{base}}_t}
\qquad\text{(11-zone)}.
$$

The final zone in the share-based calculation receives the national total less the sum of the preceding zones, preserving aggregate demand. Inputs also provide the fixed zone of each asset, its actual availability and interconnector import/export ranges. A zero denominator with positive required demand is treated as an input error.

## Adjustment objectives and operating constraints

Redispatch sequentially minimises bid payments, adjustment volume, physical throughput and a stable ordering objective. The four linear programmes share physical constraints, and each later programme retains tolerance bounds on earlier objectives. Let \(c_s,d_s\) be storage charging and discharging energy, \(h_l\ge|f_l|\), and \(v\) be the decision vector:

$$
J_1=\sum_k\sigma_kp_kx_k+V\sum_z u_z,\qquad
J_2=\sum_kx_k+\sum_z u_z,
$$

$$
J_3=\sum_s(c_s+d_s)+\sum_lh_l,\qquad
J_4=\sum_{j=1}^{n}jv_j.
$$

Both zonal cases use a value of lost load of \(V=17{,}000\) GBP/MWh. The downward payment term is \(-p_kx_k\), so the bid sign directly affects payment. \(J_2\) selects lower total adjustment, \(J_3\) selects lower storage throughput and absolute corridor flow, and \(J_4\) resolves ties through a fixed variable order. Bid, corridor, zone and storage identifiers define the fixed variable order.

Asset adjustments connect zonal energy conservation to the national schedule. Final net injection \(q_a\) combines scheduled injection with accepted signed adjustments:

$$
q_a=q_a^0+\sum_{k:a(k)=a}\sigma_kx_k,\qquad
\sum_{a:z(a)=z}q_a+u_z-\sum_l A_{zl}f_l=D_z.
$$

$$
0\le x_k\le\overline x_k,\qquad 0\le u_z\le D_z.
$$

A bid limit uses declared available MWh where provided; an MW limit is multiplied by \(\Delta t\). Ordinary generating assets satisfy \(0\le q_a\le P_a^{\mathrm{available}}\Delta t\), while interconnectors satisfy \(-E_a^{\mathrm{export}}\le q_a\le E_a^{\mathrm{import}}\). Ordinary non-storage bids sharing zone, direction, network effect, price and resource class are accepted in proportion to their available quantities. For a reference bid \(k_0\) within the group,

$$
\overline x_{k_0}x_k-\overline x_kx_{k_0}=0.
$$

A geographical boundary limits the signed aggregate flow of its member corridors. Let \(M_{bl}\) be the membership coefficient and \(C_{b,t}^{+},C_{b,t}^{-}\) the forward and reverse MW capacities. All boundaries apply simultaneously:

$$
-C_{b,t}^{-}\Delta t\le\sum_lM_{bl}f_l\le C_{b,t}^{+}\Delta t.
$$

Declared corridor-specific limits additionally impose \(-F_l^-\le f_l\le F_l^+\), while \(h_l\ge f_l\) and \(h_l\ge-f_l\) represent absolute flow. Capacities supplied directly in MWh enter the constraints as given. For example, the B6 limit of 6,700 MW becomes 3,350 MWh per half-hour, and the Western Link limit of 2,200 MW becomes 1,100 MWh. A corridor without its own limit remains subject to nodal balance and its geographical boundary memberships.

Storage inventory advances according to realised redispatch. Let \(e_s^0,e_s^1\) be initial and final internal inventory, \(E_s\) energy capacity, and \(\eta_s^c,\eta_s^d\) separate charging and discharging efficiencies:

$$
d_s-c_s=q_s^0+\sum_{k:a(k)=s}\sigma_kx_k,
$$

$$
0\le c_s\le P_s^c\Delta t,\qquad
0\le d_s\le P_s^d\Delta t,
$$

$$
e_s^1=e_s^0+\eta_s^cc_s-d_s/\eta_s^d,\qquad 0\le e_s^1\le E_s.
$$

Storage bids follow `convex_net_power_v1`, with at most one bid in each direction and \(p_{\mathrm{down}}\le p_{\mathrm{up}}+10^{-8}\). Charging and discharging are continuous variables, with final trajectories satisfying \(\min(c_s,d_s)\le10^{-8}\) MWh. Final inventory passes to the next period. Intertemporal value enters the current decision through the schedule and bids supplied by the higher-level strategy.

Bid payments and physical resource costs are accounted for separately. Bid cash flow is \(\sum_k\sigma_kp_kx_k\), while zonal operating resource cost uses actual positive injections and shortage:

$$
C_{\mathrm{zonal}}=\sum_a\max(q_a,0)c_a^{\mathrm{physical}}+V\sum_z u_z.
$$

The current copperplate balancing result uses the first term of this expression for operating cost. Comparisons therefore report unserved energy and reliability charges for each balancing method alongside their cost difference, separating generation resource expenditure from the treatment of shortage.

## Numerical solution

Redispatch solves 4 linear objectives sequentially, retaining tolerance bounds on earlier objectives in later stages. The first stage permits at most 1 GBP of payment-objective degradation per complete period; the second and third stages use numerical tolerances scaled to their objectives. HiGHS dual simplex with presolve uses primal and dual tolerances of \(10^{-9}\). Physical constraints are recalculated for the final solution, with maximum violation of equalities, inequalities and variable bounds within \(10^{-7}\).

```text
for each half-hour t:
    obtain the national ahead schedule and current storage inventory
    align zonal demand and construct available upward and downward bids
    build asset, nodal balance, corridor, boundary and storage constraints
    solve J1, J2, J3 and J4 in sequence, retaining earlier objective caps
    check physical feasibility and objective caps
    return actual injections, transfers, shortage, payments and resource costs
    pass final storage inventory to the next period
```

## The two zonal cases

The 23-zone case contains 22 computational corridors and the B6 and B7a geographical boundaries. Their forward and reverse capacities are 6,700 MW and 9,400 MW, respectively, with constant ratings across periods. The scenario covers 2025–2034 under fixed network capacity; annual changes enter through higher-level demand and asset states. Its spatial input assigns CCGT, OCGT, nuclear, run-of-river hydro, biomass and waste, and 4 storage classes to the aggregate `ENGLAND_FALLBACK` node. This aggregation determines the network location of these resources.

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

The DC network module jointly selects resource output, storage trajectories and nodal angles over a given full horizon. Let \(g_{at}\), \(c_{st}\), \(d_{st}\) and \(u_{nt}\) denote resource supply, storage charging, storage discharging and nodal unserved energy in MWh; \(F_{lt}\) denotes MW flow and \(\theta_{nt}\) denotes angles in radians. With fixed assets, the objective is

$$
\min\sum_t\left[\sum_a c_{at}^{\mathrm{marginal}}g_{at}
+\sum_s c_s^{\mathrm{deg}}d_{st}+V\sum_nu_{nt}\right].
$$

Nodal conservation connects period energy and line power through the period length:

$$
\sum_{a\in n}g_{at}+\sum_{s\in n}(d_{st}-c_{st})+u_{nt}
-\Delta t\sum_l A_{nl}F_{lt}=D_{nt},
$$

$$
0\le g_{at}\le K_a a_{at}\Delta t,\qquad
 e_{st}=e_{s,t-1}+\eta_s^cc_{st}-d_{st}/\eta_s^d.
$$

Storage satisfies power and energy bounds, with a terminal condition chosen as free, equal to initial inventory, or equal to a specified target. Unserved energy is either fixed at zero or bounded by \(0\le u_{nt}\le D_{nt}\), according to configuration. Resource availability lies in \([0,1]\), and marginal costs are nonnegative.

Active flow on AC lines and transformers follows an angle-difference relationship. Let \(S_{\mathrm{base}}\) be base capacity, \(x_l\) reactance, \(\tau_l\) tap ratio, \(\phi_l\) phase shift and \(N_l\) the number of circuits:

$$
F_{lt}=\frac{S_{\mathrm{base}}}{x_l\tau_l}
(\theta_{\mathrm{from},t}-\theta_{\mathrm{to},t}-\phi_l),
\qquad |F_{lt}|\le\overline F_l N_l.
$$

Base capacity defaults to 100 MVA and the tap ratio to 1; phase shifts are converted from degrees to radians. Circuit count scales thermal capacity, while reactance enters the angle equation at its declared equivalent value. Each connected island has one reference node with zero angle; other angles lie in \([-\pi,\pi]\). Out-of-service branches have zero flow, and DC links enter nodal balance as controllable flows within declared bounds.

Nodal prices are the marginal operating cost of nodal demand. HiGHS solves all periods in one linear programme, using primal and dual tolerances of \(10^{-8}\) and an equality-residual limit of \(10^{-7}\). Dual variables of the nodal energy balances provide prices in GBP/MWh, and the displayed system price is weighted by nodal demand. Available capacity, the linear network and storage constraints define the operating conditions of this continuous model for full-horizon cost comparisons.

## AC feasibility calculation

The AC module tests the local steady-state power flow associated with a given active-power schedule. Inputs include nodal active and reactive demand, generator active and reactive bounds, voltage setpoints, branch impedances and charging susceptances, fixed taps and phase shifts, voltage bounds and MVA ratings. Each connected island has one slack balancing asset. PV and slack buses require generators, and generators at the same bus share a voltage setpoint. Storage enters through its given active charging and discharging schedule.

Nodal complex power is calculated from complex voltage and the admittance matrix. Let \(V_n=v_ne^{j\theta_n}\) and let \(Y\) be the nodal admittance matrix:

$$
P_n+jQ_n=S_{\mathrm{base}}V_n\overline{\sum_mY_{nm}V_m}.
$$

Branches use an impedance π representation. With \(y=1/(r+jx)\), \(b_{\mathrm{sh}}=jb_{\mathrm{charge}}/2\) and \(a=\tau e^{j\phi}\), the terminal admittances are

$$
Y_{ff}=(y+b_{\mathrm{sh}})/|a|^2,\quad
Y_{ft}=-y/\overline a,\quad
Y_{tf}=-y/a,\quad Y_{tt}=y+b_{\mathrm{sh}}.
$$

The solver fits active-power balance at non-slack buses and reactive-power balance at PQ buses, holding PV and slack voltage magnitudes fixed. The slack generator supplies residual active power and network losses; nodal reactive power is checked against the aggregate limits of generators at that bus. Sending-end power and active loss are

$$
S_f=S_{\mathrm{base}}V_f\overline{Y_{ff}V_f+Y_{ft}V_t},\qquad
P_{\mathrm{loss}}=\operatorname{Re}(S_f+S_t).
$$

Apparent power at each terminal is bounded by the MVA rating multiplied by circuit count. Every in-service branch enters the admittance matrix using its declared impedance. The calculation uses fixed topology and fixed device settings.

Power flow is solved by nonlinear least squares from multiple initial conditions. The model checks consistency of voltage magnitudes and angles across converged solutions, then tests generator active and reactive limits, bus voltages, branch MVA limits and system balance among supply, charging, demand and active losses. Outputs describe local steady-state feasibility and power-flow trajectories for the given active-power schedule under fixed topology and device settings.

## Optional line expansion

The line-expansion module screens candidates using observed congestion and externally supplied benefits. Candidate data contain endpoints, line parameters, circuit numbers and limits, capital cost, fixed operation and maintenance, lifetime, discount rate, lead time, delay, planning-success probability and budget group. For candidate \(k\), annual peak utilisation of its trigger branches and the benefit-cost ratio are

$$
U_k=\max_{t,l\in\mathrm{trigger}_k}\frac{|F_{lt}|}{R_k},\qquad
AC_k=CRF(r_k,L_k)CAPEX_k+FOM_k,
$$

$$
CRF(r,L)=\frac{r(1+r)^L}{(1+r)^L-1},\quad CRF(0,L)=1/L,
\qquad BCR_k=\frac{B_k^{\mathrm{declared}}}{AC_k}.
$$

Candidates are screened in descending benefit-cost ratio and ascending identifier order. Earliest decision year, the peak-utilisation threshold, minimum benefit-cost ratio, total budget and budget-group allowance determine admission. A zero annual cost produces an infinite benefit-cost ratio. Standard parameter defaults are 0 GBP for total annual budget and \(10^{13}\) GBP per budget group, so positive total funding activates proposals. Each accepted proposal deducts its complete construction capital cost, and expected commissioning is the decision year plus lead time and delay.

Planning success is determined by a reproducible uniform number generated from the seed and proposal identifier. A value above the success probability marks planning failure. The default seed is 0, and the proposal identifier includes the run identifier, so both define the random experiment. At the start of each year, projects commission on completion and retire in their commissioning year plus the ceiling of economic lifetime. Active new branches enter the next annual network topology. The 23-zone and 11-zone cases retain fixed networks; this screening rule is a separately selected expansion method.

## Data and implementation

Zonal inputs comprise `zones`, `corridors`, `cutsets`, `asset-map`, `demand`, `ratings` and `interconnector-landings`. `align_zonal_demand` applies the two demand rules, `build_single_period_problem` constructs redispatch constraints, `solve_lexicographic` solves the 4 objectives sequentially, and `ZonalRedispatchBalancing` returns actual injections, inventory and costs. `build_network_data.py` constructs the 11-zone network; `cutsets_2025.json`, `cutsets_2029.json` and the summer/winter thermal files supply its capacity scenarios. `fixed_fleet_runner.py` executes the fixed-asset experiment.

The independent network modules use buses, branches, asset-to-bus mappings and period demand. `ReferenceDCNetworkPSM` and `validate_dc_solution` implement linear dispatch and its physical checks; `load_ac_data_from_pack`, `ReferenceACFeasibilityPSM` and `validate_ac_result` implement AC inputs, power flow and feasibility checks. `ReferenceTransmissionExpansion` reads candidates and budgets and advances construction states, while `apply_commissioned_network_assets` inserts active new lines into the network.
