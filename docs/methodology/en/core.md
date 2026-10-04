# Operation and annual feedback

The current VALUE annual workflow feeds half-hourly operation into the following year's investment and asset state. Projects advance at the start of the year, commissioned assets participate in dispatch, and annual income and capacity limits determine additions and retirements. This chapter describes the current staged market and general investment rules; the annual investment chapter gives the accounts and financing rules used in the R029 national study.

## Model clock and annual state

Each model year contains 365 days and 17,520 half-hour periods, with \(\Delta t=0.5\) h. The indices \(y\), \(t\), \(a\), \(o\) and \(k\) denote year, period, asset, economic owner and technology. Demand, scheduled output and charging or discharging in this market workflow are measured in MWh per period, rated power in MW, and storage capacity in MWh.

The annual state contains operating assets, projects awaiting commissioning, storage-pricing observations and accumulated financial quantities. Projects due at the start of a year enter the operating portfolio after their site and input conditions are checked. Annual income determines year-end decisions, and new proposals enter the construction pipeline for subsequent years. Several assets may belong to one economic owner; spatially divided physical resources and financial projects retain separate identities.

```text
Input operating assets, construction projects, demand, weather,
      technology parameters and selected modules
for each model year:
    Advance projects due for commissioning and form the operating portfolio
    Construct demand, availability and boundary-trade series
    Run the selected dispatch module; aggregate physical flows and market income
    Calculate renewable and storage expansion limits
    Allocate income to investment accounts; determine additions and retirements
    Apply planning success rates and create projects awaiting commissioning
    Update assets, construction pipeline and storage-pricing observations
Output annual operation, costs, emissions, investment and terminal asset state
```

At the end of the study window, `report_only` retains the terminal state, `pipeline_tail` advances existing construction projects, and `full_extension` extends the complete annual workflow. These options determine whether remaining projects enter service and whether operation and investment continue in subsequent years.

## Ahead market and realisation

The staged market first meets forecast demand and then adjusts the schedule against actual demand. Let \(\widehat D_t\) and \(D_t\) be forecast and actual demand, \(P_a\) rated power, \(\phi_{a,t}\) the supplied availability factor, and \(MC_{a,t}\) a time-varying or constant marginal cost. The offered energy and price of a non-storage resource are

$$
Q_{a,t}=P_a\max(\phi_{a,t},0)\Delta t,\qquad p_{a,t}=mMC_{a,t}.
$$

The bid multiplier \(m\) defaults to 1. Input conversion determines the upper bound of the availability factor, while the offer function clips negative values. This dispatch representation uses continuous energy, with generation bounded by current available capacity and intertemporal physical state represented by storage inventory. Forecast and realisation share the declared resource-availability series, and the supplied forecast and actual demand series determine the demand difference between stages.

Storage supply is limited jointly by discharge power and opening inventory. With stored-side inventory \(s_{a,t}\) and discharge efficiency \(\eta_a^d\),

$$
Q_{a,t}^{s}=\min(P_a^{dis}\Delta t,\eta_a^d s_{a,t}).
$$

Offers are sorted by increasing price and then by offer identifier. Starting with residual demand \(r_0=\widehat D_t\), sorted offer \(i\) is accepted according to

$$
q_i^0=\min\{\max(Q_i,0),r_{i-1}\},\qquad r_i=r_{i-1}-q_i^0.
$$

Clearing ends when residual demand falls to \(10^{-12}\) MWh or below. The national price \(\lambda_t\) is the price of the last accepted offer, and all accepted energy receives this common price. The price is 0 when accepted supply is zero. Any ahead shortfall is recorded and passed to the realisation stage.

Realisation uses \(g_t=D_t-\sum_aq_{a,t}^0\) to determine the adjustment direction. Generation and imports offer upward capacity \(\max(Q_a-q_a^0,0)\) at \(mMC_a\). Their downward capacity is \(q_a^0\), priced at the negative of the curtailment cost, which defaults to 0. Storage downward capacity first permits withdrawal of scheduled discharge and then charging:

$$
\overline x_a^{down}=q_a^0+
\min\left(P_a^{ch}\Delta t,\frac{E_a-s_a}{\eta_a^c}\right).
$$

Storage downward bids are priced at 0. Exports are negative injections constrained by the export-capacity series and connection location. Boundary-trade inputs specify import and export prices and availability.

Copperplate balancing accepts upward offers in ascending price order for a positive gap and downward offers in descending price order for a negative gap. Identifiers break price ties, and each acceptance is bounded by the offer quantity and remaining imbalance. With accepted adjustment \(x_j\) and direction \(\sigma_j\), final injection and balancing cash are

$$
q_a=q_a^0+\sum_{j:a(j)=a}\sigma_jx_j,\qquad
I_j^{bal}=\sigma_jx_jp_j,\qquad
\sigma_{up}=1,\quad\sigma_{down}=-1.
$$

A positive gap remaining after upward offers are exhausted becomes unserved energy \(U_t\). Feasible upward offers are accepted in price order until demand is met or offered capacity is exhausted. Final energy balance requires

$$
\left|\sum_aq_{a,t}+U_t-D_t\right|\le10^{-8}\ \mathrm{MWh}.
$$

A remaining negative gap above this tolerance stops the run. When a network module is selected, zonal redispatch adds nodal balance and transmission constraints to the same ahead schedule, as described in the transmission chapter.

Market payments and resource expenditure describe different quantities. For example, forecast demand of 50 MWh is served by wind offering 30 MWh at £0/MWh and gas offering 30 MWh at £60/MWh. The ahead schedule accepts 30 MWh of wind and 20 MWh of gas at a common price of £60/MWh, giving £3,000 in total payments. If actual demand rises to 55 MWh, gas supplies a further 5 MWh and receives £300 in balancing income. Gas operating expenditure is calculated from its final 25 MWh output and equals £1,500.

## Storage inventory and bids

Storage inventory follows final net injection. Positive \(q_{a,t}\) denotes discharge and negative values denote charging. Charging efficiency \(\eta^c\) and discharge efficiency \(\eta^d\) act on their respective directions, giving round-trip efficiency \(\eta^c\eta^d\).

$$
s_{a,t+1}=\begin{cases}
s_{a,t}-q_{a,t}/\eta_a^d,&q_{a,t}\ge0,\\
s_{a,t}-q_{a,t}\eta_a^c,&q_{a,t}<0,
\end{cases}
\qquad 0\le s_{a,t+1}\le E_a.
$$

Copperplate inventory updates allow a rounding correction of \(10^{-8}\) MWh. Zonal dispatch uses separate charging and discharging variables and rejects simultaneous charging and discharging above \(10^{-8}\) MWh.

Opening inventory in each year comes from that year's `initial_soc_mwh` input. `canonical_psm_data.py` sets this to 0 for doctoral-aligned configurations and to \(0.5E\) for ordinary configurations. Inventory is continuous within a year, and the current annual state carries storage-pricing observations forward. The following year's input determines its opening physical inventory. Directly constructed inputs use their declared inventory values. R029 carries dated inventory batches between years under the rules in the annual investment chapter.

Dynamic storage bidding divides annual equipment costs between cycle recovery and time recovery. Let \(C\) be total capital cost, \(L\) economic lifetime, \(F\) annual fixed maintenance and \(r\) the discount rate. The annual amount to recover is

$$
CRF(r,L)=\begin{cases}
1/L,&r\le0,\\
\dfrac{r(1+r)^L}{(1+r)^L-1},&r>0,
\end{cases}
\qquad A=C\,CRF(r,L)+F.
$$

The reference bid uses catalogue duration \(h\), cycle life \(N_{max}\), actual energy capacity \(E\) and actual discharge efficiency. Reference cycles, annual delivered energy and holding periods are

$$
n_{ref}=\min\left(\frac{N_{max}}L,\frac{8760}{2h}\right),\qquad
S_{ref}=E\eta^d n_{ref},\qquad d_{ref}=\max(h/\Delta t,2).
$$

Positive sales in the previous year give \(S_* =\max(S_{prev},f_{floor}S_{ref})\) and \(d_* =\max(d_{prev},2)\); otherwise the reference values apply. Previous holding time \(d_{prev}\) is weighted by delivered MWh. Defaults are \(f_{floor}=0\) and \(r=0.05\). Technologies with cycle depreciation use

$$
c_{cycle}=\frac{C}{E\eta^dN_{max}},\qquad
h_{hold}=\frac{\max(A-c_{cycle}S_*,0)}{S_*\max(d_*,1)},\qquad
p_s(d)=c_{cycle}+\max(d,0)h_{hold}.
$$

Other technologies use \(c_{cycle}=0\), and a recovery term with an invalid denominator is set to 0. `DynamicAnnualStorageCost` implements these equations. The current staged caller passes a holding time \(d=0\) and records sale ages as 0, so its realised storage bids use the cycle component. The next chapter describes national algorithms that price dated inventory batches.

Chapter 2 gives storage-catalogue durations, efficiencies, lifetimes, cycle counts and construction costs. Dynamic bidding also uses the following fixed-maintenance rates and a pumped-hydro catalogue capital cost of 360,000 GBP/MW, expressed in 2025 GBP.

|Technology|Fixed maintenance GBP/kW/year|
|---|---:|
|Pumped hydro|13.4|
|1C battery|6.6|
|0.5C battery|6.6|
|0.25C battery|6.6|
|Hydrogen storage|19.7|

The three battery technologies include cycle depreciation; pumped hydro and hydrogen storage use time recovery. Bid duration, lifetime, cycle count and fixed-maintenance rates come from the catalogue, while capital, power, energy and discharge efficiency come from the supplied asset. The asset retains its input \(E/P\). 

Alternative bid policies include fixed fees and user expressions. The fixed-fee policy uses \(p(d)=f+dh\), with supplied rates \(f\) and \(h\). User expressions can use cycle recovery, holding time, holding-recovery rate, annual cost and reference sales. 

## Current storage expansion limit

The current general expansion module estimates additional capacity from operating supply and demand duration curves. It receives accepted renewable energy \(G_t\), actual demand \(D_t\) and actual storage discharge \(d_t\), and constructs

$$
X_t=\max(G_t-D_t,0),\qquad N_t=\max(D_t-G_t-d_t,0).
$$

These inputs follow the call in `v2_module_definitions.py`. The helper also accepts explicit residual surplus or existing charging series. The current caller leaves these additional fields empty, so \(X_t\) follows directly from accepted renewable energy and demand.

The virtual store starts empty, with power and energy limits of \(10^9\) MW and \(10^9\) MWh, charging efficiency 0.98 and discharge efficiency 1. Each period charges before discharging:

$$
c_t=\min\left(X_t,P_v\Delta t,\frac{E_v-s_t}{0.98}\right),\qquad
s_t^+=s_t+0.98c_t,
$$
$$
d_t^v=\min(N_t,P_v\Delta t,s_t^+),\qquad s_{t+1}=s_t^+-d_t^v.
$$

Duration curves count hours for which charging or discharging power exceeds \(p\). With \(p_{max}\) equal to the smaller of peak charging and peak discharging power,

$$
H_c(p)=\Delta t\sum_t\mathbf1[c_t/\Delta t>p],\qquad
H_d(p)=\Delta t\sum_t\mathbf1[d_t^v/\Delta t>p],
$$
$$
B(h)=\sup\{p\in[0,p_{max}]:H_c(p)\ge h,\ H_d(p)\ge h\}.
$$

`storage_expansion_cap.py` calculates this boundary using 64 bisection steps. It returns 0 when the required duration is unattainable and \(p_{max}\) when \(h\le0\). Daily, inter-day, weekly and seasonal bands are respectively \(B(730)\), \(\max(B(365)-B(730),0)\), \(\max(B(52)-B(365),0)\) and \(\max(B(0)-B(52),0)\).

Each of the three battery technologies receives a limit of \(0.20B(365)\), while hydrogen storage receives 20% of the seasonal band. Investment accounts within a technology share its budget, and this caller uses the incremental band directly. Price and ROI are separate from this duration-curve calculation. The annual investment chapter describes the economic storage screening used in R029.

## Current investment and planning rules

General investment first allocates owner income to assets and then forms decision groups by owner, technology and region. When dispatch reports income by economic owner, `adapt_market_for_investment` uses operating-capacity shares:

$$
I_a=I_{o(a)}\frac{P_a}{\sum_{b:o(b)=o(a)}P_b}.
$$

Income belonging to an owner with several technologies therefore follows MW weights. Custom inputs require corresponding dispatch-owner and investment-owner fields. Results reported by asset enter investment accounts directly.

For an asset group, define \(P=\sum_aP_a\), \(I=\sum_aI_a\), \(O=\sum_aO_a\) and \(C=\sum_aC_a\). Operating-cost field \(O_a\) comes from `annual_operational_cost_gbp` and defaults to 0. Profit, unit capital cost, return and payback period are

$$
\pi=I-O,\qquad \kappa=C/P,\qquad ROI=\pi/C,\qquad
PB=\begin{cases}C/\pi,&\pi>0,\\\infty,&\pi\le0.\end{cases}
$$

A group with negative profit and \(\kappa>0\) retires \(\min(P,|\pi|T_{target}/\kappa)\). Otherwise, \(ROI\) above the preferred rate gives high-return investment, and \(PB\le T_{target}\) gives profit-funded investment. Both branches request \(\max(\pi/\kappa,0)\), subject to the remaining technology limit:

$$
\Delta P_k=\min\{\max(\pi/\kappa,0),H_k^{remaining}\}.
$$

Wind, solar, the three battery technologies and hydrogen storage require a positive technology limit. CCGT, OCGT, gas and biomass may use uncapped requests under the eligibility policy. Nuclear follows an exogenous construction schedule; new hydro and pumped-hydro projects require site and hydrological inputs. Groups consume the same technology budget in stable order, and concurrent policy limits use their minimum.

A group uses the maximum preferred return, minimum lifetime and target payback, maximum development time and minimum success probability among its members. Defaults are a preferred return of 0.08, lifetime of 25 years, target payback equal to lifetime, and development time of 1 year. Zero values in these fields trigger their default fallback, while a success probability of 0 remains 0. New storage inherits the group's \(E/P\) ratio.

Commissioning occurs in \(y+\max(1,\lceil development\_years\rceil)\). Expected-capacity planning multiplies power, energy, capital and total annual costs by success probability \(p\) once. Fixed-seed planning generates a deterministic draw \(u\) from the project identifier and seed, retaining the full project when \(p>0\) and \((p=1\text{ or }u<p)\). Rates, lifetimes and ratios retain their original values. `SchemeCPlanningPipelineDefinition` implements admission and sampling, while `SchemeCStateTransitionDefinition` scales assets with retirement and applies declared withdrawal years.

## Costs and emissions

System resource cost comprises annual capital recovery, fixed maintenance and actual operating expenditure for assets in service. With annual demand \(D\) and unserved energy \(U\), the cost per unit of served energy is

$$
C_{system}=C_{capital}+C_{fixed}+C_{operation},\qquad
LC_{served}=\frac{C_{system}}{D-U}.
$$

The intensity is empty when served energy is zero. Market payments, policy transfers, construction commitments and residual values are reported separately. Zonal constraint expenditure is attributed through the difference between zonal and copperplate operation from the same period-opening state, and is included in final operating expenditure.

Reliability expenditure follows the selected balancing module. The current copperplate return accumulates positive injections multiplied by resource unit costs and reports unserved energy separately. Zonal balancing includes unserved energy multiplied by VoLL. Comparisons use a common served-energy denominator and state the composition of reliability expenditure.

Operating emissions multiply actual generation by its applicable factor. For \(Q_a\) in MWh and \(e_a\) in kg/MWh, operating emissions in tonnes and total carbon intensity are

$$
M_{op}=\sum_aQ_ae_a/1000,\qquad
CI=\frac{1000(M_{op}+M_{emb,annual})}{D-U}.
$$

Chapter 9 gives factor values and their CO₂ or CO₂e labels; carbon intensity retains the emissions basis of the selected factors. Annual embodied emissions use in-service MW and annual t/MW factors. A battery-manufacturing factor expressed in kg per kWh of capacity gives annual emissions of \(Ef/L\) tonnes. Hydrogen storage treats power and energy components separately. Components lacking required factors remain unassessed, and legacy doctoral carbon scalars retain separate diagnostic units.

Storage carbon tracing uses a mixed inventory. Charging \(c\) adds \(\eta^cc\) to energy inventory and charging energy multiplied by source intensity to carbon inventory. Discharging \(d\) withdraws \(d/\eta^d\) from stored energy and transfers carbon in the same inventory fraction. Total emissions are measured at source generation; storage carbon inventory describes energy provenance and loss allocation. This tracing requires complete charging, discharging and source-intensity series.

## Data and implementation

`canonical_psm_data.py` assembles demand, resource availability, boundary trades and initial inventory into annual inputs. `staged_psm.py` constructs the ahead schedule and balancing offers, and `copperplate_balancing.py` performs price-ordered clearing. `storage_cost.py` calculates storage bids, while `storage_expansion_cap.py` gives duration-curve capacity limits. `v2_module_definitions.py` connects annual investment and planning, and `cost_ledger.py` and `carbon_ledger.py` aggregate resource expenditure and emissions.
