# Perfect-foresight dispatch and natural hydrology

## Perfect-foresight single-node dispatch

The perfect-foresight module jointly schedules generation, imports and storage across a complete time series with given asset capacities. It provides an optional single-node resource-cost comparison for national operation, with capacity investment supplied by the outer model. Inputs include period demand, resource availability and marginal cost, storage power and energy capacities, efficiencies and initial inventory. The standard application uses a half-hourly clock.

Resources and storage enter the model as period energy. Let \(x_{it}\) be resource supply, \(c_{st},d_{st}\) grid-side charging and discharging, \(S_{st}\) end-period internal inventory, and \(b_t\) unserved energy, all in MWh. Resource capacity is \(C_i\) MW, availability is \(a_{it}\in[0,1]\), nonnegative marginal cost is \(m_{it}\) GBP/MWh, and storage discharge degradation cost is \(\delta_s\) GBP/MWh. The operating objective is

$$
\min J=\sum_t\left[\sum_i m_{it}x_{it}+\sum_s\delta_sd_{st}+Vb_t\right].
$$

Supply balance and storage continuity are

$$
\sum_i x_{it}+\sum_s d_{st}+b_t-\sum_s c_{st}=D_t,
$$

$$
S_{st}=S_{s,t-1}+\eta_s^cc_{st}-d_{st}/\eta_s^d.
$$

Resource output satisfies \(0\le x_{it}\le C_ia_{it}\Delta t\); storage power bounds are \(0\le c_{st}\le P_s^c\Delta t\) and \(0\le d_{st}\le P_s^d\Delta t\); and inventory satisfies \(0\le S_{st}\le E_s\). Inventory here measures internal energy, so separate charging and discharging efficiencies enter the transition. Every available resource can supply charging through the single-node balance.

Initial and terminal inventory rules determine storage's net energy exchange over the study horizon. Initial inventory is supplied for each asset. The default cyclic rule equates final and initial inventory; fixed uses a supplied target; free allows terminal inventory anywhere within its bounds. When shortage is allowed, \(0\le b_t\le D_t\); otherwise \(b_t=0\). Defaults are \(\Delta t=0.5\) h, \(V=10{,}000\) GBP/MWh and \(\delta_s=0\), with value of lost load configurable from 0–1,000,000 GBP/MWh.

Two-stage linear optimisation selects physical trajectories at equivalent cost. The first stage minimises \(J\). The second retains the original constraints and adds

$$
J\le J^*+\varepsilon,\qquad
\varepsilon=\max(10^{-7},10^{-10}|J^*|),
$$

while minimising \(\sum_{s,t}(c_{st}+d_{st})\). Both stages use HiGHS with primal and dual feasibility tolerances of \(10^{-8}\). The final trajectory requires \(\max_{s,t}\min(c_{st},d_{st})\le10^{-6}\) MWh. Unused renewable energy is available output less actual supply.

Prices are the first-stage marginal operating cost of period demand. The supply-balance dual \(p_t\) has units GBP/MWh, while physical output follows the second-stage trajectory. Resource revenue is \(\sum_t p_tx_{it}\), net storage market revenue is \(\sum_t p_t(d_{st}-c_{st})\), and consumer payment is \(\sum_t p_t(D_t-b_t)\). System cost adds the annualised capital and fixed-maintenance fields of operating assets to variable resource expenditure, storage degradation and shortage cost.

```text
read the complete chronology, resource availability, costs and storage states
expand scalar availability or cost inputs to the declared time horizon
build period energy balance, resource limits and storage transitions
LP1: minimize variable resource cost, degradation and shortage cost
retain the LP1 optimum within the declared cost tolerance
LP2: minimize total storage charging and discharging
verify the solution and calculate unused renewable energy
return LP2 trajectories, LP1 demand duals and separate cost components
```

`PerfectForesightPSM` constructs and solves this problem, and `validate_chronology` checks period inputs. Resource availability in `PSMInput.chronology` may be a scalar or a complete series; marginal cost may be a scalar, a single-element series or a complete series. Storage inputs provide power, energy, efficiencies and the terminal rule. Hydro in this input acts as an ordinary resource with specified availability. Natural inflows and reservoir inventories follow the independent hydrological methods below.

## Available run-of-river electricity

Run-of-river hydro converts current inflow into current available electricity. Site parameters comprise the bus, capacity \(P\), turbine efficiency \(\eta\), period length \(\Delta t\) and water-to-energy coefficient \(\kappa\). For an input already expressed as a normalised electrical availability factor \(u_t\in[0,1]\),

$$
A_t=P\Delta t\,u_t.
$$

For an input expressed as period water volume \(I_t\), turbine conversion and the power limit jointly determine

$$
A_t=\min(P\Delta t,\kappa\eta I_t).
$$

Accepted generation satisfies \(0\le G_t\le A_t\), defaulting to all available energy. Unused electrical potential is \(A_t-G_t\). For example, \(P=10\) MW, \(\Delta t=0.5\) h and availability factors \([0,0.5,1]\) give \([0,2.5,5]\) MWh of available electricity. Run-of-river calculation is period-local; conventional reservoirs separately represent intertemporal regulation.

## Conventional reservoir dispatch

A conventional reservoir schedules releases over complete inflow and electricity-value series to maximise generation value. Period decisions are turbine release \(q_t\), ecological bypass \(e_t\), spill \(w_t\) and end-period volume \(S_t\). The first three are water volume per period, and inventory is water volume. Given electricity value \(p_t\), the objective is

$$
\min -\sum_t p_t\kappa\eta q_t+10^{-9}\sum_t w_t.
$$

Water continuity and storage bounds constrain releases across time:

$$
S_t=S_{t-1}+I_t-q_t-e_t-w_t,\qquad
S_{\min}\le S_t\le S_{\max}.
$$

Turbine, ordinary-release and ecological requirements are

$$
0\le q_t\le q_{\max},\qquad
0\le e_t\le R_{\max},\qquad w_t\ge0,
$$

$$
r_{\min}\le q_t+e_t\le R_{\max},\qquad
G_t=\kappa\eta q_t.
$$

The ordinary-release ceiling and ecological minimum both apply to \(q_t+e_t\), with spill entering water balance separately. Initial volume is supplied explicitly. An optional terminal target \(S_T\) adds a final equality; other configurations allow terminal volume within the storage bounds. Parameters also satisfy \(R_{\max}\ge q_{\max}\) and \(\kappa\eta q_{\max}\le P\Delta t+10^{-9}\), keeping turbine water release consistent with electric power.

Reservoir dispatch uses one full-horizon linear programme. The algorithm reads all inflows and values together, solves with SciPy/HiGHS, and returns period water volumes, generation and conservation residuals. Its reported objective includes the small spill penalty. The input labels `myopic`, `rolling_horizon` and `perfect_foresight` all call this same full-horizon algorithm, with the label returned as metadata. The mathematical definition in this chapter therefore uses perfect foresight.

```text
read site parameters, complete inflow and external electricity values
validate water units, turbine conversion, power limits and storage boundaries
build turbine release, ecological bypass, spill and end-period storage
enforce water balance, ecological release and optional terminal storage
solve the full-horizon linear programme
return electricity generation, water trajectories and balance residuals
```

## Hydrological inputs and module connection

Natural-hydrology studies require five input roles: the site table, asset-to-site mapping, run-of-river inflow, reservoir inflow and reservoir parameters. Sites are classified as run-of-river or conventional reservoir and include capacity, efficiency, bus, source and licence. Pumped storage retains the electrical-storage model. The applicable mapping assigns each asset to a single site, with mapping shares in \((0,1]\) and total shares per asset at most 1.

Inflow uses CSV series with timezone-aware timestamps. The adapter filters by site and requires finite nonnegative values, unique period identifiers and consistent units. If an expected period sequence is supplied, the complete order is checked entry by entry. Metadata declare interval length and timezone, with missing-value treatment set to none. Site, mapping and parameter tables accept JSON or CSV; the inflow reader uses the CSV adapter.

Hydrological functions can be called independently for run-of-river and conventional-reservoir studies. `load_hydrology_inputs_from_pack` assembles inputs, `adapt_hydrology_csv` converts inflow, `validate_site_mapping` processes asset mapping, `run_of_river_dispatch` calculates run-of-river electricity, and `reservoir_dispatch` solves reservoir operation. Connecting these hydrological inputs to the annual market workflow requires dedicated integration. British applications additionally require the relevant sites, inflows, abstraction conditions, conversion coefficients, storage capacities and terminal rules.
