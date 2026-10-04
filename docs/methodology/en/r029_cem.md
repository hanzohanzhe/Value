# Annual investment and asset evolution

The R029 national study uses annual operating income to drive expansion, financing and retirement. It covers 2025–2034, with 17,520 half-hour periods per year and the `thesis_final9.6` investment rules. Its `basic` scenario sets capacity-market, ancillary-service and decarbonisation-support budgets to zero. Renewable and storage expansion fractions are both 0.20, and investment decisions use complete annual operating accounts.

## Connecting national operation across years

R029 charges start-up expenditure when a physical start occurs. Let \(K_i\) be asset nameplate capacity, \(s_i\) the start-up rate in GBP/MW, and \(g_{i,t-1}\) and \(g_{i,t}\) the opening and final output. Power \(g\) is measured in MW, \(\Delta=0.5\) h, \(c_i\) is composite variable expenditure in GBP/MWh, and \(m\) is the bid multiplier. Generator bids use \(mc_i\), while operating expenditure includes

$$
z_{i,t}^{start}=\mathbf1[g_{i,t-1}\le10^{-7}\ \land\ g_{i,t}>10^{-7}],
$$
$$
C_{i,t}^{start}=z_{i,t}^{start}K_is_i,\qquad
O_{i,t}^{var}=g_{i,t}\Delta c_i+C_{i,t}^{start}.
$$

Start-up expenditure uses the nameplate MW of the entire dispatch asset and is measured in GBP per event. Existing nuclear retains positive initial output from its source parameters. Fuel, carbon-price, other operating and start-up expenditure jointly form actual variable expenditure, while income follows the national settlement rules.

R029 combines 1C, 0.5C and 0.25C batteries and hydrogen storage into one national physical pool per technology. Members share \(E/P\), efficiencies and operating-bid parameters; pumped hydro retains separate asset representation. Pool capacities and allocation to projects are

$$
P_k^{pool}=\sum_{a\in k}P_a,\qquad E_k^{pool}=\sum_{a\in k}E_a,\qquad
X_a=X_k^{pool}\frac{P_a}{P_k^{pool}}.
$$

Quantity \(X\) may represent actual income, operating expenditure or a physical pool total. `allocate_pool_amounts` distributes it by operating MW, with the final member receiving the rounding remainder. Project capital, financing, commissioning and withdrawal dates remain separate. Domestic asset cash and boundary-trade cash are aggregated separately.

Inventory retains batch ages through absolute charging periods. Positive holding fees and bid multipliers give newer batches priority; exact price ties follow original clock order. Generator, storage-batch and import streams are merged stably. Each pool shares its power limit across all batches and both ahead and balancing stages. `PriceLots` and `PriceInventory` retain remaining batches and apply self-discharge through a common inventory scale.

Annual state carries closing batches, the absolute clock and generator memory forward. When storage capacity changes from \(E_{old}>0\) to \(E_{new}\), each previous batch is multiplied by

$$
f=\min(1,E_{new}/E_{old}),\qquad e_{k,new}=fe_{k,old},\qquad
W^{retire}=\sum_ke_{k,old}-\sum_ke_{k,new}.
$$

Expansion preserves existing inventory, contraction writes inventory off in proportion to capacity, and complete withdrawal clears the store. This energy is recorded as retirement loss, with zero associated sales or receipts. New generators use their own opening output, and withdrawn generators leave the operating state.

## Annual accounts and decision units

Investment accounts combine actual ahead income, signed balancing income, variable expenditure, fixed expenditure and annualised capital. For project \(a\), let capacity-market, incremental decarbonisation and ancillary-service income be \(I_a^{CM}\), \(I_a^{decarb}\) and \(I_a^{AS}\), annual fixed expenditure \(F_a\), and annualised capital \(A_a\). Operating surplus and annual profit are

$$
S_a=I_a^{ahead}+I_a^{bal}+I_a^{CM}+I_a^{decarb}+I_a^{AS}-O_a^{var}-F_a,
\qquad \Pi_a=S_a-A_a.
$$

`build_thesis96_asset_accounts` constructs these accounts from complete annual cash flows. `net_revenue_gbp` corresponds to \(S_a\), and `net_profit_gbp` to \(\Pi_a\). Retired projects with financing obligations retain expenditure accounts and use their declared operating income.

Investment decisions are grouped by owner and technology, then allocated across regions. Retired financed assets in a group continue to contribute \(S_a\) and \(A_a\); operating MW and regional shares use active members. Exogenous REPD projects retain separate reporting accounts, while endogenous investment requires an investment owner. Nuclear and direct electrolysis use exogenous representations, and new natural-flow or pumped hydro requires additional site inputs.

For group \(i\), let operating capacity be \(P_i\), operating surplus \(S_i\), annualised capital \(A_i\), and unit new-build capital \(\kappa_i\) the capacity-weighted average of members' capital per MW. An eligible decision group requires \(A_i>0\) and \(\kappa_i>0\). Return and decision class are

$$
\Pi_i=S_i-A_i,\qquad R_i=\Pi_i/A_i,
$$
$$
class_i=\begin{cases}
High,&S_i>A_i(1+r_i),\\
Profit,&\Pi_i>0\text{ and }S_i\le A_i(1+r_i),\\
Deplete,&S_i<0,\\
Nothing,&\text{otherwise}.
\end{cases}
$$

The high-return class uses a strict inequality, so a profitable group exactly at the threshold enters Profit. Assets with \(S_i\ge0\) and \(\Pi_i\le0\) remain in operation. Preferred returns are 0.076 for solar and onshore wind, 0.089 for offshore wind, and 0.12 for the four expandable storage technologies. Other technologies use the largest bound member parameter; R029 CCGT and OCGT both use 0.089.

Loss-driven retirement uses target payback \(T_i\). Solar uses 25 years, onshore and offshore wind 30, CCGT and OCGT 25, biomass 20, the three batteries 10, and hydrogen storage 25. The literal technology key `gas` uses 20 years. This horizon enters the retirement quantity below, while the return denominator remains annualised capital.

## Storage opportunities and economic screening

R029 storage expansion uses complete renewable availability and existing storage charging and discharging. Define half-hour energy demand \(D_t\), existing charging \(C_t^{existing}\), available renewables \(V_t^{available}\), and existing discharge \(D_t^{existing\ storage}\). Then

$$
N_t=D_t+C_t^{existing}-V_t^{available}-D_t^{existing\ storage},\qquad
X_t=\max(-N_t,0),\qquad Z_t=\max(N_t,0).
$$

Here \(X_t\) is charging surplus and \(Z_t\) remaining demand. Discharge earns the same-period ahead clearing price \(p_t\). `doctoral_expansion_inputs.py` aligns demand, dispatch, prices and renewable availability weighted by operating capacity period by period.

Each candidate technology independently dispatches an initially empty virtual store with a 100 TWh energy limit. Rated energy is \(E_v=100,000,000\) MWh, power is \(P_v=E_v/h\), charging and discharging ratings are equal, and per-period inventory retention is 1. Duration and efficiency tuples are \((h,\eta_c,\eta_d)=(1,0.81,0.81)\) for 1C, \((2,0.98,0.98)\) for 0.5C, \((4,0.81,0.81)\) for 0.25C, and \((250,0.57,0.57)\) for hydrogen. The four replays evaluate supply-demand opportunities for each technology separately.

The virtual power axis is divided into continuous layers of width \(w\) MW, with per-MW inventory \(s\in[0,h]\) measured in MWh/MW. Each period allocates charging budget \(X\) from the lowest capacity coordinate, then allocates discharge budget \(Z\) in the same order. With inventory-retention factor \(\rho\), per-MW bounds and updates are

$$
\overline c=\min\left(0.5,\frac{h-\rho s}{\eta_c}\right),\qquad s^+=\rho s+\eta_cc,
$$
$$
\overline d=\min(0.5,\eta_ds^+),\qquad s'=s^+-d/\eta_d.
$$

A budget exhausted inside a layer splits it exactly into accepted and residual portions. Adjacent layers may merge when their physical and financial histories are identical. Physical replay follows capacity order, and prices are subsequently used for economic screening. Closing inventory is retained, and income accumulates from actual discharge.

Layer \(\ell\) earns \(I_\ell=\sum_tp_td_{\ell,t}\), incurs annualised capital \(A_\ell=w_\ell a_k\), and incurs maintenance \(O_\ell=w_\ell f_k+Q_\ell^co_k^c+Q_\ell^do_k^d\). Here \(d_{\ell,t}\) is period discharge from the whole layer, while \(Q_\ell^c,Q_\ell^d\) are its annual charging and discharging energy, all in MWh. Rates \(a_k,f_k\) are annual capital and fixed maintenance in GBP/(MW·year), and \(o_k^c,o_k^d\) are variable charging and discharging rates in GBP/MWh. 

Charging procurement and variable charging or discharging expenditure are 0 for the candidate technologies, while fixed maintenance follows the catalogue. Annualisation uses a 5% cost of capital and technology lifetime, with battery construction split into equipment and development components below.

$$
\Pi_\ell=I_\ell-O_\ell-A_\ell,\qquad
qualified_\ell\iff I_\ell-O_\ell\ge1.12A_\ell,\qquad
H_k=0.20\sum_{\ell:qualified}w_\ell.
$$

Screening includes layers exactly at the 12% threshold. Equivalent cycles are \(Q_\ell^d/(\eta_dE_\ell)\), while half-hours with discharge are reported separately. Tail capacity that never charges leaves the candidate set. `dispatch_virtual_storage` performs continuous-layer replay, and `assess_virtual_storage` calculates expenditure and qualifying MW.

```text
N ← demand + existing charging − available renewables − existing discharge
X ← max(−N,0); Z ← max(N,0)
for each candidate storage technology:
    Create an empty 100 TWh virtual store and continuous capacity axis
    for each half-hour:
        Allocate charging and discharging in capacity-coordinate order
        Split layers at budget cut-offs; accumulate delivered energy
            and income at the period price
        Reconcile inventory; merge adjacent layers with identical
            physical and financial histories
    Screen layers for a 12% return using income, maintenance and annual capital
    Multiply total qualifying MW by 0.20 to obtain technology opportunity H
```

Renewable expansion uses the boundary of 200 negative-net-demand periods in the weather and availability chapter, with the 0.20 expansion fraction. Both types of limits enter annual investment allocation.

## Investment quantities and funding

Retained profit can purchase \(b_i=\max(\Pi_i,0)/\kappa_i\) MW for group \(i\). For renewables, operating-capacity share \(s_i=P_i/\sum_{j:k(j)=k}P_j\) allocates technology headroom as \(h_i=s_iH_k\). Requests are

|Decision and technology|Requested addition MW|
|---|---|
|High renewables|\(h_i\)|
|Profit renewables|\(\min(h_i,b_i)\)|
|High CCGT, OCGT and biomass|\(0.01P_i\)|
|High storage|\(\max(H_k,b_i)\)|
|Profit other eligible technologies|\(b_i\)|
|Deplete or Nothing|0|

Several High storage accounts within one technology share capacity while retaining profit-funded floors. Let requests be \(q_i\), summing to \(Q\). The total allocation is

$$
B=\max\left\{\sum_ib_i,\min(Q,H_k)\right\}.
$$

Allocation starts at \(Bq_i/Q\). Any account below its profit-funded floor \(b_i\) receives that floor first; the remaining budget is redistributed in proportion to the other requests until complete. Retained-profit purchasing capacity can therefore exceed technology opportunity \(H_k\). Profit storage invests directly at \(b_i\). Loss-making groups separately retire \(\min(P_i,-S_iT_i/\kappa_i)\).

Final addition \(\Delta P_i\) requires capital expenditure \(C_i=\kappa_i\Delta P_i\). Retained-profit funding and external finance are

$$
E_i=\min\{\max(\Pi_i,0),C_i\},\qquad B_i=C_i-E_i.
$$

After the owner determines its total, projects are allocated by existing regional MW shares. New storage inherits regional members' \(E/P\), the minimum lifetime, maximum development period and minimum success probability. Planned commissioning is \(y+\max(1,\lceil development\_years\rceil)\). External finance is a funding source specified by these decision rules.

For example, a renewable group has 100 MW, technology-wide capacity of 1,000 MW, headroom of 200 MW, unit capital of £1m/MW, annualised capital of £10m, operating surplus of £11m and a 7.6% threshold. Its £1m annual profit gives a 10% return, placing it in High with a 20 MW request. Retained profit funds £1m and external finance funds £19m.

## Annual charges and loan repayment

The three battery technologies split construction expenditure between equipment and development. With equipment share \(\theta=C_{equipment}/(C_{equipment}+C_{development})\), total annual construction recovery \(J\) and fixed maintenance \(M\) are classified as

$$
A=\theta J,\qquad F=M+(1-\theta)J,\qquad A+F=J+M.
$$

Equipment recovery enters annualised capital, and development recovery enters fixed expenditure. This classification also determines the capital denominator of investment returns. Other technologies use \(\theta=1\).

|Technology|Equipment GBP/MW|Development GBP/MW|Total construction GBP/MW|
|---|---:|---:|---:|
|1C battery|130,000|200,000|330,000|
|0.5C battery|160,000|190,000|350,000|
|0.25C battery|230,000|185,000|415,000|

Endogenous projects draw finance on commissioning. For equity \(E\), debt \(B\), positive integer lifetime \(L\) and borrowing rate 0.05, annual debt payment is \(M_B=B\,CRF(0.05,L)\). Opening principal \(B_n\) gives interest and principal repayment

$$
interest_n=0.05B_n,\qquad
principal_n=\min\{B_n,\max(M_B-interest_n,0)\},\qquad
B_{n+1}=B_n-principal_n.
$$

The final year clears remaining principal. Equity is recovered linearly at \(E/L\), giving annual construction recovery

$$
J_y=E/L+interest_y+principal_y.
$$

Equity recovery and debt payments are zero after year \(L\). Projects retired physically before then continue their committed recovery and debt obligations, which remain in annual accounts. Construction retains an undrawn-finance state, and debt interest begins in the commissioning year.

Expected-capacity planning multiplies project power, energy, capital, annual charges, equity and debt commitments by success probability once. The financial schedule is prepared before operation and settled after acceptance of the complete year. `doctoral_finance.py` manages drawdown and repayment, and `doctoral_storage_costs.py` classifies battery expenditure.

## Policy scenarios

R029 uses `basic`, with all policy budgets set to zero. Optional scenarios `with_cm`, `decarbonisation_base`, `subsidy_as_usual` and `governmental_target` use explicit annual budgets and technology targets in 2025 GBP. All non-`basic` scenarios enable the capacity market and ancillary services; the latter three also include existing decarbonisation support.

When the capacity market is enabled, a fixed annual budget of £5.44bn is allocated by de-rated capacity:

$$
I_a^{CM}=5.44\times10^9\frac{f_{k(a)}P_a}{\sum_bf_{k(b)}P_b}.
$$

|Technology|De-rating factor|
|---|---:|
|CCGT, OCGT and biomass|0.95|
|Nuclear|0.85|
|Pumped hydro|0.95|
|1C battery|0.05|
|0.5C battery|0.15|
|0.25C battery|0.60|

Hydrogen-storage eligibility factors are supplied explicitly by the scenario. Ancillary services are allocated by operating MW of thermal, nuclear and storage assets. `subsidy_as_usual` and `governmental_target` allocate incremental decarbonisation budgets by eligible renewable MW. The target scenario ends a technology's eligibility when its operating capacity reaches the specified target.

Existing decarbonisation support enters the policy-cost report, while incremental support enters eligible investment income. Budgets remain unallocated when eligible capacity is zero. `allocate_thesis96_policy` calculates these transfers from the scenario, annual budgets, de-rating factors and capacity targets.

The historical thesis expenditure view includes policy levies and unserved energy valued at £8,000/MWh in the numerator, with non-battery generation, including imports where present, as the denominator. The resource-expenditure view uses actual capital, operating and reliability expenditure per unit of served energy, with VoLL supplied by the run configuration. Historical carbon indicators follow their original scalar equations. The current physical emissions ledger uses the factors in Chapter 9 and reports tCO₂e; these outputs retain their respective units and calculations.

## Construction pipeline and exogenous schedules

Initial REPD projects form a commissioning pipeline according to technology, region and development stage. Success probabilities first use technology-region values, then the arithmetic mean of known regions for that technology, and finally 0.75. Probabilities apply to projects whose configured status requires them. R029 endogenous planning uses expected-capacity mode with seed 0, multiplying capacity and financial totals by the success probability once. An initial external snapshot that already contains successful capacity retains that effective capacity thereafter.

External completion dates follow stage duration and a fixed project perturbation. `completion_year_from_months` uses deterministic \(j\) between −6 and 6 months, giving the base completion year

$$
y_{complete}=y_{base}+\left\lfloor\frac{\operatorname{round}(\max(1,m+j))}{12}\right\rfloor.
$$

For approved projects, \(m\) includes pre-construction and construction. Application dates use day-first parsing. Completion is also bounded by the full development period from application, the model starting year, and starting year plus 1 for an initial snapshot. External projects completing exactly in the starting year may be deferred by 1–3 years under a fixed project rule.

Project screening uses status, technology, capacity and dates. Capacity must be at least 1 MW and completion no later than 2040. Terminated, operating, previously completed and stalled projects leave the pending set. The default stale-project threshold is 2015 and construction grace period is 2 years. `lookup_regional_success_rate`, `resolve_repd_success` and `preprocess_doctoral_project_records` connect regional probabilities to REPD fields. Optional stochastic planning uses a deterministic draw from project name, region and technology for external projects, and from seed and proposal identifier for endogenous projects. This R029 case uses expected capacity.

The initial 2025 pipeline contains 2,775 standardised project components, including 536 source storage projects each divided into four technologies. The table gives capacity after planning-success expectations, scheduled for later commissioning.

|Technology|Project components|Expected MW|Completion years|
|---|---:|---:|---|
|Solar|386|13,106.265796|2026–2027|
|Onshore wind|215|6,871.231070|2026–2030|
|Offshore wind|27|29,924.275000|2027–2034|
|1C battery|536|1,505.519970|2026–2028|
|0.5C battery|536|49,501.496623|2026–2028|
|0.25C battery|536|6,022.079881|2026–2028|
|Hydrogen storage|536|15.055200|2026–2028|
|Nuclear|3|6,460.000000|2031–2035|

Pumped-hydro power, energy and annual charges follow an exogenous fleet schedule. Expenditure in the table is already annualised and enters the year's fixed maintenance and capital recovery directly.

|Model year|MW|MWh|Annual maintenance GBP million|Annual capital GBP million|
|---|---:|---:|---:|---:|
|2025|2,828|26,700|85.4|377.9|
|2026–2027|2,927.9|27,400|87.8|388.5|
|2028|3,377.9|30,200|96.1|425.1|
|2029|3,587.9|31,800|99.9|441.5|
|2030|4,187.9|40,800|112.4|496.8|
|2031–2034|5,687.9|70,800|134.9|596.4|
|2035|11,387.9|195,800|241.9|1,070.8|

Nuclear follows the model's fixed exogenous schedule. Heysham 1, Hartlepool, Heysham 2 and Torness have 1,155, 1,185, 1,230 and 1,190 MW respectively and withdraw from model year 2031. Sizewell B has 1,198 MW and withdraws from 2056. The two 1,630 MW Hinkley C units begin full-year operation in 2031 and 2032. Sizewell C's 3,200 MW remains in the 2035 pipeline. Initial nuclear capacity totals 5,958 MW. This schedule comes from `value_uk_nuclear_policy_v1.json`; new nuclear engineering costs await a common price base before entering the main resource-expenditure calculation.

## Annual update and numerical example

The annual loop prepares financing expenditure before operation, determines investment and retirement afterwards, and carries physical and financial states together. `doctoral_annual_cem.py` requires complete annual demand, cash, costs and expansion inputs before calling `doctoral_policy.py` for owner decisions.

```text
for each model year:
    Prepare annual equity recovery and debt schedule
    Apply exogenous pumped-hydro and nuclear schedules; advance due projects
    Restore inventory batches across years and run the complete half-hourly year
    Build project accounts from actual market cash; allocate scenario transfers
    Calculate renewable limits and economic storage opportunities
    Group by owner and technology; decide additions and retirements
    Split projects by region and apply planning success rates
    Settle financing; update physical assets while retaining financing obligations
    Save closing batches, generator memory and the remaining construction pipeline
```

The R029 2025 CCGT account provides a numerical example of retirement. It operates 28,000 MW, has unit new-build capital of £2.4m/MW, operating surplus of −£429,488,780.128199 and target payback of 25 years. Retirement is therefore

$$
\Delta P^{retire}=
\frac{429,488,780.128199\times25}{2,400,000}
=4,473.841459669\ \mathrm{MW}.
$$

This calculation uses operating surplus \(S\). Of 47 decision accounts that year, 6 enter Deplete, 38 retain capacity and 3 enter High. Renewable and storage technology limits are all zero, giving zero new proposals. The initial pipeline comes from `2025/input.json.gz`, and the account example from `2025/year-result.json.gz`, connecting the annual rules to saved model quantities.
