# VALUE Network Extensions mathematical and algorithmic reference

Version 0.6.0-alpha.2, 22 August 2026. This reference describes the code that is
executed. It does not turn an intended future architecture into a scientific
claim.

## 1. Scope and boundary

VALUE is **Variable renewable electricity Allocation, Load-enabled
excess-generation Utilisation, and system Evolution**. The built-in UK-derived configuration couples a chronological power
system model (PSM) to annual, agent-led capacity expansion (CEM). Its accepted
Prompt 64 baseline represents Great Britain as one electrical node. Optional
extensions can instead use a user-supplied DC topology or an experimental AC
feasibility check; those capabilities have separate data contracts and maturity
decisions. France, Belgium, the Netherlands, Norway and Ireland remain
time-varying boundary import resources. They are not silently converted into
buses or internal European transmission lines.

The normal dispatch interval is \(\Delta t=0.5\) hours and a full year contains
17,520 intervals. Power is MW, interval energy and storage state are MWh, marginal
prices are GBP/MWh, and annual accounts are GBP/year unless stated otherwise.

Indices used below are year \(y\), interval \(t\), dispatchable or renewable
resource \(g\), storage asset \(s\), and planning project \(j\). The annual state
contains the operating fleet, storage cost observations, active planning pipeline
and year. The data-pack snapshot, module manifests and resolved parameter set are
immutable run inputs.

## 2. Two selectable PSM formulations

### 2.1 Fast Scheme C-compatible cost-ranked market

`scheme-c-psm` is the fast Scheme C-compatible cost-ranked implementation. It is
a replaceable operational module, not VALUE's scientific definition. For a
non-storage resource, an offered interval quantity is bounded by installed power,
availability and interval duration. VRE availability is offered rather than
subtracted from demand. Thermal, hydro, imports, VRE and stored-energy tranches
therefore participate in the same merit-order procedure. Unaccepted available VRE
is voluntary curtailment. Import prices and availability come from boundary data
bindings.

The basic non-storage offer is

\[
 b_{g,t}=m\,c_{g,t},\qquad
 0\le q_{g,t}\le \bar P_g a_{g,t}\Delta t,
\]

where \(c_{g,t}\) is the implementation's technology cost, fuel/carbon and
time-cost composition and \(m\) is `market.bid_multiplier`. Only \(m=1\) is strict
bid-at-cost. Storage offers are defined in Section 3. The live FORCE algorithm
contains day-ahead and balancing stages and records accepted quantities and
settlements in the market ledger.

Ordering is deterministic for a frozen Python/runtime input. Non-storage bids are
sorted by price using Python's stable sort, preserving input order on equal keys.
One day-ahead storage merge orders by bid price, capacity and its stored-time key;
the balancing path sorts by bid price. Dynamic storage orders positive holding-cost
tranches newest first; when the holding coefficient is zero it preserves insertion
order. These rules are implementation behavior, not a claim that all equal-price
allocations are economically unique.

`scheme-c-psm` is one manifest-backed live implementation. The v2 orchestrator
invokes it once per model year and receives a typed `MarketYearResult`; the PSM
reuses source-hashed Scheme C-derived clearing functions through a run-scoped
adapter. It does not read annual output or bind replay data. The preserved whole
kernel is available only as `scheme-c-reference-comparison` and is not a module.
Independent LP validation of FORCE period clearing remains a separate release
gate and is not implied by this architectural cutover.

### 2.2 Optional perfect-foresight LP

`force-perfect-foresight-lp` is a separate, transparent single-node chronological
linear program solved by SciPy/HiGHS. It is selected instead of `scheme-c-psm` and
does not accept a storage offer-cost module: storage is centrally co-optimized.
All decision variables below are MWh per interval except \(e_{s,t}\), which is MWh
of state of charge (SOC): resource output \(p_{g,t}\), storage charge
\(x_{s,t}\), discharge \(z_{s,t}\), SOC \(e_{s,t}\), and unmet demand
\(u_t\).

\[
\min \sum_t\left(\sum_g c_{g,t}p_{g,t}
 +\sum_s c^{deg}_s z_{s,t}+VOLL\,u_t\right)
\]

subject to

\[
\sum_g p_{g,t}+\sum_s z_{s,t}+u_t-\sum_s x_{s,t}=D_t,
\]

\[
0\le p_{g,t}\le \bar P_g a_{g,t}\Delta t,
\quad 0\le x_{s,t}\le \bar P^{ch}_s\Delta t,
\quad 0\le z_{s,t}\le \bar P^{dis}_s\Delta t,
\]

\[
e_{s,t}=e_{s,t-1}+\eta^{ch}_s x_{s,t}
-\frac{z_{s,t}}{\eta^{dis}_s},
\qquad 0\le e_{s,t}\le \bar E_s.
\]

At the first interval, \(e_{s,t-1}\) is the declared initial SOC. Terminal SOC is
`cyclic` (equal to initial), `fixed` (equal to a supplied target), or `free`.
Blackout can be disabled by fixing \(u_t=0\). A second LP minimizes total charge
plus discharge while remaining within a tight tolerance of the primary optimum;
this removes cost-neutral simultaneous charging/discharging. The program returns
balance duals using the documented `d(objective)/d(demand_rhs)` sign.

### 2.3 Optional reference DC network LP

`force-reference-dc-network` is a chronological linear DC-OPF module. For bus
angle \\(\\theta_{i,t}\\), branch reactance \\(x_l\\), tap \\(\\tau_l\\), phase shift
\\(\\phi_l\\) and system base \\(S_{base}\\), an in-service AC branch uses

\\[
f_{l,t}=\\frac{S_{base}}{x_l\\tau_l}
(\\theta_{i,t}-\\theta_{j,t}-\\phi_l),
\\qquad |f_{l,t}|\\le \\bar F_l.
\\]

Nodal balances include thermal, VRE, boundary imports, storage charge/discharge,
load and involuntary curtailment. Storage retains the SOC equations in Section
2.2. One reference angle is declared per connected island. The formulation is
lossless and has no voltage-magnitude or reactive-power variables. Unsupported
fields are labelled, not returned as calculated zeros. SciPy/HiGHS solves the
production LP; an independent angle-eliminated LP validates single-bus,
congested, meshed, islanded, storage, 24/168-hour and random convex cases.

### 2.4 Optional lossless zonal redispatch balancing

`value-zonal-redispatch-balancing` preserves the national ahead schedule and
clears realised forecast error and congestion for one half-hour at a time. It
uses a lossless computational corridor graph and signed ETYS cut sets. For an
accepted upward or downward bid adjustment \(\Delta_i\), corridor energy
\(f_c\), zonal load shedding \(u_z\), ahead injection \(g^{ahead}_z\) and
realised zonal demand \(D_z\), it enforces

\[
g^{ahead}_z+\sum_{i\in z}\Delta_i+u_z
+\sum_{c\rightarrow z}f_c-\sum_{c\leftarrow z}f_c=D_z.
\]

The Study declares which dataset has national-demand authority. In the default
controlled-comparison mode,

\[
s_{z,t}=\frac{D^{network}_{z,t}}{D^{network}_{GB,t}},\qquad
D^{run}_{z,t}=s_{z,t}D^{research}_{GB,t}.
\]

Thus the research pack fixes national realised and forecast demand, while the
signed network pack fixes only spatial shares. The absolute-network-demand mode
instead sets \(D^{run}_{z,t}=D^{network}_{z,t}\) and scales the forecast by the
research forecast/real ratio. It is labelled an independent demand study and is
not eligible for causal network-cost attribution against a scenario-demand
copperplate run. Both modes require exact ordered clock alignment and per-period
zonal conservation; no cyclic repetition, interpolation or equal-share fallback
is permitted.

Each ETYS boundary constrains a signed sum of corridor flows with separate
forward and reverse ratings. Thermal, VRE, imports, DSR, storage and VOLL-priced
load shedding enter one pay-as-bid LP. Storage retains explicit MW, MWh, SOC and
efficiency constraints; non-convex bids capable of self-cycling are rejected.
The hierarchical solution first minimizes signed accepted bid value, then
absolute deviation from the ahead schedule, physical throughput and a stable
tie key. Equal-price bids in the same direction, zone and network effect are
accepted pro rata whatever their resource class (solver contract v4); storage
keeps its own convex identity. A down bid's forced part, the curtailment its
asset must take because an upper bound on its final dispatch (realised
availability, or the import side of its interconnector envelope) is below the
ahead schedule, is carved out first and only the remaining free volume is shared:
\((x_i-f_i)\,\mathrm{free}_1=(x_1-f_1)\,\mathrm{free}_i\).

This method is a zonal transport abstraction, not DC or AC power flow, security
analysis, N-1 analysis or transmission expansion. Its Prompt 99 analytical
fixtures do not replace the independent PuLP/CBC validation gate required before
annual execution.

#### Network economics of the staged path (P0-8b)

Balancing bids follow the BM convention: an accepted up bid is paid
\(x\,p\), an accepted down (dec) bid pays \(x\,p\) back, so the objective
term of a dec is \(-p\,x\) and the highest dec is accepted first. Dec prices
are economic (`network_method_rules`, rule set `network-economic-v1`, sharing
the down-regulation table of the default PSM): a fuel unit returns its avoided
running cost \(p=SRMC\cdot m_{dec}-s\); an import its period price
\(p_t\,m_{dec}\); VRE and run-of-river hydro lose their output support,
\(p=-s\); nuclear also asks the inflexibility premium,
\(p=SRMC\cdot m_{dec}-s-\pi\) (\(\pi=\) GBP 100 by default); storage bids at
most \(\min(p^{up}\eta_c\eta_d,\ \min_k p^{up}_k)\), so a storage dec never
pairs with an inc at a profit. \(m_{dec}\le m_{bid}\) is enforced. A
decremented fuel unit therefore keeps no windfall. Equal-price bids share pro
rata (zonal LP and copperplate 1.1.0, storage after generation at an equal
price).

The network cost of a period is
\(C^{net}=C(\text{zonal})-C(\text{network-free})\). The network-free case is
the same LP collapsed to one node (no corridors or cut sets) with the same
bids, export envelopes, storage physics, VOLL-priced shedding, solver and one
per-period unit-cost table that also prices the zonal case, the resource rows
and the agents' running cost. Every case therefore includes
\(VOLL\cdot u\), a national shortfall is never network cost, a time-varying
import price creates none, and an export arbitrage appears in both cases. Each
period checks \(J_1(\text{zonal})\ge J_1(\text{network-free})-\text{tol}\) on
the primary objective, whose difference is also reported
(`network_constraint_bid_objective_gbp`).

The boundary marginal value is the primary-stage dual
\(\lambda_b=-\partial J_1/\partial \bar F_b\) of the boundary limit, read only
from the primary LP (later phases optimise tie-breaks): with HiGHS row
marginals \(m\le0\), \(\lambda_b=m_b^{rev}-m_b^{fwd}\) in GBP per MWh of
transfer, positive when the forward limit binds. Status `degenerate_dual`
marks a boundary at its limit with a zero dual and `shared_member` a binding
boundary sharing a corridor with another binding one (the split is then not
unique; the reported value lies between the one-sided derivatives). The annual
`boundary_congestion_rent_diagnostic_gbp` is
\(\sum_t\sum_b|\lambda_{b,t}\,F_{b,t}|\), a diagnostic, not a cash cost.
Ledgers written before P0-8b stored a hard-coded 0.0; they are read as
`not_computed`.

#### Numerical lexicographic solver contract v4 (formula of v2)

The experimental `value-zonal-redispatch-balancing` module `4.0.0` uses four
lexicographic objectives: redispatch bid cost (GBP), absolute deviation from the
national ahead schedule (MWh), physical storage and boundary-flow throughput
(MWh), and a stable-key objective that selects a reproducible asset-level
solution. Only the first three objectives are locked: the stable-key phase is
last and has no later phase against which to impose a cap.

For a locked objective (k), evaluated at its optimum (x^*), the numerical
cap is calculated as:

```text
U_k     = sum(abs(c_i * x_i*))
C_k     = sum(abs(c_i))
gamma_n = n * epsilon / (1 - n * epsilon)
epsilon_effective = max(solver_tolerance_k, bound_canonicalisation_tolerance)
tau_k   = max(unit_floor_k, epsilon_effective * max(1, U_k), gamma_n * U_k, C_k * epsilon_effective)
objective_k(x) <= objective_k(x*) + tau_k
```

Here (n) is the non-zero objective-term count and `solver_tolerance_k` is the
largest active primal, dual or IPM tolerance. The floors are `1e-8 GBP` and
`1e-9 MWh`. The returned solution is checked again using
`d_k = max(0, objective_k(x_final) - objective_k(x*))`; non-finite inputs,
invalid term counts or a post-solve cap violation fail the run. The statement
"numerical tolerance does not relax physical feasibility" means energy balance, SOC, transfer
capacity and settlement identities remain hard constraints.

The built-in defaults are SciPy `1.8.1`, `scipy.optimize.linprog` with
`highs-ds`, presolve, and primal/dual feasibility tolerances of `1e-9`. There is
no automatic fallback to `highs-ipm`, another solver or copperplate balancing.
The recorded embedded HiGHS binary is currently a source-registered
`candidate`, not independently validated execution; default settings must not
be promoted to an independently validated solver-stack claim.

Solver contract v4 (Q5) first locks total load shedding after the primary solve
(fixed at zero when the primary sheds nothing, otherwise
\(\sum u\le u^*\)) and then applies the cap above only to the bid-cost terms.
The validated ceilings per half-hour are `1.0 GBP`, `0.001 MWh` schedule
deviation and `0.001 MWh` throughput. Recorded reference thresholds are
`1.0 GBP`, `0.01 MWh` and `0.01 MWh` respectively. Classification uses
`max(computed_tolerance, observed_degradation) / validated_ceiling`: up to 10%
is `GO`; above 10% and up to 100% is `GO_WITH_NUMERICAL_WARNING`; above 100%
is `COMPLETED_WITH_NUMERICAL_WARNING`, including values above the recorded
reference threshold. A numerical warning and unvalidated status propagate to every later
PSM/CEM year and the complete study. Failed runs retain declared inputs, solver
settings, completed-phase evidence and raw solver status rather than changing
models.

### 2.5 Experimental AC feasibility check

`force-reference-ac-feasibility` checks a declared active-power schedule using

\\[
P_i+jQ_i=V_i\\,\\overline{\\sum_jY_{ij}V_j}\\,S_{base}.
\\]

It models active/reactive balance, voltage magnitude, real losses, branch MVA
limits, charging, shunts, fixed transformer taps and phase shifts. Each island
has one declared slack-balancing asset. The production solver uses polar bounded
nonlinear least squares and the independent validator uses rectangular
coordinates. Successful evidence is `LOCAL_SOLUTION_VALIDATED`; this module is
not AC OPF and has no global-optimum certificate or DC fallback.

### 2.6 Limited economic-dispatch equivalence

Continuous thermal bid-at-marginal-cost clearing is equivalent to a single-period
convex economic-dispatch problem only when the same resource limits and demand are
used and omitted constraints are unnecessary. FORCE does not thereby become
equivalent to unit commitment, DC optimal power flow or AC optimal power flow. The
current built-in market omits binary commitment, start-up/shut-down, minimum stable
output, minimum up/down times, ramping, reserves and internal network constraints.
Storage also introduces intertemporal state and an agent offer rule, so a
compatibility-market outcome is not automatically the perfect-foresight optimum.

## 3. Storage physics and pricing

Every storage technology has explicit charge power, discharge power, energy
capacity, charge/discharge efficiency and a technology duration. Energy delivered
and energy withdrawn from the storage pool are related by the declared efficiency;
MW is never silently treated as MWh. A sales-weighted average dwell is

\[
\bar h_{s,y}=\frac{\sum_k E^{sold}_{s,k}h_{s,k}}
{\sum_k E^{sold}_{s,k}},
\]

so it is the average number of model intervals that each sold MWh spent in the
storage pool, weighted by sold energy.

### 3.1 Dynamic annual-average recovery

`dynamic-annual-storage-cost` calculates annualized project cost

\[
A_{s,y}=CRF(r,L_s)\,CAPEX_s+FOM_s,
\qquad
CRF(r,L)=\frac{r(1+r)^L}{(1+r)^L-1},
\]

with \(CRF(0,L)=1/L\). CAPEX is the asset's project capital cost; fixed O&M is
power capacity in kW multiplied by its technology GBP/kW/year parameter.

Only electrochemical batteries receive cycle depreciation:

\[
c^{cycle}_s=\frac{CAPEX_s}
{\bar E_s\eta^{dis}_s N^{cycle}_s}.
\]

Pumped hydro and hydrogen have \(c^{cycle}_s=0\); their recovery is entirely in
the utilization/dwell component. With preceding-year pricing-basis sales
\(Q^{basis}_{s,y}\) and average dwell \(\bar h^{basis}_{s,y}\), the remaining
holding coefficient is

\[
c^{hold}_{s,y}=
\frac{\max(A_{s,y}-c^{cycle}_sQ^{basis}_{s,y},0)}
{Q^{basis}_{s,y}\max(\bar h^{basis}_{s,y},1)}.
\]

A tranche stored for \(h\) intervals bids

\[
b^{store}_{s,y}(h)=c^{cycle}_s+h\,c^{hold}_{s,y}.
\]

In the first year, and after a year with zero sales, the denominator is a declared
full-utilization design case. It uses the lesser of lifetime cycles per year and
the physical full charge/discharge cycle rate. In later years, actual preceding-
year sold MWh and dwell are used. An optional utilization floor is a sensitivity,
not part of the published zero-floor rule. Exact one-year feedback can yield high
bids and oscillation at low utilization; this is reported rather than silently
smoothed. The equation is an agent cost-recovery offer rule, not proof of globally
minimum system cost.

`scheme-c-legacy-storage-tariff` preserves the historical tariff equation for a
reproduction scenario. `user-formula-storage-cost` evaluates arithmetic over a
small approved variable set and cannot execute arbitrary Python. A project using
the perfect-foresight PSM selects no storage-cost module because the LP determines
charge/discharge directly.

## 4. Annual CEM and planning chain

The compatibility CEM is modularized as follows:

1. `vre-expansion-cap` and `storage-expansion-scheme-c` calculate technology
   expansion headroom from the selected data and PSM result.
2. `agent-investment` applies Scheme C agent revenues, costs, retirement and
   proposal logic subject to the headroom.
3. `planning-pipeline` imports and filters REPD-like projects, applies
   expected-capacity or seeded-stochastic planning success, records stage timing,
   deferral, failure, admission and commissioning.
4. `scheme-c-state-transition` advances accepted investments, retirements,
   operating assets, observations and pipeline exactly one year.

The next PSM year therefore depends on the previous market outcome and planning
state. Expected-capacity mode is an expectation calculation; it is not realized
project success. Seeded-stochastic mode is reproducible only with the frozen seed,
project revision and data snapshot. Investment decisions are agent-led and caps,
planning delay, retirement and stochastic success create path dependence. FORCE
does not claim this CEM solves a global, perfect-foresight capacity-expansion
optimum.

### 4.1 Optional hydrology contracts

`force-hydrology-extension` supplies separate run-of-river and reservoir
contracts. Run-of-river output is bounded by contemporaneous inflow and turbine
capacity; unused water is explicit curtailment. Reservoir dispatch includes
inflow, turbine release, environmental bypass, spill, storage balance and terminal
volume. It does not create another pumped-hydro asset: existing pumped hydro
remains a charge/discharge storage technology. Analytical and independent
24/168-hour fixtures are accepted; a real UK hydrology pathway is
`NOT_EVALUATED` until a Study supplies and validates the required site data.

### 4.2 Optional transmission-expansion lifecycle

`reference-transmission-expansion` is a transparent central-planner lifecycle
reference. Externally supplied candidate corridors are screened against observed
DC congestion, a declared annual benefit/cost ratio and shared budgets. A
successful proposal enters the network planning pipeline, retains
candidate→proposal→project→asset lineage, and is injected into the actual next
year topology only after commissioning. Commissioned network annualised CAPEX and
FOM enter the resource-cost ledger. Construction carbon enters only with a
declared factor and provenance. This experimental method is not a validated
national or ten-year transmission plan.

Terminal policy is explicit. `report_only` reports pipeline and remaining asset
life at the configured horizon. `pipeline_tail` advances planning-only tail years.
`full_extension` creates a distinct project revision for a longer full model; it
does not rewrite the original run. Residual value is informational and excluded
from current resource cost.

## 5. Ledgers and reported denominators

The canonical CEM system resource cost is

\[
C^{CEM}_y=C^{annualised\ capital}_y+C^{physical\ operation}_y,
\qquad
c_y=C^{CEM}_y/(D_y-U_y).
\]

The denominator is served demand, not gross generation. Named operating components
must reconcile to the typed PSM operating total. Market settlements, storage bid
recovery, policy transfers, pipeline commitments and informational residual values
are separate views and are not added again to physical resource cost. A missing
component remains unallocated or `not_evaluated`; it is never manufactured as
zero.

The carbon ledger pins one of two explicit factor scenarios:
`force_current_authoritative_v1` or `scheme_c_reproduction_2026_07_18`. It can
separate direct thermal emissions, import electricity, local asset installation
embodied emissions and storage lifecycle emissions when the run provides activity
and a compatible factor. Missing factor/activity combinations are
`not_evaluated`, not zero. Total carbon and carbon intensity are publishable only
when the selected boundary is complete and reconciled.

Energy balance, planning events, market periods, cost, carbon, storage audit,
module calls and source/data hashes are stored as compact JSON/JSONL/SQLite/NPZ
artifacts. Detailed rows are loaded on demand rather than inserted into the main
run-status payload.

### 5.1 VRE curtailment attribution for zonal redispatch

The optional staged zonal path uses three dispatches with the same realised
inputs. Let \(A_r\) be realised available VRE, \(G_{PF}\) VRE used by the
perfect-forecast reference clear, \(G_{CP}\) VRE used after a forecast schedule
and realised reference balancing (since P0-8b both references are the
network-free LP of section 2.4, not the greedy copperplate), and \(G_Z\) final VRE used after zonal
redispatch. The authoritative period identity is

\[
A_r-G_Z=(A_r-G_{PF})+(G_{PF}-G_{CP})+(G_{CP}-G_Z).
\]

The published fields split signed effects without losing their gross values:

```text
final VRE curtailment
  = economic curtailment
  + forecast-added curtailment
  - forecast-avoided curtailment
  + redispatch-added curtailment
  - redispatch-avoided curtailment
```

`Forecast & scheduling impact` is the difference between the two matched
copperplate cases. It is not presented as an isolated weather-forecast effect.
`Redispatch impact` is the difference between realised copperplate balancing and
final zonal redispatch. It includes participants' redispatch response and is not
labelled a pure physical-network effect. For example, changing VRE use from
10 MWh in the realised copperplate case to 7 MWh after redispatch adds 3 MWh of
curtailment; changing it from 7 MWh to 10 MWh avoids 3 MWh.

Copperplate allocation between economically equivalent zero-cost VRE objects is
not unique. FORCE therefore groups objects by canonical technology and stable
bid-tranche ID, and allocates each group's aggregate copperplate dispatch in
proportion to realised available VRE. Final zonal dispatch is not redistributed.
National final curtailment and national net redispatch impact are direct matched
counterfactual quantities. Zone, technology and object results are reproducible
attributions under this reference rule.

Formal VRE here is Solar, Onshore wind and Offshore wind. Energy accepted for
demand, storage charging, export, cross-zone delivery or effective demand-side
response is used energy, not curtailment. Hydro spillage, unused imports,
storage and network losses, and load shedding retain separate accounts. Avoided
curtailment is a physical MWh result: it is not assigned a default GBP value and
is not subtracted again from system resource cost.

The annual rate is available-VRE-energy weighted:

\[
r_y=\frac{\sum_t C^{final}_{y,t}}{\sum_t A^{realised}_{y,t}},
\]

not the mean of period rates. Storage dwell remains a separate sales-energy-
weighted quantity defined in Section 3; the two denominators must not be mixed.

New zonal evidence uses `gridform.market-ledger/v6`, with separate
`zonal_period_accounting`, `vre_curtailment_period` and
`vre_curtailment_detail` tables. Completed v4/v5 files are read-only and expose
curtailment as `legacy_partial`: historical avoided-curtailment fields are
unavailable (`null`), never inferred as zero. A module composition that does not
provide the matched counterfactual capability may still run with attribution
unavailable. The Network & redispatch waterfall is presentation-only and never
reconstructs or repairs this identity.

## 6. Ensembles and interpretation

Weather, demand and planning seeds define explicit child runs with frozen inputs.
Aggregation reports child success, missing members and statistics; a small ensemble
is exploratory evidence and not a probabilistic confidence claim. Comparisons are
valid only when units, denominator, horizon, terminal policy and factor scenario are
shown side by side.

## 7. Executable module inventory

The shipped manifests are `scheme-c-psm`, `force-perfect-foresight-lp`,
`value-reference-dc-network`, `value-zonal-redispatch-balancing`,
`force-reference-ac-feasibility`,
`dynamic-annual-storage-cost`, `scheme-c-legacy-storage-tariff`,
`user-formula-storage-cost`, `agent-investment`, `planning-pipeline`,
`vre-expansion-cap`, `storage-expansion-scheme-c` and
`scheme-c-state-transition`, plus the optional
`reference-transmission-expansion`. Hydrology and data/network contracts are
registered domain extensions rather than substitute PSM manifests. Versions,
entry points and implementation hashes are
generated in [generated/MODULES.md](generated/MODULES.md). Parameter defaults and
fixed/editable classifications are generated in
[generated/PARAMETERS.md](generated/PARAMETERS.md).

## 8. Deliberately unsupported or deferred

- AC optimal-power-flow co-optimization, global AC certificates, N-1 security,
  discrete transformer control and reactive storage support;
- a validated full-year or ten-year endogenous transmission pathway;
- full unit commitment, ramps, minimum output/up/down times and reserves;
- proof of global optimality for the multi-year CEM;
- a clean public-contract replacement of every copied Scheme C compatibility
  object;
- an independently verified mathematical equivalence between the Scheme C
  compatibility market and the LP for storage-rich chronological cases;
- complete redistributable UK input data and public code rights;
- a real UK run-of-river/reservoir pathway without supplied site, inflow and
  storage data.

Claims for these capabilities are `not_evaluated` unless a future version adds an
executable module and matching validation evidence.
