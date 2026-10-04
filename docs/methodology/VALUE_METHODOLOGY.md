# VALUE runtime implementation overview

This developer overview describes runtime objects and contracts. The complete bilingual mathematical methodology, edition 0.3, is maintained in the [methodology chapters](README.md).

## 1. Scope, clock and information structure

VALUE is a modular power-system simulation and capacity-expansion framework. It represents market participation through declared offers and links each completed operating year to investment, planning, commissioning, retirement and the next year's opening state. The standard British research clock uses 30-minute periods. A complete non-leap model year therefore contains 17,520 periods.

The default market method is bid at cost. Thermal generation, variable renewable energy (VRE), storage and external interconnector offers enter the same market process. VRE is not subtracted from demand before clearing. Storage is represented as a market participant with physical power, energy and state-of-charge limits. This information structure differs from a perfect-foresight co-optimization: each market period uses the information declared for that period, while annual investment uses completed annual evidence.

The normal annual sequence is:

1. advance projects already in the planning pipeline;
2. clear every selected PSM period and, when selected, the balancing stage;
3. assemble physical, cost, carbon, storage and curtailment evidence;
4. calculate VRE and storage expansion headroom;
5. evaluate owner-level investment and retirement;
6. admit investment proposals into planning;
7. commission, delay or reject eligible projects; and
8. construct the next model year's opening state.

A one-day VALUE 101 Run calls the production PSM for 48 periods but does not provide annual economics. An annual VALUE-UK Run clears all 17,520 periods before the CEM stages use its results. A 2025 to 2034 Study contains 175,200 operating periods and ten annual decisions. Readiness confirms that the inputs can execute; it is not scientific validation.

## 2. Reproducible model identities

Five versioned objects define a calculation.

| Object | Function | Frozen evidence |
| --- | --- | --- |
| Data Pack | Binds source files to named roles, formats, units and clocks | Pack ID, manifest, file inventory, source notes and hashes |
| Module | Implements one typed lifecycle slot | Module ID, semantic and scientific version, entry point and source hash |
| Study | Selects years, one base Data Pack, modules, parameters and optional domains | Immutable Study revision and dependency graph |
| Run | Executes one exact Study revision | Input snapshot, status, checkpoints and artifact index |
| Result evidence | Stores physical and economic outcomes | SQLite ledgers, compact summaries, diagnostics and provenance |

`Check readiness` resolves exact module versions, validates every required role, unit and chronology, verifies identities and hashes, estimates resources, and freezes an input snapshot. A single-node Study freezes the declared base Data Pack and does not search for a Network Pack. A zonal Study also resolves and freezes one compatible Network Pack. A missing or incompatible network role blocks the Run; VALUE does not silently substitute a different pack or return to single-node operation.

The VALUE-UK research suite installs two independent data components and creates two saved, unrun Studies. The copperplate and zonal templates share the same base data, national demand, clock, storage-cost method and annual CEM chain. Their declared system domain and balancing implementation differ.

## 3. National bid-at-cost PSM

The built-in PSM is `value-staged-bid-at-cost-psm`. Its purpose is to produce the national ahead schedule and period evidence used by balancing and the annual CEM. It reads forecast and realized demand, renewable availability, the operating asset state, interconnector boundaries and the selected storage-cost function. Power is expressed in MW, period energy in MWh, and offer prices in GBP/MWh.

For each half-hour, agents submit available quantities with prices derived from their declared costs. The national market accepts the least-cost available offers needed to meet the market requirement under the selected single-node information structure. The ahead schedule is immutable when balancing begins. The staged design keeps forecast-driven corrections distinct from any subsequent network-congestion adjustment.

The built-in copperplate balancing module compares the national schedule with realized demand and availability. It accepts upward and downward flexibility bids on a pay-as-bid basis and updates the physical period result. Bid records and settlement records remain separate from resource-cost accounting.

| Module contract | Declaration |
| --- | --- |
| Lifecycle position | PSM, followed by current-period balancing |
| Required inputs | Demand forecast and realization, VRE availability, operating assets, import offers and storage bids |
| State reads | `operating.assets` and current storage state |
| State writes | Physical storage state through the balancing result; the annual PSM does not commission assets |
| Outputs | Ahead schedule, final dispatch, prices, accepted offers, storage flows and period summaries |
| Configurable parameters | Bid multiplier, market-trace level and balance diagnostics |

The model does not include thermal start-up decisions, minimum up and down times, ramping, reserve co-optimization or integer unit-commitment variables unless a different PSM module explicitly implements them. Bid at cost is therefore comparable to economic dispatch under the declared simplified thermal constraints, not to a full mixed-integer unit-commitment model.

### Known limitations

The national market has one internal node. It cannot reveal internal British congestion. The sequential market does not claim a globally optimal multi-year dispatch, and its outcomes depend on declared agent information and offer rules.

## 4. Thermal generation, VRE, imports and unmet demand

Thermal assets expose available capacity and a declared resource cost. Their accepted energy cannot exceed the realized period envelope. The built-in bid-at-cost method does not add hidden operational priority among thermal technologies.

Solar, onshore wind and offshore wind expose time-varying available energy through their profiles. They participate in clearing rather than being removed from demand. Available VRE that is not finally used is recorded as curtailment. This makes competition with storage, thermal generation and imports visible in the market record.

Interconnectors are external boundary offers. Each country-specific price series determines the declared offer price and each signed profile constrains its available boundary quantity. They are not modeled as internal GB transmission branches. In zonal operation, a landing assignment and a period envelope place the same external offer at a zone without turning the neighbouring country into an internal node.

Load shedding is a last-resort system-operator action. The zonal module prices it at the configured value of lost load, with a built-in value of £17,000/MWh. VALUE records unserved MWh by zone and the number of half-hour periods in which shedding occurs. Expected interruption hours equal the affected half-hours multiplied by 0.5. This statistic describes the simulated chronology; it is not, by itself, a probabilistic reliability assessment.

The DSR interface accepts the same typed flexibility-bid contract. The distributed benchmark declares zero DSR capacity, so it changes no result until a researcher supplies a reviewed capacity and offer method below VOLL.

## 5. Storage physics and state of charge

Every storage technology declares charge power in MW, discharge power in MW, energy capacity in MWh, charge efficiency, discharge efficiency and an opening state of charge. Technology records also declare a duration or an equivalent fixed relationship between power and the energy pool. The physical variables use discharged energy as electricity delivered to the market and charged energy as electricity taken from the market.

For period `t`, the storage balance is:

`SOC[t+1] = SOC[t] + eta_charge * charge[t] - discharge[t] / eta_discharge`

subject to:

`0 <= SOC[t+1] <= energy_capacity`

`0 <= charge[t] <= charge_power * period_hours`

`0 <= discharge[t] <= discharge_power * period_hours`

The actual post-balancing charge and discharge update SOC. In the zonal method this means redispatch, not the national ahead schedule, determines the physical state passed to the next period. The solver checks energy balance and rejects a numerically material simultaneous charge and discharge solution.

Storage records preserve the charging time of energy tranches. The sales-weighted mean dwell is the average number of model periods spent in storage by each MWh sold, weighted by delivered MWh. It is used by the dynamic storage-cost method below.

### Known limitations

The built-in storage method does not optimize the full year with perfect knowledge. Degradation is represented through the selected cost method rather than an electrochemical state-of-health model. A researcher who needs different chronology, degradation or terminal-SOC assumptions must select a compatible PSM or storage-cost module and disclose its information structure.

## 6. Dynamic and legacy storage pricing

The default module is `dynamic-annual-storage-cost`. It implements dynamic annual-average project-cost recovery. Its inputs are the storage asset, previous-year sold energy and the previous-year sales-weighted dwell. It reads and writes `storage.cost-observation`. Its output is a callable bid-cost function used by the PSM.

For discount rate `r` and economic life `L`, the capital recovery factor is:

`CRF(r,L) = r(1+r)^L / ((1+r)^L - 1)`

The annual levelized project cost is:

`A[y] = CAPEX * CRF(r,L) + FOM_per_kW_year * 1000 * power_capacity_MW`

For battery technologies only, cycle depreciation is:

`cycle_cost = CAPEX / (usable_energy_per_cycle * maximum_cycles)`

where `usable_energy_per_cycle = energy_capacity_MWh * discharge_efficiency`. Pumped hydro and hydrogen storage have no battery cycle-depreciation component in the supplied technology catalogue.

If the previous year sold `S` MWh with sales-weighted mean dwell `D` periods, the holding coefficient is:

`holding_cost = max(A[y] - cycle_cost * S, 0) / (S * D)`

and the offer attached to a tranche held for `d` periods is:

`storage_offer(d) = cycle_cost + d * holding_cost`

The method therefore separates degradation that necessarily accompanies a battery cycle from the project-cost recovery associated with holding and selling energy. After each year, actual sold MWh and dwell-weighted sales become the next year's denominator.

If no previous-year sales exist, including the first model year, the module uses a full-utilization design case. Reference annual cycles are the smaller of cycle-life use per economic year and the physical charge-discharge limit. Users may set `storage.cost.utilisation_floor_fraction` to keep the denominator above a declared fraction of that reference. A zero floor reproduces the published thesis-exact rule; non-zero floors are sensitivity cases.

`value-legacy-storage-tariff` retains the historical fixed plus dwell-time tariff for reproduction comparisons. It does not claim project-cost recovery. A Study must select one storage pricing module. The legacy and dynamic methods should be compared in cloned Studies with all other data, modules and parameters held fixed.

### Known limitations

Previous-year sales can make offers oscillate when utilization changes sharply. The audit artifact reports the pricing basis, sold energy, dwell, annual project cost and recovery difference, but the ordinary Runs page need not display every audit field. The dynamic method is a research method, not an assertion that all storage operators bid this way in Britain.

## 7. VRE and storage expansion headroom

`vre-expansion-cap` and `value-storage-expansion-policy` calculate annual headroom before investment proposals are accepted. Both modules read the completed market-year result and the operating asset state, write no asset state directly, and output typed expansion-headroom records.

The VRE policy calculates separate solar, onshore-wind and offshore-wind ceilings from demand, renewable profiles, installed capacity and the declared expansion fraction. The storage policy uses physical storage dispatch, system excess and `expansion.storage_cap_fraction`. Headroom is a shared technology budget for the model year. It is not multiplied by the number of incumbent generator rows or commissioned child assets.

Headroom constrains capacity that investment agents may propose; it does not itself commission a project. A missing headroom record is zero for a technology whose eligibility mode requires headroom. Thermal technologies can be explicitly uncapped by the investment policy. Natural-flow hydro and pumped hydro require site and hydrology evidence rather than generic headroom.

### Known limitations

These are policy rules, not a network-capacity expansion optimization. The current zonal system does not change the national expansion ceiling by congestion location and contains no executable transmission-expansion CEM.

## 8. Owner-level investment

`agent-investment` evaluates one economic owner and technology-region group once per model year. It receives annual market results, capital cost, policy support, model parameters and expansion headroom. It reads operating assets and produces proposals, retirements and complete asset-economics records. It does not commission assets directly.

The investment method evaluates the declared four-tier owner decision logic in the active CEM implementation. The calculation uses the owner's annual operating evidence and the candidate's cost and support assumptions, then applies technology eligibility and the one shared headroom budget. Several physical assets owned by the same economic agent do not create duplicate independent investment agents. Commissioned children inherit the owner identity but do not multiply the owner's opportunity or the technology cap.

Each accepted proposal must carry CAPEX, fixed O&M, economic life, owner, technology, capacity and location or allocation evidence. Unknown technologies are denied. New natural-flow hydro and pumped hydro are deferred unless the proposal supplies the required site, hydrology, energy-capacity and new-build cost evidence.

### Known limitations

The owner rule is an agent-based investment heuristic, not a system-wide least-cost capacity-expansion optimization. Investment outcomes depend on annual realized evidence, exposed policy assumptions and planning outcomes. They should not be described as a proof of the globally optimal generation mix.

## 9. Planning pipeline and commissioning

`planning-pipeline` connects existing project evidence and new investment proposals to the physical fleet. It consumes prepared project records, planning timelines, success rates and investment economics. The module reads `year_state.planning_projects` and writes the next planning state, commissioned operating assets and their economics.

At the start of a year, existing projects advance according to their stage, timeline, success mode and seed. Projects may remain in planning, fail, reach commissioning or be treated according to the declared uncertain-project rule. Later in the annual sequence, eligible investment proposals are admitted as new planning projects. The two phases are recorded separately so that an admitted proposal cannot commission in the same logical operation unless its explicit timeline permits it.

Commissioned assets inherit stable project and owner identity, technology, capacity, CAPEX, fixed O&M, economic life and spatial allocation. VALUE writes events and summaries to the planning evidence store. Reporting counts expected capacity once; it does not multiply an already weighted project capacity by success probability again.

The configurable planning fields include success mode, random seed, stage timelines, stale-project treatment and source preprocessing. Seeded modes must reproduce the same decisions under the same frozen input snapshot.

### Known limitations

Planning probabilities and completion dates are scenario assumptions. A large commissioning cohort can be a real consequence of the input cohort and rules even when the ledger reconciles. Users should audit source dates, mapping and expected-capacity interpretation before treating such a cohort as a forecast.

## 10. Retirement and annual state transition

`value-annual-state-transition` applies accepted planning and retirement results after the annual decisions. It reads the completed year state and writes `year_state.next`, including operating assets, planning projects, storage observations and economics needed by the next year.

Newly commissioned assets enter the next year's actual PSM inventory. Partial retirement scales both physical capacity and the associated economic record. Full retirement removes operating availability while retaining the event evidence. The transition writes an annual checkpoint only after the year boundary is complete. If a Run stops within a model year, the current release recomputes that year rather than claiming a verified subannual continuation.

### Known limitations

The transition is annual. It does not model construction or retirement within an operating year. A module that changes that chronology must declare a different state-transition contract and compatible evidence.

## 11. Cost, settlement, policy and carbon ledgers

The headline cost identity is `value.cem-system-resource-cost/v1`:

`system_resource_cost = annualized commissioned-fleet CAPEX and FOM + final physical operating cost`

The denominator for the headline average is served demand, equal to demand minus unserved energy. Settlement payments are transfers and are not added again to physical resource cost. Policy payments, consumer accounts, pipeline commitments and residual asset value remain separate views. In a zonal Run, transmission-constraint resource cost is the difference between matched unconstrained and realized constrained physical cost. It is already within final operating cost and is reported as an attribution, not added twice.

The current carbon scenario stores factor IDs and database hashes. It separates direct operational emissions, external import emissions, annualized embodied emissions for active generation and storage equipment, and storage charging inventory. Generation-side emissions already include electricity used for charging, so the carbon ledger does not add charging supply a second time. It reports total tCO2e, operational intensity and overall intensity when every required factor and denominator is physically interpretable.

The doctoral-reproduction carbon scenario preserves its historical calculation boundary. Historical storage scalars without a declared physical unit remain labelled `not_physically_interpretable`; VALUE does not rename them as tCO2e or replace them with zero.

Every ledger line records its source, classification, inclusion in the headline and any reason for exclusion. A reconciliation failure blocks a scientific result rather than silently filling a missing component with zero.

## 12. Hydrology and other optional domains

Natural-flow hydro, reservoir hydro and pumped hydro are distinct. Pumped hydro is a storage technology governed by electrical charge, discharge and SOC. It is not duplicated as a natural-inflow generator.

The optional hydrology domain can bind run-of-river availability and reservoir inflow, capacity and water-state data. Run-of-river output is bounded by the supplied inflow or availability series. A reservoir implementation must conserve its declared water stock across periods and state its initial and terminal assumptions. The British base Study only activates hydrology when a compatible extension and its conditional data roles are selected.

An optional domain adds versioned roles, parameters, lifecycle hooks and result artifacts. It does not become active merely because its package is installed. The Study must select it and readiness must resolve every conditional input.

### Known limitations

VALUE does not infer hydrology from installed electrical capacity. Missing inflow or reservoir data cannot be replaced by a generic capacity factor without declaring a different method. The current release includes no transmission-expansion implementation even though the extension interface can host one later.

## 13. Fixed-zonal transmission and redispatch

The fixed zonal method is a post-thesis VALUE extension. It is a lossless transport and redispatch model, not a DC load-flow implementation. It represents transfer envelopes between computational zones but does not calculate voltage angles, impedance-based flows, reactive power or electrical losses.

### Spatial representation

The Network Pack supplies DSO-aligned zones, directed computational corridors, simultaneous ETYS cutsets, rating profiles, asset mappings, zonal demand allocation and interconnector landings. An asset's zone is immutable once resolved for a Study. Assets with project coordinates use the declared spatial assignment. Offshore assets without a connection point use the documented nearest-coast DSO rule. An unresolved English aggregate connects to a representative England zone through an unconstrained link so that missing geography is visible without inventing a constrained boundary. Northern Ireland is outside the modeled GB system.

The default `scenario_scaled_zonal_shares` mode keeps the base Data Pack's national demand authoritative. Network data allocate that total among zones, and the shares must reconcile to the national value each period. The alternative `network_pack_absolute_demand` mode allows the Network Pack to supply absolute zonal demand. Comparisons must use the same demand authority.

### Transfer constraints

Each corridor can have different forward and reverse limits. A positive flow follows the corridor's declared direction; a negative flow uses its reverse envelope. ETYS cutsets constrain signed linear combinations of corridor flows in both directions. A time-dependent rating multiplier can reduce a boundary for maintenance or seasonal availability. This version uses no endogenous losses.

### Redispatch problem

The national ahead schedule remains the commercial starting point. For each half-hour, the zonal module solves one linear redispatch problem with zonal balances, corridor and cutset limits, realized asset availability, interconnector envelopes, storage power and energy limits, DSR bids and load shedding. Thermal increases or decreases, VRE curtailment, storage changes, import adjustments, DSR and load shedding compete through the same declared flexibility-bid interface. There is no hidden physical priority list.

The built-in solver uses SciPy HiGHS and four lexicographic phases:

1. minimize accepted bid cost, with load shedding at £17,000/MWh;
2. minimize total deviation from the national schedule while retaining the first objective within its numerical cap;
3. minimize physical throughput, including storage movement and absolute corridor flow, while retaining the earlier objectives; and
4. apply a stable key to make tied solutions reproducible.

Upward and downward redispatch are recorded pay as bid. National ahead settlement, redispatch settlement, policy transfers and physical resource cost remain separate. The module writes solver identity, tolerances, input hash and objective-lock diagnostics. A solver failure preserves the declared input and fails the zonal Run. Automatic solver substitution and automatic copperplate fallback are disabled.

Storage uses actual post-redispatch charge and discharge for SOC and sold-energy records. Interconnectors retain their external import/export envelope and assigned landing zone. DSR has zero capacity in the distributed benchmark but the executable bid interface remains available.

### Curtailment attribution

VALUE distinguishes potential VRE, curtailment before network relief, and final physical curtailment. Energy absorbed by extra storage charging, extra exports or additional local demand response is not counted as final curtailment. The reported `redispatch impact` is final constrained curtailment minus the matched copperplate counterfactual. A positive value means the network and redispatch process added curtailment; a negative value means it avoided curtailment.

Forecast correction and congestion redispatch retain separate attribution. Total system resource cost includes the physical consequences of both. Detailed records preserve accepted bids, cashflows, boundary loading, unserved energy and the matched counterfactual needed to interpret the difference.

### State reads and state writes

The zonal module reads the immutable national ahead schedule, realized zonal demand, asset availability, flexibility bids, Network Pack and opening storage SOC. It writes final zonal dispatch, corridor flows, accepted redispatch, load shedding, curtailment attribution, accounting views, solver diagnostics and actual closing storage SOC.

### Configurable parameters

Users can select demand authority, solver method within the declared HiGHS family, presolve and bounded numerical tolerances. The built-in VOLL is configurable. Corridor limits, directional cutsets, maintenance ratings, zones and mappings belong to the versioned Network Pack rather than ad hoc Run settings.

### Known limitations

This is not a security analysis. It does not perform AC or DC power flow, voltage or reactive-power analysis, transient or frequency stability, N-1 contingency analysis, endogenous loss calculation or transmission expansion. Boundary capabilities are input assumptions. Passing the zonal solver proves feasibility under this declared transport representation; it is a necessary but insufficient condition for real network security.

## 14. Results, auditability and declared claims

VALUE stores high-volume period records in SQLite and compact JSON summaries for the browser. The artifact index identifies the producing Module, Study revision, Run, year and source hash. Market replay exposes orders and accepted dispatch when the selected trace level records them. Full annual Runs can retain compact period evidence to control disk use. The planning store records projects by stage, location, outcome and commissioning year.

Every complete Run should be archived with:

- the Study revision and frozen input snapshot;
- Data Pack and Network Pack manifests and hashes;
- exact Module manifests and source identities;
- annual checkpoints and artifact index;
- physical, cost, carbon, storage, planning and network ledgers;
- solver diagnostics where an optimization module is selected; and
- source rights and attribution records.

Internal conservation and regression tests establish implementation consistency. Independent optimization checks establish agreement only for the declared formulations and information structures that they test. A successful one-day lesson does not validate annual economics. A successful readiness check does not validate a scientific scenario. A configured ten-year Study is not a completed ten-year result.

The built-in single-node method can support studies of market competition, storage pricing, investment and planning under its stated constraints. The fixed zonal extension can support experiments on transfer limits and redispatch under its stated transport assumptions. Neither method supports claims about full unit commitment, AC feasibility, security compliance, globally optimal multi-year expansion or predictive certainty unless a separately documented Module and validation record supply that evidence.

## Implementation references

The maintained module declarations are under `gridform_core/manifests`. Typed public interfaces are under `gridform_core/v2`. Storage recovery is implemented by the selected storage-cost module and audited through `storage-cost-audit.json`. Cost and carbon definitions are maintained in `gridform_core/cost_ledger.py` and `gridform_core/carbon_ledger.py`. The post-thesis zonal formulation is implemented in `gridform_core/zonal_redispatch.py`, with network inputs defined by `gridform_core/zonal_contracts.py` and solver settings defined by `gridform_core/zonal_solver_contract.py`.

The VALUE-UK suite retains object-level source, transformation, licence and attribution records inside both component bundles. Those records, rather than this methodology summary, govern reuse of the supplied data.
