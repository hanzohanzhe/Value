# GridForm model-visibility architecture plan

## 1. Outcome

The local website must execute the same typed, public contracts that third-party
PSM and CEM modules implement. There must be no separate "clean architecture"
used only by tests while production enters a Scheme C compatibility script through
an unrelated callback interface.

A completed run must let a researcher answer, without reading private runtime
state:

1. Which data, parameters and module code were used?
2. Which projects entered, advanced, failed, were deferred or commissioned?
3. Which orders were offered and accepted in each market period?
4. How did a market result become an investment decision and then next-year state?
5. Can the result be repeated from an immutable run bundle?

The normal Run centre remains concise. Detailed evidence is exposed in collapsible
planning panels, an Audit view, paginated APIs and downloadable artifacts.

## 2. Audited current state

### 2.1 Displayed architecture

The UI and public Python contracts describe:

```text
ModelState(year y)
  -> PSMInput -> PSMResult
  -> ordered CEM modules -> CapacityDecision[]
  -> StateTransition -> ModelState(year y+1)
```

The relevant files are:

- `gridform_core/contracts.py`
- `gridform_core/interfaces.py`
- `gridform_core/orchestrator.py`
- `model-sdk/contracts.ts`

### 2.2 Actual website execution

The production website currently executes:

```text
app/page.tsx
  -> POST /api/projects/{id}/runs
  -> backend/server.py::_start_run
  -> backend/model_runner.py::run
  -> modular_run.py::run_modular_scheme_c
  -> compat/modular_case3.py::main
  -> callback wrappers in scheme_c_modules.py
  -> compat/modular_simulation_model.py and investment-support functions
```

`AnnualModelOrchestrator` is not this production path. The runtime wrappers accept
`Callable[..., Any]`, `*args` and `**kwargs`, rather than `PSMInput`, `PSMResult`,
`CapacityDecision` and `ModelState`.

### 2.3 The real annual order

The current UI suggests:

```text
PSM -> investment -> planning -> VRE cap -> storage cap -> next year
```

The copied Scheme C path actually behaves more like:

```text
restore/check initial pipeline
  -> remove/filter/defer projects
  -> commission projects due in year y into the operating fleet
  -> apply exogenous annual changes
  -> run PSM for year y
  -> calculate revenues and costs
  -> calculate VRE and storage expansion headroom
  -> make agent investment decisions subject to that headroom
  -> admit new proposals to the planning pipeline
  -> apply success/timeline rules
  -> checkpoint state for year y+1
```

This difference is not cosmetic. Planning has both a beginning-of-year transition
and an end-of-year admission role, and expansion caps are inputs to investment
rather than modules that run after it.

### 2.4 Visibility gaps

| Gap | Current evidence | Consequence |
| --- | --- | --- |
| Dual execution architecture | Website calls `modular_case3.main()`; typed orchestrator is separate | A module can pass public contract tests yet never run from the website |
| Callback wrappers instead of contracts | `Callable[..., Any]` wrappers record start/complete | Module IDs prove invocation, not semantic compatibility |
| Incorrect public stage order | UI differs from copied annual lifecycle | Users misunderstand when capacity enters the PSM and when caps constrain investment |
| Positional result tuples | `results[20]`, `results[22]`, `results[-8]`, etc. | Adding or moving one return value can silently corrupt later calculations |
| Global configuration and import-time options | `config` mutation, environment variables, late imports | A run cannot be understood from the project JSON alone |
| Hidden fixed assumptions | Single node, 17,520 periods, Python 3.10, virtual pool sentinel | Users may mistake numerical/runtime assumptions for editable science |
| Hidden editable assumptions | planning filters, success mode, timelines, cap fractions | Scenario sensitivity requires editing code or environment variables |
| Destructive pipeline filtering | failed/filtered projects are removed from the live list | No durable count or reason for failed projects |
| Coarse module evidence | start/complete events and a few counts | No input/output/state hashes or causal link between stages |
| Slow optional market trace | per-row CSV writes inside the market loop | Full audit can materially slow a 17,520-period year |
| Aggregated frontend result | annual costs and capacities only | Users cannot inspect planning evolution or period clearing |
| Silent exception handling | broad exceptions followed by `pass` | Missing evidence may appear as a valid zero or absent record |
| Incomplete run identity | data/project snapshot but no code hash or resolved parameter set | Later reproduction can use different code or hidden defaults |

## 3. Lessons from established model platforms

GridForm is not required to imitate an optimization package internally, but it
should offer an equivalent inspection boundary.

- PyPSA attaches the generated Linopy model to `n.model`, where users can inspect
  named variables, constraints and the objective before or after solution. Its
  `create_model()` and `solve_model()` steps are explicit.
- GridPath uses a common modular platform and database-oriented inputs/outputs for
  production-cost, capacity-expansion and related studies.
- Switch modules explicitly define arguments, model components, input loading and
  post-solve output hooks.
- ASSUME separates units, operators, bidding strategies and market clearing, and
  stores detailed outputs in a database for analysis.

GridForm's non-optimization equivalent of PyPSA's visible model must be a named
annual lifecycle plus a queryable market and planning ledger.

Primary references:

- https://docs.pypsa.org/latest/user-guide/network-optimization/
- https://docs.pypsa.org/latest/api/networks/optimize/
- https://gridpath.readthedocs.io/en/stable/introduction.html
- https://switch-model.org/
- https://assume.readthedocs.io/en/stable/introduction.html

## 4. Target architecture

### 4.1 One production path

```text
HTTP run request
  -> validate ProjectV2 + DataPack + ModuleManifest + ParameterSet
  -> create immutable ResolvedRun
  -> resolve exact module versions from ModuleRegistry
  -> AnnualModelOrchestratorV2.run(...)
  -> typed YearResultV2 + artifact references
  -> status summary + paginated artifact APIs
```

The browser, CLI and integration tests all call the same application service.
There is no fallback to `modular_case3.main()` when a typed module fails.

### 4.2 Correct annual lifecycle

```text
YearState(y)
  -> PlanningPipeline.advance(y)
       returns commissioned, failed, deferred, active and OperatingState(y)
  -> PSM.run(OperatingState(y))
       returns named MarketYearResult
  -> ExpansionPolicy.evaluate(PSM result, OperatingState)
       returns VRE/storage/other headroom decisions
  -> InvestmentModule.decide(PSM result, headroom, policy, state)
       returns proposals and retirements
  -> PlanningPipeline.admit(proposals)
       returns project events and PipelineState(y+1)
  -> StateTransition.apply(...)
       returns YearState(y+1)
```

The pipeline remains one selectable module but has two explicit methods:
`advance_year()` and `admit_projects()`. This accurately represents the current
Scheme C science without hiding commissioning before PSM execution.

### 4.3 Contract families

Use named dataclasses or validated typed models for:

- `ResolvedRun`
- `YearState`
- `OperatingState`
- `PlanningProject`
- `PlanningEvent`
- `PSMInput`
- `MarketYearResult`
- `PeriodSummary`
- `MarketOrder`
- `ExpansionHeadroom`
- `InvestmentProposal`
- `InvestmentDecision`
- `YearResult`
- `ArtifactReference`

Contracts carry a schema version and units. `Mapping[str, Any]` is permitted only
inside a declared extension namespace, never for core fields.

### 4.4 Scheme C anti-corruption adapter

The retained Scheme C return tuple must not be changed. Introduce a boundary:

```text
legacy run_simulation tuple
  -> SchemeCLegacyResultAdapter.validate_and_convert()
  -> named MarketYearResult
```

The adapter owns all old tuple positions in one place, verifies tuple length and
field shapes, and fails loudly on incompatibility. No other production file may
use a numeric index into the legacy result.

After parity is established, the modular copy may gain a native named result, but
the retained reference remains untouched.

### 4.5 Module manifests

Every executable module declares:

```yaml
schema_version: gridform.module/v2
id: scheme-c-psm
version: 2.0.0
slot: psm
contract: gridform.psm/v2
inputs: [...]
outputs: [...]
parameters: [...]
units: {...}
state_reads: [...]
state_writes: [...]
determinism: deterministic | seeded | stochastic
artifacts: [...]
implementation: package.module:ClassName
```

The API catalog must be generated from the same manifests used by the registry.
Hard-coded parallel lists in `catalog.py`, `server.py` and the registry are removed.

## 5. Planning pipeline visibility

### 5.1 Do not lose projects

The operating pipeline may retain only active projects for speed, but every
transition must first append an immutable event. Filtering must become a recorded
decision, not disappearance.

Required event types:

- `source_imported`
- `excluded_existing_stock`
- `filtered_status_zombie`
- `filtered_schedule_zombie`
- `filtered_below_minimum_size`
- `filtered_outside_horizon`
- `admitted_external`
- `admitted_model_investment`
- `success_evaluated`
- `failed_planning`
- `deferred`
- `stage_advanced`
- `commissioned`
- `depleted_or_retired`

Every failure has a stable `reason_code`, not only free text.

### 5.2 Planning project schema

At minimum:

```text
project_id
name
source                         external_repd | model_investment
technology
capacity_mw
original_capacity_mw
region
latitude
longitude
development_stage
status
decision_year
expected_completion_year
success_mode
success_probability
random_draw                    nullable
outcome
failure_reason_code            nullable
assigned_asset_id              nullable
```

Generate stable IDs from source identifiers. Do not use the display name alone.

### 5.3 Planning artifacts and UI

Persist:

```text
model-output/planning/pipeline.sqlite
  projects
  events
  annual_summary

model-output/planning/summary.json
```

The Run centre shows one collapsed `Planning pipeline` section per year:

- active projects and MW;
- commissioned projects and MW;
- failed/filtered projects and MW;
- projects expected in the next three years;
- breakdown by stage, technology and region;
- a project table with location/region and failure reason.

The summary loads with the normal run response. The project table is paginated and
loaded only when opened. A geographic map is optional after the table is correct.

## 6. Parameter policy

Every effective value belongs to exactly one category.

### 6.1 Fixed Scheme C model assumptions

These are documented in the README/model card and included in the run manifest,
but are not arbitrary controls in the first advanced-settings UI:

- single GB node with no internal transmission constraints;
- external interconnectors represented as boundary import offers;
- half-hour periods and 17,520 periods in a full year;
- bid-at-cost continuous dispatch without start/stop, ramping, minimum output or
  minimum up/down constraints;
- the very large virtual storage-pool power/energy sentinel used to avoid binding
  the diagnostic pool;
- the Python 3.10 parity environment for the retained Scheme C implementation;
- the definition and accounting boundary of system cost.

Changing one of these requires a new PSM/module version or a future contract
capability, not an undocumented project override.

### 6.2 User-editable scientific parameters

Expose under `Advanced settings`, with type, unit, default, bounds and explanation:

- planning success mode (`expected` or seeded `stochastic`);
- random seed when stochastic mode is selected;
- include uncertain REPD projects;
- zombie filtering enabled;
- status-staleness year or age rule;
- construction grace years;
- minimum project size;
- maximum pipeline completion year/horizon;
- planning timeline statistic and supported overrides;
- model-investment defer/spread years;
- VRE expansion-cap fraction;
- storage expansion-cap fraction;
- storage capacity-credit method where the selected storage module supports it;
- scenario/policy selection;
- clearly labelled experimental bid multiplier, only if retained for sensitivity.

Success-rate values and detailed planning timelines normally remain versioned Data
Pack inputs. The UI may offer an override layer, but must show source value versus
project override.

### 6.3 Runtime and output controls

These affect execution or artifacts, not scientific meaning:

- checkpoint enabled;
- market trace level (`off`, `summary`, `full`);
- generation trace level;
- console verbosity;
- artifact compression/batch size.

Store them separately from scientific parameters in `ResolvedRun`.

### 6.4 Parameter registry

Define one authoritative registry with fields:

```text
id, group, type, default, allowed_values, minimum, maximum, unit,
visibility, scientific_effect, module_owner, source_precedence
```

Projects store overrides only. Before execution, the resolver writes the complete
effective set to `resolved-run.json`. Model code receives typed parameters and must
not read scientific choices directly from environment variables.

Environment variables remain allowed only for launcher/runtime mechanics and are
captured in the run manifest.

## 7. Fast period-level market evidence

### 7.1 Storage choice

A single large JSON document is rejected because serialization and memory growth
would slow annual runs. Use standard-library SQLite with prepared statements and
batched transactions. JSON is an API/export representation, not the primary store.

### 7.2 Trace levels

- `off`: no period ledger; intended only for controlled performance tests.
- `summary` (default): one row per period and market stage.
- `full`: summary plus all offered/accepted/rejected orders and storage state.

### 7.3 SQLite schema

`period_summary` includes:

```text
year, period, market_stage, forecast_demand_mwh, real_demand_mwh,
accepted_supply_mwh, storage_charge_mwh, storage_discharge_mwh,
vre_available_mwh, vre_accepted_mwh, curtailed_mwh, import_mwh,
clearing_price_gbp_per_mwh, physical_resource_cost_gbp,
market_payment_gbp, blackout_mwh, energy_balance_residual_mwh
```

`orders` includes:

```text
year, period, market_stage, sequence, order_id, agent_id, asset_id,
technology, side, offered_mwh, bid_price_gbp_per_mwh, accepted_mwh,
settlement_price_gbp_per_mwh, physical_cost_gbp_per_mwh,
status, rejection_reason_code
```

`storage_state` includes charge/discharge/SOC and only the minimum pricing evidence
needed to reproduce the submitted order. Detailed annual storage-cost audit remains
a downloadable artifact, not a main Run-centre card.

### 7.4 Performance rules

- one writer object per run, not per period;
- prepared inserts and in-memory buffers;
- commit in bounded batches or at year end;
- no `json.dumps`, pandas DataFrame creation or console printing inside the hot
  order loop;
- `NullMarketLedger` makes disabled tracing nearly free;
- record writer time and rows so overhead can be benchmarked;
- a performance gate compares trace `off`, `summary` and `full` on a fixed fixture.

The API exposes paginated endpoints and streams an explicit export when requested.
It never loads the complete ledger into `status.json`.

## 8. Run bundle and causal evidence

Target run directory:

```text
status.json
resolved-run.json
project-snapshot.json
data-pack-snapshot.json
module-manifest-snapshot.json
provenance.json
model.log
model-output/
  annual-results.json
  module-events.jsonl
  market/market.sqlite
  planning/pipeline.sqlite
  planning/summary.json
  checkpoints/
```

`provenance.json` contains module source hashes, Git commit when available,
dependency versions, Python executable/version, data hashes, random seeds and
initial-state hash.

Each stage event contains:

```text
run_id, year, stage, module_id, module_version, action,
input_contract_version, output_contract_version,
input_state_hash, output_state_hash, artifact_ids, duration_ms
```

## 9. API and frontend changes

New API capabilities:

- module manifests and parameter schemas;
- project validation against selected module capabilities;
- effective-parameter preview before save/run;
- planning annual summary and paginated projects/events;
- period summaries and paginated market orders;
- artifact metadata/download;
- run provenance.

The frontend gains:

1. generated advanced settings grouped by Planning, Expansion, Market experiment,
   and Output/runtime;
2. an accurate annual lifecycle diagram;
3. planning pipeline summaries in annual results;
4. an on-demand Audit view for market periods and causal stage evidence;
5. badges that distinguish fixed assumptions, Data Pack values and project
   overrides.

Do not add all storage pricing internals to the main page. Visibility means they
are queryable and downloadable, not permanently displayed.

## 10. Migration strategy

Use a strangler migration; do not rewrite the complete Scheme C loop at once.

1. Freeze retained hashes and accepted numerical fixtures.
2. Introduce v2 contracts and manifests without switching production.
3. Centralize tuple interpretation in a validated named adapter.
4. Add planning events around existing pipeline mutations.
5. Add parameter resolution while preserving current effective defaults.
6. Implement the accurate v2 orchestrator and Scheme C stage adapters.
7. Run old and new paths side-by-side in tests only; compare stage and annual output.
8. Switch the website to the v2 application service after parity.
9. Delete production fallback to the old entry point; retain it only as a reference
   comparison command.
10. Add market ledger and frontend inspection incrementally after the cutover.

## 11. Release gates

No prompt is complete until its relevant gates pass:

- retained reference hashes unchanged;
- contract/schema tests;
- wrong-slot/wrong-version module rejection;
- no numeric indexing of legacy PSM results outside the one adapter;
- planning event conservation: imported = active + commissioned + failed/filtered
  plus explicitly classified exclusions;
- per-period energy-balance residual within declared tolerance;
- deterministic replay for expected mode and seeded stochastic mode;
- two-period wiring test;
- full 2025 run;
- full 2025-2026 state-transition test;
- comparison with retained Scheme C fixture;
- frontend build and rendered-page tests;
- trace-overhead benchmark recorded, not guessed;
- API pagination tests that never embed complete ledgers in workspace/status calls.

## 12. Definition of done

The visibility refactor is complete only when:

- changing a project module ID changes the typed implementation executed by the
  same runner used by the website;
- no website run calls `modular_case3.main()` as its orchestration boundary;
- the UI diagram matches the tested annual lifecycle;
- all scientific parameters are either fixed and documented, Data Pack-bound, or
  explicitly editable through the parameter registry;
- every pipeline loss has a recorded reason and every commissioning has a source;
- every period summary is queryable without loading an annual file into memory;
- positional Scheme C outputs cannot escape the compatibility adapter;
- a run bundle identifies data, code, modules, parameters, environment and seed;
- retained Scheme C files and reference outputs remain byte-for-byte unchanged.
