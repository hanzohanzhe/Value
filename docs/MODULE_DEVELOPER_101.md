# VALUE General Module Authoring and Replacement 101

[中文版](MODULE_DEVELOPER_101_ZH.md)

If you have not yet decided whether the change belongs in a data pack, Study
parameter, module or platform contract, start with
[`BUILD_YOUR_OWN_MODEL_101.md`](BUILD_YOUR_OWN_MODEL_101.md).

This handbook describes the live `value.module/v2` module system used by the local
website and annual orchestrator. It applies to all seven supported slots. It
does not require changes to Scheme C or pretend that unsupported extension
points already exist.

## 1. Decide whether the change is data, a parameter, a module or architecture

| Intended change | Correct extension point |
| --- | --- |
| New source files, country or field mapping | Data pack / data adapter |
| A registered numeric assumption | Study parameter |
| A different algorithm for an existing lifecycle stage | Module |
| A different chart or export | Result transformation / frontend |
| A lifecycle stage that does not currently exist | Core architecture extension |

Examples:

- A fixed alternative demand profile belongs in a data pack.
- Endogenous price-responsive demand currently belongs in a complete PSM, or a
  future demand contract; there is no separate demand slot today.
- DC/AC algorithms belong in a complete PSM, but the current v2 input has no
  buses, lines or nodal demand. Add versioned network data roles and a PSM
  contract first, then make the network solver replaceable; an ordinary bundle
  implementing the existing contract is insufficient.
- Carbon factors are data/parameters. Replacing the carbon-accounting method
  would require a future carbon-ledger slot.
- Storage cost recovery is a `storage_cost` module.
- Project success and commissioning are a `pipeline` module.
- Agent investment logic is an `investment` module.

The rule is: **data in a pack, values in parameters, algorithms in an existing
slot; do not disguise a new lifecycle stage as the wrong module.**

## 2. How replacement actually works

```text
module.zip
  -> validate bundle, manifest, entry point and contract
  -> atomically install below VALUE_DATA_HOME/modules
  -> workspace registry loads built-in and external modules
  -> a Study stores one selected module ID per slot
  -> run freezes ID, version, contract and source SHA-256
  -> registry instantiates the selected entry class
  -> orchestrator calls it at the fixed lifecycle point
  -> typed output enters the next stage
```

Replacement means selecting an alternative implementation in a new Study
revision. It does not overwrite Scheme C, delete the previous implementation or
mutate an old Study. The previous revision remains reproducible and supports A/B
comparison and rollback.

External bundles cannot shadow built-in IDs. Editing the source of an
installed module in place (same ID and version) is accepted and recorded, not
refused (DECISIONS A16-4): Check readiness shows the amber warning
`GF_PREFLIGHT_MODULE_SOURCE_CHANGED` with the installed and the current source
SHA-256, every Run freezes the new source hash, and Compare marks the module
method as changed. The installation record and the scientific version are not
updated, so a change you intend to publish or compare as a method should still
get a new module version (or ID), scientific version and package name and be
installed as a bundle.

## 3. Annual lifecycle

```text
YearState(y)
  -> pipeline.advance_year       -> OperatingState(y)
  -> psm.run                     -> MarketYearResult(y)
  -> vre_cap/storage_cap.evaluate -> ExpansionHeadroom(y)
  -> investment.decide           -> InvestmentDecision(y)
  -> pipeline.admit_projects     -> next planning pipeline
  -> transition.apply            -> YearState(y+1)
```

`storage_cost` is injected into an offer-based PSM when that PSM requires
`storage.bid-cost-function`; it is not another annual stage. A PSM declaring
`storage.central-cooptimization` cannot also select a storage-offer policy.

The orchestrator owns the year loop. A module implements one stage and must not
launch a hidden ten-year script.

## 4. Supported slots and contracts

| Slot | Contract | Required callable | Returns |
| --- | --- | --- | --- |
| `psm` | `gridform.psm/v2` | `run(model_input)` | `MarketYearResult` |
| `storage_cost` | `gridform.storage-cost/v1` | `create(**parameters)` | annual storage-offer object |
| `vre_cap` | `gridform.expansion-policy/v2` | `evaluate(run, state, market)` | `ExpansionHeadroom` |
| `storage_cap` | `gridform.expansion-policy/v2` | `evaluate(run, state, market)` | `ExpansionHeadroom` |
| `investment` | `gridform.investment/v2` | `decide(run, state, market, headroom)` | `InvestmentDecision` |
| `pipeline` | `gridform.planning/v2` | `advance_year(...)`, `admit_projects(...)` | planning results |
| `transition` | `gridform.state-transition/v2` | `apply(run, current_state, planning, investment)` | next `YearState` |

Authoritative definitions are in `gridform_core/v2/interfaces.py`,
`gridform_core/v2/contracts.py` and `gridform_core/v2/orchestrator.py`. Do not
depend on private `scheme_c_1000twh/compat` internals.

## 5. What each module can replace

### PSM

Use for bidding and settlement, unit commitment/economic dispatch, perfect
foresight, storage chronology, endogenous demand response, imports and
reliability. The current v2 contract directly supports copper-plate models.
Zonal/DC/AC formulations become PSM implementations after the network-contract
upgrade described in the top-level guide.

```python
class MyPSM:
    id = "my-psm"
    version = "1.0.0"

    def run(self, model_input):
        # PSMInput -> MarketYearResult
        ...
```

Handle or explicitly reject demand, resources, storage, blackout and terminal
SOC. Returned year and module ID must match the input and entry class.

### Storage cost

Use for dynamic/legacy/alternative storage recovery and offer rules.

```python
class MyStorageCostDefinition:
    id = "my-storage-cost"
    version = "1.0.0"

    def create(self, **parameters):
        return MyAnnualStorageOffer(**parameters)

class MyAnnualStorageOffer:
    def prepare_year(
        self, year, *, capital_cost_gbp, power_capacity_mw,
        energy_capacity_mwh, discharge_efficiency,
    ):
        ...

    def bid_price_gbp_per_mwh(self, dwell_periods):
        ...
```

### VRE and storage expansion policies

Use for technical potential, supply-chain limits, policy caps or
curtailment/utilisation-based headroom. Return finite non-negative MW and do not
multiply a shared technology budget by the incumbent asset count.

```python
class MyExpansionPolicy:
    id = "my-expansion-policy"
    version = "1.0.0"

    def evaluate(self, run, state, market):
        return ExpansionHeadroom(
            f"{run.run_id}:{self.id}:{market.year}",
            market.year,
            self.id,
            {"solar": 1000.0},
        )
```

### Investment

Use for NPV/IRR/payback/real-options rules, heterogeneous agents, finance
constraints, investment and retirement. Proposals must carry enough owner and
economic information for the pipeline to create CAPEX, FOM, lifetime and
efficiency records.

```python
class MyInvestment:
    id = "my-investment"
    version = "1.0.0"

    def decide(self, run, state, market, headroom):
        return InvestmentDecision(
            f"{run.run_id}:investment:{market.year}",
            market.year,
            self.id,
            (),
            {},
        )
```

### Planning pipeline

Use for project stages, lead times, success processes, external-pipeline
integration, commissioning, failure and deferral. `advance_year` processes the
existing pipeline before the PSM; `admit_projects` processes new investment
proposals after investment. Do not apply probability twice or lose commissioned
asset economics and identity.

### State transition

Use for retirements, degradation, residual-value/cumulative state and year-boundary
carry-over. The returned year must be exactly `current_state.year + 1`, capacity
cannot be negative, and physical/economic records must scale together.

### Optional VRE counterfactual evidence for staged PSMs

The built-in `StagedBidAtCostPSM` adapter is currently the only integration that
automatically captures the three dispatch cases and writes VRE curtailment
attribution v2. Its resolved manifest declares output
`force.vre-counterfactual-snapshot/v1` and capability
`evidence.vre-counterfactual-snapshot/v1`; the selected balancing component also
produces `network.zonal-redispatch-result/v1`.

For an external module, those declarations establish manifest compatibility
only. They do not cause VALUE to install or invoke a generic evidence adapter.
A third-party PSM that needs `results.vre-curtailment-attribution/v2` must supply
its own execution integration adapter and write complete, reconciled
`gridform.market-ledger/v6` period/detail evidence. Full end-to-end execution of
that external path has not yet been verified.

One snapshot has `run_id`, `year`, `period`, `period_id`, one lowercase
`realised_input_sha256`, module identities and a complete row set. Every row has:

| Field | Unit or rule |
| --- | --- |
| `asset_id`, `owner_id` | stable non-empty identities |
| `canonical_technology` | exactly `Solar`, `Onshore wind` or `Offshore wind` |
| `zone_id` | stable zone identity |
| `bid_tranche_id` | stable tranche identity; not solver row order or a display-formatted float |
| `realised_available_vre_mwh` | MWh in the period |
| `perfect_forecast_copperplate_dispatch_mwh` | MWh in the matched perfect-forecast case |
| `realised_copperplate_dispatch_mwh` | MWh in the matched forecast-schedule/realised copperplate case |
| `zonal_final_dispatch_mwh` | MWh in final zonal redispatch |

The object/tranche set, realised input and period identity must match across all
three cases. The built-in bid-at-cost adapter derives `bid_tranche_id` from the
canonical technology and a decimal-normalised declared offer basis. An external
module may use another deterministic rule, but it must publish that rule and
keep the ID stable across equivalent solver allocations. Missing keys, NaN,
infinity, material negative values or dispatch above realised availability fail
the attribution contract; do not replace a missing dispatch with zero.

Installation and ordinary runs remain valid when an experimental PSM does not
declare the snapshot capability. Its attribution is `unavailable`, normally
with `module_does_not_provide_counterfactual_snapshot`; a selected balancing
component without final zonal dispatch uses
`selected_balancing_does_not_provide_final_zonal_dispatch`. Missing values are
`null`, never a numeric default. The built-in adapter treats claimed but missing
or invalid evidence as a run error. An external adapter must enforce the same
rule before publishing v2 evidence.

Use the complete payload in
`examples/external_psm_bundle/README.md` as the schema example. From a VALUE
source checkout, the focused static, registry and core-contract check is:

```powershell
py -3.10 -m pytest tests/test_prompt94_staged_market_contracts.py `
  tests/test_module_installation.py tests/test_vre_curtailment_attribution.py -q
```

These tests do not execute a third-party adapter end to end. Add integration
coverage, hand-calculated added and avoided cases and an independent domain
oracle for the module's own scientific claim. Passing installation and manifest
resolution alone does not establish execution conformance or scientific
validity.

## 6. How modules connect

Connection uses three independent checks:

1. slot and contract;
2. typed dataclasses passed between stages;
3. `provides_capabilities` / `requires_capabilities` closure.

Capability closure demonstrates interface compatibility, not scientific
suitability. Every concrete cross-module composition still requires integration
tests.

## 7. Exact `module.zip` layout

```text
my-module.zip
├── force-bundle.json       # generated descriptor; do not hand-edit
├── value-module.json       # value.module/v2 manifest
├── LICENSE                 # required
├── README.md               # optional; strongly recommended
└── src/
    └── my_unique_package/
        ├── __init__.py
        └── plugin.py
```

`scripts/build_module_bundle.py` writes the descriptor (schema
`value.module-bundle/v1`). Its file name `force-bundle.json` is a compatibility
name kept from before the VALUE name (see
[`BRAND_AND_VARIANTS.md`](BRAND_AND_VARIANTS.md)); the manifest is
`value-module.json`. Contract IDs such as `gridform.storage-cost/v1` are kept
for the same reason.

The deterministic `value.module-bundle/v1` limits are 25 MiB compressed,
100 MiB expanded and 1,000 members. Absolute/traversal paths, duplicates,
encryption, links and native/executable files are rejected. Accepted source/data
types are `.py/.pyi/.json/.csv/.txt/.md/.toml/.yaml/.yml`.

The installer is offline, does not call `pip`, and runs external code in the
VALUE Python process without an OS sandbox. Install trusted code only.

## 8. General manifest

```json
{
  "schema_version": "value.module/v2",
  "id": "my-research-module",
  "name": "My research module",
  "version": "1.0.0",
  "scientific_version": "paper-method-2026-01",
  "slot": "investment",
  "implementation": "my_unique_package.plugin:MyInvestment",
  "contract_version": "gridform.investment/v2",
  "inputs": ["market.year-result", "expansion.headroom"],
  "outputs": ["investment.proposals", "investment.retirements"],
  "parameters": [],
  "state_reads": ["operating.assets"],
  "state_writes": [],
  "determinism": "deterministic",
  "artifacts": ["investment/decisions.json"],
  "description": "State method, scope and assumptions.",
  "status": "ready",
  "selection_required": false,
  "provides_capabilities": ["investment.proposals"],
  "requires_capabilities": ["market.year-result", "expansion.headroom"],
  "units": {
    "market.year-result": "GBP, MWh",
    "expansion.headroom": "MW",
    "investment.proposals": "MW"
  },
  "execution_kind": "live_module"
}
```

IDs use 3–64 lowercase letters/numbers/hyphens and start with a letter. Versions
are semantic. The implementation must exist below `src/`. Unit keys must already
be declared inputs, outputs or parameters. Determinism is `deterministic`,
`seeded` or `stochastic`.

Third-party manifests cannot currently create new Advanced Settings controls.
New UI parameters require parameter-registry/frontend work; a module must not
read an undeclared desktop JSON file.

### 8.1 Solver-contract fragment for a zonal or alternative optimiser

A module that performs zonal redispatch declares its solver contract in the
manifest. This complete fragment is the built-in contract shape; a third party
uses its own declared version and documented semantics where it differs.

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

Every locked phase must emit v7 solver diagnostics for each period, including
the declared input SHA-256, solver and module identities, active tolerances,
objective unit/optimum/final value, observed degradation, computed tolerance,
ceilings, term-count/scale, validation class and error code. The platform's
universal validators still enforce energy balance, SOC, capacity, settlement
and ledger identities; a solver contract cannot weaken them. A different
optimiser may execute, but has no validated badge until it passes its declared
independent random, mutation, 24-hour and 168-hour gates.

## 9. Standard authoring workflow

1. Define the slot and exact scientific boundary.
2. Copy an example and change ID, package, class and all versions.
3. Depend only on public typed contracts.
4. Build a hand-calculated minimum fixture before complex logic.
5. Write manifest and method README, including units, randomness and limits.
6. Build the deterministic ZIP.
7. Install and validate it without overwriting an old module.
8. Clone a baseline Study and change only the target slot.
9. Run tests from short to long; do not start ten years after a failed lower gate.

References:

- `examples/external_module_bundle`: installable storage-cost example;
- `examples/external_psm_bundle`: installable PSM example;
- `examples/external_modules`: callable fixtures for all other slots, not
  scientific alternatives.

Build command:

```powershell
py -3.10 scripts\build_module_bundle.py `
  --manifest path\to\value-module.json `
  --source-root path\to\src `
  --license path\to\LICENSE `
  --readme path\to\README.md `
  --output work\my-module.zip
```

## 10. General test ladder

1. **Package/static:** imports, schema, semver, units, paths, hashes and
   byte-identical repeated builds.
2. **Contract unit:** required callables, typed fixture/result, identity, year,
   serialization and no unexpected input mutation.
3. **Boundary/negative:** zero, empty, extreme, unknown, missing, NaN, negative,
   duplicate and incompatible-capability cases; constraint mutations must fail.
4. **Composition:** real upstream/downstream modules, capability closure, no
   hidden config/absolute paths, resolution/event hashes identify the selected code.
5. **Two-period wiring:** selected code actually runs, no fallback, annual chain
   reaches the next state; this is not annual economic evidence.
6. **Domain short tests:** slot-specific physical/economic fixtures.
7. **Full year:** 17,520 half-hours, ledgers, target behaviour, performance,
   memory, disk and output scale.
8. **Two-year coupling:** proposals, pipeline, commissioning, asset economics,
   next-year PSM injection, retirements, observations and checkpoints.
9. **Multi-year/ten-year:** only where interannual state is affected; check
   trajectories, seeds, oscillation/fallback, numerical stability and resume parity.
10. **Independent/publication:** independent oracle for optimality/equivalence
    claims; archive ZIP, hashes, manifest, licence, data/Study revisions,
    parameters, seeds, environment, report and limitations.

Slot-specific minimums:

| Slot | Minimum domain checks |
| --- | --- |
| `psm` | hand merit order; 24/168h; balance; curtailment/import/blackout; SOC, efficiency, MW/MWh, terminal SOC; resource cost versus payment |
| `storage_cost` | first year; zero/low/normal prior sales; dwell; battery cycle depreciation; no pumped-hydro cycle depreciation; invalid values |
| expansion policies | finite non-negative headroom; mapping; no incumbent multiplication; zero-dispatch/excess cases |
| `investment` | owner grouping; shared caps; profit/retirement boundaries; complete proposal economics |
| `pipeline` | seeded replay; probability once; commission/fail/defer; complete commissioned identity |
| `transition` | exactly next year; no negative capacity; retirement economics scale; no lost pipeline/cumulative state |

Installation conformance proves wiring and limited fixtures, not scientific
validity.

## 11. Universal acceptance criteria

- retained Scheme C source is unchanged;
- no author-specific absolute path or hidden fallback;
- no NaN, infinity or illegal negative result;
- seeded methods replay;
- units agree across contract, manifest, code and output;
- actual ID/version/source hash is recorded;
- the new Study supports controlled A/B comparison and rollback;
- failures are explicit and do not silently change assumptions.

PSMs must separate offer price, market payment, physical resource cost and
capital/FOM. Named operating components must reconcile to the typed operational
total. Full Inspect auction replay additionally requires compatible declared
inputs, outcomes and orders in `market/market.sqlite`; period summaries alone do
not prove order-level replay.

## 12. Install, replace and roll back

- **Install:** staging validation precedes atomic promotion and hash recording.
- **Replace:** publish new identity, install, clone the baseline Study, change one
  slot, test and compare provenance.
- **Roll back:** rerun an old Study revision or select the old module; never
  overwrite source to simulate rollback.
- **Disable:** changes registry visibility, not existing Study definitions or
  historical evidence; referenced modules should remain enabled.
- **Quarantine:** built-in modules are fail-closed. A local manifest that
  cannot be read, an implementation that raises anything while importing
  (also `SystemExit`), or an external ID/namespace shared with another local
  entry is quarantined: it is not registered, `/api/health` turns
  `degraded`, and only Studies that select it are refused. Colliding local
  entries are all quarantined (no entry silently wins); a local entry that
  reuses a built-in ID or namespace is quarantined and the built-in stays.
- **Checks after install/enable:** conflicts are refused before anything is
  written; afterwards the registry is rebuilt in process and in a fresh
  worker-like Python process, and the change is rolled back byte for byte if
  either refuses. A failed import is remembered until **Rescan** (at the top
  of the Modules page and on every disabled or quarantined entry); **Enable**
  forgets remembered failures first, so it always reports a fresh scan.
  **Rescan** also re-imports every installed module and extension, so an
  in-place edit that breaks a module that is already loaded is quarantined at
  once instead of at the next Run or restart.
- **Disabled and quarantined:** the Modules page lists every disabled or
  quarantined local module and extension below the module list, each with
  **Enable**, **Rescan** and **Remove**. Check readiness of a Study that selects
  one shows the blocking error and disables Run.
- **Remove:** after a confirmation, moves the installer folder and the
  manifests to `modules/disabled-manifests/removed/<modules|extensions>/<id>/`;
  nothing is deleted. It refuses an enabled, working entry (disable it first)
  and one that saved Studies, active Runs or, for an extension, retained Run
  history use.
- **Same ID after a fix:** an installed ID stays taken while it is installed,
  even disabled. Repair the source in place and Enable or Rescan (recorded as in
  section 2), or Remove the entry and install the repaired bundle; a published
  method change should use a new version.
- **Offline rescue:** `module_recovery list`,
  `disable module|extension <id>`, `park-manifest module|extension <file>`
  and `park-installation module|extension <id> [<version>]` (a damaged
  installation record) work from the installer's files alone and never
  import installed code; `verify` builds the registry as a new worker would.
  In a source checkout run `python -B -m gridform_core.module_recovery ...`;
  on an installed VALUE use the bundled interpreter as shown in the user
  guide, "Offline module recovery".

### 12.1 Changing a built-in module (method upgrade)

Built-in modules live in the VALUE source tree (`gridform_core/`; the retained
Scheme C kernel in `gridform_core/builtin/scheme_c_1000twh/runtime_compat/`).
A change to how a built-in module computes is a method change, not an in-place
edit:

1. Make the change. Gate it behind a correction id in
   `gridform_core/data/methodology/corrections/` when only one methodology
   profile should apply it; never edit the retained `compat/` tree.
2. Raise the module version in its manifest
   (`gridform_core/manifests/<id>.json`) and in the implementation class.
3. Append one bump to `docs/release/VERSION_LEDGER.json`
   (`from`, `to`, `package`, `correction_ids`, `reason`,
   `requires_user_opt_in`); `true` makes saved Studies ask for an explicit
   method-upgrade confirmation before they run, `false` is for code-only
   changes. `python -B scripts/check_version_ledger.py` checks it.
4. After any edit under `runtime_compat/`, register it:
   `python -B scripts/seal_runtime_overlay.py --correction <id>`. Until then
   Check readiness refuses every Run with
   `GF_PREFLIGHT_RUNTIME_OVERLAY_UNSEALED`, and a Run started through the API
   stops with `GF_COMPATIBILITY_001`.
5. Regenerate `docs/generated/` and run the tests; a change of numbers needs a
   golden revision under the same correction id.

## 13. Explicit current limitations

1. Only the seven listed slots are plug-and-play.
2. There is no independent `bid_strategy`, `demand_profile`,
   `carbon_accounting` or `network_expansion` slot today.
3. Third-party manifests cannot register new UI parameters automatically.
4. The installer does not install dependencies.
5. External code is trusted in-process Python, not sandboxed.
6. Conformance is not scientific validation.
7. Contract compatibility is not proof that every module composition is
   scientifically appropriate.

Non-programmers can install, select, run and compare a packaged module. Authoring
a new scientific module remains Python software development plus domain
validation.
