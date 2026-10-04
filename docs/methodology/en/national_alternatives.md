# National dispatch algorithms

VALUE provides Native and Doctoral sequential-clearing pathways for national single-node dispatch. Both allocate supply every half-hour using bids and physical states, balance aggregate national demand, and represent cross-border imports and exports as exogenous trading capacity. Native retains the original Scheme C market agents and expenditure statistics. Doctoral separates the ahead plan, realisation and state commitment, with period-by-period energy and cash checks. The current Doctoral entry point produces annual operating results. The R029 national study adds start-up event costs, technology storage pools and inventory carry-over, and connects complete annual accounts to investment, as described in the annual investment chapter.

## Inputs and agents

The national algorithms dispatch power in MW and convert it to energy using \(\Delta=0.5\) h. Forecast and actual demand are \(\widehat D_t\) and \(D_t\), available power is \(a_{i,t}\), realised power is \(g_{i,t}\), and the ramp allowance per period is \(r_i\). Standard annual inputs contain 17,520 periods. Demand in the input interface is supplied as \(\Delta\widehat D_t\) and \(\Delta D_t\) MWh.

Operating cost follows the agent-constructor parameters. Gas and biomass unit costs combine `gen_cost + fuel_cost + carbon_price + unit_time_cost`; nuclear, renewables and natural-flow hydro combine `gen_cost + unit_time_cost`. The `carbon_price` field is already expressed as expenditure per unit of generation. Ordinary generator bids in the two current national pathways are

$$
b_{i,t}=mc_i+s_i\mathbf1[i\notin\mathcal A_{t-1}],
$$

where \(c_i\) is composite unit operating cost, \(s_i\) the start-up bid adder, \(\mathcal A_{t-1}\) the previously accepted generator set, and \(m\) defaults to 1. Hydro and renewables have a zero start-up adder. R029 uses the separate start-up event equations in the annual investment chapter.

Native maps the year's operating and commissioned assets to existing market agents. It first matches names, then technology and normalised region. Multiple candidates are weighted by previously mapped capacity, constructor capacity, or equal shares, in that order. For allocation weight \(w_{aj}\) from asset \(a\) to agent \(j\), agent capacity and the income returned to assets are

$$
K_j=\sum_aw_{aj}K_a,\qquad
R_a=\sum_jR_j\frac{w_{aj}K_a}{\sum_bw_{bj}K_b}.
$$

Wind-agent capacity multipliers are \(K_j/20\), solar multipliers are \(K_j\), and conventional-generator power limits are \(K_j\). Storage power and energy are aggregated by technology. `scheme_c_native_psm.py` creates new agents each year and restores previous annual sales and sales-weighted holding time for bidding. Physical inventory follows the initial state of the newly created objects.

Doctoral constructs agents from annual asset capacities, resource availability, nuclear policy, and complete generator and storage parameter rows. These rows specify costs, efficiencies, ramps, opening output, downward prices and natural hydro or biomass budgets. A new asset may reuse a row through `doctoral_parameter_source_id`, retaining that row's ramp and budget values. Storage has equal rated charging and discharging power. Empty opening batches correspond to zero inventory; non-zero inventory is recovered with its batch ages. Direct renewable electrolysis and the common electrolyser are switched off in this Doctoral pathway.

Demand error comes directly from the supplied series \(D_t-\widehat D_t\). Compatibility filenames are `2022fd.csv` and `2022reald.csv`, with actual files bound by the data pack. `canonical_psm_data.py` forms half-hourly energy inputs using the reading and time-alignment rules in Chapter 2.

## Native availability and storage

Native derives site wind speed from the magnitude of wind components and uses the wind curves in Chapter 3. `piecewise_limit1` to `piecewise_limit4` use cut-in, rated and cut-out speeds \((3,10.5,30)\) m/s, while `piecewise_limit5` uses \((3,9.7,25)\) m/s. The kernel first calculates output for a 20 MW turbine, then applies asset-capacity multiplier \(K/20\). Solar uses the same radiation interval and normalisation as Chapter 3. Hourly values are repeated for two half-hour periods, following the compatibility clock.

Native creates stored-side MWh batches indexed by charging period. Let \(e_{b,k}\) be inventory in storage \(b\) charged during period \(k\), with rated power \(P_b\), energy \(E_b\), and current-period batch \(e_{b,t}\). Grid-side charging power is

$$
p_{b,t}^{ch}=\min\left(
X_t,\frac{E_b-\sum_ke_{b,k}}{\eta_b^c\Delta},
\left[P_b-\frac{e_{b,t}}{\eta_b^c\Delta}\right]_+
\right),\qquad
e_{b,t}\leftarrow e_{b,t}+\eta_b^cp_{b,t}^{ch}\Delta.
$$

Here \(X_t\) is the surplus power available for charging at that step. A batch can discharge at most \(\min(P_b,e_{b,k}\eta_b^d/\Delta)\), and delivery of \(q\) MW reduces inventory by \(q\Delta/\eta_b^d\). Batch offers within a stage share a declining power budget. The ahead market accepts all existing batches; balancing accepts batches aged at least 2 periods. Each stage constructs its power budget separately, so total output is read from the combined stage results.

Inventory is multiplied by \(1-\delta\) each period for self-discharge. Electrochemical and other types use \(\delta=0.000021\), pumped hydro uses 0.000001, and hydrogen storage uses 0.000005. Batches below 0.001 MWh are removed. Dynamic bidding applies the annual cost-recovery equations in the preceding chapter with actual batch age \(t-k\):

$$
b_{b,k,t}=m\{c_{cycle}+(t-k)h_{hold}\}.
$$

Native uses the selected `storage.bid-cost-function`. The dynamic policy records delivered MWh and MWh multiplied by age for the next year's bids. Positive holding fees make newer batches cheaper; zero holding fees preserve stable batch order.

## Native clearing and expenditure statistics

Native performs forecast clearing, surplus allocation and actual-demand balancing in sequence. Conventional generator acceptance is bounded by

$$
U_{i,t}=\min(g_{i,t-1}+r_i,a_{i,t}),
$$

with hydro and biomass additionally constrained by the remaining cumulative budget \(B_i-H_i\). Budget variables are cumulative MW-period values, converted to MWh by multiplying by \(\Delta\). An ordinary generator accepts the smaller of the limit and residual forecast demand. When nuclear's upper limit exceeds remaining demand \(L\), it accepts \(\max(g_{i,t-1}-r_i,L)\), with the excess entering inflexible surplus. Renewables serve remaining demand up to availability and retain the remainder as available surplus.

```text
for each half-hour:
    Update weather availability, boundary prices and capacity,
        hydro and biomass budgets; apply self-discharge
    Construct generator and storage-batch offers; stably sort by price
    Meet forecast demand subject to ramps, capacities, budgets and inventory
    if actual demand is below forecast:
        Charge storage from forecast oversupply, then from existing surplus
        Accept positive-price exports in descending external-price order
        Supply the common electrolyser, then apply downward dispatch
    else:
        Use existing surplus and charge storage with the remainder
        Merge the marginal and subsequent generators, batches aged at least
            2 periods, and import offers
        Fill the gap by price; record remaining shortage as unserved energy
    Aggregate final output, stage expenditure, income and supply-demand residuals
```

The compatibility configuration retains a common electrolyser as flexible demand. Source initial parameters are 10 MW, a ramp of 0.125 MW per period and efficiency 0.65, with overrides supplied by the running data pack. 

Natural-budget returns after downward dispatch depend on the national algorithm. Native applies its budget branch to hydro, while Doctoral applies it to hydro and biomass.

Native settles generators and storage at separate uniform prices. Ahead generator income is \(g_i^A\Delta\lambda_g^A\), while storage income is \(g_b^A\Delta\lambda_b^A\); each price is the largest accepted bid in its respective category. Balancing income follows the same categorisation. When storage alone supplies demand and the accepted generator set is empty, the current Native income function returns an empty account map.

Native's displayed price divides stage expenditure by actual demand in MW. Let \(F_t\) be the source accumulator of accepted-offer, storage, downward and upward charges. Then

$$
\overline p_t=\begin{cases}F_t/D_t,&D_t>0,\\0,&D_t=0,\end{cases}
\qquad C_t^{reported}=\Delta F_t.
$$

Annual agent income comes from separate income accounts, while the displayed price describes this stage-expenditure measure. Annual operating expenditure is \(\sum_tC_t^{reported}\) plus reported current-cycle depreciation; annual system expenditure adds annualised capital and fixed maintenance. Final boundary supply enters annual generation, while storage discharge is reported separately from this annual generation statistic.

Native retains both raw supply-demand residuals and compatibility adjustments. Using energy quantities for supply \(G_t\), unserved demand \(U_t\), forecast and actual demand \(\widehat d_t,d_t\), and recorded charging \(c_t\),

$$
c_t^{accounted}=\min\{c_t,\max(\widehat d_t-d_t,0)\},\qquad
r_t^{raw}=G_t+U_t-d_t-c_t^{accounted},
$$
$$
a_t^{compat}=\begin{cases}-r_t^{raw},&|r_t^{raw}|>10^{-9}\ \mathrm{MWh},\\0,&\text{otherwise},\end{cases}
\qquad r_t^{reported}=r_t^{raw}+a_t^{compat}.
$$

The compatibility adjustment aligns the reported quantities. The physical supply-demand relationship is assessed using \(r_t^{raw}\) together with the recorded flows. This expenditure view contains historical stage charges and bid components; physical resource-cost analysis uses separate components tied to actual operation.

## Doctoral batch inventory

Doctoral represents each batch by a raw quantity \(z_{b,k}=e_{b,k}/\Delta\), with rated inventory \(E_b/\Delta\). Reported physical inventory is \(e_{b,k}=\Delta z_{b,k}\) MWh. Self-discharge uses the preceding section's period parameters, and batch prices use fixed fee \(f_b\) and per-period holding fee \(h_b\) from the bound parameter rows:

$$
b_{b,k,t}=m\{f_b+(t-k)h_b\}.
$$

The prototype `config.py` provides the following rates. A run uses the complete storage rows bound by `doctoral_market_factory.py`; dynamic annual cost recovery is an optional Native bidding policy.

|Prototype technology|Charge efficiency|Discharge efficiency|Fixed fee \(f\)|Holding fee \(h\) per period|
|---|---:|---:|---:|---:|
|Pumped hydro|0.87|0.87|0|1.1008|
|1C battery|0.81|0.81|0|1.0558|
|0.25C battery|0.81|0.81|0|0.7369|
|0.5C battery|0.98|0.98|135.26|0.1736|
|Hydrogen storage|0.57|0.57|884.4|0.0055|

All batches and both ahead and balancing stages share the delivered-power limit of a battery. If power already delivered in the period is \(p_{b,used}^{dis}\), and remaining demand is \(L\), batch withdrawal and grid-side delivery are

$$
w_{b,k,t}=\min\left(z_{b,k},\frac L{\eta_b^d},
\frac{(P_b-p_{b,used}^{dis})_+}{\eta_b^d}\right),\qquad
q_{b,k,t}=\eta_b^dw_{b,k,t},\qquad z_{b,k}\leftarrow z_{b,k}-w_{b,k,t}.
$$

Delivered energy is \(q\Delta\). The ahead stage accepts all existing batches, and the upward stage accepts batches aged at least 2 periods. Raw balances below 0.001 are removed, corresponding to at most 0.0005 MWh per batch. The raw expenditure diagnostic retains \(w\times b\), while sale cash uses delivered MWh and the settlement price.

Charging orders storage by ascending \((f_b,h_b,\eta_b^c\eta_b^d)\). Grid-side charging power uses the raw inventory headroom:

$$
p_{b,t}^{ch}=\min\left(
(P_b-z_{b,t}/\eta_b^c)_+,X_t,
E_b/\Delta-\sum_kz_{b,k}
\right),\qquad
z_{b,t}\leftarrow z_{b,t}+\eta_b^cp_{b,t}^{ch}.
$$

The final term directly uses raw inventory headroom, giving a conservative charging bound. For the 0.5C prototype, a batch aged 4 periods bids \(135.26+4\times0.1736=135.9544\). A 10 MWh batch has raw quantity 20. Delivery of 10 MW, or 5 MWh, withdraws \(5/0.98=5.1020408\) MWh from stored energy and earns £679.772 when settled at that bid.

## Doctoral planning and realisation

Doctoral forms its ahead plan on a copy of the opening state. It updates natural budgets and self-discharge and accepts generator and storage offers in stable price order. Conventional generators use the ramp bounds above; hydro and biomass also respect remaining budgets. Nuclear retains ramp-constrained output according to \(\max(g_{i,t-1}-r_i,L)\). When nuclear is absent from the accepted set, its remembered output is multiplied by 0.99. Unaccepted renewable availability and surplus already generated by nuclear are recorded separately.

Realisation selects the adjustment direction from the power already scheduled to serve demand. Subtracting the non-renewable surplus already generated in the ahead stage gives

$$
S_t=\sum_ag_{a,t}^{A}-W_t^{A,nonVRE}.
$$

When \(D_t<S_t\), the downward target is \(S_t-D_t\). Storage charges first, existing surplus is then processed, positive-price exports are accepted in descending external-price order, and generators are curtailed in configured downward-price order. For accepted output \(g\), previous output \(g_0\), and ramp allowance \(r\), the thermal downward bound and accepted quantity are

$$
Q_i=\begin{cases}
\min(2r,g),&g-g_0=r,\\
g-(g_0-r),&g-g_0\ne r\text{ and }g_0\ge r,\\
g,&g_0<r,
\end{cases}
\qquad q_i=\min\{L_{down},\max[0,\min(g,Q_i)]\}.
$$

Hydro and biomass return curtailed quantities to their used budgets, and previous generator output is read by object identity. Non-renewable output retained by ramp limits is recorded separately as spill.

When \(D_t\ge S_t\), upward dispatch first uses existing surplus and offers remaining surplus to storage. It then starts from the last generator accepted ahead, merges that generator and subsequent generators with storage batches aged at least 2 periods and import offers, and fills the remaining gap. An empty ahead generator set starts from the first generator in the offer list.

For the accepted marginal generator, upward output is bounded by \(\min(g_{current}+r_i,a_{i,t})-g_i^{accepted}\). Unaccepted generators use \(\min(g_{current}+r_i,a_{i,t})\), with remaining-budget constraints for hydro and biomass. Imports use the original external price. Positive-price exports in this branch are accepted in ascending external-price order, and any remaining positive gap becomes unserved energy.

Final physical quantities are aggregated from the dispatch-output list, with renewable energy sent to storage and exports allocated back to its source. Let \(G\) include final generation, storage discharge and imports; \(C\) be charging, \(X\) exports, \(W\) non-renewable spill and \(d\) actual demand, all in MWh. Then

$$
U=\max(0,d+C+X+W-G),\qquad r=G+U-d-C-X-W.
$$

Commitment requires \(|r|\le10^{-7}\) MWh, non-negative generation and renewable output within availability. Storage additionally reconciles opening and closing inventory with three loss categories:

$$
E_{open}+C-D-L_{decay}-L_{conversion}-L_{numeric}=E_{close},
$$
$$
L_{conversion}=C(1-\eta_c)+D(1/\eta_d-1).
$$

Here \(C\) and \(D\) are grid-side charging and discharging energy. Inventory losses comprise self-discharge, conversion losses and small-batch removal; `COMMIT` passes closing inventory and generator output to the next period.

## Doctoral settlement and annual expenditure

Doctoral settles generators and storage separately in ahead and upward markets. Ahead cash is determined before downward realisation changes output: generator income is \(g_i^A\Delta\lambda_g^A\), and storage income is \(g_b^A\Delta\lambda_b^A\). Storage-only supply still receives its corresponding cash. Accepted downward quantity \(q_i\) uses the configured signed rate \(\kappa_i\):

$$
R_i=R_i^A+R_i^{up}+R_i^{down},\qquad
R_i^{down}=\begin{cases}
q_i\Delta\kappa_i,&i\notin\{Nuclear,VRE,Battery\},\\
0,&i\in\{Nuclear,VRE,Battery\}.
\end{cases}
$$

Downward amounts for nuclear, renewables and batteries remain historical expenditure diagnostics. Variable generation expenditure is \(g_i\Delta c_i\), import procurement is imported MWh multiplied by the external price, and storage variable operating expenditure is 0. Fuel, carbon-price and other costs decompose this variable expenditure. Export receipts and external procurement retain their separate cash directions.

Annual expenditure adds fixed maintenance, annualised capital and reliability expenditure:

$$
C_{system}=C_{variable}+C_{fixed}+C_{capital}+VoLL\sum_tU_t.
$$

Fixed and capital expenditure enter only complete 17,520-period annual summaries; both are 0 in shorter diagnostic runs. Annual generation statistics include storage discharge and boundary supply. The displayed `clearing_price` is the ahead generator price. Investment accounts read actual market cash, operating expenditure and annual capital separately to calculate profit under the following chapter's rules.

## Data and implementation

`scheme_c_native_psm.py` passes annual assets to `modular_simulation_model.py` and connects the selected storage policy through `storage_cost.py`. For Doctoral, `doctoral_market_factory.py` reads parameter rows, `doctoral_market_kernel.py` performs sequential bidding, `doctoral_market.py` manages planning, realisation and state commitment, and `doctoral_settlement.py` produces cash and expenditure components. Reconstructing either pathway requires its corresponding demand, resource availability, boundary prices and capacity, technology parameters and initial batches. Each pathway's settlement mapping supplies its annual accounts.
