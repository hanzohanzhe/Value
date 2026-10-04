# VALUE 101

## What this package is

VALUE 101 is a small, synthetic electricity system for learning the real VALUE workflow. It uses the same Data Pack contract, module registry, bid-at-cost PSM, CEM lifecycle and result ledgers as an ordinary VALUE Study. It is not a second demonstration kernel and it does not replay stored answers.

The installer contains two CC0 teaching Data Packs:

- `value-101-baseline-v1`: one complete annual single-node system;
- `value-101-network-v1`: the same teaching inputs plus a fixed three-zone transport and redispatch exercise.

It does not contain the UK research pack or the doctoral 1000 TWh reproduction data. The numbers are synthetic and must not be presented as results for Great Britain.

## Install and open VALUE

1. Double-click `VALUE-Setup.exe` on Windows 10 or 11.
2. Keep the installer window open while the progress bar completes extraction, setup and local-service startup.
3. Wait for the browser to open at [http://127.0.0.1:8800](http://127.0.0.1:8800), or start `VALUE` from the desktop or Start menu.
4. Check the lower-left status. It should show Python 3.10 and a ready local VALUE service.

No terminal, separate Python, Node, Git, administrator account or internet connection is required after download. Application state is stored at `%LOCALAPPDATA%\VALUE\state`. Closing the browser does not stop VALUE. Use the `Stop VALUE` Start-menu shortcut when finished. The `Uninstall VALUE` shortcut removes this VALUE installation and its application state. The older `%LOCALAPPDATA%\VALUE-101` pilot is a separate optional installation: it is not migrated and may remain installed.

## The five objects

**Data Pack.** A versioned bundle that maps demand, weather, fleet, costs, policy and planning files to VALUE's 25 named input roles.

**Module.** One executable implementation of a typed model slot, such as PSM clearing, storage pricing, investment or planning.

**Study.** A saved combination of years, one Data Pack, selected Modules, parameters and optional domains. Saving creates an immutable revision.

**Run.** One execution of an exact Study revision. A Run has its own status, artifacts and provenance.

**Results.** Stored bids, dispatch, storage, unused VRE, costs, carbon, planning events, module identities and hashes. The browser reads these artifacts; it does not invent missing values.

## What Check readiness resolves

`Check readiness` is the preflight between a saved Study and a Run. It validates the selected immutable Study revision, resolves the exact installed Module versions, and checks every required data role, unit and chronology. It verifies Data Pack and Module identities and hashes, estimates the number of periods, disk space, peak memory and runtime, then freezes the declared input snapshot before execution. If any required input cannot be resolved, VALUE fails closed and reports the missing or incompatible role with a corrective action.

For a **single node** Study, the saved revision already contains its explicit `data_pack_id`. Preflight does not search for a separate Network Pack. It validates and freezes the declared Data Pack, Modules, parameters and run clock. Interconnectors remain boundary offers inside the selected base Data Pack; no internal transmission-network dataset is introduced.

For a **zonal** Study, the saved revision contains the base Data Pack, zonal System domain, network extension and `zonal_demand_mode`. Preflight resolves one compatible installed Network Pack and verifies its exact ID, manifest and hash, zones, cutsets, time-dependent ratings, zonal demand, spatial mapping and model clock. It records whether national demand remains authoritative and the Network Pack supplies allocation shares, or whether the Network Pack supplies absolute zonal demand. The frozen input snapshot retains the exact Network Pack ID and hash. VALUE must not silently select an arbitrary pack or fall back to copperplate.

Before the check, `Network pack: Check readiness to confirm` means that the identity is not yet confirmed. After a successful check, VALUE displays `Network pack: <pack-id> · verified`. On failure, the readiness report names the missing or incompatible role and the corrective action. The phrase **resolved during preflight** means **not yet confirmed**; it does not mean missing, randomly selected or downloaded during the Run.

```text
Single node:
Saved Study → declared Data Pack → validate and freeze

Zonal:
Saved Study → declared base Data Pack
            → resolve compatible Network Pack
            → validate alignment
            → freeze both identities
```

## Create the baseline Study

Open `Learn`, select `Open lesson`, then choose `Create baseline Study`. VALUE saves:

| Field | Saved value |
| --- | --- |
| Name | `VALUE 101 baseline` |
| Years | 2025 to 2026 |
| Data Pack | `value-101-baseline-v1` |
| Market | National single node |
| Period length | 30 minutes |
| Full model year | 17,520 periods |

Creating the Study does not run the model.

## Run one market day

Choose `Run one market day`.

This route reads the first 48 half-hours of the annual Data Pack and calls the selected production PSM once for 2025. It records bids, accepted dispatch, storage flows and unused VRE. It deliberately does **not** run investment, expansion caps, planning admission or the annual state transition.

Use this result to learn `Market replay` and `VRE & curtailment`. Do not interpret it as annual economics, annual income or a capacity-expansion result.

## Run the complete two-year model

Choose `Run complete two-year model` when you want annual PSM-CEM results. This is a production-sized local calculation and can take much longer than the one-day lesson.

For 2025 VALUE clears all 17,520 half-hour periods. It then evaluates annual expansion headroom and investment, advances and admits planning projects, and writes the opening state for 2026. The 2026 PSM then clears another 17,520 periods from that updated state, followed by the 2026 CEM stages.

The completed Run therefore contains 35,040 market periods plus two annual state transitions. Annual income, cost recovery, investment and planning results come from this route, not from the one-day lesson.

The annual route stores compact period summaries, physical dispatch, storage and unused VRE. Use the one-day route when you need the complete auction-level bidding record.

Closing the browser does not stop a background Run. Return to `Runs` to inspect progress or results.

## The baseline module chain

| Study slot | Module ID | Purpose |
| --- | --- | --- |
| PSM | `value-bid-at-cost-psm` | Clears the national bid-at-cost market for every selected period |
| Storage cost | `dynamic-annual-storage-cost` | Produces storage offers using dynamic annual-average project-cost recovery |
| Investment | `agent-investment` | Evaluates owner-level investment and retirement after an annual PSM result |
| Pipeline | `planning-pipeline` | Advances projects, records failure or commissioning, and admits new proposals |
| VRE cap | `vre-expansion-cap` | Applies solar and wind expansion headroom |
| Storage cap | `value-storage-expansion-policy` | Applies storage expansion headroom |
| Transition | `value-annual-state-transition` | Writes the next model year's opening state |

The one-day route calls only the selected PSM and its storage-cost dependency. The complete two-year route calls the full chain above.

## The 25 input roles

| Role group | Required formats | What it supplies |
| --- | --- | --- |
| `config.model_parameters` | JSON | Model and scenario parameters |
| `costs.capital` | JSON | CAPEX, FOM and economic-life assumptions |
| `demand.forecast`, `demand.real` | CSV | Forecast and realised MWh for every half-hour |
| `fleet.generators` | JSON | Generator, storage and import asset records |
| `market.<country>.price` | CSV | Import offer prices for Belgium, France, Ireland, Netherlands and Norway |
| `market.<country>.profile` | CSV | Signed import availability profiles for the same five boundaries |
| `planning.success_rates` | CSV | Planning success assumptions |
| `planning.timelines` | JSON | Stage and completion timing assumptions |
| `policy.support` | JSON | Policy-support parameters |
| `profiles.vre_offshore`, `profiles.vre_onshore`, `profiles.vre_solar` | CSV | Half-hour renewable availability |
| `projects.repd` | CSV | Prepared planning-project records |
| `source.repd_raw` | CSV | Source project records retained for provenance |
| `weather.solar`, `weather.wind` | NetCDF | Weather fields used by the selected weather method |

Open `Data` to inspect each binding, checksum, licence and source declaration. A real research dataset must be installed as one complete Data Pack; clicking a preset is not a substitute for mapping and validating the files.

## System domain and optional domains

The **System domain** chooses the main physical market formulation. Basic mode exposes only executable choices:

- `National single node`: one GB-wide bid-at-cost market with no internal transmission constraints. Interconnectors remain external boundary offers.
- `Fixed zonal network and redispatch`: the same national ahead market followed by fixed, lossless zonal transfer limits and pay-as-bid redispatch.

The zonal method is a transport-constraint model. It does not calculate voltage, reactive power, AC feasibility, dynamic security or N-1 security.

An **Optional domain** adds a separately versioned capability, conditional data roles, hooks, state or result artifacts. It does not replace the System domain. Basic mode shows only optional domains that the selected executable path can actually use. Advanced mode exposes technical contracts and experimental components for developers.

## Build a research model

Research changes enter through the same contracts used by the full application, not through one-click scenario presets.

### Replace the data

1. Open `Data` to read the 25 role definitions, units and clocks.
2. Prepare files or an adapter that maps your source schema to those roles.
3. Create a Data Pack manifest with role URI, format, checksum, licence, provenance and transformation version.
4. Validate and install the bundle locally.
5. Select the installed Data Pack in a new Study revision.

The application does not assume that your filenames match the teaching filenames. It relies on the role bindings in the manifest.

### Replace one or more Modules

1. Open `Modules` and choose the slot and contract you intend to implement.
2. Build a bundle containing `value-module.json` and an importable Python package.
3. Declare the module ID, semantic version, slot, contract version, entry point, inputs, outputs, state reads/writes and artifacts.
4. Run the bundle's contract tests, then install it locally.
5. Open `Studies`, switch to `Advanced`, and select the compatible implementation.

A bidding-strategy replacement is one possible PSM Module. The same mechanism also supports storage-cost, investment, planning, expansion-policy and state-transition implementations.

### Add a model domain

Use an extension bundle when the change adds a new domain rather than replacing one slot. Declare its conditional data roles, typed contracts, lifecycle hooks, parameters, state and result artifacts. Open `Add data` for the adapter and extension workflow.

## Read the results

- `Runs`: status, annual results and Study-to-Run identity.
- `Market replay`: period bids, accepted energy and clearing evidence.
- `VRE & curtailment`: available, accepted and unused renewable energy.
- `Network & redispatch`: corridor loading, redispatch, network impact and load shedding when the zonal method is selected.
- `Inspect`: planning events, commissioning, ledgers, module identities and provenance.

Missing scientific evidence must appear as `Not evaluated`, never as a silent zero.

## Optional network lesson

The network lesson creates a matched copperplate control and fixed three-zone case using `value-101-network-v1`. National demand, fleet, weather, ahead-market method and clock are held constant. Only the delivery method changes.

Each case runs the complete 2025 to 2026 route: 17,520 half-hours per year followed by the same investment, expansion, planning and annual-transition stages. The network pack contains a full annual clock; its CSV files may have 17,521 text rows when one row is a header, but still contain exactly 17,520 numeric periods.

The output records corridor loading, upward and downward redispatch, network-added and network-avoided curtailment, load shedding, redispatch resource cost and settlement. It contains no transmission-expansion implementation and is not a validated GB network dataset.

## If VALUE does not start

Use `Stop VALUE`, then start `VALUE` once. If a bundled pack is missing, reinstall from the same `VALUE-Setup.exe`. If port 8800 or 8766 is occupied by another application, close that application; VALUE refuses to terminate a process it does not own.

Installer and startup diagnostics are under `%LOCALAPPDATA%\VALUE\diagnostics`. Teaching state and Runs are under `%LOCALAPPDATA%\VALUE\state`.

## Licence

VALUE source code is Apache-2.0. This guide is CC BY 4.0. The bundled synthetic teaching data are CC0-1.0.
