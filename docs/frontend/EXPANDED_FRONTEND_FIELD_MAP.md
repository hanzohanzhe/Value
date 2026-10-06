# Expanded frontend field map

Version: VALUE Network Extensions 0.6.0-alpha.2  
Date: 20 August 2026  
Authority: registry and server contracts; this document is a navigation map

The browser does not maintain a second model catalogue. Study choices, active
data roles, maturity acknowledgements, graph identity and result capabilities
come from the local API and are frozen in the saved revision or run snapshot.

## Study composer

| Step | User-facing field | Saved field / authority | Effect |
| --- | --- | --- | --- |
| Identity | Name | `name` | Display label; changing it creates a revision but is not a solver input |
| Identity | Research purpose | `purpose` | Human provenance |
| Identity | First / final model year | `start_year`, `end_year` | Chronology and CEM horizon |
| Identity | Data pack | `data_pack_id` plus manifest/object hashes | Selects immutable semantic bindings |
| System domain | Single node / DC / AC feasibility | selected `psm` plus required extensions | Chooses the physical PSM contract; AC is local feasibility, not AC OPF |
| Optional domains | Hydrology / transmission expansion | `selected_extensions` | Activates conditional roles and optional lifecycle modules; installation alone is not activation |
| Model chain | One implementation per slot | `modules` | Resolved by `ModuleRegistryV2`; incompatible options remain visible with a reason |
| Review | Extension parameters | `extension_parameters` | Namespaced values validated by the selected extension schema |
| Review | Experimental acknowledgement | `maturity_acknowledgements` | Version-pinned `force.experimental-ack/v1`; required before save/run |
| Review | Base scientific/runtime parameters | `parameters`, `runtime_options` | Registry-backed values with effective source preview |
| Review | Graph SHA-256 | server `graph_preview.graph_sha256` | Must equal save, preflight, snapshot and execution graph identities |

Unknown module slots, extension IDs, parameters, roles and acknowledgement
versions fail closed. A legacy Study with no extension fields means no extension;
it is not silently migrated to a network model.

## Module and extension package boundary

| Package | Browser action | Contains | Does not do |
| --- | --- | --- | --- |
| `force.module-bundle/v1` | Modules → Install a model module | Hash inventory, `gridform.module/v2`, Python source, licence, optional notes | Declare a new data-contract namespace or run `pip` |
| `force.extension-bundle/v1` | Modules → Install a model extension | Hash inventory, extension manifest, roles, parameters, capabilities, hooks/artifacts and licence | Silently select itself or replace a PSM |
| `force.data-bundle/v1` | Data → Install a data pack | Non-executable manifest, rights records and data objects | Install Python or change a saved Study |

External Python executes in the FORCE process and must be trusted. Transactional
validation is a packaging/contract gate, not an operating-system sandbox or a
scientific endorsement.

The 13 shipped module IDs, slots, contracts, maturity and current source hashes
are generated in [`../generated/MODULES.md`](../generated/MODULES.md). The
optional `network_expansion` slot is present only when a compatible Study uses
it. Storage-cost is absent when the selected PSM centrally co-optimises storage.

## Data roles

All Studies retain the 25 base PSM/CEM roles described role by role in
[`../../README_BILINGUAL.md`](../../README_BILINGUAL.md#5-data每一项上传什么--what-each-data-interface-requires).
The following roles are conditional on the exact draft or saved Study.

| Group | Role | Required | Shipped parser / template boundary |
| --- | --- | ---: | --- |
| Network | `force.network.buses` | yes | JSON; stable `bus_id`, voltage and optional WGS84 fields |
| Network | `force.network.branches` | yes | JSON; typed endpoints, branch kind, impedance and rating units |
| Network | `force.network.asset-map` | yes | JSON; electrical asset/demand identity to bus |
| Network | `force.network.nodal-demand` | yes | CSV; complete period/bus MWh and reconciliation to base demand |
| Network | `force.network.contingencies` | no | Declared by manifest; no N-1 result claim in the reference DC workflow |
| Network | `force.network.dynamic-ratings` | no | Declared by manifest; no fabricated result when unused |
| Network | `force.network.expansion-candidates` | no | Compatibility role; endogenous lifecycle uses the typed JSON role below |
| AC network | `force.network.ac.generators` | yes | JSON; P/Q limits, voltage setpoint and one slack asset per island |
| AC network | `force.network.ac.reactive-demand` | yes | CSV; complete bus/period Mvar grid |
| AC network | `force.network.ac.active-schedule` | yes | CSV; declared asset/period active schedule to check |
| AC network | `force.network.ac.initial-voltage` | no | JSON; bounded starting voltage, not a solved result |
| Hydrology | `force.hydrology.site-catalogue` | yes | CSV; stable site identity and run-of-river/reservoir class |
| Hydrology | `force.hydrology.asset-site-map` | yes | CSV; explicit electrical-asset/site shares; pumped hydro rejected |
| Hydrology | `force.hydrology.run-of-river-inflow` | yes | CSV; unique timestamp/site non-negative inflow or usable availability |
| Hydrology | `force.hydrology.reservoir-inflow` | yes | CSV; unique timestamp/site non-negative natural inflow |
| Hydrology | `force.hydrology.reservoir-parameters` | yes | JSON; finite volume, release and explicit water-to-energy conversion |
| Network expansion | `force.network.expansion.candidates` | yes | JSON; endpoints, circuits, MW/MVA, CAPEX/FOM/life, lead time, shared corridor limit and optional sourced carbon |

The UI shows both manifest-declared formats and the narrower set for which this
release has a runtime parser. A format without a parser is not selectable as
ready. Template and preview responses are bounded and do not mutate a pack.

## Domain preflight

| Domain | Preview evidence | Blocking examples |
| --- | --- | --- |
| Single node | Base role/parameter/runtime checks | Missing base binding, incompatible storage-cost selection |
| DC network | buses, islands/slacks, branch endpoints/ratings, mappings, nodal-demand reconciliation | island without reference, dangling asset, missing period, zero/invalid rating, missing SciPy solver |
| AC feasibility | DC topology plus P/Q assets, reactive demand, declared schedule and voltage input | incomplete bus/period grid, no slack asset, missing AC acknowledgement/solver |
| Hydrology | site classes, asset map, inflow coverage, reservoir bounds/conversion | pumped hydro mapped as natural-flow hydro, duplicate timestamps, dangling site, incomplete chronology |
| Transmission expansion | corridor endpoints, circuits, shared budgets and economic/carbon identity | unknown bus, zero budget where a proposal is claimed, incompatible DC/extension graph |

## Optional-domain results

Every route below is read-only, bounded and available only for a completed or
archived run. The response includes run/project/graph identity and source
artifact hashes.

| Browser view | API | Source artifact | Current decision |
| --- | --- | --- | --- |
| Capability tabs | `/api/runs/{run}/domains/capabilities` | Artifact presence plus frozen graph | `GO` |
| DC overview | `/api/runs/{run}/domains/network/summary?year=YYYY` | typed JSON, declared-input JSONL and indexed SQLite | `GO` in reference scope; rechecks ratings and nodal balance |
| DC periods | `/api/runs/{run}/domains/network/periods?year=YYYY&limit=N&offset=N` | period bus index | `GO`; includes injections, withdrawals, blackout, angle and nodal LP dual |
| DC branches | `/api/runs/{run}/domains/network/branches?year=YYYY&limit=N&offset=N` | period branch index | `GO`; flow, rating and utilisation |
| AC feasibility | `/api/runs/{run}/domains/ac/results?year=YYYY` | `force.ac-feasibility-output/v1` | `EXPERIMENTAL`; explicitly not AC OPF |
| Natural-flow water | `/api/runs/{run}/domains/hydrology/summary` | declared hydrology result index | `NO_GO` when ordinary annual execution emitted none; returns `not_evaluated`, never reconstructed zeros |
| Expansion summary | `/api/runs/{run}/domains/expansion/summary` | `force.network-expansion-history/v1` SQLite | `EXPERIMENTAL`; yearly proposals/admission/commission/failure/retirement |
| Expansion events | `/api/runs/{run}/domains/expansion/events?limit=N&offset=N` | same history index | `EXPERIMENTAL`; candidate/project/asset/corridor lineage |

Storage SOC remains authoritative in the market ledger and is linked rather than
duplicated in the network index. Counterfactual benefit is not inferred from one
expansion run; it requires a controlled comparison Study.

## Current non-programmer boundary

A non-programmer can install reviewed data/module/extension ZIPs, compose and
save the exact graph, diagnose conditional inputs, run the accepted single-node
path, inspect artifact-backed DC/AC/expansion evidence, compare and export without
editing JSON. The hydrology scientific fixtures and adapter are present, but the
ordinary annual PSM-to-result-index connection still requires developer work.
No real-UK network/hydrology pack or national transmission-expansion baseline is
accepted in this release.

## Result views: displayed value -> API field (P0 fixes, 2026-10)

Every number on a result view is either the recorded value with its basis or a
state word (`app/features/shared/valueStates.ts`). The browser formats; it never
subtracts, rescales or fills a missing value with 0
(`app/features/shared/format.ts`).

| View | Displayed | API field (source) | Missing / special |
| --- | --- | --- | --- |
| Run context bar | Methodology pill | `methodology.status`, `methodology.profile_id` (`/api/runs/{run}`) | `Methodology not recorded` (pre-2026-10 or unresolved) |
| Run context bar | Energy balance | `energy_balance_status` | `reproduction_conformant` → ● Conformant (teal); `reproduction_with_declared_deviations` → ● Declared deviations; `superseded_pre_fix` → ● Superseded |
| Run context bar | Stress events | `stress.stress_periods`, `stress.shortfall_mwh`, `stress.shortfall_basis`, `stress.shortfall_upper_mwh` | 0 → `None` (muted); `lower_bound` → `≥ x` with the upper bound on hover; absent → `Not recorded` |
| Run context bar | Notices | `validation_gate.status/gates`, `energy_balance.balance_account`, `result_publication`, `advisories`, `stress` | Priority: gate failed → Q14 withheld → pre-fix → stress |
| Runs | Annual totals | `results[].metrics` (`total_system_cost_gbp`, `cost_per_mwh_gbp`, …) | Hidden unless `result_coverage` says the year is complete; `result_publication.status=withheld` → Withheld (Q14); `publication_blocked.reason_code=GF_VALIDATION_GATE_FAILED` → `Annual results not published` |
| Runs | Average system cost | `cost_per_mwh_gbp` labelled by `system_cost_definition_id` | CEM ledger → `/MWh served`; `legacy_storage_tariff` → `/MWh generated`; otherwise `(basis not recorded)` |
| Runs | Cost composition | `total_levelized_capital_cost_gbp`, `total_operational_cost_gbp`, mechanism costs and statuses, `system_cost_includes_voll`, `operating_cost_voll_gbp`, `voll_gbp_per_mwh`, `ror_hydro_compatibility_capital_gbp` | `Not modelled` mechanisms are listed, never drawn; the memo row is excluded from the headline |
| Runs | Coverage pill | `result_coverage` | `Complete year`, `Partial year · n%`, `Running`, `Stopped · n%`, `Non-annual run`; `Withheld` only for Q14 |
| Market replay | Window card | dispatch timeline v2 bucket: `real_demand_mwh`, `accepted_supply_mwh`, `shortfall_mwh`, `stress_periods`, `shortfall_basis`, `shortfall_upper_mwh`, `storage_charge_mwh`, `storage_discharge_mwh`, `price_gbp_per_mwh` + `price_basis` | Shortfall absent → `Not recorded`; price label by basis (Q6) |
| Market replay | Stress band and legend | bucket `stress_periods > 0` | 4 px amber band; no "shortfall" bar |
| Market replay | Stress events — full year | `/api/runs/{run}/market/stress-events?year=&limit=&offset=` (`value.stress-events/v1`) | `status=not_recorded` for ledgers without the `stress_event` table; empty text follows the coverage rule |
| VRE & curtailment | KPIs and events | `/market/vre-summary`: `years[]`, `excess_scope`, `curtailment_semantics`, `event_basis`, `unused_vre_events`, `excess_curtailment_events` | Corrected columns → `Non-VRE spill`, `VRE curtailment`, basis `corrected_unused_vre`; a group with 0 affected periods → `No events recorded` |
| Network & redispatch | Fallback notice | capabilities `runtime_fallback_audit.spatially_indicative_technologies` | Shown only when a technology-year exceeds the audit threshold |
| Inspect › Market | Raw boundary check | `energy_balance.boundary_id`, `raw_boundary_status`, `maximum_absolute_boundary_residual_mwh`, `periods` | Raw evidence only; not a status-bar field |
| Data › CSV mapping | Currency and rate | catalog `fx_required_for`, `conversion_pairs[].requires_fx`; preview request `fx`; review `source_sample_rows`, `fx` | EUR needs EUR per GBP, FX basis and price year (`GF_MAPPING_FX`) |
