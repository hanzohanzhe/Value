# How to Build Your Own Model Based on VALUE — 101

[中文版](BUILD_YOUR_OWN_MODEL_101_ZH.md)

This is the top-level route from “I have my own data or method” to a runnable,
auditable and reproducible VALUE-derived model. It is written for researchers
and model developers and does not require knowledge of private Scheme C
implementation details.

For code, manifest and ZIP details for one module, continue with
[`MODULE_DEVELOPER_101.md`](MODULE_DEVELOPER_101.md). This guide decides whether
to change data, a parameter, a module or the platform. Module Developer 101 then
explains the implementation.

## 1. A VALUE model is not one Python file

A reproducible VALUE study has five parts:

```text
model identity
  = VALUE platform and contract version
  + data-pack revision and object SHA-256 values
  + Study years, scientific parameters and revision
  + module ID, version and source hash for all seven slots
  + any versioned platform-contract extension
```

The website is not a second, simplified model. Browser and command-line runs
submit the same frozen Study to the same application service, module registry
and annual orchestrator. A Study is the composition recipe. It does not own or
mutate source databases and does not copy module source into Scheme C.

## 2. One data foundation and three depths of replacement

Connect data first, then select one of three mechanisms according to the depth
of the scientific change. Not every change should be a module.

| Layer | Use it for | Python required | Changes lifecycle or input dimensions |
| --- | --- | ---: | ---: |
| Data foundation: replace the pack | Same semantics, different country, year or source | an adapter may be | No |
| Method 1: Study parameters | Same algorithm, different registered assumptions | No | No |
| Method 2: module replacement | Different algorithm at an existing lifecycle point | Yes | No |
| Method 3: platform-contract upgrade | New input dimension, state or lifecycle stage | Yes | Yes |

The shortest decision rule is:

```text
Same field, different values or source?       -> data pack
Same algorithm, different registered premise? -> Study parameter
Same lifecycle position, different method?     -> module
New input dimension, state or stage?            -> platform contract upgrade
```

### Examples

| Research change | Correct route |
| --- | --- |
| German half-hour demand, weather and fleet data | data pack / adapter |
| A different fixed demand profile | data pack; adapter if required |
| VOLL, discount rate, planning success or seed | Study parameter |
| A new storage offer-cost rule | `storage_cost` module |
| A new bidding, clearing or unit-commitment method | `psm` module |
| A new investor, project pipeline or state transition | corresponding CEM module |
| Replace all seven algorithms but retain the annual chain and typed contracts | select seven replacement modules |
| Endogenous price-responsive demand inside clearing | complete `psm`; extend the contract first if new fields are required |
| Bus, line, nodal demand and DC/AC power flow | network data/contract upgrade, then a network PSM |
| Endogenous transmission investment and commissioning | platform upgrade plus network investment, pipeline and transition contracts |
| A different carbon-accounting method | platform upgrade; there is no carbon-ledger slot today |

## 3. Data foundation: connect your own database

### 3.1 What a data pack owns

A data pack is a versioned, validated manifest that maps source-specific files
to stable semantic roles. Runtime code must not rely on an author's desktop
path. The v2 contract currently has 25 required roles:

- PSM: existing fleet, forecast/actual demand, wind/solar weather, and import
  availability and prices for France, Belgium, the Netherlands, Norway and
  Ireland;
- CEM: solar, onshore and offshore profiles; normalized and raw REPD projects;
  capital and policy/support costs; planning timelines and success rates; and
  model parameters.

The authoritative roles, allowed formats and units are `DATASET_SLOTS` in
`gridform_core/dataset_slots.py` (re-exported by `gridform_core/catalog.py`). The **Data** page is generated from the same list.
Do not infer scientific meaning from a filename alone.

### 3.2 Every binding should declare

- semantic role;
- pack-relative URI;
- an allowed format such as CSV, Parquet, NetCDF, Zarr, JSON or XLSX;
- unit, timezone, temporal resolution, currency year and technology mapping;
- source organisation, access date, licence, attribution and transformation;
- SHA-256 of the file or normalized object.

### 3.3 Standard replacement workflow

1. Copy the synthetic pack template or create a manifest with a new pack ID and
   revision.
2. Retain raw files; normalize names, units and technology classes at the
   adapter boundary.
3. Bind normalized outputs to all 25 roles using pack-relative paths.
4. Validate chronology length, unique keys, missing values, units, non-negative
   capacities, year coverage and checksums.
5. Confirm `25/25 inputs ready` on **Data**.
6. Create a new Study and select the pack; never rewrite an old Study revision.
7. Run two-period wiring, two-year smoke and then the full annual gate.

CSV, SQL and an API are source transports. PSM/CEM modules consume canonical
objects produced by the adapter. Do not put database connections, desktop paths
or source-specific column names inside scientific modules.

### 3.4 Boundary of data-only replacement

Changing values and sources is not the same as adding a data dimension. The 25
roles currently contain no buses, branches, transformers, asset-to-bus mapping
or nodal demand. Adding such files to a pack would not make the canonical
adapter pass them to `PSMInput`. Use Method 3 to add explicit roles and a typed
contract first.

## 4. Method 1: replace assumptions with Study parameters

Use this route for sensitivity analysis when the algorithm is unchanged. In
**Studies**, select the pack, years and modules, then edit registered scientific
parameters in the basic or Advanced settings.

Examples include:

- VOLL, discount rate and cost base year;
- planning success mode, seed, zombie filtering and minimum project size;
- expansion headroom, storage-utilisation floor or smoothing window;
- terminal policy, carbon-factor scenario and output granularity.

Rules:

1. Only keys in the parameter registry are credible Study overrides; do not use
   hidden environment variables.
2. Register unit, default, range and scientific meaning before execution.
3. Every save creates an append-only Study revision.
4. A run freezes effective values and their sources for comparison.
5. A setting that changes input shape, result shape or call order is really a
   module or platform upgrade.

This route needs no `module.zip`. Clone a Study, change one variable and retain
the rest of the identity for a clean sensitivity comparison.

## 5. Method 2: replace an existing lifecycle module

### 5.1 Seven public slots

```text
YearState(y)
  -> pipeline.advance_year
  -> psm.run
  -> vre_cap.evaluate + storage_cap.evaluate
  -> investment.decide
  -> pipeline.admit_projects
  -> transition.apply
  -> YearState(y+1)
```

| Slot | Responsibility |
| --- | --- |
| `psm` | period clearing, offers, storage state and reliability |
| `storage_cost` | annual storage cost/offer rule for an offer-based PSM |
| `vre_cap` | annual wind and solar expansion headroom |
| `storage_cap` | annual storage expansion headroom |
| `investment` | investment proposals by economic owner |
| `pipeline` | project admission, success, failure, deferral and commissioning |
| `transition` | retirement, carry-over and next-year system state |

This is not a cosmetic plugin system limited to agent bidding. A researcher can
replace one slot or all seven in one Study. Each downstream stage receives the
real typed output from the preceding stage.

Replacing all seven still has a boundary: the annual call order, current input
dimensions, shared state, cost/carbon ledgers and result contracts are owned by
the platform. It creates a new model within the VALUE lifecycle; it does not
turn VALUE into an arbitrary-script launcher with unconstrained signatures.

### 5.2 What is `module.zip`?

It is a `value.module-bundle/v1` installation package containing at least:

```text
my-module.zip
  force-bundle.json        # generated exact file inventory and SHA-256 values
  value-module.json        # value.module/v2 manifest
  LICENSE
  README.md                # recommended equations, assumptions and scope
  src/
    my_package/
      __init__.py
      plugin.py            # entry class named by the manifest
```

The installer checks safe paths, hashes, manifest, entry point, slot/contract
and callable conformance, then promotes the bundle atomically into the local
module registry. It does not call `pip`, download dependencies or accept native
binaries. External code still executes in the VALUE Python process.
Conformance proves wiring, not scientific validity.

See [`MODULE_DEVELOPER_101.md`](MODULE_DEVELOPER_101.md) for exact fields,
templates for all seven slots, build commands and the test ladder.

### 5.3 User workflow

1. Give the implementation a new stable ID, semantic/scientific version and
   package name.
2. Pass unit, contract and deterministic-fixture tests.
3. Upload and review the ZIP under **Modules → Install a model module**.
4. Clone a Study revision and select the module in the matching slot.
5. Run two-period wiring, then two-year smoke, full annual and required
   multi-year tests.
6. Compare the Runs on **Compare**, with the baseline Run as the reference
   Run; inspect clearing and planning in **Inspect** and curtailment attribution
   on the Run's **Network & redispatch** page.

### 5.4 Evidence capabilities for VRE curtailment attribution

A replacement PSM does not receive detailed zonal VRE attribution merely by
returning final dispatch or declaring a capability. The built-in staged adapter
is currently the only automatic capture path. It supplies the same VRE
object/tranche set for perfect-forecast copperplate, forecast-schedule plus
realised copperplate, and final zonal dispatch.

For a third-party PSM, declaring
`evidence.vre-counterfactual-snapshot/v1` and resolving a balancing module that
produces `network.zonal-redispatch-result/v1` establishes compatibility only.
The module author must also provide an execution integration adapter and a
complete, reconciled market-ledger evidence path (the `value.market-ledger/v6`
attribution tables, kept by later ledger versions). Stable asset,
owner, zone, technology and bid-tranche identities, MWh units and one matched
realised-input SHA-256 are evidence requirements, not optional display metadata.
Full external execution of this path has not yet been verified.

A module that does not claim the capability may still run, but attribution
remains unavailable and all unsupported quantities are `null`, not zero. See
Module Developer 101 for the exact fields, example payload and focused static
checks. Scientific acceptance still requires external integration coverage,
added/avoided fixtures, constraint failures and an independent oracle
appropriate to the new module.

### 5.5 Alternative zonal solver contract

A zonal balancing replacement must declare `solver_contract` in its
`value.module/v2` manifest, publish the solver identity, numerical
lexicographic semantics, one-sided objective caps, advanced-setting bounds and
no-fallback behaviour. The built-in `value-zonal-redispatch-balancing` module is
`4.0.0` (solver contract v4: total load shedding is locked after the primary
solve, then only the bid-cost terms carry a numerical lock; GBP 1 is the
acceptance ceiling); it uses SciPy `1.8.1` and `highs-ds` by default. Its recorded embedded
HiGHS binary is source-registered as `candidate`, not independently validated.

The following usable manifest fragment is intentionally identical to the
built-in module's executable `solver_contract`; copy it before changing a
third-party solver's declared contract and validation gates.

```json
{
  "solver_contract": {
    "schema_path": "gridform_core/data/contracts/network-solver-contract-v4.schema.json",
    "semantics": "four_phase_lexicographic_primary_shed_lock_then_numerical_bid_cost_cap_gbp1_acceptance_ceiling_mwh_coefficient_aware",
    "defaults": {
      "schema_version": "value.network-solver-contract/v4",
      "contract_version": "value.zonal-lexicographic-shed-lock/v4",
      "method": "highs-ds",
      "presolve": true,
      "primal_feasibility_tolerance": 1e-09,
      "dual_feasibility_tolerance": 1e-09,
      "ipm_optimality_tolerance": 1e-09,
      "warning_fraction": 0.1,
      "validated_ceilings": {
        "primary_bid_cost_gbp": 1.0,
        "secondary_schedule_deviation_mwh": 0.001,
        "physical_throughput_mwh": 0.001
      },
      "absolute_ceilings": {
        "primary_bid_cost_gbp": 1.0,
        "secondary_schedule_deviation_mwh": 0.01,
        "physical_throughput_mwh": 0.01
      },
      "is_builtin_default": true,
      "requires_acknowledgement": false
    },
    "ranges": {
      "method": [
        "highs-ds",
        "highs-ipm",
        "highs"
      ],
      "primal_feasibility_tolerance": [
        1e-10,
        1e-07
      ],
      "dual_feasibility_tolerance": [
        1e-10,
        1e-07
      ],
      "ipm_optimality_tolerance": [
        1e-12,
        1e-07
      ],
      "warning_fraction": {
        "exclusive_minimum": 0.0,
        "maximum": 1.0
      }
    },
    "recorded_reference_thresholds": {
      "primary_bid_cost_gbp": 1.0,
      "secondary_schedule_deviation_mwh": 0.01,
      "physical_throughput_mwh": 0.01
    },
    "stable_key_rule": {
      "objective": "sum((variable_index + 1) * variable_value)",
      "variable_order": "sorted bid, corridor, zone, storage-asset and absolute-flow keys",
      "locked": false
    },
    "automatic_solver_fallback": false,
    "automatic_copperplate_fallback": false
  }
}
```

Each period and locked phase must write v7 solver diagnostics, and the platform
continues to enforce energy, SOC, capacity, settlement and ledger validators.
Changing optimiser does not bypass those validators. An alternative optimiser
may run, but it has no validated badge until its declared independent random,
mutation, 24-hour and 168-hour gates pass. Treat its result as a separate Study
revision, preserve warning/failure evidence, and keep the experimental zonal
network scoped as a lossless transport representation rather than security
analysis or transmission expansion.

## 6. Method 3: upgrade the platform contract or lifecycle

If a method needs data, state or a stage that existing contracts cannot express,
do not hide it in `extensions`, global variables or an unrelated slot. Make an
explicit, versioned platform upgrade.

### 6.1 When it is required

- new dimensions: buses, branches, nodal load, reserve zones or fuel networks;
- new inter-year state: transmission assets, retirement queues, obligations or
  fuel inventory;
- new lifecycle stages: transmission expansion, capacity market, independent
  demand response or carbon market;
- new public outputs: nodal prices, branch flows, reactive power or shadow
  prices;
- a scientific result that cannot be represented losslessly by existing typed
  outputs.

### 6.2 Correct upgrade sequence

1. Write an extension proposal covering the question, equations, inputs,
   outputs, state ownership and compatibility boundary.
2. Define semantic roles, schema, units, temporal/spatial indices and
   provenance for new data.
3. Add a versioned contract such as `value.network-psm/v1`; do not silently
   change v2 semantics.
4. Extend the canonical adapter so inputs are validated, frozen and delivered.
5. Declare module capabilities and compatibility rules; incompatible Studies
   must fail preflight.
6. If there is a new stage, update the orchestrator, checkpoints, state
   transition and registry.
7. Extend result schemas, SQLite/JSON artifacts, Inspect and the comparator.
8. Supply migration or keep the old contract executable.
9. Pass old-model regression, new-contract conformance, analytical fixtures and
   multi-year state tests.
10. Release a new platform version. Algorithms implementing that new contract
    can then become ordinary interchangeable module bundles.

### 6.3 Concrete DC/AC transmission route

The accepted GB baseline remains single-node, but VALUE now
ships a solver-neutral network contract alongside it. It adds conditional buses,
branches, asset-to-bus mapping and nodal-demand roles without migrating old
Studies. Therefore:

```text
Constrained period dispatch only
  = network data roles + typed network PSM contract + canonical adapter
  + DC or AC PSM module + network outputs and validation

Endogenous transmission expansion as well
  = all of the above
  + network assets in YearState
  + location-aware InvestmentProposal
  + network planning / expansion policy
  + commissioning and transition
```

The shipped reference contract provides:

- `value.network.buses`, `value.network.branches`;
- `value.network.asset-map` and `value.network.nodal-demand`;
- angles, limits, KCL/KVL, congestion and nodal prices for DC;
- voltage, reactive power, losses, taps and convergence status for AC;
- `network.single-node`, `network.dc/v1` and `network.ac/v1` capabilities.

The shipped reference DC module has analytical 2/3-bus, 24/168-hour, random,
island and mutation checks. The experimental AC module is local feasibility of a
declared schedule, not AC OPF. A replacement solver must still provide its own
independent validation, and existing single-node Studies must retain their old
contract and results.

## 7. Four derivative-model recipes

### A. Another country, still single-node

```text
new data pack + adapter
  -> existing modules
  -> new Study parameters
  -> wiring -> annual -> multi-year
```

### B. Keep the PSM and study a new investment theory

```text
existing or new data pack
  -> new investment.zip
  -> optional pipeline.zip
  -> new Study revision
  -> two-year state-injection test -> multi-year pathway
```

### C. Replace the whole model inside the current annual framework

```text
your data pack
  + psm/storage_cost/vre_cap/storage_cap/investment/pipeline/transition modules
  + your Study parameters
  -> VALUE orchestrator, ledgers, checkpoints, comparison and Inspect
```

This is a genuinely different model that deliberately reuses the VALUE
lifecycle and public contracts.

### D. Add transmission expansion

```text
value-network-contract-extension
  + network data-pack roles
  + replacement or reference network PSM module
  + optional value-network-expansion-extension
  + network-expansion module
  + network result views and validation suite
```

This is deliberately two package types: a `value.extension-bundle/v1` declares
the new roles/capabilities, while a `value.module-bundle/v1` supplies executable
solver or lifecycle logic. A single module ZIP must not invent hidden data roles
or mutate the core contract.

## 8. Recommended derivative-project layout

Keep source data, executable code and study recipes separate instead of making
one opaque ZIP:

```text
my-value-model/
  MODEL_CARD.md
  CITATION.cff
  LICENSES/
  data-pack/
    manifest.json
    SOURCE_REGISTER.md
  modules/
    my-psm-1.0.0.zip
    my-investment-1.0.0.zip
  studies/
    baseline.study.json
    sensitivity.study.json
  validation/
    fixtures/
    expected-results/
    TEST_REPORT.md
```

Install/import data packs, modules and Studies separately, then compose them in
a Study. Users can upgrade one component and reviewers can see whether data or
method changed.

## 9. Test gates proportional to the change

| Change | Minimum gate |
| --- | --- |
| data pack | schema, units, checksums, year coverage, chronology alignment and two-period wiring |
| Study parameter | type/range, effective value/source and one-variable A/B |
| module | unit, contract conformance, wiring and annual; at least two years if stateful |
| all seven modules | full-chain integration, ledgers, checkpoint/replay, annual and multi-year |
| platform contract | old-contract regression, migration, capability negotiation, analytical and fault-injection cases |

Do not confuse run modes:

- two-period verification proves wiring and artifacts only;
- two-year smoke proves cross-year calls, not annual economics;
- full annual evaluates all 17,520 half-hours;
- multi-year evaluates the CEM pathway and state inheritance;
- a new algorithm also needs an independent benchmark, analytical solution or
  external solver oracle.

## 10. Versioning, audit and publication

Every result should freeze and retain:

- VALUE platform, API and contract-schema versions;
- Study ID/revision, years and effective parameters;
- data-pack ID/revision, bindings and object SHA-256 values;
- module ID, version, scientific version, source SHA-256 and capabilities;
- resolved module graph, initial state and annual state hashes;
- cost/carbon definition, terminal policy, seed and solver identity;
- validation reports, run artifacts and licences.

Publish a `MODEL_CARD.md` describing the research question, which layer changed,
unsupported capabilities, data redistribution rights, validation scope and
permitted claims. A smoke pass is not annual validation; successful installation
is not scientific validation.

## 11. Final release checklist

- [ ] I can state whether each change is data, parameter, module or platform.
- [ ] Data uses relative paths and records source, licence, transformation and
      SHA-256.
- [ ] Scheme C compatibility code and built-in module IDs were not overwritten.
- [ ] Every module has a manifest, licence, method note and conformance evidence.
- [ ] The Study revision freezes effective parameters, module graph and data.
- [ ] Every cross-year state change has at least a two-year test.
- [ ] Annual/multi-year claims come from runs of the corresponding length.
- [ ] New dimensions/stages use a versioned contract, not hidden fields/globals.
- [ ] Old-contract compatibility or migration is tested.
- [ ] The model card separates software operation, numerical validation and a
      scientific baseline.

## 12. Continue reading

- Module code, manifest, ZIP and testing:
  [`MODULE_DEVELOPER_101.md`](MODULE_DEVELOPER_101.md)
- Every website section and run workflow: [`USER_GUIDE.md`](USER_GUIDE.md)
- Current equations and unsupported scope:
  [`MATHEMATICAL_REFERENCE.md`](MATHEMATICAL_REFERENCE.md)
- Installation: [`INSTALLATION.md`](INSTALLATION.md)
- Validation and permitted claims:
  [`VALIDATION_AND_CLAIMS.md`](VALIDATION_AND_CLAIMS.md)
