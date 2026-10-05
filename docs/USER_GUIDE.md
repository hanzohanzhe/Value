# VALUE Network Extensions local test guide

This guide covers VALUE Network Extensions 0.6.0-alpha.2. VALUE means Variable renewable electricity Allocation, Load-enabled excess-generation Utilisation, and system Evolution. The browser workbench, API and command line use the same local application service.

A Research project joins a versioned data pack, executable PSM and CEM modules, model years, scientific parameters and output settings. The browser and command line call the same application service and module registry. A project selection does not act as a shortcut to an unrelated fixed script.

## 1. Scientific scope

The accepted built-in GB baseline is a single-node model without internal transmission constraints. Interconnectors are external import offers, not internal network branches. Its fast cost-ranked PSM, the optional perfect-foresight LP and external user modules are replaceable implementations; no one clearing algorithm defines VALUE. VRE may be curtailed and is not subtracted from demand before clearing.

This repository also exposes optional network capabilities. Chronological DC network clearing has independent analytical, random, 24-hour and 168-hour checks. AC is an experimental feasibility checker rather than AC optimal power flow. Transmission expansion is an experimental causal lifecycle without a validated full-year or ten-year Great Britain pathway. Selecting a network module requires compatible topology and branch data and records the selected capability's maturity in the run identity.

One model year runs in this order:

1. advance the planning pipeline and commission projects due in the year;
2. clear the PSM with the commissioned fleet;
3. calculate shared VRE and storage expansion headroom;
4. let investment agents propose projects;
5. admit, defer or reject projects in the planning pipeline;
6. checkpoint the assets, projects, owners and storage state for the next year.

The public CEM retains the compatibility ID `force-cem-v1`. It is a modular formulation derived from the Scheme C research model. It preserves the agent investment and planning-pipeline structure, but it is not an exact numerical reproduction of the retained Scheme C kernel. The retained kernel is comparison evidence and cannot be selected as a project PSM.

This release does not implement AC optimal power flow, full unit commitment or ramping. It does not claim global optimality for its agent-based multi-year expansion model. DC validation does not promote the experimental AC or transmission-expansion modules to a validated scientific baseline.

## 2. Install and start

The evidenced environment is 64-bit Windows 10 or 11, CPython 3.10 and Node.js 22 or newer. Keep at least 2 GiB free for installation and short tests. Full annual studies require more space.

For the first installation, double-click [install-value.cmd](../install-value.cmd). Start the application with [start-value.cmd](../start-value.cmd), then open:

```text
http://127.0.0.1:8800
```

The local API uses `http://127.0.0.1:8766`. Both services bind only to loopback. Port 3000 is a development-server address and is not the packaged application address.

The browser only ever talks to `http://127.0.0.1:8800` (or `http://localhost:8800`). That page forwards `/api` requests to the local API with a session that only the API and the page server know; the API refuses requests from web pages and requests without the session. If the page shows **Open VALUE from its launcher**, it was opened under another address or the page server and the API do not share a data directory: close it and start VALUE again with its launcher. VALUE assumes one person per computer; do not install it on shared lab computers or remote-desktop servers (see [SECURITY.md](../SECURITY.md)).

Stop the managed services with [stop-value.cmd](../stop-value.cmd). If launch fails, run:

```powershell
py -3.10 scripts\doctor.py --capability force-native
```

The doctor reports the exact Python, Node.js, dependency, port, disk or state-directory failure. See [INSTALLATION.md](INSTALLATION.md) for capability-specific installation.

## 3. Castle 101: the first half hour

Use Castle before loading research data. It is a small, deterministic teaching
system bundled under CC0-1.0, but it follows the ordinary VALUE execution path.
The browser does not read a prepared result file.

1. Before the meeting, double-click [check-castle-demo.cmd](../check-castle-demo.cmd).
   Continue only when it ends with `READY`.
2. Double-click [start-value.cmd](../start-value.cmd) and choose **Learn: Castle
   101** at `http://127.0.0.1:8800`.
3. Read the system card, select **Load Castle Study**, open **Review**, and save
   the exact Study revision.
4. Select **Run Castle tutorial**. Open the bid and dispatch evidence, unused
   VRE, storage behaviour and the planning event that commissions the synthetic
   solar project in 2026.
5. Return to Learn and select **Create legacy-tariff Study**. Run that Study,
   select both completed tutorial runs in the comparison panel, and export the
   JSON.

Only `module.storage_cost` should differ. Castle uses 48 half-hour periods in
each of two model years, so it teaches chronology and the PSM–CEM hand-off; it
does not estimate annual British cost or carbon. VALUE therefore withholds the
annual deltas instead of scaling the short run into a false annual result.

The detailed [Castle learner guide](tutorial/CASTLE_101.md),
[one-page card](tutorial/CASTLE_101_QUICK_CARD.md),
[presenter runbook](tutorial/STUART_DEMO_RUNBOOK.md), and
[printable PDF](../output/pdf/VALUE_Castle_101_guide.pdf) all describe this same
route. After Castle, continue with the research-data workflow below.

## 4. Local state and research data

An existing source installation uses `.gridform`. A clean installation defaults to `%LOCALAPPDATA%\FORCE`. Set `FORCE_DATA_HOME` before launch to choose another location:

```powershell
$env:FORCE_DATA_HOME = "D:\FORCE-Research"
.\scripts\start-local.ps1
```

The state root contains data packs, content-addressed input objects, project revisions, runs, archives and recoverable trash. Do not place private research data inside the Python package or commit the installed UK pack to Git.

## 5. First research study

Install the CC0 synthetic contract pack if no pack is available:

```powershell
py -3.10 scripts\install_synthetic_pack.py
```

Alternatively, open **Data**, choose **Install a FORCE data pack**, select a
reviewed `force.data-bundle/v1` ZIP, acknowledge its licence and attribution,
and install. FORCE streams it to local staging, verifies its exact inventory and
25 semantic roles, and only then promotes it atomically. A cancelled upload or
failed check leaves existing packs unchanged. The selected file is not retained
as a second copy. A different revision must use a new versioned pack ID.

The normal workflow is:

1. Select a pack in Data interfaces and confirm that all required roles are ready.
2. Review executable implementations in Model modules.
3. Create a Research project with a name, start year, end year and data pack.
4. In **System domain**, choose single node, reference DC or experimental AC
   feasibility. The server supplies required contract extensions.
5. In **Optional domains**, add hydrology or transmission expansion only when
   the Study needs them, and acknowledge each experimental version explicitly.
6. In **Model chain**, review or replace compatible PSM/CEM implementations.
7. In **Review**, inspect conditional inputs, effective parameters and the exact
   graph SHA-256, then save the immutable revision.
8. In Run centre, select a mode and run Check readiness.
9. Use a two-period wiring check and two-year smoke for new data or modules.
10. Run two full years before committing computing time to a ten-year study.

The synthetic pack tests installation and contracts. It does not support conclusions about the GB electricity system.

## 6. Workspace pages

Overview shows the selected data pack, runtime, modules and annual chain. Data
interfaces maps source-specific files to stable roles. Its active Study/draft
context adds Network, AC feasibility, Hydrology or Network expansion groups only
when their extensions are selected. Templates and bounded previews use the same
canonical adapters as preflight. It also installs complete, non-executable data
bundles with visible progress and exact validation errors. Replacing one file
creates a new content-addressed object and binding revision; it does not alter
the source file.

Model modules lists the Python implementations and extension capabilities
resolved by one registry. Public slots are `psm`, `storage_cost`, `pipeline`,
`vre_cap`, `storage_cap`, `investment`, `transition` and the optional
`network_expansion` slot. The page installs module and extension bundles through
separate fail-closed transactions; installing an extension does not activate it
in a Study. Storage-cost modules apply only to an offer-based PSM.

Research projects store scientific composition, not arbitrary desktop paths. Saving changed data, modules, years or parameters creates an append-only revision with a new SHA-256 identity.

Run centre runs preflight, shows a bounded physical-domain preview, starts the
model, reports progress, resumes verified checkpoints and controls exports and
retention. Closing the browser does not stop a run. Audit exposes paginated
market periods, planning events, cost and carbon evidence without loading
complete ledgers into the main page. **Network & redispatch** reads immutable
typed network and attribution artifacts; it does not calculate a second result
in React. Natural-flow hydrology remains `not_evaluated` when annual execution
emitted no typed hydrology result index.

For a reconciled v6 zonal run, the main **Run** page is deliberately compact: it
shows final VRE curtailment, the available-VRE-energy-weighted curtailment rate
and Redispatch net impact. Open **Network & redispatch** for economic,
forecast-added/avoided and redispatch-added/avoided values, the presentation-only
waterfall, a technology selector, the zone-by-technology summary and bounded
object/tranche pages. The object table shows period, zone, technology, asset,
tranche, economic, forecast-added/avoided, redispatch-added/avoided, redispatch
net and final values. It does not currently show all three raw dispatch cases,
the reference allocation, method ID, identity hash, residual or tolerance, and
the period/resource export buttons do not export these attribution fields.

For bounded programmatic detail, use
`GET /api/runs/{run_id}/network-redispatch/curtailment-detail` with `year`,
`limit` and `offset` (and optionally `technology`). That response contains the
raw dispatch, reference and detail fields. The compact v2 audit artifact is
`model-output/network/vre-curtailment-attribution.json`. Complete period and
detail evidence is stored in `market/market.sqlite`, in
`vre_curtailment_period` and `vre_curtailment_detail`.

`legacy_partial` means an older completed ledger did not measure avoided
curtailment under the v2 contract. `unavailable` means the selected module graph
did not provide the matched-counterfactual evidence, or no attribution evidence
was recorded. In both states the missing quantities stay blank/`null`, not
`0 MWh`. These states describe evidence availability; they are not labels for a
failed scientific validation. Automatic v2 capture currently exists only for
the built-in staged adapter; capability resolution alone does not execute a
third-party evidence adapter. A v2-producing integration whose identity does
not reconcile must fail separately and retain failure evidence.

Result views use one set of state words (P0-9). Only `invalid` is shown in a
red frame:

| State | Meaning | What to do |
| --- | --- | --- |
| `reconciled` | Recorded values passed their identity checks | Read the values |
| `unavailable` | No evidence of this kind was recorded (for example a copperplate Run has no attribution tables) | Nothing is wrong; choose a method that records it if you need it |
| `withheld` | Values exist but are not published here (a non-annual or unfinished Run, or a partial year) | Open the Run in Inspect for the period-level ledger |
| `invalid` | The recorded evidence contradicts itself (identities or year sets do not match) | Treat the Run's results as unverified and inspect its ledgers |
| `Not modelled` / `Not computed` / `Not recorded` | The method does not model the quantity / the implementation does not compute it yet / an older Run did not record it | Never read these as zero |

### 6.1 Experimental zonal solver controls and evidence

`value-zonal-redispatch-balancing` `2.0.0` is an Experimental, lossless
transport representation. It is not a security analysis, N-1 study, DC/AC
power-flow result, and not transmission expansion; copperplate remains the default
VALUE study mode. Select it only in a separate Study revision with compatible
zonal input contracts.

The built-in baseline uses SciPy `1.8.1`, `highs-ds`, presolve and `1e-9`
primal/dual feasibility tolerances. It has no automatic fallback to
`highs-ipm`, another solver or copperplate. The associated embedded HiGHS
binary is source-registered as `candidate`, not independently validated, so the
default configuration is not a claim of independently validated execution.

Advanced settings may select `highs-ds`, `highs-ipm` or `highs`; primal and
dual feasibility tolerances from `1e-10` through `1e-7`; and IPM optimality
tolerance from `1e-12` through `1e-7`. The warning fraction must be greater
than `0` and at most `1`. Each validated ceiling must be greater than `0` and
strictly below its read-only recorded reference threshold. The recorded
reference thresholds are `0.10 GBP` per half-hour for primary bid cost,
`0.01 MWh` per half-hour for schedule deviation, and `0.01 MWh` per half-hour
for physical throughput; they are not user-editable. Any non-default save needs
one explicit acknowledgement: it creates a new project revision and removes the
built-in solver-validated label. The run shows no repeated confirmation dialog.

The Run summary names the method and solver-contract version, solver-stack
status, maximum tolerance-ceiling utilisation, warning/unvalidated-period count
and a link to detailed evidence. New runs write ledger schema v7 diagnostics
for every period and locked phase; JSON and SQLite are the authoritative detailed
exports. Numerical warning and unvalidated status propagate through later PSM
and CEM years. If a solver fails, diagnostics are non-finite, a locked objective
cap is violated or physical feasibility fails, the zonal study remains failed
and preserves the declared input, identities, settings, completed phases
and raw solver status. To compare another method, explicitly create a separate
copperplate or alternative-solver Study; never treat a failure as permission to
switch models.

## 7. Run modes

| Mode | Work performed | Annual economic interpretation |
| --- | --- | --- |
| Two-period wiring check | Two half-hours in one model year | Not allowed |
| Two-year smoke test | Two half-hours in each of two years | Not allowed |
| Run two full years | 17,520 half-hours in each year | Allowed within model scope |
| Run complete study | Every configured full year | Allowed within model scope |

Preflight checks the selected runtime capability, module compatibility, 25 data interfaces, parameter validity, output directory, free space and estimated scale. Fix errors before starting a run.

## 8. PSM and storage policy

`scheme-c-psm` is the FORCE bid-at-cost market. It requires one storage-cost module:

- `dynamic-annual-storage-cost` starts from full-utilisation design output, then recovers annualised project cost from preceding-year sold MWh and sales-weighted dwell time. Cycle depreciation applies only to batteries.
- `scheme-c-legacy-storage-tariff` implements the historical tariff equation for controlled comparison. It does not make the complete modular trajectory an exact retained-kernel reproduction.
- `user-formula-storage-cost` evaluates a restricted arithmetic expression over approved variables. It cannot execute arbitrary Python.

Run centre can clone a study while changing only the storage-cost module. This is the safest route for a controlled dynamic-versus-legacy comparison.

`force-perfect-foresight-lp` is a different PSM. SciPy/HiGHS centrally co-optimises chronological generation and storage, so no storage offer-cost module is selected. A separately encoded PuLP/CBC oracle validates 24-hour, 168-hour and randomized convex cases, including mutation failures for balance, efficiency, SOC, terminal and import constraints. This does not redefine the sequential FORCE market as a global LP.

## 9. Planning and commissioned assets

The planning ledger records source, technology, region, capacity, stage, success, delay, failure and commissioning year. A project commissioned for a model year enters that year's PSM before clearing. The asset carries MW, MWh, CAPEX, FOM, economic life and stable physical and owner identities.

Investment is grouped by economic owner, technology and region. Commissioned children do not duplicate the owner agent. Wind, solar and storage use one shared annual technology headroom rather than one cap per incumbent row.

Generic REPD battery entries without a declared duration use the visible `scheme_c_proportional_split` compatibility mapping. In expected-capacity mode, one probability scales MW, MWh, CAPEX and FOM consistently. Superseded applications are excluded. These are model assumptions, not observations reported by REPD.

Existing natural-flow hydro can operate. A new hydro asset requires site, hydrology and new-build CAPEX evidence. It cannot inherit the existing-stock compatibility value. Pumped hydro remains a separate storage technology.

## 10. Costs and carbon

The headline cost definition is `force.cem-system-resource-cost/v1`:

```text
annualised CAPEX and FOM for the commissioned fleet
+ physical operating resource cost
```

The GBP/MWh denominator is served demand. Settlements, policy transfers, storage bid recovery, uncommissioned projects and informational residual value remain separate accounts. The cost ledger is `ledgers/annual-cost-ledger.json`.

A native annual run pins either `force_current_authoritative_v1` or `scheme_c_reproduction_2026_07_18`. The carbon ledger can account for direct thermal emissions, imports, local installation embodied emissions and storage lifecycle emissions. Missing activity or factors produce `not_evaluated`, not a silent zero. JSON and SQLite ledgers must agree.

The Scheme C reproduction scenario is intentionally different. Its historical
storage scalars 40/50 do not have a declared physical unit. FORCE therefore
returns a null total with `not_physically_interpretable` and the reason code
`legacy_storage_scalars_have_no_declared_physical_unit`; it does not relabel the
legacy value as tCO2e.

## 11. Result bundle

Important artifacts include:

| Artifact | Purpose |
| --- | --- |
| `resolved-run.json` | Frozen project, data, module and parameter identity |
| `preflight.json` | Readiness checks and scale estimate |
| `year-results-v2.json` | Annual market, investment, planning and next state |
| `checkpoints-v2/state-YYYY.json` | Identity-verified atomic annual checkpoint |
| `market/market.sqlite` | Period market records |
| `market/field-dictionary.json` | v6 market and VRE attribution field units and semantics |
| `model-output/network/vre-curtailment-attribution.json` | Compact attribution capability, method, annual totals and residual evidence |
| `planning/project-index.sqlite` | Project and event index |
| `ledgers/annual-cost-ledger.json` | Reconciled cost accounting |
| `ledgers/annual-carbon-ledger.*` | JSON and SQLite carbon accounting |
| `terminal/fleet-vintage.json` | Remaining life and residual-value evidence |
| `artifact-index.json` | Artifact roles and checksums |
| `provenance.json` | Input, code and execution provenance |
| `performance.json` | Module and annual timings |

Validate a completed bundle without rerunning the model:

```powershell
py -3.10 -m gridform_core.bundle_validator <run-directory>
```

### Scientific validation, energy balance and stress events

`validation/scientific-validation.json` (v2) recomputes every status from
checks executed on the run; nothing is a written-in "passed". Three groups are
gates:

- **Run invariants**: period coverage, demand input reconciliation,
  generation cross-path check, annual state chain.
- **Energy balance**: the read-only oracle recomputes each period on the
  boundary the PSM declares in its ledger. A shortfall (demand the accepted
  supply did not meet) is booked as unserved energy and reported as a
  **stress event**; it does not fail the energy balance. A residual that
  remains after booking it (supply recorded beyond every use) does.
- **Storage invariants**: charge and discharge within rated power, no store
  charging and discharging in the same period, state of charge within its
  capacity, and the per-store energy audit.

Under the default (corrected) methodology a failed gate makes scientific
validation `failed` and annual economics are not published. Under the
doctoral reproduction methodology the run keeps the thesis behaviour: a
failure that matches a declared deviation (for example the double counting of
must-run surplus, or storage power limits reset in each clearing stage) is
shown as `reproduction_with_declared_deviations`, a clean run as
`reproduction_conformant`, anything else as `failed`. Its annual results
appear on result pages only when every raw invariant passes; otherwise they
remain in Inspect and exports. The adjusted residual column of the market
ledger is not evidence of an energy balance. Check a run, including an old
one, read-only:

```powershell
py -3.10 -B -m gridform_core.energy_balance_oracle <run-directory>
```

Exit code 0 is passed, 1 failed, 2 not evaluated. Runs produced before these
checks existed are re-checked when they are read; their old `passed` is shown
as superseded.

## 12. Cancellation, recovery and retention

Request safe cancellation writes a cancellation request. A native run stops after its next complete annual checkpoint. Resume is available for failed or cancelled runs when frozen data, project revision, parameters, modules and implementation hashes still match.

Archive creates and validates a complete audit ZIP before changing run status. Restore validates that ZIP. Prepare audit bundle creates a downloadable result package. Move to trash requires the exact run ID and moves the run into recoverable local trash.

Each run's model worker holds a lease on `<run>/worker.lock`. Closing VALUE does not stop a running worker: the stop message lists runs that continue in the background, and the next start takes over their supervision through the lease. If a worker exits or disappears, the run becomes failed (or cancelled when cancellation was requested) with `GF_WORKER_EXITED` or `GF_WORKER_LOST` within seconds, or at the next start, and can then be resumed or moved to trash. Runs started by an older VALUE cannot always be verified (`worker_liveness: unverifiable`); Mark lost needs the exact run ID and is accepted only after 15 minutes without any change in the run directory. Only one VALUE backend may use a data directory; a second one stops with exit code 3 without changing anything.

Move to trash moves the run directory first and records `deleting` only in the trash copy; if the move fails, the run is unchanged. Disk reservations are held only by active runs and only for output they have not yet written; finished runs count with their actual bytes (hard links once). Moving a run to trash frees quota; archiving does not.

Do not copy a checkpoint between scenarios. Matching years do not make two execution identities compatible.

## 13. Comparing runs

Run centre compares two to six completed annual runs and exports JSON or CSV. Smoke runs are excluded. The comparison first checks horizon, data, non-storage modules, cost and carbon definitions, denominator and terminal policy. It only reports unqualified numerical deltas when definitions match.

Dynamic and legacy controlled clones use the same FORCE cost identity and can be compared directly. Retained Scheme C cost uses a historical definition, so that comparison remains labelled and descriptive.

VRE-curtailment values can be viewed side by side even when their data pack,
network pack, period set, realised inputs, initial state, attribution contract,
method or capability differ. Numerical deltas are enabled only when all those
identities match; otherwise delta fields remain `null` with a reason code.

## 14. Connecting another database

Keep source-specific paths, formats and column names inside an adapter:

1. create a data-pack manifest revision;
2. read CSV, Parquet, NetCDF, SQL or API data;
3. normalize technologies, units, currency year, timezone and half-hour chronology;
4. map outputs to stable semantic roles;
5. record source, licence, attribution, checksum and transformation;
6. run structural and semantic validation;
7. pass wiring, two-year smoke and full annual gates.

Weather and demand bindings use pack-relative URIs resolved by the workspace registry. Runtime code must not depend on the author's desktop path. An external adapter example is in [examples/external_modules/README.md](../examples/external_modules/README.md).

## 15. Adding a model module

Start with [`Build Your Own Model 101`](BUILD_YOUR_OWN_MODEL_101.md) to decide
whether to replace a data pack, Study parameter, existing module or platform
contract. For the replacement lifecycle, all seven public slots, exact
ZIP/manifest format, entry templates and the test ladder, use the
[`Module Developer 101`](MODULE_DEVELOPER_101.md) ([Chinese](MODULE_DEVELOPER_101_ZH.md)).

An external module is an installed Python package with a `gridform.module/v2` manifest. It declares a stable ID, slot, semantic version, contract, typed inputs and outputs, state read/write sets, parameters, capabilities, determinism and artifacts.

Put an exogenous demand profile in a data pack/adapter. Use the matching slots
for storage cost, expansion, investment, planning and transition algorithms.
DC/AC solution algorithms belong in a complete PSM. This 0.6 line already
provides the solver-neutral network contract, conditional topology/nodal-demand
roles, a reference DC implementation and an experimental AC-feasibility data
contract. A replacement network PSM declares those capabilities and is composed
with the matching extension(s). A new contract family or lifecycle stage without
a current slot still requires an explicit extension and platform validation. Do
not disguise it as another module or add hidden compatibility switches. Install
and validate external modules before selection.

The Modules page now accepts a reviewed `force.module-bundle/v1` ZIP. The user must acknowledge that it contains executable Python. FORCE then checks the exact SHA-256 inventory, safe paths, manifest, entry point, slot/contract and callable conformance before atomically promoting the package and refreshing Study selectors. Built-in IDs cannot be shadowed. A referenced external module cannot be disabled until its saved Studies are migrated.

This installer is offline and self-contained: it does not run `pip`, download dependencies or accept native binaries. Version-scoped source directories are organisational isolation, not an operating-system sandbox; external code executes inside the FORCE Python process. Conformance demonstrates contract wiring, not scientific validity. Build the supplied example with `scripts/build_module_bundle.py`, install it from Modules, then run a two-period wiring check before a full study.

## 16. Command-line execution

The public application service also accepts a project JSON:

```powershell
py -3.10 -m gridform_core.application `
  --project examples\release-dynamic-storage-2025-2034.scenario.json `
  --pack .gridform\data-packs\uk-scheme-c-1000twh `
  --output outputs\my-dynamic-run `
  --run-id my-dynamic-run `
  --mode full
```

Browser and CLI runs use the same orchestrator, registry, parameter resolver and output contracts. For long runs, keep checkpoints enabled. Set `runtime.generation_trace_level=off` or `summary` when a full generation trace is not required. Public period summaries, annual totals, investments and storage observations remain available.

Scripts that call the running local API need its session. Read it from the API's data directory and send it as a header; do not send an `Origin` header:

```python
import json, urllib.request
from backend.api_session import authorized_headers  # run from the VALUE source/app directory

headers = authorized_headers(r"C:\Users\me\AppData\Local\VALUE\state", 8766, json_body=True)
request = urllib.request.Request("http://127.0.0.1:8766/api/projects/validate",
                                 data=json.dumps({"name": "check"}).encode(), headers=headers, method="POST")
print(urllib.request.urlopen(request).status)
```

Without the session only a reduced `GET /api/health` answers. Request bodies need an explicit `Content-Type` such as `application/json` (form and `text/plain` bodies are refused with 415).

## 17. Troubleshooting

Connection refused usually means the packaged services are not running or the browser is on the development port. Start GridForm and use port 8800. A Python 3.12 warning means an older incompatible backend may still own the API port. Stop the managed services and restart with Python 3.10.

**Open VALUE from its launcher** (or an HTTP 421/403 answer) means the page was not opened through the launcher: another host name, a bookmark from another installation, or a page server that reads a different data directory than the API. Stop VALUE and start it again with its launcher. `python -B scripts/verify_local_security_boundary.py` checks a running installation and prints PASS when every cross-site, rebinding and session-less probe is refused.

Twenty-five bound inputs do not guarantee preflight success. Units, chronology, checksums, capabilities, parameters and disk are checked separately. Follow the corrective action in the reported error.

After an interrupted long run, keep the output directory. Resume from the last complete `checkpoints-v2/state-YYYY.json`. The incomplete current year is recomputed; checkpointed years are not.

If a full GB annual run reports zero operational cost, inspect its mode, physical cost activities and ledger status. A wiring check does not publish annual economics.

If diagnose reports stray bytecode, it is Python bytecode inside `__pycache__` folders of the installation. VALUE never reads it (every interpreter uses a fresh `pycache_prefix`). `diagnose-value --repair-bytecode` moves it to `state/quarantine/`; start does the same automatically when the installation is writable.

**A local module or extension is quarantined** (`/api/health` says
`degraded`, Modules shows the entry with its reason): VALUE keeps running and
only Studies that select that entry are refused. Disable it on the Modules
page, or repair it, install it under a new ID and press **Rescan**. If VALUE
does not get that far, or every run is refused with
`GF_EXECUTION_ARCHIVE_MODULE_RECORD`, stop VALUE and use the offline module
recovery below.

Changing modules while runs are queued or running needs an explicit
confirmation: queued runs would start with the changed code, and a run that
is already running keeps its code but can no longer be resumed after the
change.

### Offline module recovery

`module_recovery` reads and moves the installer's files only; it never
imports installed code. Stop VALUE first: the tool refuses while VALUE holds
the data directory. On an installed VALUE run it with the bundled Python and
the installation's data directory (`<prefix>` is the installation folder;
installations made with `--python` use that interpreter instead):

```bash
# Linux and macOS
PYTHONPATH="<prefix>/app" "<prefix>/runtime/python/bin/python3.10" -B -s \
  -m gridform_core.module_recovery --modules-root "<prefix>/state/modules" list
```

```bat
rem Windows (Command Prompt)
set PYTHONPATH=<prefix>\app
"<prefix>\runtime\python\python.exe" -B -s -m gridform_core.module_recovery --modules-root "<prefix>\state\modules" list
```

`-B` keeps bytecode out of the installation. From a source checkout,
`python -B -m gridform_core.module_recovery list` uses
`$VALUE_DATA_HOME/modules`. Replace `list` with:

| Command | Use |
| --- | --- |
| `list` | every installed entry, its visible problems and a `fix:` line |
| `disable module <id>`, `disable extension <id>` | the same as Disable on the Modules page |
| `park-manifest module\|extension <file.json>` | move an unreadable active manifest aside |
| `park-installation module\|extension <id> [<version>]` | move an installation whose record is damaged (`GF_MODULE_INSTALL_RECORD_INVALID`) aside, with its active manifest when no enabled version is left |

Parked files go to `modules/disabled-manifests/`, which VALUE never scans.
A parked module ID stays taken, like a disabled one.

## 18. Reproducibility and claim boundary

Archive the project revision, data manifest and hashes, module manifests and implementation hashes, Python environment, random seed, planning uncertainty mode, carbon factor scenario, storage policy, preflight and validation records with every published result.

FORCE can support claims about execution under its declared bid-at-cost, investment and planning rules when the energy, cost, carbon and lineage audits pass. Current evidence does not support claims of internal GB transmission, full unit commitment, global optimality for agent dispatch or CEM expansion, or exact retained Scheme C reproduction.

Software is Apache-2.0, repository documentation is CC BY 4.0, and the synthetic pack is CC0-1.0. A result bundle is not permission to redistribute all installed UK source data. See [MATHEMATICAL_REFERENCE.md](MATHEMATICAL_REFERENCE.md), [VALIDATION_AND_CLAIMS.md](VALIDATION_AND_CLAIMS.md) and [LICENSING.md](../LICENSING.md).
